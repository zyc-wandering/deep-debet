from __future__ import annotations

import asyncio
import logging
import re
from typing import AsyncGenerator, List, Optional, Tuple

from app.agents.context_manager import ContextManager
from app.models import DebaterConfig, DebateMessage, DebateStage, SearchResult
from app.providers.base import LLMProvider, SearchProvider

logger = logging.getLogger(__name__)


class DebaterAgent:
    def __init__(
        self,
        config: DebaterConfig,
        llm: LLMProvider,
        search: SearchProvider,
        context_manager: ContextManager | None = None,
    ) -> None:
        self.config = config
        self.llm = llm
        self.search = search
        self.context_manager = context_manager or ContextManager()
        self.rolling_summary = ""

    def _system_prompt(self) -> str:
        return (
            f"你是辩手 {self.config.name}。\n"
            f"背景：{self.config.background}\n"
            f"立场：{self.config.stance}\n"
            f"公众形象与表达偏好：{self.config.personality}\n"
            "你正在参与一场严肃的多方辩论，不是综艺吵架节目。\n"
            "要求：\n"
            "1. 你的发言要像真实、有判断力的专业人士，而不是模板化聊天助手。\n"
            "2. 不要把“我同意某某”“我认为”当作固定起手式。必要时可以承认对方局部合理，但不必每轮都先礼貌铺垫。\n"
            "3. 可以直接反驳、追问、拆解定义、补充机制、比较代价，关键是推进讨论，而不是围绕同一句话来回空转。\n"
            "4. 每一轮至少完成以下之一：指出一个关键漏洞；补进一个新维度；提出一个可检验标准；把争论推进到下一层条件判断。\n"
            "5. 如果某个分歧已经重复出现，不要重说原话。改为补充边界、条件、优先级、代价分配、执行路径或判定标准。\n"
            "6. 允许锋利，但不要进行人身攻击、阴谋化表演、喊口号或纯情绪输出。\n"
            "7. 你的目标不是赢得吵架，而是让旁观者看清：真正的分歧在哪里、该看什么证据、下一步该怎么判断。\n"
            "8. 输出 180-280 字中文，信息密度高，句式自然，避免重复口头禅。"
        )

    async def produce_turn(
        self,
        topic: str,
        brief: str,
        messages: List[DebateMessage],
        enable_search: bool,
    ) -> Tuple[str, List[SearchResult]]:
        references: List[SearchResult] = []
        if enable_search:
            try:
                references = await self.search.search(f"{topic} {self.config.stance}", num_results=2)
            except Exception:
                references = []

        turn_instruction = (
            "请给出本轮发言。\n"
            "优先挑一个最值得推进的分歧，不必机械回应最近一句。\n"
            "你可以直接反驳，也可以先重定义问题、拆开条件、指出被跳过的执行成本或责任链。\n"
            "如果对方某个局部判断合理，只需顺手承认后立刻推进，不要把让步写成固定开场。\n"
            "本轮必须带来推进：新增一个分析维度、明确一个判定标准、补一段因果机制，或把争论推进到更具体的场景。\n"
            "不要重复自己的旧句式，不要空泛表态，不要变成骂街。"
        )
        self.rolling_summary = self.context_manager.refresh_rolling_summary(messages)
        ctx = self.context_manager.build(
            current_speaker=self.config.name,
            system_prompt=self._system_prompt(),
            brief=brief,
            rolling_summary=self.rolling_summary,
            messages=messages,
            turn_instruction=turn_instruction,
        )

        refs_text = "\n".join([f"- {r.title}: {r.snippet[:120]}" for r in references])
        user_prompt = ctx.to_prompt()
        if refs_text:
            user_prompt = f"{user_prompt}\n\n## Optional Realtime References\n{refs_text}"

        try:
            text = await self.llm.chat(self._system_prompt(), user_prompt)
            if text.strip():
                return text.strip(), references
        except Exception as exc:
            logger.warning("Debater LLM failed for %s: %s", self.config.name, exc)

        return self._fallback_turn(topic, brief, messages, references), references

    async def produce_turn_stream(
        self,
        topic: str,
        brief: str,
        messages: List[DebateMessage],
        enable_search: bool,
    ) -> AsyncGenerator[str, None]:
        """Stream debate turn content token by token."""
        references: List[SearchResult] = []
        if enable_search:
            try:
                references = await self.search.search(f"{topic} {self.config.stance}", num_results=2)
            except Exception:
                references = []

        turn_instruction = (
            "请给出本轮发言。\n"
            "优先挑一个最值得推进的分歧，不必机械回应最近一句。\n"
            "你可以直接反驳，也可以先重定义问题、拆开条件、指出被跳过的执行成本或责任链。\n"
            "如果对方某个局部判断合理，只需顺手承认后立刻推进，不要把让步写成固定开场。\n"
            "本轮必须带来推进：新增一个分析维度、明确一个判定标准、补一段因果机制，或把争论推进到更具体的场景。\n"
            "不要重复自己的旧句式，不要空泛表态，不要变成骂街。"
        )
        self.rolling_summary = self.context_manager.refresh_rolling_summary(messages)
        ctx = self.context_manager.build(
            current_speaker=self.config.name,
            system_prompt=self._system_prompt(),
            brief=brief,
            rolling_summary=self.rolling_summary,
            messages=messages,
            turn_instruction=turn_instruction,
        )

        refs_text = "\n".join([f"- {r.title}: {r.snippet[:120]}" for r in references])
        user_prompt = ctx.to_prompt()
        if refs_text:
            user_prompt = f"{user_prompt}\n\n## Optional Realtime References\n{refs_text}"

        full_content = ""
        try:
            # Stream tokens from LLM
            async for token in self.llm.chat_stream(self._system_prompt(), user_prompt):
                full_content += token
                yield token
        except Exception as exc:
            logger.warning("Debater LLM stream failed for %s: %s", self.config.name, exc)
            # Fallback: yield the fallback content
            fallback = self._fallback_turn(topic, brief, messages, references)
            # Stream fallback character by character
            for char in fallback:
                yield char
                await asyncio.sleep(0.01)

    async def produce_turn_stream_stage(
        self,
        topic: str,
        brief: str,
        messages: List[DebateMessage],
        stage: DebateStage,
        intensity: str,
        enable_search: bool,
        selected_focus: str = "",
        user_context: str = "",
    ) -> AsyncGenerator[str, None]:
        """Stream debate turn with stage-specific prompting."""
        references: List[SearchResult] = []
        if enable_search:
            try:
                references = await self.search.search(f"{topic} {self.config.stance}", num_results=2)
            except Exception:
                references = []

        # Get stage-specific instruction
        turn_instruction = self._get_stage_instruction(stage, intensity, selected_focus, user_context)

        self.rolling_summary = self.context_manager.refresh_rolling_summary(messages)
        ctx = self.context_manager.build(
            current_speaker=self.config.name,
            system_prompt=self._system_prompt_stage(stage, intensity, selected_focus, user_context),
            brief=brief,
            rolling_summary=self.rolling_summary,
            messages=messages,
            turn_instruction=turn_instruction,
        )

        refs_text = "\n".join([f"- {r.title}: {r.snippet[:120]}" for r in references])
        user_prompt = ctx.to_prompt()
        if refs_text:
            user_prompt = f"{user_prompt}\n\n## Optional Realtime References\n{refs_text}"

        full_content = ""
        try:
            async for token in self.llm.chat_stream(
                self._system_prompt_stage(stage, intensity, selected_focus, user_context),
                user_prompt,
            ):
                full_content += token
                yield token
        except Exception as exc:
            logger.warning("Debater LLM stream failed for %s: %s", self.config.name, exc)
            fallback = self._fallback_turn_stage(topic, brief, messages, references, stage)
            for char in fallback:
                yield char
                await asyncio.sleep(0.01)

    def _system_prompt_stage(
        self,
        stage: DebateStage,
        intensity: str,
        selected_focus: str = "",
        user_context: str = "",
    ) -> str:
        """Generate system prompt for specific stage and intensity."""
        base_prompt = (
            f"你是辩手 {self.config.name}。\n"
            f"背景：{self.config.background}\n"
            f"立场：{self.config.stance}\n"
            f"公众形象与表达偏好：{self.config.personality}\n"
        )
        focus_context = self._format_focus_context(selected_focus, user_context)

        stage_guidance = {
            DebateStage.opening: (
                "这是开场陈述阶段。请直接阐述你的核心立场和论证框架。\n"
                "不要回应他人（因为还没有人发言），专注建立你的分析基础。\n"
                "明确表达：1)你对核心问题的判断；2)你的分析框架；3)预期的关键分歧点。"
            ),
            DebateStage.free_debate: (
                "这是自由辩论阶段。你的发言要像真实、有判断力的专业人士。\n"
                "要求：\n"
                "1. 不要把'我同意某某''我认为'当作固定起手式。必要时可以承认对方局部合理，但不必每轮都先礼貌铺垫。\n"
                "2. 可以直接反驳、追问、拆解定义、补充机制、比较代价。\n"
                "3. 每一轮至少完成以下之一：指出一个关键漏洞；补进一个新维度；提出一个可检验标准；把争论推进到下一层条件判断。\n"
                "4. 如果某个分歧已经重复出现，不要重说原话。改为补充边界、条件、优先级、代价分配、执行路径或判定标准。\n"
                "5. 允许锋利，但不要进行人身攻击、阴谋化表演、喊口号或纯情绪输出。"
            ),
            DebateStage.closing: (
                "这是总结陈词阶段。请回应以下要求：\n"
                "1. 明确指出辩论中最强的反对意见是什么，以及你如何回应。\n"
                "2. 说明你的立场在辩论过程中是否有调整，或为什么保持稳定。\n"
                "3. 不要简单重复之前的观点，要展示交锋后的立场澄清或升级。\n"
                "4. 给出一个清晰的结论：在什么条件下你的方案可行，在什么条件下不可行。"
            ),
        }

        intensity_modifier = {
            "mild": "语气保持克制和学术性，避免过度对抗。",
            "balanced": "保持专业辩论的紧张感，但聚焦议题而非人身。",
            "intense": "可以更加直接和锋利，但仍必须基于论证而非情绪。",
        }

        guidance = stage_guidance.get(stage, stage_guidance[DebateStage.free_debate])
        intensity_text = intensity_modifier.get(intensity, intensity_modifier["balanced"])

        length_guidance = "输出 180-280 字中文，信息密度高，句式自然，避免重复口头禅。"

        return f"{base_prompt}\n{focus_context}\n{guidance}\n{intensity_text}\n{length_guidance}"

    def _get_stage_instruction(
        self,
        stage: DebateStage,
        intensity: str,
        selected_focus: str = "",
        user_context: str = "",
    ) -> str:
        """Get turn instruction for specific stage."""
        focus_instruction = ""
        if selected_focus:
            focus_instruction = (
                f"\n本场必须显式覆盖的讨论切面：{selected_focus}。\n"
                "你可以支持、反驳、重定义或比较它，但不能忽略它，也不能把整场讨论收缩成单一路径。\n"
            )
        context_instruction = ""
        if user_context.strip():
            context_instruction = (
                f"\n用户补充背景如下，请把它当作场景信息而不是立场指令：{user_context.strip()}\n"
            )
        instructions = {
            DebateStage.opening: (
                "请给出开场陈述。\n"
                "直接阐述你的核心立场和论证框架，不要回应他人。\n"
                "建立你的分析基础，让旁听者理解你的判断从何而来。"
            ),
            DebateStage.free_debate: (
                "请给出本轮发言。\n"
                "优先挑一个最值得推进的分歧，不必机械回应最近一句。\n"
                "你可以直接反驳，也可以先重定义问题、拆开条件、指出被跳过的执行成本或责任链。\n"
                "如果对方某个局部判断合理，只需顺手承认后立刻推进，不要把让步写成固定开场。\n"
                "本轮必须带来推进：新增一个分析维度、明确一个判定标准、补一段因果机制，或把争论推进到更具体的场景。\n"
                "不要重复自己的旧句式，不要空泛表态，不要变成骂街。"
            ),
            DebateStage.closing: (
                "请给出总结陈词。\n"
                "必须回应以下三点：\n"
                "1. 指出对方最强的反对意见，并给出你的回应。\n"
                "2. 说明你的立场在辩论中是否有所调整或为什么保持不变。\n"
                "3. 给出清晰的结论：什么条件下可行，什么条件下不可行。\n"
                "不要简单重复之前的话，要展示交锋后的立场澄清。"
            ),
        }
        return f"{instructions.get(stage, instructions[DebateStage.free_debate])}{focus_instruction}{context_instruction}"

    def _format_focus_context(self, selected_focus: str, user_context: str) -> str:
        lines = []
        if selected_focus:
            lines.append(f"本场用户更关心的讨论切面：{selected_focus}")
            lines.append("这只要求你显式覆盖该维度，不代表用户偏向任何结论。")
        if user_context.strip():
            lines.append(f"用户补充背景：{user_context.strip()}")
            lines.append("把它视为背景补充，不要把它解释成用户站队。")
        return "\n".join(lines).strip()

    async def follow_up_stream(
        self,
        topic: str,
        brief: str,
        messages: List[DebateMessage],
        question: str,
    ) -> AsyncGenerator[str, None]:
        """Stream follow-up response preserving persona."""
        # Build context from previous debate
        own_messages = [m for m in messages if m.speaker == self.config.name]
        own_positions = "\n".join([f"- {m.content[:150]}..." for m in own_messages[-3:]])

        system_prompt = (
            f"你是辩手 {self.config.name}。\n"
            f"背景：{self.config.background}\n"
            f"立场：{self.config.stance}\n"
            f"公众形象与表达偏好：{self.config.personality}\n\n"
            "辩论已经结束，现在用户想向你提问。要求：\n"
            "1. 保持你在辩论中的立场、语气和分析框架。\n"
            "2. 基于你在辩论中的发言，回答用户的问题。\n"
            "3. 可以澄清、补充或细化，但不要突然改变立场。\n"
            "4. 回答控制在 200 字以内，信息密度高。"
        )

        user_prompt = (
            f"话题：{topic}\n\n"
            f"你在辩论中的主要观点：\n{own_positions}\n\n"
            f"用户问题：{question}\n\n"
            "请基于你的立场回答。"
        )

        full_response = ""
        try:
            async for token in self.llm.chat_stream(system_prompt, user_prompt):
                full_response += token
                yield token

            if not full_response.strip():
                raise ValueError("Empty response")
        except Exception as exc:
            logger.warning("Debater follow-up stream failed for %s: %s", self.config.name, exc)
            fallback = self._fallback_follow_up(question)
            for char in fallback:
                yield char
                await asyncio.sleep(0.01)

    def _fallback_turn_stage(
        self,
        topic: str,
        brief: str,
        messages: List[DebateMessage],
        references: List[SearchResult],
        stage: DebateStage,
    ) -> str:
        """Fallback turn based on stage."""
        if stage == DebateStage.opening:
            return self._fallback_opening(topic)
        elif stage == DebateStage.closing:
            return self._fallback_closing(topic, messages)
        else:
            return self._fallback_turn(topic, brief, messages, references)

    def _fallback_opening(self, topic: str) -> str:
        """Fallback for opening statement."""
        return (
            f"关于「{topic}」，我的立场很明确：{self.config.stance}。"
            f"作为{self.config.background}，我认为关键在于厘清责任分配和可检验标准。"
            "后续辩论中我会围绕边界条件、执行成本和问责机制展开论证。"
        )

    def _fallback_closing(self, topic: str, messages: List[DebateMessage]) -> str:
        """Fallback for closing statement."""
        own_messages = [m for m in messages if m.speaker == self.config.name]
        if own_messages:
            return (
                f"总结我的立场：{self.config.stance}。"
                "对方最强的反对意见我已经回应——关键在于边界条件是否清晰。"
                "我的立场在交锋中没有改变，因为核心判断仍然成立："
                "在没有明确问责机制前，贸然推进风险过高。"
                "只有当监督框架和止损机制到位时，这一方案才具备可行性。"
            )
        return (
            f"关于「{topic}」，我坚持{self.config.stance}。"
            "对方若认为可行，必须回答：谁来承担失败成本，如何纠错。"
            "这些问题没有明确答案前，我的立场不会改变。"
        )

    def _fallback_follow_up(self, question: str) -> str:
        """Fallback for follow-up response."""
        return (
            f"关于您的问题「{question[:30]}...」，"
            f"我作为{self.config.background}，仍坚持我在辩论中的立场。"
            "具体回答取决于边界条件是否清晰、问责机制是否到位。"
            "这些问题不解决，我的判断不会改变。"
        )

    def _fallback_turn(
        self,
        topic: str,
        brief: str,
        messages: List[DebateMessage],
        references: List[SearchResult],
    ) -> str:
        own_turn_index = sum(1 for msg in messages if msg.speaker == self.config.name)
        last_message = messages[-1] if messages else None
        style_lead = self._style_lead()
        counter = self._counter_line(last_message, own_turn_index)
        stance_argument = self._stance_argument(topic, own_turn_index)
        evidence = self._evidence_line(brief, references, own_turn_index)
        close = self._close_line(topic, own_turn_index)
        return " ".join(part for part in [style_lead, counter, stance_argument, evidence, close] if part).strip()

    def _style_lead(self) -> str:
        style_map = {
            "high_signal": "先把结论压实：",
            "structured": "先把争点拆开，不然讨论会继续打转：",
            "blunt": "别把这事说成姿态问题，先看约束：",
            "narrative": "真正危险的不是表面分歧，而是被忽略的后果链：",
            "cross_exam": "先追一个绕不过去的问题：",
            "empirical": "先看证据和可检验标准，再谈态度：",
        }
        return style_map.get(self.config.speaking_style, "我先把核心判断说透：")

    def _stance_argument(self, topic: str, own_turn_index: int) -> str:
        stance = self.config.stance

        if any(word in stance for word in ["积极", "支持", "推进", "赞成"]):
            options = [
                "支持推进不等于盲目乐观，关键是证明收益是否持续大于新增风险，而且责任链要能落地。",
                "如果一项方案能明显改善效率、质量或可及性，讨论重点就该转向怎么设边界，而不是停留在抽象戒备。",
                "真正的问题不是该不该动，而是在哪些场景先动、用什么指标判断它确实比旧方案更好。",
            ]
            return options[own_turn_index % len(options)]

        if any(word in stance for word in ["审慎", "监管", "风险", "反对", "怀疑"]):
            options = [
                "我更在意的是失误如何被发现、谁来兜底、代价落在谁身上，这些没交代清楚前，推进就是把风险后移。",
                "如果主要收益建立在乐观假设上，而损失一旦发生却高度集中，审慎不是保守，是基本决策纪律。",
                "争论到这里不能只看理想收益，必须把极端失败场景、问责路径和纠偏成本摆上桌面。",
            ]
            return options[own_turn_index % len(options)]

        if any(word in stance for word in ["务实", "落地", "ROI", "成本", "商业"]):
            options = [
                "我关心的是谁付转型成本、多久见效、失败后怎么止损，这些不清楚，再漂亮的原则都落不了地。",
                "一套方案能不能执行，不看口号，看预算、人手、改造周期和回退机制能不能闭环。",
                "如果收益讲不清、成本算不明、责任链也没有对应动作，那它就还不是可部署方案。",
            ]
            return options[own_turn_index % len(options)]

        options = [
            "这件事不能只看立场标签，得把实际约束、利益排序和长期副作用一起摆出来。",
            "争论如果停留在价值口号，就很难推进；关键是把判断条件说清，把例外场景分开。",
            "旁观者真正需要的不是谁声音更大，而是哪条判断链更完整、哪些证据能改变结论。",
        ]
        return options[own_turn_index % len(options)]

    def _counter_line(self, last_message: DebateMessage | None, own_turn_index: int) -> str:
        if not last_message:
            return ""
        if last_message.speaker == self.config.name:
            return "我把刚才没展开的关键约束补上："

        speaker = last_message.speaker
        options = [
            f"针对 {speaker} 刚才那条判断，我不同意把问题说得那么平，因为最关键的代价分布还没被处理。",
            f"{speaker} 的说法抓住了一部分现象，但它把决定成败的边界条件跳过去了。",
            f"如果顺着 {speaker} 的逻辑继续推，下一步就得回答谁承担失败成本，而这恰恰是争点所在。",
        ]
        return options[own_turn_index % len(options)]

    def _evidence_line(
        self,
        brief: str,
        references: List[SearchResult],
        own_turn_index: int,
    ) -> str:
        signals = self._brief_signals(brief, references)
        if not signals:
            return "现有材料还不足以直接下结论，所以更合理的推进方式是先明确：什么证据会真正改变各方判断。"
        return signals[own_turn_index % len(signals)]

    def _brief_signals(self, brief: str, references: List[SearchResult]) -> List[str]:
        bullet_lines = []
        for line in brief.splitlines():
            cleaned = re.sub(r"\s+", " ", line.strip("- ").strip())
            if cleaned and not cleaned.startswith("#"):
                bullet_lines.append(cleaned)

        fallback_points = [line for line in bullet_lines if len(line) > 20][:4]
        from_brief = [
            f"主持人简报里有个点不能轻轻带过：{line[:90]}。这意味着判断标准不能只看单一好处。"
            for line in fallback_points
        ]
        from_refs = [
            f"外部材料至少提示了一个现实约束：{ref.title} 涉及 {ref.snippet[:60]}，说明这不是只靠态度就能解决的问题。"
            for ref in references[:2]
        ]
        return from_brief + from_refs

    def _close_line(self, topic: str, own_turn_index: int) -> str:
        options = [
            "所以这轮真正该推进的问题是：什么条件满足时可以放行，什么条件一旦出现就必须收紧。",
            "与其继续重复立场，不如把下一步判定标准讲清楚，否则争论只会在原地空转。",
            "如果不能把边界、责任和验收标准说出来，这场讨论就还没有进入可决策阶段。",
        ]
        return options[own_turn_index % len(options)]

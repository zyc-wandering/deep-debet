from __future__ import annotations

import logging
import re
from typing import List, Tuple

from app.agents.context_manager import ContextManager
from app.models import DebaterConfig, DebateMessage, SearchResult
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

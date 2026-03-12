from __future__ import annotations

import asyncio
import logging
import re
from typing import AsyncGenerator, List, Tuple

from app.agents.context_manager import ContextManager
from app.models import DebaterConfig, DebateMessage, DebateStage, SearchResult
from app.prompts.debater import (
    append_optional_references,
    build_base_system_prompt,
    build_follow_up_system_prompt,
    build_follow_up_user_prompt,
    build_general_turn_instruction,
    build_stage_system_prompt,
    build_stage_turn_instruction,
)
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
        return build_base_system_prompt(self.config)

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

        self.rolling_summary = self.context_manager.refresh_rolling_summary(messages)
        ctx = self.context_manager.build(
            current_speaker=self.config.name,
            system_prompt=self._system_prompt(),
            brief=brief,
            rolling_summary=self.rolling_summary,
            messages=messages,
            turn_instruction=self._general_turn_instruction(),
        )
        user_prompt = append_optional_references(ctx.to_prompt(), references)

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
        references: List[SearchResult] = []
        if enable_search:
            try:
                references = await self.search.search(f"{topic} {self.config.stance}", num_results=2)
            except Exception:
                references = []

        self.rolling_summary = self.context_manager.refresh_rolling_summary(messages)
        ctx = self.context_manager.build(
            current_speaker=self.config.name,
            system_prompt=self._system_prompt(),
            brief=brief,
            rolling_summary=self.rolling_summary,
            messages=messages,
            turn_instruction=self._general_turn_instruction(),
        )
        user_prompt = append_optional_references(ctx.to_prompt(), references)

        try:
            async for token in self.llm.chat_stream(self._system_prompt(), user_prompt):
                yield token
        except Exception as exc:
            logger.warning("Debater LLM stream failed for %s: %s", self.config.name, exc)
            fallback = self._fallback_turn(topic, brief, messages, references)
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
        references: List[SearchResult] = []
        if enable_search:
            try:
                references = await self.search.search(f"{topic} {self.config.stance}", num_results=2)
            except Exception:
                references = []

        self.rolling_summary = self.context_manager.refresh_rolling_summary(messages)
        system_prompt = self._system_prompt_stage(stage, intensity, selected_focus, user_context)
        ctx = self.context_manager.build(
            current_speaker=self.config.name,
            system_prompt=system_prompt,
            brief=brief,
            rolling_summary=self.rolling_summary,
            messages=messages,
            turn_instruction=self._get_stage_instruction(stage, selected_focus, user_context),
        )
        user_prompt = append_optional_references(ctx.to_prompt(), references)

        try:
            async for token in self.llm.chat_stream(system_prompt, user_prompt):
                yield token
        except Exception as exc:
            logger.warning("Debater LLM stream failed for %s: %s", self.config.name, exc)
            fallback = self._fallback_turn_stage(topic, brief, messages, references, stage)
            for char in fallback:
                yield char
                await asyncio.sleep(0.01)

    def _general_turn_instruction(self) -> str:
        return build_general_turn_instruction()

    def _system_prompt_stage(
        self,
        stage: DebateStage,
        intensity: str,
        selected_focus: str = "",
        user_context: str = "",
    ) -> str:
        return build_stage_system_prompt(
            config=self.config,
            stage=stage,
            intensity=intensity,
            selected_focus=selected_focus,
            user_context=user_context,
        )

    def _get_stage_instruction(
        self,
        stage: DebateStage,
        selected_focus: str = "",
        user_context: str = "",
    ) -> str:
        return build_stage_turn_instruction(
            stage=stage,
            selected_focus=selected_focus,
            user_context=user_context,
        )

    async def follow_up_stream(
        self,
        topic: str,
        brief: str,
        messages: List[DebateMessage],
        question: str,
    ) -> AsyncGenerator[str, None]:
        own_messages = [m for m in messages if m.speaker == self.config.name]
        own_positions = "\n".join(f"- {m.content[:150]}..." for m in own_messages[-3:])

        system_prompt = build_follow_up_system_prompt(self.config)
        user_prompt = build_follow_up_user_prompt(topic, own_positions, question)

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
        if stage == DebateStage.opening:
            return self._fallback_opening()
        if stage == DebateStage.closing:
            return self._fallback_closing(messages)
        return self._fallback_turn(topic, brief, messages, references)

    def _fallback_opening(self) -> str:
        return (
            f"我的核心立场是：{self.config.stance}。我不会只给态度判断，而是用可检验标准来判断谁更站得住。"
            "后面我会重点看三件事：证据是否足够硬、因果链是否闭合、以及失败成本到底由谁承担。"
        )

    def _fallback_closing(self, messages: List[DebateMessage]) -> str:
        own_messages = [m for m in messages if m.speaker == self.config.name]
        if own_messages:
            return (
                f"总结我的立场：{self.config.stance}。这轮交锋之后，我仍然认为更应偏向这一路径，"
                "因为对手没有补上关键的证据缺口或责任链说明。即便我承认局部条件需要修正，"
                "核心判断仍成立：没有更清晰的验证标准前，对方方案站不稳。"
            )
        return (
            f"我最后仍然偏向 {self.config.stance}。如果对方无法回答失败成本、纠错机制和证据门槛，"
            "那它的观点就还没有达到可决策的强度。"
        )

    def _fallback_follow_up(self, question: str) -> str:
        return (
            f"关于你的问题“{question[:30]}...”，我仍然坚持我在辩论中的基本判断。"
            "关键不在于口头立场，而在于证据够不够硬、逻辑链能不能闭合、以及风险由谁承担。"
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
        parts = [
            self._style_lead(),
            self._counter_line(last_message, own_turn_index),
            self._stance_argument(own_turn_index),
            self._evidence_line(brief, references, own_turn_index),
            self._close_line(own_turn_index),
        ]
        return " ".join(part for part in parts if part).strip()

    def _style_lead(self) -> str:
        style_map = {
            "high_signal": "先把最硬的一点压出来：",
            "structured": "先把争点拆开，不然讨论会继续打转：",
            "blunt": "别绕圈子，先看成本和止损：",
            "narrative": "真正危险的不是表面分歧，而是被忽略的后果链条：",
            "cross_exam": "先追一个绕不过去的问题：",
            "empirical": "先看证据和判定标准，再谈态度：",
        }
        return style_map.get(self.config.speaking_style, "我先把核心判断说透：")

    def _stance_argument(self, own_turn_index: int) -> str:
        stance = self.config.stance
        if any(word in stance for word in ["支持", "赞成", "推进", "积极"]):
            options = [
                "支持推进不等于盲目乐观，关键是证明收益是否持续大于新增风险，而不是只喊方向正确。",
                "如果一套方案真更优，就该能回答它为什么不是把复杂成本往后推，而不是停留在愿景口号。",
                "真正的争点不是该不该动，而是在哪些条件下先动，以及什么证据足以证明它比旧方案更强。",
            ]
            return options[own_turn_index % len(options)]
        if any(word in stance for word in ["审慎", "监管", "反对", "怀疑", "风险"]):
            options = [
                "我更在意的是失败如何被发现、谁来兜底、责任链怎么落地，以及判定标准是否清晰；这些没交代清楚前，推进就是把风险后移。",
                "如果主要收益建立在乐观假设上，而损失一旦发生却高度集中，那么审慎不是保守，而是基本决策纪律。",
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
            "旁观者真正需要的不是谁声音更大，而是哪条逻辑链更完整、哪类证据真能改变结论。",
        ]
        return options[own_turn_index % len(options)]

    def _counter_line(self, last_message: DebateMessage | None, own_turn_index: int) -> str:
        if not last_message:
            return ""
        if last_message.speaker == self.config.name:
            return "我把刚才没展开的关键约束补上："

        speaker = last_message.speaker
        options = [
            f"针对 {speaker} 刚才那条判断，我不同意它把问题说得那么平，因为最脆弱的前提还没被证明。",
            f"{speaker} 抓住了局部现象，但把决定成败的因果链和责任链跳过去了。",
            f"如果顺着 {speaker} 的逻辑继续推，下一步就得回答谁承担失败成本，而这恰恰是对方没有补上的漏洞。",
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
            return "现有材料还不足以下绝对结论，所以更合理的做法是先把能改变结论的证据门槛讲清。"
        return signals[own_turn_index % len(signals)]

    def _brief_signals(self, brief: str, references: List[SearchResult]) -> List[str]:
        bullet_lines: List[str] = []
        for line in brief.splitlines():
            cleaned = re.sub(r"\s+", " ", line.strip("- ").strip())
            if cleaned and not cleaned.startswith("#"):
                bullet_lines.append(cleaned)

        from_brief = [
            f"主持人简报里有个点不能带过：{line[:90]}。这说明不能只看单一收益，而要看完整代价链。"
            for line in bullet_lines[:4]
            if len(line) > 20
        ]
        from_refs = [
            f"外部材料至少提示了一个现实约束：{ref.title} 涉及 {ref.snippet[:60]}，这不是只靠态度就能跨过去的问题。"
            for ref in references[:2]
        ]
        return from_brief + from_refs

    def _close_line(self, own_turn_index: int) -> str:
        options = [
            "所以这轮真正该推进的问题是：什么条件满足时可以放行，什么条件一旦出现就必须收紧。",
            "与其继续重复立场，不如把下一步判定标准讲清楚，否则争论只会在原地空转。",
            "如果不能把边界、责任和验收标准说出来，这场讨论就还没有进入可决策阶段。",
        ]
        return options[own_turn_index % len(options)]

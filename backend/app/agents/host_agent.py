from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, AsyncGenerator, Dict, List, Optional, Tuple

from app.models import DebaterConfig, DebateMessage, FocusOption, SearchResult, StructuredReport
from app.prompts.host import (
    HOST_SYSTEM_PROMPT,
    build_debater_generation_prompt,
    build_focus_options_prompt,
    build_follow_up_prompt,
    build_research_prompt,
    build_structured_summary_prompt,
    build_summary_prompt,
)
from app.providers.base import LLMProvider, SearchProvider

logger = logging.getLogger(__name__)


class HostAgent:
    def __init__(self, llm: LLMProvider, search: SearchProvider) -> None:
        self.llm = llm
        self.search = search

    async def research_topic(self, topic: str) -> Tuple[str, List[SearchResult]]:
        queries = [
            topic,
            f"{topic} 最新争议",
            f"{topic} 数据 研究 报告",
        ]
        all_results: List[SearchResult] = []
        for query in queries:
            try:
                all_results.extend(await self.search.search(query, num_results=3))
            except Exception:
                continue

        if not all_results:
            return self._fallback_brief(topic), []

        citations_text = "\n".join(f"- {r.title}: {r.snippet[:160]} ({r.url})" for r in all_results[:9])
        user_prompt = build_research_prompt(topic, citations_text)
        try:
            brief = await self.llm.chat(HOST_SYSTEM_PROMPT, user_prompt)
            if brief.strip():
                return brief.strip(), all_results
        except Exception as exc:
            logger.warning("Host research fallback activated for topic %r: %s", topic, exc)

        return self._fallback_brief(topic, all_results), all_results

    async def create_debaters(
        self,
        topic: str,
        debater_count: int,
        brief: str,
        selected_focus: FocusOption | None = None,
        intensity: str = "balanced",
        user_context: str = "",
    ) -> List[DebaterConfig]:
        user_prompt = build_debater_generation_prompt(
            topic=topic,
            debater_count=debater_count,
            brief=brief,
            intensity=intensity,
            selected_focus=selected_focus,
            user_context=user_context,
        )

        try:
            raw = await self.llm.chat(HOST_SYSTEM_PROMPT, user_prompt)
            data = self._extract_json_array(raw)
            configs = [DebaterConfig(**row) for row in data[:debater_count]]
            if len(configs) >= debater_count:
                return configs[:debater_count]
        except Exception as exc:
            logger.warning("Host debater generation fallback activated for topic %r: %s", topic, exc)

        return self._fallback_debaters(topic, debater_count)

    async def summarize_debate(
        self,
        topic: str,
        brief: str,
        messages: List[DebateMessage],
        references: List[SearchResult],
    ) -> str:
        transcript = "\n".join(f"- {m.speaker}: {m.content}" for m in messages)
        refs = "\n".join(f"- [{r.title}]({r.url})" for r in references[:12])
        user_prompt = build_summary_prompt(topic, brief, transcript)

        try:
            report = await self.llm.chat(HOST_SYSTEM_PROMPT, user_prompt)
            if report.strip():
                report = self._ensure_directional_verdict(report.strip(), messages)
                if refs:
                    report += f"\n\n## 参考链接\n{refs}\n"
                return report.strip()
        except Exception as exc:
            logger.warning("Host summary fallback activated for topic %r: %s", topic, exc)

        return self._fallback_report(topic, brief, messages, references)

    async def extract_focus_options(self, topic: str, brief: str) -> List[FocusOption]:
        user_prompt = build_focus_options_prompt(topic, brief)
        try:
            raw = await self.llm.chat(HOST_SYSTEM_PROMPT, user_prompt)
            data = self._extract_json_array(raw)
            focus_options = [FocusOption(**row) for row in data[:3]]
            if len(focus_options) >= 2:
                return focus_options
        except Exception as exc:
            logger.warning("Host focus option extraction fallback for topic %r: %s", topic, exc)

        return self._fallback_focus_options(topic)

    async def summarize_debate_structured(
        self,
        topic: str,
        brief: str,
        messages: List[DebateMessage],
        references: List[SearchResult],
    ) -> StructuredReport:
        transcript = "\n".join(f"- {m.speaker}: {m.content}" for m in messages)
        user_prompt = build_structured_summary_prompt(topic, brief, transcript)

        try:
            raw = await self.llm.chat(HOST_SYSTEM_PROMPT, user_prompt)
            data = self._normalize_structured_report_data(self._extract_json_object(raw))
            report = StructuredReport(**data)
            report.host_conclusion = self._ensure_directional_conclusion(report.host_conclusion, messages)
            return report
        except Exception as exc:
            logger.warning("Host structured summary fallback for topic %r: %s", topic, exc)

        return self._fallback_structured_report(topic, brief, messages)

    async def follow_up_stream(
        self,
        topic: str,
        brief: str,
        messages: List[DebateMessage],
        question: str,
        structured_report: Optional[StructuredReport],
    ) -> AsyncGenerator[str, None]:
        transcript = "\n".join(f"- {m.speaker}: {m.content}" for m in messages[-10:])
        synthesis = structured_report.synthesis if structured_report else ""
        user_prompt = build_follow_up_prompt(topic, brief, synthesis, transcript, question)

        full_response = ""
        try:
            async for token in self.llm.chat_stream(HOST_SYSTEM_PROMPT, user_prompt):
                full_response += token
                yield token
            if not full_response.strip():
                raise ValueError("Empty response")
        except Exception as exc:
            logger.warning("Host follow-up stream fallback: %s", exc)
            fallback = self._fallback_follow_up(question, messages)
            for char in fallback:
                yield char
                await asyncio.sleep(0.01)

    def _extract_json_array(self, raw: str) -> List[dict]:
        text = raw.strip()
        if "```" in text:
            parts = text.split("```")
            body = parts[1] if len(parts) > 1 else text
            if body.strip().startswith("json"):
                body = body.strip()[4:]
            text = body.strip()
        start = text.find("[")
        end = text.rfind("]")
        if start >= 0 and end > start:
            text = text[start : end + 1]
        parsed = json.loads(text)
        if not isinstance(parsed, list):
            raise ValueError("Expected list")
        return parsed

    def _extract_json_object(self, raw: str) -> dict:
        text = raw.strip()
        if "```" in text:
            parts = text.split("```")
            body = parts[1] if len(parts) > 1 else text
            if body.strip().startswith("json"):
                body = body.strip()[4:]
            text = body.strip()
        start = text.find("{")
        end = text.rfind("}")
        if start >= 0 and end > start:
            text = text[start : end + 1]
        parsed = json.loads(text)
        if not isinstance(parsed, dict):
            raise ValueError("Expected object")
        return parsed

    def _normalize_structured_report_data(self, data: Dict[str, Any]) -> Dict[str, Any]:
        normalized = dict(data)
        raw_nodes = normalized.get("argument_nodes") or []
        nodes: List[Dict[str, Any]] = []
        for raw_node in raw_nodes:
            if not isinstance(raw_node, dict):
                continue
            node = dict(raw_node)
            if "id" in node and node["id"] is not None:
                node["id"] = str(node["id"])
            node["targets"] = [str(target) for target in (node.get("targets") or []) if target is not None]
            nodes.append(node)
        normalized["argument_nodes"] = nodes
        return normalized

    def _fallback_brief(self, topic: str, results: List[SearchResult] | None = None) -> str:
        bullets = [f"- {r.title}: {r.snippet[:120]}" for r in (results or [])[:6]]
        if not bullets:
            bullets = [
                "- 该议题通常同时涉及技术可行性、利益分配、风险外部性和治理边界。",
                "- 决定胜负的关键往往不是态度，而是谁能给出更硬的证据与更完整的责任链。",
                "- 需要区分短期收益、长期后果，以及失败时由谁承担纠错成本。",
            ]
        return (
            f"## {topic} 背景简报\n\n"
            "以下为主持人预备材料：\n"
            + "\n".join(bullets)
            + "\n\n本场辩论应围绕“证据强度、逻辑链完整度、执行代价与纠错机制”展开。"
        )

    def _fallback_debaters(self, topic: str, debater_count: int) -> List[DebaterConfig]:
        pool = [
            DebaterConfig(
                name="技术推进派 Lin",
                background="AI 系统架构师，偏工程理性",
                stance=f"对《{topic}》持积极推进态度",
                personality="强调效率与扩展性，但必须给出可检验机制",
                speaking_style="high_signal",
                avatar_emoji="A",
            ),
            DebaterConfig(
                name="制度审慎派 Zhou",
                background="公共政策研究者，关注问责与外部性",
                stance=f"对《{topic}》持审慎监管态度",
                personality="逻辑严谨，擅长追问前提、责任链和漏洞",
                speaking_style="structured",
                avatar_emoji="Z",
            ),
            DebaterConfig(
                name="落地经营派 Chen",
                background="产品负责人，关注成本、ROI 和回退机制",
                stance=f"对《{topic}》持务实落地态度",
                personality="结果导向，不接受只谈原则不谈成本",
                speaking_style="blunt",
                avatar_emoji="C",
            ),
            DebaterConfig(
                name="社会后果派 Fang",
                background="社会研究者，关注长期结构性后果",
                stance=f"对《{topic}》强调长期社会与伦理风险",
                personality="擅长揭示被忽略的后果链条",
                speaking_style="narrative",
                avatar_emoji="F",
            ),
            DebaterConfig(
                name="交叉质询派 Xu",
                background="独立评论者，专门拆解论证漏洞",
                stance=f"对《{topic}》持高压质疑立场",
                personality="不怕承认局部错误，但会迅速换到更强论点继续追击",
                speaking_style="cross_exam",
                avatar_emoji="X",
            ),
        ]
        return pool[:debater_count]

    def _fallback_report(
        self,
        topic: str,
        brief: str,
        messages: List[DebateMessage],
        references: List[SearchResult],
    ) -> str:
        by_speaker: Dict[str, List[DebateMessage]] = {}
        for msg in messages:
            by_speaker.setdefault(msg.speaker, []).append(msg)

        winner, rationale = self._pick_winner(messages)

        lines = [
            f"# 辩论报告：{topic}",
            "",
            "## 背景摘要",
            brief,
            "",
            "## 各方核心观点",
        ]
        for speaker, speaker_messages in by_speaker.items():
            lines.append(f"### {speaker}")
            lines.append(f"- 代表性论点：{speaker_messages[0].content if speaker_messages else '暂无'}")
            lines.append(f"- 发言次数：{len(speaker_messages)}")
            lines.append("")

        lines.extend(
            [
                "## 综合分析",
                "本场不是谁态度更强，而是谁能拿出更清晰的证据、闭合的因果链和更稳的反驳结构。",
                "",
                "## 最终裁决",
                f"- 胜出观点：更接近 {winner} 所代表的论证路径。",
                f"- 最强辩手：{winner}",
                f"- 胜出原因：{rationale}",
                "",
            ]
        )

        if references:
            lines.append("## 参考链接")
            for result in references[:12]:
                lines.append(f"- [{result.title}]({result.url})")
        return "\n".join(lines).strip()

    def _fallback_focus_options(self, topic: str) -> List[FocusOption]:
        return [
            FocusOption(name="执行风险", description="现实落地时最可能出问题的环节与代价"),
            FocusOption(name="长期收益", description="中长期成长、积累与结构性回报"),
            FocusOption(name="责任链条", description="失败时谁承担代价，如何纠错与止损"),
        ]

    def _fallback_structured_report(
        self,
        topic: str,
        brief: str,
        messages: List[DebateMessage],
    ) -> StructuredReport:
        by_speaker: Dict[str, List[str]] = {}
        for msg in messages:
            by_speaker.setdefault(msg.speaker, []).append(msg.content)

        core_arguments = [
            {
                "speaker": speaker,
                "stance": "参见发言记录",
                "key_points": [contents[0][:100] + "..."] if contents else ["暂无观点"],
            }
            for speaker, contents in by_speaker.items()
        ]
        winner, rationale = self._pick_winner(messages)

        return StructuredReport(
            background_summary=brief[:200] if brief else f"关于 {topic} 的背景摘要。",
            core_arguments=core_arguments,
            clash_points=[],
            synthesis="本场核心不在于每方都有道理，而在于谁的证据、因果链和反驳能力更完整。",
            host_conclusion=(
                f"- 胜出观点：更接近 {winner} 所代表的论证路径。\n"
                f"- 最强辩手：{winner}\n"
                f"- 胜出原因：{rationale}"
            ),
            argument_nodes=[],
        )

    def _fallback_follow_up(self, question: str, messages: List[DebateMessage]) -> str:
        winner, rationale = self._pick_winner(messages)
        return f"关于你的问题“{question[:30]}...”，基于现有交锋，当前更占优的一方是 {winner}。{rationale}"

    def _pick_winner(self, messages: List[DebateMessage]) -> Tuple[str, str]:
        if not messages:
            return "信息不足的一方", "当前材料太少，尚无法形成可靠裁决。"

        by_speaker: Dict[str, List[DebateMessage]] = {}
        for msg in messages:
            by_speaker.setdefault(msg.speaker, []).append(msg)

        ranked = sorted(
            ((speaker, self._speaker_score(speaker_messages)) for speaker, speaker_messages in by_speaker.items()),
            key=lambda item: (item[1][0], item[1][1]),
            reverse=True,
        )
        winner, (score, evidence_hits) = ranked[0]
        runner_up = ranked[1][0] if len(ranked) > 1 else None

        reasons = []
        if evidence_hits > 0:
            reasons.append("其论证里有更明确的证据或判定标准")
        if self._count_hits(by_speaker[winner], ["漏洞", "前提", "假设", "因果", "标准", "证据不足", "站不住"]) > 0:
            reasons.append("更积极地抓住并追打了对手的逻辑漏洞")
        if self._count_hits(by_speaker[winner], ["我承认", "我修正", "更准确地说", "我收回"]) > 0:
            reasons.append("在局部受挫时有修正能力，而不是硬撑")
        if not reasons:
            reasons.append("其逻辑链更完整，回应对手也更充分")

        if runner_up:
            return winner, f"原因是：{', '.join(reasons)}；相比之下，{runner_up} 没有把关键反驳补齐。"
        return winner, f"原因是：{', '.join(reasons)}。"

    def _ensure_directional_verdict(self, report: str, messages: List[DebateMessage]) -> str:
        if all(token in report for token in ["胜出观点", "最强辩手", "胜出原因"]):
            return report

        winner, rationale = self._pick_winner(messages)
        verdict_block = (
            "## 最终裁决\n"
            f"- 胜出观点：更接近 {winner} 所代表的论证路径。\n"
            f"- 最强辩手：{winner}\n"
            f"- 胜出原因：{rationale}"
        )
        return f"{report}\n\n{verdict_block}"

    def _ensure_directional_conclusion(self, conclusion: str, messages: List[DebateMessage]) -> str:
        if all(token in conclusion for token in ["胜出观点", "最强辩手", "胜出原因"]):
            return conclusion

        winner, rationale = self._pick_winner(messages)
        return (
            f"- 胜出观点：更接近 {winner} 所代表的论证路径。\n"
            f"- 最强辩手：{winner}\n"
            f"- 胜出原因：{rationale}"
        )

    def _speaker_score(self, messages: List[DebateMessage]) -> Tuple[int, int]:
        evidence_hits = self._count_hits(messages, ["证据", "数据", "研究", "报告", "样本", "来源", "统计"])
        logic_hits = self._count_hits(messages, ["因为", "所以", "因此", "如果", "那么", "意味着", "前提", "因果", "逻辑"])
        attack_hits = self._count_hits(messages, ["漏洞", "假设", "证据不足", "因果链", "矛盾", "标准", "站不住"])
        concession_hits = self._count_hits(messages, ["我承认", "我修正", "更准确地说", "我收回", "这一点成立但"])
        hedge_hits = self._count_hits(messages, ["都对", "都有道理", "各有道理", "见仁见智", "难分高下"])
        score = evidence_hits * 3 + logic_hits * 2 + attack_hits * 3 + concession_hits * 2 - hedge_hits * 4 + len(messages)
        return score, evidence_hits

    def _count_hits(self, messages: List[DebateMessage], keywords: List[str]) -> int:
        text = "\n".join(msg.content for msg in messages)
        return sum(text.count(keyword) for keyword in keywords)

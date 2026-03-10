from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, AsyncGenerator, Dict, List, Optional, Tuple

from app.models import DebaterConfig, DebateMessage, FocusDimension, SearchResult, StructuredReport
from app.providers.base import LLMProvider, SearchProvider

logger = logging.getLogger(__name__)


HOST_SYSTEM_PROMPT = """You are a professional debate host and research analyst.
You produce balanced, evidence-oriented synthesis in concise Chinese.
"""


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
        for q in queries:
            try:
                all_results.extend(await self.search.search(q, num_results=3))
            except Exception:
                continue

        if not all_results:
            return self._fallback_brief(topic), []

        citations_text = "\n".join(f"- {r.title}: {r.snippet[:160]} ({r.url})" for r in all_results[:9])
        user_prompt = (
            f"话题：{topic}\n\n"
            f"请基于以下材料生成 500-800 字背景简报，要求中立、结构清晰。\n"
            f"材料：\n{citations_text}\n"
        )
        try:
            brief = await self.llm.chat(HOST_SYSTEM_PROMPT, user_prompt)
            if brief.strip():
                return brief.strip(), all_results
        except Exception as exc:
            logger.warning("Host research fallback activated for topic %r: %s", topic, exc)

        return self._fallback_brief(topic, all_results), all_results

    async def create_debaters(self, topic: str, debater_count: int, brief: str) -> List[DebaterConfig]:
        user_prompt = (
            f"针对话题《{topic}》，设计 {debater_count} 位辩手。\n"
            "请只返回 JSON 数组，字段为 name, background, stance, personality, speaking_style, avatar_emoji。\n"
            "要求：\n"
            "1. 立场差异要明确，但都必须像真实社会中的利益相关方或分析者，而不是网络骂战选手。\n"
            "2. 分歧应来自利益位置、风险偏好、制度约束、价值排序或分析框架，而不是单纯情绪对立。\n"
            "3. personality 和 speaking_style 要体现思考方式，例如数据派、制度派、产业派、人文派、交叉质询派，不要写成人身攻击型角色。\n"
            "4. 每位辩手都应具备专业感，允许承认对方局部合理，但在核心判断上保持鲜明分歧。\n"
            "5. speaking_style 请尽量使用短标签，例如 structured / empirical / blunt / narrative / cross_exam / high_signal。\n"
            "6. 这些辩手不应共享同一种发言模板。不要把他们设计成每轮都用“我同意”“我认为”起手的机械角色；他们应能直接反驳、追问、重定义问题，并推动讨论深入。\n"
            f"背景简报：\n{brief[:1200]}"
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
        transcript = "\n".join([f"- {m.speaker}: {m.content}" for m in messages])
        refs = "\n".join([f"- [{r.title}]({r.url})" for r in references[:12]])
        user_prompt = (
            f"话题：{topic}\n\n"
            f"背景简报：\n{brief}\n\n"
            f"辩论记录：\n{transcript[:6000]}\n\n"
            "请输出 Markdown 报告，包含：\n"
            "1) 背景摘要\n2) 各方核心观点与代表发言\n3) 交锋焦点\n4) 综合分析\n5) 主持人结论\n"
            "语言简洁但信息密度高。\n"
        )
        try:
            report = await self.llm.chat(HOST_SYSTEM_PROMPT, user_prompt)
            if report.strip():
                if refs:
                    report += f"\n\n## 参考链接\n{refs}\n"
                return report.strip()
        except Exception as exc:
            logger.warning("Host summary fallback activated for topic %r: %s", topic, exc)

        return self._fallback_report(topic, brief, messages, references)

    async def extract_dimensions(self, topic: str, brief: str) -> List[FocusDimension]:
        """Extract focus dimensions from research for pre-debate configuration."""
        user_prompt = (
            f"话题：{topic}\n\n"
            f"背景简报：\n{brief[:1500]}\n\n"
            "请基于以上材料，提取 3-5 个辩论应聚焦的核心维度。\n"
            "每个维度应是一个具体的争议焦点，而非宽泛的概念。\n\n"
            "请返回 JSON 数组，每个元素包含：\n"
            '- "name": 维度名称（10字以内）\n'
            '- "description": 维度说明（50字以内）\n'
            '- "selected": true（默认选中）\n'
        )
        try:
            raw = await self.llm.chat(HOST_SYSTEM_PROMPT, user_prompt)
            data = self._extract_json_array(raw)
            dimensions = [FocusDimension(**row) for row in data[:5]]
            if dimensions:
                return dimensions
        except Exception as exc:
            logger.warning("Host dimension extraction fallback for topic %r: %s", topic, exc)

        return self._fallback_dimensions(topic)

    async def summarize_debate_structured(
        self,
        topic: str,
        brief: str,
        messages: List[DebateMessage],
        references: List[SearchResult],
    ) -> StructuredReport:
        """Generate structured report with argument analysis."""
        transcript = "\n".join([f"- {m.speaker}: {m.content}" for m in messages])

        user_prompt = (
            f"话题：{topic}\n\n"
            f"背景简报：\n{brief}\n\n"
            f"辩论记录：\n{transcript[:6000]}\n\n"
            "请输出结构化报告，包含以下部分：\n"
            "1. background_summary: 背景摘要（200字以内）\n"
            "2. core_arguments: 各方核心观点数组，每个包含 speaker, stance, key_points（要点数组）\n"
            "3. clash_points: 交锋焦点数组，每个包含 topic 和 positions（各方立场字典）\n"
            "4. synthesis: 综合分析（300字以内）\n"
            "5. host_conclusion: 主持人结论（150字以内）\n"
            "6. argument_nodes: 论证节点数组，每个包含 speaker, content, turn_index, targets（回应的节点ID数组）, status（claim/support/attack/concession）, focal_point\n\n"
            "请返回 JSON 格式。"
        )

        try:
            raw = await self.llm.chat(HOST_SYSTEM_PROMPT, user_prompt)
            data = self._normalize_structured_report_data(self._extract_json_object(raw))
            return StructuredReport(**data)
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
        """Stream host follow-up response with neutrality."""
        transcript = "\n".join([f"- {m.speaker}: {m.content}" for m in messages[-10:]])
        synthesis = structured_report.synthesis if structured_report else ""

        user_prompt = (
            f"话题：{topic}\n\n"
            f"背景简报：\n{brief[:800]}\n\n"
            f"辩论综合：\n{synthesis[:500]}\n\n"
            f"近期辩论记录：\n{transcript[:2000]}\n\n"
            f"用户问题：{question}\n\n"
            "作为主持人，请基于以上材料回答用户问题。要求：\n"
            "1. 保持中立立场，不偏袒任何一方\n"
            "2. 基于辩论记录和背景材料给出分析\n"
            "3. 指出哪些部分有明确证据，哪些属于推测\n"
            "4. 回答控制在 300 字以内，信息密度高\n"
        )

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
        bullets = []
        for r in (results or [])[:6]:
            bullets.append(f"- {r.title}：{r.snippet[:120]}")
        if not bullets:
            bullets = [
                "- 该议题通常同时涉及技术可行性、伦理边界、商业激励和政策治理。",
                "- 需要区分短期影响与长期结构性后果，避免只给单一结论。",
                "- 建议重点关注普通用户、企业、监管者、研究者等不同利益相关方。",
            ]
        return (
            f"## {topic} 背景简报\n\n"
            "以下为主持人预备材料（MVP 回退版本）：\n"
            + "\n".join(bullets)
            + "\n\n本场辩论将围绕“价值、风险、可执行路径”展开。"
        )

    def _fallback_debaters(self, topic: str, debater_count: int) -> List[DebaterConfig]:
        pool = [
            DebaterConfig(
                name="技术推进派 Lin",
                background="AI 系统架构师，偏工程理性",
                stance=f"对《{topic}》持积极推进态度",
                personality="强调可扩展性和试错速度，反感空泛恐惧",
                speaking_style="high_signal",
                avatar_emoji="因",
            ),
            DebaterConfig(
                name="制度审慎派 Zhou",
                background="公共政策研究者，关注制度设计与问责",
                stance=f"对《{topic}》持审慎监管态度",
                personality="逻辑严谨，擅长追问边界条件和责任链",
                speaking_style="structured",
                avatar_emoji="衡",
            ),
            DebaterConfig(
                name="落地经营派 Chen",
                background="互联网产品负责人，关注增长、预算与 ROI",
                stance=f"对《{topic}》持务实落地态度",
                personality="结果导向，习惯把问题拆成成本、周期和止损",
                speaking_style="blunt",
                avatar_emoji="账",
            ),
            DebaterConfig(
                name="社会后果派 Fang",
                background="社会学作者，长期观察技术与组织关系",
                stance=f"对《{topic}》强调社会与伦理风险",
                personality="擅长从长期结构性后果切入，表达锋利但克制",
                speaking_style="narrative",
                avatar_emoji="衡",
            ),
            DebaterConfig(
                name="交叉质询派 Xu",
                background="独立评论者，专门拆解论证漏洞",
                stance=f"对《{topic}》持怀疑和反直觉立场",
                personality="专挑假设漏洞，逼迫各方给出更硬的判定标准",
                speaking_style="cross_exam",
                avatar_emoji="问",
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
        by_speaker: dict[str, list[str]] = {}
        for msg in messages:
            by_speaker.setdefault(msg.speaker, []).append(msg.content)

        lines = [
            f"# 辩论报告：{topic}",
            "",
            "## 背景摘要",
            brief,
            "",
            "## 各方核心观点",
        ]
        for speaker, quotes in by_speaker.items():
            lines.append(f"### {speaker}")
            lines.append(f"- 代表观点：{quotes[0] if quotes else '暂无'}")
            lines.append(f"- 发言次数：{len(quotes)}")
            lines.append("")

        lines.extend(["## 主持人结论", "该议题不存在单一正确答案，建议按场景分层决策。", ""])
        if references:
            lines.append("## 参考链接")
            for r in references[:12]:
                lines.append(f"- [{r.title}]({r.url})")
        return "\n".join(lines).strip()

    def _fallback_dimensions(self, topic: str) -> List[FocusDimension]:
        """Fallback dimensions when extraction fails."""
        return [
            FocusDimension(
                name="技术可行性",
                description="该议题在技术层面的实现难度与风险",
                selected=True,
            ),
            FocusDimension(
                name="经济影响",
                description="对相关产业和就业市场的经济效应",
                selected=True,
            ),
            FocusDimension(
                name="伦理边界",
                description="涉及的道德伦理问题与社会接受度",
                selected=True,
            ),
            FocusDimension(
                name="治理机制",
                description="监管框架与问责制度的完善程度",
                selected=True,
            ),
        ]

    def _fallback_structured_report(
        self,
        topic: str,
        brief: str,
        messages: List[DebateMessage],
    ) -> StructuredReport:
        """Fallback structured report when generation fails."""
        by_speaker: Dict[str, List[str]] = {}
        for msg in messages:
            by_speaker.setdefault(msg.speaker, []).append(msg.content)

        core_arguments = []
        for speaker, contents in by_speaker.items():
            core_arguments.append({
                "speaker": speaker,
                "stance": "参见发言记录",
                "key_points": [contents[0][:100] + "..."] if contents else ["暂无观点"],
            })

        return StructuredReport(
            background_summary=brief[:200] if brief else f"关于{topic}的背景",
            core_arguments=core_arguments,
            clash_points=[],
            synthesis="辩论涉及多个维度，各方立场存在实质性分歧。",
            host_conclusion="该议题不存在单一正确答案，建议按场景分层决策。",
            argument_nodes=[],
        )

    def _fallback_follow_up(self, question: str, messages: List[DebateMessage]) -> str:
        """Fallback follow-up response."""
        return (
            f"关于您的问题「{question[:30]}...」，"
            "基于现有辩论记录，主持人认为这是一个需要更多证据支持的问题。"
            "建议参考辩论中各方提出的具体论据和判定标准。"
        )

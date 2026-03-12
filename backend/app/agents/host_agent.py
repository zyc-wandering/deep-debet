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
    build_json_array_repair_prompt,
    build_json_object_repair_prompt,
    build_markdown_repair_prompt,
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
            f"{topic} 争议",
            f"{topic} 数据 研究 报告",
        ]

        all_results: List[SearchResult] = []
        for query in queries:
            try:
                all_results.extend(await self.search.search(query, num_results=3))
            except Exception:
                continue

        citations_text = "\n".join(f"- {r.title}: {r.snippet[:160]} ({r.url})" for r in all_results[:9])
        if not citations_text:
            citations_text = "- 未检索到可用外部材料。请明确区分已知、推测与待验证部分。"

        brief = await self._chat_required_text(build_research_prompt(topic, citations_text))
        return brief, all_results

    async def create_debaters(
        self,
        topic: str,
        debater_count: int,
        brief: str,
        selected_focus: FocusOption | None = None,
        intensity: str = "balanced",
        user_context: str = "",
    ) -> List[DebaterConfig]:
        data = await self._chat_json_array(
            user_prompt=build_debater_generation_prompt(
                topic=topic,
                debater_count=debater_count,
                brief=brief,
                intensity=intensity,
                selected_focus=selected_focus,
                user_context=user_context,
            ),
            schema_description=(
                "返回 JSON 数组；每个元素必须包含 name, background, stance, personality, "
                "speaking_style, avatar_emoji 六个字段。"
            ),
        )

        configs = [DebaterConfig(**row) for row in data[:debater_count]]
        if len(configs) < debater_count:
            raise ValueError(f"Expected {debater_count} debaters, got {len(configs)}")
        return configs[:debater_count]

    async def summarize_debate(
        self,
        topic: str,
        brief: str,
        messages: List[DebateMessage],
        references: List[SearchResult],
    ) -> str:
        transcript = "\n".join(f"- {m.speaker}: {m.content}" for m in messages)
        return await self._chat_markdown_with_requirements(
            user_prompt=build_summary_prompt(topic, brief, transcript),
            requirements=(
                "必须包含“背景摘要”“各方核心观点与代表性论证”“关键交锋与漏洞暴露”"
                "“让步、修正与立场变化”“综合分析”“最终裁决”六个部分，"
                "且最终裁决必须包含三行：胜出观点、最强辩手、胜出原因。"
            ),
            required_tokens=["背景摘要", "最终裁决", "胜出观点", "最强辩手", "胜出原因"],
        )

    async def extract_focus_options(self, topic: str, brief: str) -> List[FocusOption]:
        data = await self._chat_json_array(
            user_prompt=build_focus_options_prompt(topic, brief),
            schema_description='返回 2-3 个元素的 JSON 数组；每个元素只包含 "name" 和 "description"。',
        )
        focus_options = [FocusOption(**row) for row in data[:3]]
        if len(focus_options) < 2:
            raise ValueError(f"Expected at least 2 focus options, got {len(focus_options)}")
        return focus_options

    async def summarize_debate_structured(
        self,
        topic: str,
        brief: str,
        messages: List[DebateMessage],
        references: List[SearchResult],
    ) -> StructuredReport:
        transcript = "\n".join(f"- {m.speaker}: {m.content}" for m in messages)
        data = await self._chat_json_object(
            user_prompt=build_structured_summary_prompt(topic, brief, transcript),
            schema_description=(
                "返回 JSON 对象，必须包含 background_summary, core_arguments, clash_points, "
                "synthesis, host_conclusion, argument_nodes 六个字段。"
            ),
        )
        normalized = self._normalize_structured_report_data(data)
        report = StructuredReport(**normalized)
        if not all(token in report.host_conclusion for token in ["胜出观点", "最强辩手", "胜出原因"]):
            repaired = await self._chat_markdown_with_requirements(
                user_prompt=build_markdown_repair_prompt(
                    requirements="只输出主持人结论，且必须包含三行：胜出观点、最强辩手、胜出原因。",
                    raw_output=report.host_conclusion,
                ),
                requirements="只输出主持人结论，必须包含：胜出观点、最强辩手、胜出原因。",
                required_tokens=["胜出观点", "最强辩手", "胜出原因"],
            )
            report.host_conclusion = repaired
        return report

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

        yield_count = 0
        try:
            async for token in self.llm.chat_stream(HOST_SYSTEM_PROMPT, user_prompt):
                yield_count += 1
                yield token
            if yield_count == 0:
                raise ValueError("Empty streamed response")
        except Exception as exc:
            logger.warning("Host follow-up stream fallback to non-stream chat: %s", exc)
            text = await self._chat_required_text(user_prompt)
            for char in text:
                yield char
                await asyncio.sleep(0.005)

    async def _chat_required_text(self, user_prompt: str) -> str:
        text = (await self.llm.chat(HOST_SYSTEM_PROMPT, user_prompt)).strip()
        if not text:
            raise ValueError("Empty LLM response")
        return text

    async def _chat_markdown_with_requirements(
        self,
        user_prompt: str,
        requirements: str,
        required_tokens: List[str],
    ) -> str:
        raw = await self._chat_required_text(user_prompt)
        if self._contains_all_tokens(raw, required_tokens):
            return raw

        repaired = await self._chat_required_text(
            build_markdown_repair_prompt(requirements=requirements, raw_output=raw)
        )
        if not self._contains_all_tokens(repaired, required_tokens):
            raise ValueError(f"LLM output still missing required tokens: {required_tokens}")
        return repaired

    async def _chat_json_array(self, user_prompt: str, schema_description: str) -> List[dict]:
        raw = await self._chat_required_text(user_prompt)
        try:
            return self._extract_json_array(raw)
        except Exception:
            repaired = await self._chat_required_text(
                build_json_array_repair_prompt(schema_description=schema_description, raw_output=raw)
            )
            return self._extract_json_array(repaired)

    async def _chat_json_object(self, user_prompt: str, schema_description: str) -> Dict[str, Any]:
        raw = await self._chat_required_text(user_prompt)
        try:
            return self._extract_json_object(raw)
        except Exception:
            repaired = await self._chat_required_text(
                build_json_object_repair_prompt(schema_description=schema_description, raw_output=raw)
            )
            return self._extract_json_object(repaired)

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
            raise ValueError("Expected JSON array")
        return parsed

    def _extract_json_object(self, raw: str) -> Dict[str, Any]:
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
            raise ValueError("Expected JSON object")
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

    def _contains_all_tokens(self, text: str, tokens: List[str]) -> bool:
        return all(token in text for token in tokens)

from __future__ import annotations

import asyncio
import json
from time import monotonic
from typing import Any, AsyncGenerator, Dict, List, Optional, Tuple

from app.models import (
    DebaterConfig,
    DebateLanguage,
    DebateMessage,
    FocusOption,
    SearchResult,
    StructuredReport,
)
from app.prompts.host import (
    build_debater_generation_prompt,
    build_focus_options_prompt,
    build_follow_up_prompt,
    build_json_array_repair_prompt,
    build_json_object_repair_prompt,
    build_markdown_repair_prompt,
    build_research_prompt,
    build_structured_summary_prompt,
    build_summary_prompt,
    get_host_system_prompt,
)
from app.providers.base import LLMProvider, SearchProvider
from app.utils.logger import debate_logger


class HostAgent:
    def __init__(
        self,
        llm: LLMProvider,
        search: SearchProvider,
        debate_language: DebateLanguage = DebateLanguage.zh,
    ) -> None:
        self.llm = llm
        self.search = search
        self.debate_language = debate_language

    def _system_prompt(self) -> str:
        return get_host_system_prompt(self.debate_language)

    async def research_topic(self, topic: str) -> Tuple[str, List[SearchResult]]:
        research_start = monotonic()
        queries = [topic]
        if self.debate_language == DebateLanguage.en:
            queries.extend([f"{topic} controversy", f"{topic} data research report"])
        else:
            queries.extend([f"{topic} 争议", f"{topic} 数据 研究 报告"])

        all_results: List[SearchResult] = []
        for query in queries:
            try:
                debate_logger.search_request(query, "tavily", 3)
                results = await self.search.search(query, num_results=3)
                all_results.extend(results)
            except Exception as exc:
                debate_logger.warning(
                    f"Search failed for query: {query}",
                    event_type="search_error",
                    query=query,
                    error=str(exc),
                )
                continue

        citations_text = "\n".join(f"- {r.title}: {r.snippet[:160]} ({r.url})" for r in all_results[:9])
        if not citations_text:
            if self.debate_language == DebateLanguage.en:
                citations_text = "- No usable external materials were retrieved. Explicitly distinguish known facts, inference, and verification gaps."
            else:
                citations_text = "- 未检索到可用外部材料。请明确区分已知、推测与待验证部分。"

        prompt = build_research_prompt(topic, citations_text, language=self.debate_language)
        debate_logger.llm_request("host", "research_topic", {"topic": topic}, prompt_length=len(prompt))

        llm_start = monotonic()
        try:
            brief = await self._chat_required_text(prompt)
            debate_logger.llm_response(
                "host",
                "research_topic",
                duration_sec=monotonic() - llm_start,
                token_count=len(brief) // 4,
                response_length=len(brief),
                success=True,
            )
        except Exception as exc:
            debate_logger.llm_response(
                "host",
                "research_topic",
                duration_sec=monotonic() - llm_start,
                token_count=0,
                response_length=0,
                success=False,
                error=str(exc),
            )
            raise

        debate_logger.info(
            "Research completed",
            event_type="research_complete",
            duration_sec=monotonic() - research_start,
            query_count=len(queries),
            result_count=len(all_results),
        )
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
                language=self.debate_language,
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
        summarize_start = monotonic()
        transcript = "\n".join(f"- {m.speaker}: {m.content}" for m in messages)
        transcript_length = len(transcript)
        debate_logger.info(
            "Starting summarize_debate",
            event_type="summarize_debate_start",
            topic=topic,
            message_count=len(messages),
            transcript_length=transcript_length,
        )

        if self.debate_language == DebateLanguage.en:
            requirements = (
                'Must include "Background Summary", "Core Arguments and Representative Reasoning per Debater", '
                '"Key Clashes and Exposed Vulnerabilities", "Concessions, Revisions, and Position Changes", '
                '"Synthesis", and "Final Verdict", and the verdict must include lines for '
                '"Winning View", "Strongest Debater", and "Why It Won".'
            )
            required_tokens = ["Background Summary", "Final Verdict", "Winning View", "Strongest Debater"]
        else:
            requirements = (
                "必须包含“背景摘要”“各方核心观点与代表性论证”“关键交锋与漏洞暴露”"
                "“让步、修正与立场变化”“综合分析”“最终裁决”六个部分，"
                "且最终裁决必须包含三行：胜出观点、最强辩手、胜出原因。"
            )
            required_tokens = ["背景摘要", "最终裁决", "胜出观点", "最强辩手", "胜出原因"]

        prompt = build_summary_prompt(topic, brief, transcript, language=self.debate_language)
        debate_logger.llm_request("host", "summarize_debate", {"topic": topic}, prompt_length=len(prompt))

        llm_start = monotonic()
        try:
            result = await self._chat_markdown_with_requirements(
                user_prompt=prompt,
                requirements=requirements,
                required_tokens=required_tokens,
            )
            debate_logger.llm_response(
                "host",
                "summarize_debate",
                duration_sec=monotonic() - llm_start,
                token_count=len(result) // 4,
                response_length=len(result),
                success=True,
            )
            debate_logger.info(
                "summarize_debate completed",
                event_type="summarize_debate_complete",
                duration_sec=monotonic() - summarize_start,
                result_length=len(result),
            )
            return result
        except Exception as exc:
            debate_logger.llm_response(
                "host",
                "summarize_debate",
                duration_sec=monotonic() - llm_start,
                token_count=0,
                response_length=0,
                success=False,
                error=str(exc),
            )
            debate_logger.error(
                "summarize_debate failed",
                event_type="summarize_debate_error",
                duration_sec=monotonic() - summarize_start,
                exc=exc,
            )
            raise

    async def extract_focus_options(self, topic: str, brief: str) -> List[FocusOption]:
        data = await self._chat_json_array(
            user_prompt=build_focus_options_prompt(topic, brief, language=self.debate_language),
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
        summarize_start = monotonic()
        transcript = "\n".join(f"- {m.speaker}: {m.content}" for m in messages)
        debate_logger.info(
            "Starting summarize_debate_structured",
            event_type="summarize_structured_start",
            topic=topic,
            message_count=len(messages),
            transcript_length=len(transcript),
        )

        prompt = build_structured_summary_prompt(
            topic,
            brief,
            transcript,
            language=self.debate_language,
        )
        debate_logger.llm_request(
            "host",
            "summarize_debate_structured",
            {"topic": topic},
            prompt_length=len(prompt),
        )

        llm_start = monotonic()
        try:
            data = await self._chat_json_object(
                user_prompt=prompt,
                schema_description=(
                    "返回 JSON 对象，必须包含 background_summary, core_arguments, clash_points, "
                    "synthesis, host_conclusion, argument_nodes 六个字段。"
                ),
            )
            debate_logger.llm_response(
                "host",
                "summarize_debate_structured",
                duration_sec=monotonic() - llm_start,
                token_count=len(str(data)) // 4,
                response_length=len(str(data)),
                success=True,
            )
        except Exception as exc:
            debate_logger.llm_response(
                "host",
                "summarize_debate_structured",
                duration_sec=monotonic() - llm_start,
                token_count=0,
                response_length=0,
                success=False,
                error=str(exc),
            )
            debate_logger.error(
                "summarize_debate_structured failed",
                event_type="summarize_structured_error",
                duration_sec=monotonic() - summarize_start,
                exc=exc,
            )
            raise

        normalized = self._normalize_structured_report_data(data)
        report = StructuredReport(**normalized)
        debate_logger.info(
            "summarize_debate_structured data parsed",
            event_type="summarize_structured_parsed",
            synthesis_length=len(report.synthesis),
            core_arguments_count=len(report.core_arguments),
            clash_points_count=len(report.clash_points),
            argument_nodes_count=len(report.argument_nodes),
        )

        if self.debate_language == DebateLanguage.en:
            conclusion_tokens = ["Winning View", "Strongest Debater", "Why It Won"]
            repair_requirements = (
                'Return only the host conclusion, and it must contain lines for '
                '"Winning View", "Strongest Debater", and "Why It Won".'
            )
        else:
            conclusion_tokens = ["胜出观点", "最强辩手", "胜出原因"]
            repair_requirements = "只输出主持人结论，且必须包含三行：胜出观点、最强辩手、胜出原因。"
        if not all(token in report.host_conclusion for token in conclusion_tokens):
            repaired = await self._chat_markdown_with_requirements(
                user_prompt=build_markdown_repair_prompt(
                    requirements=repair_requirements,
                    raw_output=report.host_conclusion,
                    language=self.debate_language,
                ),
                requirements=repair_requirements,
                required_tokens=conclusion_tokens,
            )
            report.host_conclusion = repaired
            debate_logger.info(
                "Host conclusion repaired",
                event_type="host_conclusion_repaired",
                original_conclusion=report.host_conclusion[:200],
                repaired_conclusion=repaired[:200],
            )
        debate_logger.info(
            "summarize_debate_structured completed",
            event_type="summarize_structured_complete",
            duration_sec=monotonic() - summarize_start,
        )
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
        user_prompt = build_follow_up_prompt(
            topic,
            brief,
            synthesis,
            transcript,
            question,
            language=self.debate_language,
        )

        yield_count = 0
        try:
            async for token in self.llm.chat_stream(self._system_prompt(), user_prompt):
                yield_count += 1
                yield token
            if yield_count == 0:
                raise ValueError("Empty streamed response")
        except Exception as exc:
            debate_logger.warning(
                "Host follow-up stream fallback to non-stream chat",
                event_type="host_follow_up_fallback",
                error=str(exc),
            )
            text = await self._chat_required_text(user_prompt)
            for char in text:
                yield char
                await asyncio.sleep(0.005)

    async def _chat_required_text(self, user_prompt: str) -> str:
        text = (await self.llm.chat(self._system_prompt(), user_prompt)).strip()
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
            build_markdown_repair_prompt(
                requirements=requirements,
                raw_output=raw,
                language=self.debate_language,
            )
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
                build_json_array_repair_prompt(
                    schema_description=schema_description,
                    raw_output=raw,
                    language=self.debate_language,
                )
            )
            return self._extract_json_array(repaired)

    async def _chat_json_object(self, user_prompt: str, schema_description: str) -> Dict[str, Any]:
        raw = await self._chat_required_text(user_prompt)
        try:
            return self._extract_json_object(raw)
        except Exception:
            repaired = await self._chat_required_text(
                build_json_object_repair_prompt(
                    schema_description=schema_description,
                    raw_output=raw,
                    language=self.debate_language,
                )
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

        # 处理 host_conclusion - LLM 可能返回 dict 而不是 string
        host_conclusion = normalized.get("host_conclusion")
        if isinstance(host_conclusion, dict):
            # 将 dict 转换为格式化的 markdown 字符串
            lines = []
            for key, value in host_conclusion.items():
                # 将 snake_case 转换为可读格式
                readable_key = key.replace("_", " ").title()
                lines.append(f"**{readable_key}**: {value}")
            normalized["host_conclusion"] = "\n\n".join(lines)
        elif not isinstance(host_conclusion, str):
            normalized["host_conclusion"] = str(host_conclusion) if host_conclusion else ""

        # 处理 argument_nodes
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

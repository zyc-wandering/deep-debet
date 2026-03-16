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
    build_substitute_debaters_prompt,
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
                "返回 JSON 数组；每个元素必须包含 name, age, ethnicity, background, stance, "
                "personality, speaking_style, avatar_emoji 八个字段。"
            ),
        )

        configs = [DebaterConfig(**row) for row in data[:debater_count]]
        if len(configs) < debater_count:
            raise ValueError(f"Expected {debater_count} debaters, got {len(configs)}")
        return configs[:debater_count]

    async def create_substitute_debaters(
        self,
        topic: str,
        brief: str,
        existing_debaters: List[DebaterConfig],
        selected_focus: FocusOption | None = None,
        intensity: str = "balanced",
        substitute_count: int = 3,
    ) -> List[DebaterConfig]:
        """Generate substitute debaters that offer perspectives different from the main lineup."""
        existing_dicts = [d.model_dump() for d in existing_debaters]
        data = await self._chat_json_array(
            user_prompt=build_substitute_debaters_prompt(
                topic=topic,
                brief=brief,
                existing_debaters=existing_dicts,
                selected_focus=selected_focus,
                intensity=intensity,
                substitute_count=substitute_count,
                language=self.debate_language,
            ),
            schema_description=(
                "返回 JSON 数组；每个元素必须包含 name, age, ethnicity, background, stance, "
                "personality, speaking_style, avatar_emoji 八个字段。"
            ),
        )
        configs = [DebaterConfig(**row) for row in data[:substitute_count]]
        return configs

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
                '"Synthesis", and "Final Verdict", and the verdict must include '
                '"Winning View", "Strongest Debater", and 2-3 independent "Reasons for Victory" '
                'from different dimensions (logic, value, response capability).'
            )
            required_tokens = ["Background Summary", "Final Verdict", "Winning View", "Strongest Debater"]
        else:
            requirements = (
                "必须包含“背景摘要”“各方核心观点与代表性论证”“关键交锋与漏洞暴露”"
                "“让步、修正与立场变化”“综合分析”“最终裁决”六个部分，"
                "且最终裁决的胜出原因必须提供2-3个独立的、不同维度的原因（如逻辑完整性、价值洞察、回应能力等）。"
            )
            required_tokens = ["背景摘要", "最终裁决", "胜出观点", "最强辩手"]

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

        # 验证 host_conclusion - 支持新的结构化格式（含 reasoning_list）或旧格式
        host_conclusion_valid = False
        if isinstance(report.host_conclusion, dict):
            # 新格式：检查是否有 winning_argument 和 reasoning_list
            hc = report.host_conclusion
            host_conclusion_valid = (
                hc.get("winning_argument")
                and hc.get("strongest_debater")
                and len(hc.get("reasoning_list", [])) >= 2
            )
        elif isinstance(report.host_conclusion, str):
            # 旧格式：检查是否包含必要的 token
            if self.debate_language == DebateLanguage.en:
                host_conclusion_valid = all(token in report.host_conclusion for token in ["Winning View", "Strongest Debater"])
            else:
                host_conclusion_valid = all(token in report.host_conclusion for token in ["胜出观点", "最强辩手"])

        if not host_conclusion_valid:
            if self.debate_language == DebateLanguage.en:
                repair_requirements = (
                    'Return a JSON object with fields: "winning_argument" (string), '
                    '"strongest_debater" (string), "reasoning" (string), and '
                    '"reasoning_list" (array of 2-3 independent reasons from different dimensions).'
                )
            else:
                repair_requirements = (
                    '返回JSON对象，包含字段："winning_argument"（胜出观点）、'
                    '"strongest_debater"（最强辩手）、"reasoning"（裁决概述）、'
                    '"reasoning_list"（2-3个独立胜出原因的字符串数组）'
                )
            raw_output = (
                report.host_conclusion
                if isinstance(report.host_conclusion, str)
                else str(report.host_conclusion)
            )
            repaired = await self._chat_markdown_with_requirements(
                user_prompt=build_markdown_repair_prompt(
                    requirements=repair_requirements,
                    raw_output=raw_output,
                    language=self.debate_language,
                ),
                requirements=repair_requirements,
                required_tokens=["winning_argument", "strongest_debater", "reasoning_list"],
            )
            # 尝试解析修复后的JSON
            try:
                import json
                repaired_dict = json.loads(repaired)
                report.host_conclusion = repaired_dict
            except Exception:
                report.host_conclusion = repaired
            conclusion_preview = (
                str(report.host_conclusion)[:200]
                if not isinstance(report.host_conclusion, str)
                else report.host_conclusion[:200]
            )
            debate_logger.info(
                "Host conclusion repaired",
                event_type="host_conclusion_repaired",
                original_conclusion=conclusion_preview,
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

    async def _chat_required_text(self, user_prompt: str, *, max_retries: int = 2) -> str:
        last_exc: Exception | None = None
        for attempt in range(max_retries + 1):
            try:
                text = (await self.llm.chat(self._system_prompt(), user_prompt)).strip()
                if text:
                    return text
                last_exc = ValueError("Empty LLM response")
                debate_logger.warning(
                    f"Empty LLM response (attempt {attempt + 1}/{max_retries + 1}), retrying…",
                    event_type="llm_empty_response_retry",
                    attempt=attempt + 1,
                )
            except Exception as exc:
                last_exc = exc
                debate_logger.warning(
                    f"LLM call failed (attempt {attempt + 1}/{max_retries + 1}): {exc}",
                    event_type="llm_call_retry",
                    attempt=attempt + 1,
                    error=str(exc),
                )
            if attempt < max_retries:
                await asyncio.sleep(1.5 * (attempt + 1))
        raise last_exc or ValueError("Empty LLM response after retries")

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

        # 处理 host_conclusion - 支持新的结构化格式或旧格式
        host_conclusion = normalized.get("host_conclusion")
        if isinstance(host_conclusion, dict):
            # 新格式：保留为字典，确保包含所有必要字段
            hc = host_conclusion
            # 确保 reasoning_list 存在且为列表
            if "reasoning_list" not in hc or not isinstance(hc.get("reasoning_list"), list):
                # 兼容旧格式或缺失字段：从 reasoning 字段拆分或创建默认值
                reasoning = hc.get("reasoning", "")
                if reasoning:
                    # 尝试从 reasoning 字段创建 reasoning_list
                    hc["reasoning_list"] = [reasoning]
                else:
                    hc["reasoning_list"] = []
            normalized["host_conclusion"] = hc
        elif isinstance(host_conclusion, str):
            # 旧格式：保持为字符串，后续会触发修复
            normalized["host_conclusion"] = host_conclusion
        else:
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

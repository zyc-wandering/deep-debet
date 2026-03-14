from __future__ import annotations

import asyncio
import logging
from typing import AsyncGenerator, List, Tuple

from app.agents.context_manager import ContextManager
from app.models import DebaterConfig, DebateLanguage, DebateMessage, DebateStage, FocusOption, SearchResult
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
        debate_language: DebateLanguage = DebateLanguage.zh,
    ) -> None:
        self.config = config
        self.llm = llm
        self.search = search
        self.context_manager = context_manager or ContextManager()
        self.rolling_summary = ""
        self.debate_language = debate_language

    def _system_prompt(self) -> str:
        return build_base_system_prompt(self.config, language=self.debate_language)

    async def produce_turn(
        self,
        topic: str,
        brief: str,
        messages: List[DebateMessage],
        enable_search: bool,
    ) -> Tuple[str, List[SearchResult]]:
        references = await self._load_references(topic, enable_search)
        user_prompt = self._build_general_turn_prompt(brief, messages, references)
        text = (await self.llm.chat(self._system_prompt(), user_prompt)).strip()
        if not text:
            raise ValueError(f"Empty debater response for {self.config.name}")
        return text, references

    async def produce_turn_stream(
        self,
        topic: str,
        brief: str,
        messages: List[DebateMessage],
        enable_search: bool,
    ) -> AsyncGenerator[str, None]:
        references = await self._load_references(topic, enable_search)
        user_prompt = self._build_general_turn_prompt(brief, messages, references)
        async for token in self._stream_or_chat(self._system_prompt(), user_prompt):
            yield token

    async def produce_turn_stream_stage(
        self,
        topic: str,
        brief: str,
        messages: List[DebateMessage],
        stage: DebateStage,
        intensity: str,
        enable_search: bool,
        selected_focus: FocusOption | None = None,
        user_context: str = "",
    ) -> AsyncGenerator[str, None]:
        references = await self._load_references(topic, enable_search)
        self.rolling_summary = self.context_manager.refresh_rolling_summary(
            messages,
            language=self.debate_language,
        )
        system_prompt = self._system_prompt_stage(stage, intensity, selected_focus, user_context)
        ctx = self.context_manager.build(
            current_speaker=self.config.name,
            system_prompt=system_prompt,
            brief=brief,
            rolling_summary=self.rolling_summary,
            messages=messages,
            turn_instruction=self._get_stage_instruction(stage, selected_focus, user_context),
            language=self.debate_language,
        )
        user_prompt = append_optional_references(
            ctx.to_prompt(),
            references,
            language=self.debate_language,
        )
        async for token in self._stream_or_chat(system_prompt, user_prompt):
            yield token

    def _general_turn_instruction(self) -> str:
        return build_general_turn_instruction(language=self.debate_language)

    def _system_prompt_stage(
        self,
        stage: DebateStage,
        intensity: str,
        selected_focus: FocusOption | None = None,
        user_context: str = "",
    ) -> str:
        return build_stage_system_prompt(
            config=self.config,
            stage=stage,
            intensity=intensity,
            selected_focus=selected_focus,
            user_context=user_context,
            language=self.debate_language,
        )

    def _get_stage_instruction(
        self,
        stage: DebateStage,
        selected_focus: FocusOption | None = None,
        user_context: str = "",
    ) -> str:
        return build_stage_turn_instruction(
            stage=stage,
            selected_focus=selected_focus,
            user_context=user_context,
            language=self.debate_language,
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

        system_prompt = build_follow_up_system_prompt(self.config, language=self.debate_language)
        user_prompt = build_follow_up_user_prompt(
            topic,
            own_positions,
            question,
            language=self.debate_language,
        )
        async for token in self._stream_or_chat(system_prompt, user_prompt):
            yield token

    async def _load_references(self, topic: str, enable_search: bool) -> List[SearchResult]:
        if not enable_search:
            return []
        try:
            return await self.search.search(f"{topic} {self.config.stance}", num_results=2)
        except Exception:
            return []

    def _build_general_turn_prompt(
        self,
        brief: str,
        messages: List[DebateMessage],
        references: List[SearchResult],
    ) -> str:
        self.rolling_summary = self.context_manager.refresh_rolling_summary(
            messages,
            language=self.debate_language,
        )
        ctx = self.context_manager.build(
            current_speaker=self.config.name,
            system_prompt=self._system_prompt(),
            brief=brief,
            rolling_summary=self.rolling_summary,
            messages=messages,
            turn_instruction=self._general_turn_instruction(),
            language=self.debate_language,
        )
        return append_optional_references(
            ctx.to_prompt(),
            references,
            language=self.debate_language,
        )

    async def _stream_or_chat(self, system_prompt: str, user_prompt: str) -> AsyncGenerator[str, None]:
        yielded = 0
        try:
            async for token in self.llm.chat_stream(system_prompt, user_prompt):
                yielded += 1
                yield token
            if yielded == 0:
                raise ValueError("Empty streamed response")
        except Exception as exc:
            logger.warning("Debater stream fallback to non-stream chat for %s: %s", self.config.name, exc)
            text = (await self.llm.chat(system_prompt, user_prompt)).strip()
            if not text:
                raise ValueError(f"Empty non-stream response for {self.config.name}") from exc
            for char in text:
                yield char
                await asyncio.sleep(0.005)

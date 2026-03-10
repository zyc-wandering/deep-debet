from __future__ import annotations

import asyncio
from datetime import timedelta
from time import monotonic
from typing import AsyncGenerator, List, Optional

from app.agents.context_manager import ContextManager
from app.agents.debater_agent import DebaterAgent
from app.agents.host_agent import HostAgent
from app.models import (
    DebaterConfig,
    DebateConfigureRequest,
    DebateMessage,
    DebateSession,
    DebateStage,
    DebateStartRequest,
    FocusOption,
    FollowUpMessage,
    SSEEvent,
    SessionState,
    utc_now,
)
from app.providers.base import LLMProvider, SearchProvider
from app.providers.image_generation import ImageGenerationService
from app.storage.report_writer import ReportWriter
from app.storage.session_store import SessionStore
from app.utils.formatting import chunk_text


class DebateOrchestrator:
    def __init__(
        self,
        llm: LLMProvider,
        search: SearchProvider,
        session_store: SessionStore,
        report_writer: ReportWriter,
        image_service: ImageGenerationService | None = None,
    ) -> None:
        self.llm = llm
        self.search = search
        self.session_store = session_store
        self.report_writer = report_writer
        self.image_service = image_service or ImageGenerationService()

    async def run(self, request: DebateStartRequest) -> AsyncGenerator[SSEEvent, None]:
        """Backward-compatible alias for the Phase 3 start flow."""
        async for event in self.start(request):
            yield event

    async def start(self, request: DebateStartRequest) -> AsyncGenerator[SSEEvent, None]:
        """Start a session and stop after host research plus focus selection."""
        host = HostAgent(self.llm, self.search)
        session = DebateSession(
            topic=request.topic,
            model_variant=request.model_variant,
            state=SessionState.running,
            debater_count=request.debater_count,
            time_limit_sec=request.time_limit_sec,
            max_turns=request.max_turns,
            enable_debater_search=request.enable_debater_search,
            fun_mode=request.fun_mode,
        )
        self.session_store.create(session)

        try:
            yield self._phase_event(
                session.session_id,
                "booting",
                "Topic received",
                "Initializing host workspace and debate session.",
            )
            yield self._phase_event(
                session.session_id,
                "researching",
                "Researching",
                "The host is gathering background, conflict lines, and validation signals.",
            )

            brief, references = await host.research_topic(request.topic)
            session.brief = brief
            session.research_references = references
            self.session_store.update(session)

            for chunk in chunk_text(brief, chunk_size=36):
                yield SSEEvent(event="host_research", data={"session_id": session.session_id, "chunk": chunk})
                await asyncio.sleep(0.015)

            focus_options = await host.extract_focus_options(request.topic, brief)
            session.focus_options = focus_options
            session.state = SessionState.configuring
            self.session_store.update(session)

            yield SSEEvent(
                event="focus_options_ready",
                data={
                    "session_id": session.session_id,
                    "focus_options": [option.model_dump() for option in focus_options],
                },
            )
            yield self._phase_event(
                session.session_id,
                "configuring",
                "Choose your focus",
                "Select the discussion angle you care about more, then continue into the debate.",
            )
        except Exception as exc:
            session.state = SessionState.error
            session.error = str(exc)
            self.session_store.update(session)
            yield self._error_event(session.session_id, "start", str(exc))

    async def configure(self, request: DebateConfigureRequest) -> AsyncGenerator[SSEEvent, None]:
        """Resume a researched session after the user submits focus, intensity, and context."""
        start_clock = monotonic()
        host = HostAgent(self.llm, self.search)
        session = self.session_store.get(request.session_id)
        if not session:
            yield self._error_event(request.session_id, "configure", "Session not found")
            return

        selected_focus = self._get_focus_option(session, request.pre_debate_config.selected_focus_id)
        if not selected_focus:
            yield self._error_event(request.session_id, "configure", "Selected focus option is invalid")
            return

        session.pre_debate_config = request.pre_debate_config
        session.state = SessionState.running
        session.error = None
        self.session_store.update(session)

        try:
            yield self._phase_event(
                session.session_id,
                "assembling",
                "Assembling debaters",
                "Generating personas, stances, and speaking styles for this configured run.",
            )
            debaters = await host.create_debaters(
                topic=session.topic,
                debater_count=session.debater_count,
                brief=session.brief,
                selected_focus=selected_focus,
                intensity=request.pre_debate_config.intensity,
                user_context=request.pre_debate_config.user_context,
            )
            session.debaters = debaters
            session.deadline_at = utc_now() + timedelta(seconds=session.time_limit_sec)
            self.session_store.update(session)

            avatar_tasks = [
                asyncio.create_task(self._generate_avatar_with_event(debater, session.session_id))
                for debater in debaters
            ]

            yield SSEEvent(
                event="debaters_ready",
                data={
                    "session_id": session.session_id,
                    "debaters": [debater.model_dump() for debater in debaters],
                    "topic": session.topic,
                    "time_limit_sec": session.time_limit_sec,
                    "max_turns": session.max_turns,
                    "deadline_at": session.deadline_at.isoformat() if session.deadline_at else None,
                },
            )

            yield self._phase_event(
                session.session_id,
                "generating_background",
                "Generating background",
                "Preparing debate imagery for the configured session.",
            )

            background_path = await self.image_service.generate_debate_background(
                session.topic,
                [debater.model_dump() for debater in debaters],
                session.session_id,
            )
            if background_path:
                yield SSEEvent(
                    event="background_ready",
                    data={"session_id": session.session_id, "background_path": background_path},
                )

            avatar_results = await asyncio.gather(*avatar_tasks, return_exceptions=True)
            avatars: dict[str, str] = {}
            for index, result in enumerate(avatar_results):
                if isinstance(result, str):
                    avatars[debaters[index].name] = result

            yield SSEEvent(
                event="avatars_ready",
                data={"session_id": session.session_id, "avatars": avatars},
            )

            debater_agents = self._build_debater_agents(debaters)
            selected_focus_name = selected_focus.name
            user_context = request.pre_debate_config.user_context
            intensity = request.pre_debate_config.intensity

            async for event in self._run_opening(
                session=session,
                debater_agents=debater_agents,
                topic=session.topic,
                brief=session.brief,
                intensity=intensity,
                selected_focus=selected_focus_name,
                user_context=user_context,
            ):
                yield event

            async for event in self._run_free_debate(
                session=session,
                debater_agents=debater_agents,
                topic=session.topic,
                brief=session.brief,
                enable_search=session.enable_debater_search,
                intensity=intensity,
                max_turns=session.max_turns,
                selected_focus=selected_focus_name,
                user_context=user_context,
            ):
                yield event

            async for event in self._run_closing(
                session=session,
                debater_agents=debater_agents,
                topic=session.topic,
                brief=session.brief,
                intensity=intensity,
                selected_focus=selected_focus_name,
                user_context=user_context,
            ):
                yield event

            async for event in self._run_summary(
                session=session,
                topic=session.topic,
                brief=session.brief,
                host=host,
                references=session.research_references,
                report_writer=self.report_writer,
            ):
                yield event

            yield self._phase_event(
                session.session_id,
                "generating_summary_image",
                "Generating summary image",
                "Rendering the final visual summary.",
            )
            summary_image_path = await self.image_service.generate_summary_image(
                session.topic,
                [debater.model_dump() for debater in debaters],
                session.session_id,
            )

            duration_sec = int(monotonic() - start_clock)
            session.state = SessionState.done if not session.stop_requested else SessionState.stopped
            self.session_store.update(session)

            yield SSEEvent(
                event="done",
                data={
                    "session_id": session.session_id,
                    "report_path": str(session.report_path) if session.report_path else "",
                    "summary_image_path": summary_image_path,
                    "total_turns": len(session.messages),
                    "duration_sec": duration_sec,
                },
            )
        except Exception as exc:
            session.state = SessionState.error
            session.error = str(exc)
            self.session_store.update(session)
            yield self._error_event(session.session_id, "configure", str(exc))

    async def _run_opening(
        self,
        session: DebateSession,
        debater_agents: List[DebaterAgent],
        topic: str,
        brief: str,
        intensity: str,
        selected_focus: str,
        user_context: str,
    ) -> AsyncGenerator[SSEEvent, None]:
        session.current_stage = DebateStage.opening
        self.session_store.update(session)

        yield self._phase_event(
            session.session_id,
            "opening",
            "Opening statements",
            "Each debater establishes a starting position and analysis frame.",
        )
        yield self._stage_change_event(session.session_id, "opening", "Opening statements")

        turn_id = 0
        for agent in debater_agents:
            if session.stop_requested or self._deadline_passed(session):
                break
            async for event in self._stream_debater_turn(
                session=session,
                agent=agent,
                topic=topic,
                brief=brief,
                turn_id=turn_id,
                stage=DebateStage.opening,
                intensity=intensity,
                selected_focus=selected_focus,
                user_context=user_context,
            ):
                yield event
            turn_id += 1

    async def _run_free_debate(
        self,
        session: DebateSession,
        debater_agents: List[DebaterAgent],
        topic: str,
        brief: str,
        enable_search: bool,
        intensity: str,
        max_turns: int,
        selected_focus: str,
        user_context: str,
    ) -> AsyncGenerator[SSEEvent, None]:
        session.current_stage = DebateStage.free_debate
        self.session_store.update(session)

        yield self._phase_event(
            session.session_id,
            "free_debate",
            "Free debate",
            "Debaters contest each other while keeping the selected focus in play.",
        )
        yield self._stage_change_event(session.session_id, "free_debate", "Free debate")

        turn_id = len([message for message in session.messages if message.stage == DebateStage.opening])
        free_debate_turn = 0

        while free_debate_turn < max_turns:
            if session.stop_requested or self._deadline_passed(session):
                break

            for agent in debater_agents:
                if session.stop_requested or self._deadline_passed(session) or free_debate_turn >= max_turns:
                    break

                citations = []
                if enable_search:
                    try:
                        citations = await self.search.search(f"{topic} {agent.config.stance}", num_results=2)
                    except Exception:
                        citations = []

                async for event in self._stream_debater_turn(
                    session=session,
                    agent=agent,
                    topic=topic,
                    brief=brief,
                    turn_id=turn_id,
                    stage=DebateStage.free_debate,
                    intensity=intensity,
                    citations=citations,
                    selected_focus=selected_focus,
                    user_context=user_context,
                ):
                    yield event

                turn_id += 1
                free_debate_turn += 1

    async def _run_closing(
        self,
        session: DebateSession,
        debater_agents: List[DebaterAgent],
        topic: str,
        brief: str,
        intensity: str,
        selected_focus: str,
        user_context: str,
    ) -> AsyncGenerator[SSEEvent, None]:
        session.current_stage = DebateStage.closing
        self.session_store.update(session)

        yield self._phase_event(
            session.session_id,
            "closing",
            "Closing statements",
            "Each debater answers the strongest opposing view and clarifies their final judgment.",
        )
        yield self._stage_change_event(session.session_id, "closing", "Closing statements")

        turn_id = len(session.messages)
        for agent in debater_agents:
            if session.stop_requested or self._deadline_passed(session):
                break
            async for event in self._stream_debater_turn(
                session=session,
                agent=agent,
                topic=topic,
                brief=brief,
                turn_id=turn_id,
                stage=DebateStage.closing,
                intensity=intensity,
                selected_focus=selected_focus,
                user_context=user_context,
            ):
                yield event
            turn_id += 1

    async def _run_summary(
        self,
        session: DebateSession,
        topic: str,
        brief: str,
        host: HostAgent,
        references: List,
        report_writer: ReportWriter,
    ) -> AsyncGenerator[SSEEvent, None]:
        session.current_stage = DebateStage.summary
        self.session_store.update(session)

        yield self._phase_event(
            session.session_id,
            "summarizing",
            "Summarizing",
            "The host is synthesizing disagreements, evidence, and final judgment.",
        )

        structured_report = await host.summarize_debate_structured(topic, brief, session.messages, references)
        session.structured_report = structured_report

        for chunk in chunk_text(structured_report.synthesis, chunk_size=44):
            yield SSEEvent(event="host_summary", data={"session_id": session.session_id, "chunk": chunk})
            await asyncio.sleep(0.01)

        report = await host.summarize_debate(topic, brief, session.messages, references)
        report_path = report_writer.write_markdown(topic, report)
        session.report_path = str(report_path.resolve())

        yield SSEEvent(
            event="structured_report",
            data={"session_id": session.session_id, "report": structured_report.model_dump()},
        )

        self.session_store.update(session)

    async def _stream_debater_turn(
        self,
        session: DebateSession,
        agent: DebaterAgent,
        topic: str,
        brief: str,
        turn_id: int,
        stage: DebateStage,
        intensity: str,
        citations: Optional[List] = None,
        selected_focus: str = "",
        user_context: str = "",
    ) -> AsyncGenerator[SSEEvent, None]:
        content_parts = []
        citations = citations or []

        async for token in agent.produce_turn_stream_stage(
            topic=topic,
            brief=brief,
            messages=session.messages,
            stage=stage,
            intensity=intensity,
            enable_search=False,
            selected_focus=selected_focus,
            user_context=user_context,
        ):
            content_parts.append(token)
            yield SSEEvent(
                event="debate_token",
                data={
                    "session_id": session.session_id,
                    "speaker": agent.config.name,
                    "turn_id": turn_id,
                    "token": token,
                    "stage": stage.value,
                },
            )

        content = "".join(content_parts)
        message = DebateMessage(
            speaker=agent.config.name,
            role="debater",
            content=content,
            turn_index=turn_id,
            citations=citations or [],
            stage=stage,
        )
        session.messages.append(message)
        session.stage_transcript.setdefault(stage, []).append(message)
        self.session_store.update(session)

        yield SSEEvent(
            event="debate_turn_end",
            data={
                "session_id": session.session_id,
                "speaker": agent.config.name,
                "turn_id": turn_id,
                "full_content": content,
                "citations": [citation.model_dump() for citation in citations] if citations else [],
                "stage": stage.value,
            },
        )

    async def follow_up(
        self,
        session_id: str,
        target_role: str,
        question: str,
    ) -> AsyncGenerator[SSEEvent, None]:
        session = self.session_store.get(session_id)
        if not session:
            yield SSEEvent(event="error", data={"session_id": session_id, "message": "Session not found"})
            return

        if session.state not in (SessionState.done, SessionState.stopped):
            yield SSEEvent(
                event="error",
                data={"session_id": session_id, "message": "Debate not yet complete"},
            )
            return

        follow_up = FollowUpMessage(target_role=target_role, question=question)
        session.follow_up_messages.append(follow_up)
        self.session_store.update(session)

        if target_role == "host":
            async for event in self._follow_up_host(session, follow_up):
                yield event
        else:
            debater_agent = None
            for debater in session.debaters:
                if debater.name == target_role:
                    debater_agent = DebaterAgent(
                        config=debater,
                        llm=self.llm,
                        search=self.search,
                        context_manager=ContextManager(),
                    )
                    break

            if debater_agent:
                async for event in self._follow_up_debater(session, debater_agent, follow_up):
                    yield event
            else:
                yield SSEEvent(
                    event="error",
                    data={"session_id": session_id, "message": f"Debater {target_role} not found"},
                )

        self.session_store.update(session)

    async def _follow_up_host(
        self,
        session: DebateSession,
        follow_up: FollowUpMessage,
    ) -> AsyncGenerator[SSEEvent, None]:
        host = HostAgent(self.llm, self.search)
        response_parts = []
        async for token in host.follow_up_stream(
            topic=session.topic,
            brief=session.brief,
            messages=session.messages,
            question=follow_up.question,
            structured_report=session.structured_report,
        ):
            response_parts.append(token)
            yield SSEEvent(
                event="follow_up_token",
                data={
                    "session_id": session.session_id,
                    "follow_up_id": follow_up.id,
                    "target_role": "host",
                    "token": token,
                },
            )

        follow_up.response = "".join(response_parts)
        yield SSEEvent(
            event="follow_up_end",
            data={
                "session_id": session.session_id,
                "follow_up_id": follow_up.id,
                "target_role": "host",
                "full_response": follow_up.response,
            },
        )

    async def _follow_up_debater(
        self,
        session: DebateSession,
        agent: DebaterAgent,
        follow_up: FollowUpMessage,
    ) -> AsyncGenerator[SSEEvent, None]:
        response_parts = []
        async for token in agent.follow_up_stream(
            topic=session.topic,
            brief=session.brief,
            messages=session.messages,
            question=follow_up.question,
        ):
            response_parts.append(token)
            yield SSEEvent(
                event="follow_up_token",
                data={
                    "session_id": session.session_id,
                    "follow_up_id": follow_up.id,
                    "target_role": agent.config.name,
                    "token": token,
                },
            )

        follow_up.response = "".join(response_parts)
        yield SSEEvent(
            event="follow_up_end",
            data={
                "session_id": session.session_id,
                "follow_up_id": follow_up.id,
                "target_role": agent.config.name,
                "full_response": follow_up.response,
            },
        )

    async def _generate_avatar_with_event(self, debater: DebaterConfig, session_id: str) -> str | None:
        try:
            return await self.image_service.generate_debater_avatar(debater.model_dump(), session_id)
        except Exception as exc:
            import logging

            logging.getLogger(__name__).warning("Failed to generate avatar for %s: %s", debater.name, exc)
            return None

    def _build_debater_agents(self, debaters: List[DebaterConfig]) -> List[DebaterAgent]:
        return [
            DebaterAgent(
                config=debater,
                llm=self.llm,
                search=self.search,
                context_manager=ContextManager(),
            )
            for debater in debaters
        ]

    def _deadline_passed(self, session: DebateSession) -> bool:
        return session.deadline_at is not None and utc_now() >= session.deadline_at

    def _get_focus_option(self, session: DebateSession, focus_id: str) -> Optional[FocusOption]:
        for option in session.focus_options:
            if option.id == focus_id:
                return option
        return None

    def _phase_event(self, session_id: str, phase: str, title: str, detail: str) -> SSEEvent:
        return SSEEvent(
            event="phase",
            data={"session_id": session_id, "phase": phase, "title": title, "detail": detail},
        )

    def _stage_change_event(self, session_id: str, stage: str, title: str) -> SSEEvent:
        return SSEEvent(
            event="stage_change",
            data={"session_id": session_id, "stage": stage, "title": title},
        )

    def _error_event(self, session_id: str, stage: str, message: str) -> SSEEvent:
        return SSEEvent(
            event="error",
            data={"session_id": session_id, "stage": stage, "message": message, "retrying": False},
        )

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
    DebateMessage,
    DebateSession,
    DebateStage,
    DebateStartRequest,
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
        """Run a complete debate with structured stages."""
        start_clock = monotonic()
        host = HostAgent(self.llm, self.search)
        session = DebateSession(
            topic=request.topic,
            model_variant=request.model_variant,
            deadline_at=utc_now(),
            max_turns=request.max_turns,
            pre_debate_config=request.pre_debate_config,
        )
        self.session_store.create(session)

        try:
            # Phase: Booting
            yield SSEEvent(
                event="phase",
                data={
                    "session_id": session.session_id,
                    "phase": "booting",
                    "title": "辩题已接收",
                    "detail": "正在初始化主持人工作区与本轮会话。",
                },
            )

            # Phase: Researching
            yield SSEEvent(
                event="phase",
                data={
                    "session_id": session.session_id,
                    "phase": "researching",
                    "title": "主持人正在调研",
                    "detail": "收集背景资料、争议焦点与可验证线索。",
                },
            )
            brief, references = await host.research_topic(request.topic)
            session.brief = brief
            self.session_store.update(session)

            for chunk in chunk_text(brief, chunk_size=36):
                yield SSEEvent(event="host_research", data={"session_id": session.session_id, "chunk": chunk})
                await asyncio.sleep(0.015)

            # Extract dimensions for pre-debate configuration
            dimensions = await host.extract_dimensions(request.topic, brief)
            yield SSEEvent(
                event="dimensions_extracted",
                data={
                    "session_id": session.session_id,
                    "dimensions": [d.model_dump() for d in dimensions],
                },
            )

            # If no pre-debate config provided, use default
            if not session.pre_debate_config:
                from app.models import PreDebateConfig
                session.pre_debate_config = PreDebateConfig(
                    dimensions=dimensions,
                    intensity="balanced",
                    user_context="",
                )
                self.session_store.update(session)

            # Phase: Assembling
            yield SSEEvent(
                event="phase",
                data={
                    "session_id": session.session_id,
                    "phase": "assembling",
                    "title": "正在配置辩手",
                    "detail": "根据主持人研究结果生成角色、立场与发言策略。",
                },
            )
            debaters = await host.create_debaters(request.topic, request.debater_count, brief)
            session.debaters = debaters
            session.deadline_at = utc_now() + timedelta(seconds=request.time_limit_sec)
            self.session_store.update(session)

            # Generate debater avatars in background
            avatar_tasks = []
            for debater in debaters:
                task = asyncio.create_task(
                    self._generate_avatar_with_event(debater, session.session_id)
                )
                avatar_tasks.append(task)

            yield SSEEvent(
                event="debaters_ready",
                data={
                    "session_id": session.session_id,
                    "debaters": [d.model_dump() for d in debaters],
                    "topic": request.topic,
                    "time_limit_sec": request.time_limit_sec,
                    "max_turns": request.max_turns,
                    "deadline_at": session.deadline_at.isoformat(),
                },
            )

            # Generate debate background
            yield SSEEvent(
                event="phase",
                data={
                    "session_id": session.session_id,
                    "phase": "generating_background",
                    "title": "正在生成辩论场景",
                    "detail": "AI正在绘制辩手头像与辩论舞台背景...",
                },
            )

            background_path = await self.image_service.generate_debate_background(
                request.topic, [d.model_dump() for d in debaters], session.session_id
            )

            if background_path:
                yield SSEEvent(
                    event="background_ready",
                    data={
                        "session_id": session.session_id,
                        "background_path": background_path,
                    },
                )

            # Wait for avatars to complete
            avatar_results = await asyncio.gather(*avatar_tasks, return_exceptions=True)
            debater_avatars = {}
            for i, result in enumerate(avatar_results):
                if isinstance(result, str):
                    debater_avatars[debaters[i].name] = result

            yield SSEEvent(
                event="avatars_ready",
                data={
                    "session_id": session.session_id,
                    "avatars": debater_avatars,
                },
            )

            # Build debater agents
            debater_agents = self._build_debater_agents(debaters)
            intensity = session.pre_debate_config.intensity if session.pre_debate_config else "balanced"

            # === STAGE 1: Opening Statements ===
            async for evt in self._run_opening(
                session, debater_agents, request.topic, brief, host, intensity
            ):
                yield evt

            # Check if stopped after opening
            if session.stop_requested:
                # Still try to do closing statements before summary
                pass  # Continue to closing

            # === STAGE 2: Free Debate ===
            free_debate_turns = 0
            async for evt in self._run_free_debate(
                session, debater_agents, request.topic, brief, request.enable_debater_search,
                intensity, max_turns=request.max_turns
            ):
                if evt.event == "debate_turn_end":
                    free_debate_turns += 1
                yield evt

            # === STAGE 3: Closing Statements ===
            async for evt in self._run_closing(
                session, debater_agents, request.topic, brief, host, intensity
            ):
                yield evt

            # === STAGE 4: Host Summary ===
            async for evt in self._run_summary(
                session, request.topic, brief, host, references, report_writer=self.report_writer
            ):
                yield evt

            # Generate summary image
            yield SSEEvent(
                event="phase",
                data={
                    "session_id": session.session_id,
                    "phase": "generating_summary_image",
                    "title": "正在生成总结海报",
                    "detail": "AI正在绘制辩论总结可视化海报...",
                },
            )

            summary_image_path = await self.image_service.generate_summary_image(
                request.topic,
                [d.model_dump() for d in debaters],
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
            yield SSEEvent(
                event="error",
                data={
                    "session_id": session.session_id,
                    "stage": "orchestrator",
                    "message": str(exc),
                    "retrying": False,
                },
            )

    async def _run_opening(
        self,
        session: DebateSession,
        debater_agents: List[DebaterAgent],
        topic: str,
        brief: str,
        host: HostAgent,
        intensity: str,
    ) -> AsyncGenerator[SSEEvent, None]:
        """Run opening statements stage."""
        session.current_stage = DebateStage.opening
        self.session_store.update(session)

        yield SSEEvent(
            event="phase",
            data={
                "session_id": session.session_id,
                "phase": "opening",
                "title": "开场陈述",
                "detail": "每位辩手阐述核心立场与论证框架。",
            },
        )
        yield SSEEvent(
            event="stage_change",
            data={
                "session_id": session.session_id,
                "stage": "opening",
                "title": "开场陈述",
            },
        )

        turn_id = 0
        for agent in debater_agents:
            if session.stop_requested or utc_now() >= session.deadline_at:
                break

            async for evt in self._stream_debater_turn(
                session, agent, topic, brief, turn_id, DebateStage.opening, intensity
            ):
                yield evt
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
    ) -> AsyncGenerator[SSEEvent, None]:
        """Run free debate stage."""
        session.current_stage = DebateStage.free_debate
        self.session_store.update(session)

        yield SSEEvent(
            event="phase",
            data={
                "session_id": session.session_id,
                "phase": "free_debate",
                "title": "自由辩论",
                "detail": "辩手们就核心分歧展开交锋。",
            },
        )
        yield SSEEvent(
            event="stage_change",
            data={
                "session_id": session.session_id,
                "stage": "free_debate",
                "title": "自由辩论",
            },
        )

        turn_id = len([m for m in session.messages if m.stage == DebateStage.opening])
        free_debate_turn = 0

        while free_debate_turn < max_turns:
            if session.stop_requested or utc_now() >= session.deadline_at:
                break

            for agent in debater_agents:
                if session.stop_requested or utc_now() >= session.deadline_at or free_debate_turn >= max_turns:
                    break

                # Get citations if search enabled
                citations = []
                if enable_search:
                    try:
                        citations = await self.search.search(f"{topic} {agent.config.stance}", num_results=2)
                    except Exception:
                        citations = []

                async for evt in self._stream_debater_turn(
                    session, agent, topic, brief, turn_id, DebateStage.free_debate, intensity, citations
                ):
                    yield evt

                turn_id += 1
                free_debate_turn += 1

    async def _run_closing(
        self,
        session: DebateSession,
        debater_agents: List[DebaterAgent],
        topic: str,
        brief: str,
        host: HostAgent,
        intensity: str,
    ) -> AsyncGenerator[SSEEvent, None]:
        """Run closing statements stage."""
        session.current_stage = DebateStage.closing
        self.session_store.update(session)

        yield SSEEvent(
            event="phase",
            data={
                "session_id": session.session_id,
                "phase": "closing",
                "title": "总结陈词",
                "detail": "每位辩手回应最强反对意见并总结立场。",
            },
        )
        yield SSEEvent(
            event="stage_change",
            data={
                "session_id": session.session_id,
                "stage": "closing",
                "title": "总结陈词",
            },
        )

        turn_id = len(session.messages)
        for agent in debater_agents:
            if session.stop_requested or utc_now() >= session.deadline_at:
                break

            async for evt in self._stream_debater_turn(
                session, agent, topic, brief, turn_id, DebateStage.closing, intensity
            ):
                yield evt
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
        """Run host summary stage."""
        session.current_stage = DebateStage.summary
        self.session_store.update(session)

        yield SSEEvent(
            event="phase",
            data={
                "session_id": session.session_id,
                "phase": "summarizing",
                "title": "主持人正在总结",
                "detail": "收束分歧、整理证据，并生成最终报告。",
            },
        )

        # Generate structured report
        structured_report = await host.summarize_debate_structured(
            topic, brief, session.messages, references
        )
        session.structured_report = structured_report

        # Stream summary chunks
        for chunk in chunk_text(structured_report.synthesis, chunk_size=44):
            yield SSEEvent(event="host_summary", data={"session_id": session.session_id, "chunk": chunk})
            await asyncio.sleep(0.01)

        # Generate markdown report
        report = await host.summarize_debate(topic, brief, session.messages, references)
        report_path = report_writer.write_markdown(topic, report)
        session.report_path = str(report_path.resolve())

        # Send structured report event
        yield SSEEvent(
            event="structured_report",
            data={
                "session_id": session.session_id,
                "report": structured_report.model_dump(),
            },
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
    ) -> AsyncGenerator[SSEEvent, None]:
        """Stream a single debater turn."""
        content_parts = []
        citations = citations or []

        # Stream tokens
        async for token in agent.produce_turn_stream_stage(
            topic=topic,
            brief=brief,
            messages=session.messages,
            stage=stage,
            intensity=intensity,
            enable_search=False,
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

        # Add to stage transcript
        if stage not in session.stage_transcript:
            session.stage_transcript[stage] = []
        session.stage_transcript[stage].append(message)

        self.session_store.update(session)

        yield SSEEvent(
            event="debate_turn_end",
            data={
                "session_id": session.session_id,
                "speaker": agent.config.name,
                "turn_id": turn_id,
                "full_content": content,
                "citations": [c.model_dump() for c in citations] if citations else [],
                "stage": stage.value,
            },
        )

    async def follow_up(
        self,
        session_id: str,
        target_role: str,
        question: str,
    ) -> AsyncGenerator[SSEEvent, None]:
        """Handle post-debate follow-up Q&A."""
        session = self.session_store.get(session_id)
        if not session:
            yield SSEEvent(
                event="error",
                data={"session_id": session_id, "message": "Session not found"},
            )
            return

        if session.state not in (SessionState.done, SessionState.stopped):
            yield SSEEvent(
                event="error",
                data={"session_id": session_id, "message": "Debate not yet complete"},
            )
            return

        # Create follow-up message
        follow_up = FollowUpMessage(
            target_role=target_role,
            question=question,
        )
        session.follow_up_messages.append(follow_up)
        self.session_store.update(session)

        # Generate response
        if target_role == "host":
            async for evt in self._follow_up_host(session, follow_up):
                yield evt
        else:
            # Find debater agent
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
                async for evt in self._follow_up_debater(session, debater_agent, follow_up):
                    yield evt
            else:
                yield SSEEvent(
                    event="error",
                    data={"session_id": session_id, "message": f"Debater {target_role} not found"},
                )

        # Mark follow-up as complete
        self.session_store.update(session)

    async def _follow_up_host(
        self,
        session: DebateSession,
        follow_up: FollowUpMessage,
    ) -> AsyncGenerator[SSEEvent, None]:
        """Generate host follow-up response."""
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
        """Generate debater follow-up response."""
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

    async def _generate_avatar_with_event(
        self, debater: DebaterConfig, session_id: str
    ) -> str | None:
        """Generate avatar for a debater and emit event."""
        try:
            avatar_path = await self.image_service.generate_debater_avatar(
                debater.model_dump(), session_id
            )
            return avatar_path
        except Exception as exc:
            import logging
            logging.getLogger(__name__).warning(f"Failed to generate avatar for {debater.name}: {exc}")
            return None

    def _build_debater_agents(self, debaters: List[DebaterConfig]) -> List[DebaterAgent]:
        return [
            DebaterAgent(
                config=cfg,
                llm=self.llm,
                search=self.search,
                context_manager=ContextManager(),
            )
            for cfg in debaters
        ]

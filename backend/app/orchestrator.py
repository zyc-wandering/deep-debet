from __future__ import annotations

import asyncio
from datetime import timedelta, timezone
from time import monotonic
from typing import AsyncGenerator, List, Optional

from app.agents.context_manager import ContextManager
from app.agents.debater_agent import DebaterAgent
from app.agents.host_agent import HostAgent
from app.config import create_debate_dir
from app.execution.turn_executor import DebaterTurnExecutor
from app.models import (
    DebaterConfig,
    DebateConfigureRequest,
    DebateConfirmRequest,
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
from app.stage import (
    ClosingStageExecutor,
    FreeDebateStageExecutor,
    OpeningStageExecutor,
    StageRegistry,
    SummaryStageExecutor,
)
from app.stage.base import StageContext
from app.storage.report_writer import ReportWriter
from app.storage.session_store import SessionStore
from app.utils.formatting import chunk_text, with_trace_metadata
from app.utils.logger import debate_logger


class DebateOrchestrator:
    """Refactored debate orchestrator using stage-based architecture.

    Responsibilities:
    - Lifecycle management (start, configure, stop)
    - SSE event generation
    - Coordination of stage execution via StageRegistry

    Previous monolithic stage logic has been extracted to:
    - OpeningStageExecutor
    - FreeDebateStageExecutor
    - ClosingStageExecutor
    - SummaryStageExecutor
    """

    def __init__(
        self,
        llm: LLMProvider,
        search: SearchProvider,
        session_store: SessionStore,
        report_writer: ReportWriter,
        image_service: ImageGenerationService | None = None,
        stage_registry: StageRegistry | None = None,
        turn_executor: DebaterTurnExecutor | None = None,
    ) -> None:
        self.llm = llm
        self.search = search
        self.session_store = session_store
        self.report_writer = report_writer
        self.image_service = image_service or ImageGenerationService()
        self.turn_executor = turn_executor or DebaterTurnExecutor()
        self.stage_registry = stage_registry or self._create_default_stage_registry()

    def _create_default_stage_registry(self) -> StageRegistry:
        """创建默认的阶段注册表"""
        registry = StageRegistry()
        registry.register(OpeningStageExecutor(self.turn_executor))
        registry.register(FreeDebateStageExecutor(turn_executor=self.turn_executor))
        registry.register(ClosingStageExecutor(self.turn_executor))
        # SummaryStageExecutor 需要特殊依赖，在 configure 中手动处理
        return registry

    async def run(self, request: DebateStartRequest) -> AsyncGenerator[SSEEvent, None]:
        """Backward-compatible alias for the Phase 3 start flow."""
        async for event in self.start(request):
            yield event

    async def start(
        self, request: DebateStartRequest
    ) -> AsyncGenerator[SSEEvent, None]:
        """Start a session and stop after host research plus focus selection."""
        start_time = monotonic()
        host = HostAgent(self.llm, self.search, debate_language=request.debate_language)

        # Create per-debate directory for all artifacts
        debate_dir = create_debate_dir(request.topic)

        session = DebateSession(
            topic=request.topic,
            model_variant=request.model_variant,
            debate_language=request.debate_language,
            state=SessionState.running,
            debater_count=request.debater_count,
            time_limit_sec=request.time_limit_sec,
            max_turns=request.max_turns,
            enable_debater_search=request.enable_debater_search,
            fun_mode=request.fun_mode,
            debate_dir=str(debate_dir),
        )
        self.session_store.create(session)

        # 初始化日志上下文
        with debate_logger.session_context(session.session_id, session.trace_id):
            debate_logger.session_created(
                session_id=session.session_id,
                topic=request.topic,
                config={
                    "model_variant": request.model_variant.value,
                    "debater_count": request.debater_count,
                    "time_limit_sec": request.time_limit_sec,
                    "max_turns": request.max_turns,
                    "enable_debater_search": request.enable_debater_search,
                    "fun_mode": request.fun_mode,
                    "language": request.debate_language.value,
                },
            )

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

                debate_logger.info(
                    "Starting topic research",
                    event_type="research_start",
                    topic=request.topic,
                )
                research_start = monotonic()
                brief = ""
                references: list = []
                with debate_logger.span_context("host:research"):
                    token_buf = ""
                    async for item in host.research_topic_stream(request.topic):
                        if isinstance(item, tuple):
                            # Final yield: (brief, references)
                            brief, references = item
                        else:
                            # Streaming token
                            token_buf += item
                            # Flush in small chunks for smooth rendering
                            while len(token_buf) >= 12:
                                chunk = token_buf[:12]
                                token_buf = token_buf[12:]
                                yield SSEEvent(
                                    event="host_research",
                                    data=with_trace_metadata(
                                        {"session_id": session.session_id, "chunk": chunk}
                                    ),
                                )
                    # Flush remaining buffer
                    if token_buf:
                        yield SSEEvent(
                            event="host_research",
                            data=with_trace_metadata(
                                {"session_id": session.session_id, "chunk": token_buf}
                            ),
                        )

                research_duration = monotonic() - research_start
                debate_logger.info(
                    "Topic research completed",
                    event_type="research_complete",
                    duration_sec=research_duration,
                    brief_length=len(brief),
                    reference_count=len(references),
                )
                session.brief = brief
                session.research_references = references
                self.session_store.update(session)

                debate_logger.info(
                    "Extracting focus options", event_type="focus_extraction_start"
                )
                focus_start = monotonic()
                with debate_logger.span_context("host:focus_options"):
                    focus_options = await host.extract_focus_options(
                        request.topic, brief
                    )
                debate_logger.info(
                    "Focus options extracted",
                    event_type="focus_extraction_complete",
                    duration_sec=monotonic() - focus_start,
                    option_count=len(focus_options),
                    options=[{"name": opt.name, "id": opt.id} for opt in focus_options],
                )
                session.focus_options = focus_options
                session.state = SessionState.configuring
                self.session_store.update(session)
                debate_logger.session_state_changed(
                    session.session_id,
                    old_state=SessionState.running.value,
                    new_state=SessionState.configuring.value,
                    reason="Research complete, waiting for focus selection",
                )

                yield SSEEvent(
                    event="focus_options_ready",
                    data=with_trace_metadata(
                        {
                            "session_id": session.session_id,
                            "focus_options": [
                                option.model_dump() for option in focus_options
                            ],
                        }
                    ),
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
                debate_logger.session_state_changed(
                    session.session_id,
                    old_state=SessionState.running.value,
                    new_state=SessionState.error.value,
                    reason=f"Error during start: {str(exc)}",
                )
                debate_logger.exception(
                    "Error in start phase",
                    event_type="phase_error",
                    phase="start",
                    duration_sec=monotonic() - start_time,
                )
                yield self._error_event(session.session_id, "start", str(exc))

    async def configure(
        self, request: DebateConfigureRequest
    ) -> AsyncGenerator[SSEEvent, None]:
        """Resume a researched session after the user submits focus, intensity, and context."""
        start_clock = monotonic()
        session = self.session_store.get(request.session_id)
        if not session:
            debate_logger.error(
                "Session not found in configure",
                event_type="session_not_found",
                session_id=request.session_id,
            )
            yield self._error_event(
                request.session_id, "configure", "Session not found"
            )
            return

        # 初始化日志上下文
        with debate_logger.session_context(session.session_id, session.trace_id):
            debate_logger.info(
                "Configure phase started",
                event_type="configure_start",
                session_id=session.session_id,
                selected_focus_id=request.pre_debate_config.selected_focus_id,
                intensity=request.pre_debate_config.intensity,
            )

            host = HostAgent(
                self.llm, self.search, debate_language=session.debate_language
            )

            selected_focus = self._get_focus_option(
                session, request.pre_debate_config.selected_focus_id
            )
            if not selected_focus:
                debate_logger.error(
                    "Invalid focus option selected",
                    event_type="invalid_focus",
                    selected_focus_id=request.pre_debate_config.selected_focus_id,
                    valid_ids=[opt.id for opt in session.focus_options],
                )
                yield self._error_event(
                    request.session_id, "configure", "Selected focus option is invalid"
                )
                return

            session.pre_debate_config = request.pre_debate_config
            session.state = SessionState.running
            session.error = None
            self.session_store.update(session)
            debate_logger.session_state_changed(
                session.session_id,
                old_state=SessionState.configuring.value,
                new_state=SessionState.running.value,
                reason="Focus selected, starting debate",
            )

            try:
                yield self._phase_event(
                    session.session_id,
                    "assembling",
                    "Assembling debaters",
                    "Generating personas, stances, and speaking styles for this configured run.",
                )
                debate_logger.info(
                    "Creating debaters", event_type="create_debaters_start"
                )
                debater_start = monotonic()
                with debate_logger.span_context("host:create_debaters"):
                    debaters = await host.create_debaters(
                        topic=session.topic,
                        debater_count=session.debater_count,
                        brief=session.brief,
                        selected_focus=selected_focus,
                        intensity=request.pre_debate_config.intensity,
                        user_context=request.pre_debate_config.user_context,
                    )
                debate_logger.info(
                    "Debaters created",
                    event_type="create_debaters_complete",
                    duration_sec=monotonic() - debater_start,
                    debater_count=len(debaters),
                    debater_names=[d.name for d in debaters],
                )
                session.debaters = debaters
                self.session_store.update(session)

                main_count = len(debaters)

                # Generate substitute debaters concurrently with images
                debate_logger.info(
                    "Creating substitute debaters", event_type="create_subs_start"
                )
                sub_task = asyncio.create_task(
                    host.create_substitute_debaters(
                        topic=session.topic,
                        brief=session.brief,
                        existing_debaters=debaters,
                        selected_focus=selected_focus,
                        intensity=request.pre_debate_config.intensity,
                        substitute_count=3,
                    )
                )

                # Start avatar generation for main debaters
                avatar_tasks = [
                    asyncio.create_task(
                        self._generate_avatar_with_event(
                            debater, session.session_id, session.debate_dir
                        )
                    )
                    for debater in debaters
                ]

                # Wait for substitutes (needed for debaters_ready event)
                try:
                    substitutes = await sub_task
                    debate_logger.info(
                        "Substitute debaters created",
                        event_type="create_subs_complete",
                        substitute_count=len(substitutes),
                        sub_names=[s.name for s in substitutes],
                    )
                except Exception as exc:
                    debate_logger.warning(
                        f"Substitute debater generation failed: {exc}",
                        event_type="create_subs_failed",
                    )
                    substitutes = []

                # Store substitutes in session for later use in confirm()
                session.substitute_debaters = substitutes
                self.session_store.update(session)

                # Start avatar generation for substitutes too
                sub_avatar_tasks = [
                    asyncio.create_task(
                        self._generate_avatar_with_event(
                            sub, session.session_id, session.debate_dir
                        )
                    )
                    for sub in substitutes
                ]

                # Await all avatars (main + substitute) BEFORE emitting debaters_ready
                all_avatar_tasks = avatar_tasks + sub_avatar_tasks
                avatar_results = await asyncio.gather(
                    *all_avatar_tasks, return_exceptions=True
                )

                # Build avatars dict and update debater configs
                avatars: dict[str, str] = {}
                all_debaters = debaters + substitutes
                for index, result in enumerate(avatar_results):
                    if isinstance(result, str):
                        debater_name = all_debaters[index].name
                        avatars[debater_name] = result
                        # Update the debater's avatar_url so it appears in debaters_ready
                        all_debaters[index].avatar_url = result

                # Now emit debaters_ready with complete avatar URLs
                yield SSEEvent(
                    event="debaters_ready",
                    data=with_trace_metadata(
                        {
                            "session_id": session.session_id,
                            "debaters": [d.model_dump() for d in all_debaters],
                            "main_count": main_count,
                            "topic": session.topic,
                            "time_limit_sec": session.time_limit_sec,
                            "max_turns": session.max_turns,
                            "deadline_at": None,  # deadline set when debate actually starts in confirm()
                        }
                    ),
                )

                # Emit avatars_ready for backward compatibility (avatars already ready)
                yield SSEEvent(
                    event="avatars_ready",
                    data=with_trace_metadata(
                        {"session_id": session.session_id, "avatars": avatars}
                    ),
                )

                # Transition to drafting state — wait for user to confirm lineup
                old_state = session.state
                session.state = SessionState.drafting
                self.session_store.update(session)
                debate_logger.session_state_changed(
                    session.session_id,
                    old_state=old_state.value,
                    new_state=SessionState.drafting.value,
                    reason="Debaters ready, waiting for user to confirm lineup",
                )

                yield self._phase_event(
                    session.session_id,
                    "drafting",
                    "Confirm lineup",
                    "Review debaters and confirm lineup to start the debate.",
                )

            except Exception as exc:
                old_state = session.state
                session.state = SessionState.error
                session.error = str(exc)
                self.session_store.update(session)
                debate_logger.session_state_changed(
                    session.session_id,
                    old_state=old_state.value,
                    new_state=SessionState.error.value,
                    reason=f"Error during configure: {str(exc)}",
                )
                debate_logger.exception(
                    "Error in configure phase",
                    event_type="phase_error",
                    phase="configure",
                    duration_sec=monotonic() - start_clock,
                )
                yield self._error_event(session.session_id, "configure", str(exc))

    async def confirm(
        self, request: DebateConfirmRequest
    ) -> AsyncGenerator[SSEEvent, None]:
        """Start the debate after user confirms the debater lineup."""
        start_clock = monotonic()
        session = self.session_store.get(request.session_id)
        if not session:
            debate_logger.error(
                "Session not found in confirm",
                event_type="session_not_found",
                session_id=request.session_id,
            )
            yield self._error_event(request.session_id, "confirm", "Session not found")
            return

        with debate_logger.session_context(session.session_id, session.trace_id):
            if session.state != SessionState.drafting:
                debate_logger.error(
                    "Session not in drafting state",
                    event_type="invalid_state",
                    session_id=session.session_id,
                    current_state=session.state.value,
                )
                yield self._error_event(
                    session.session_id,
                    "confirm",
                    f"Session not in drafting state (current: {session.state.value})",
                )
                return

            # Apply user's debater selection if provided
            if request.debater_ids:
                all_debaters = session.debaters + session.substitute_debaters
                debater_map = {d.id: d for d in all_debaters}
                new_lineup = [
                    debater_map[did]
                    for did in request.debater_ids
                    if did in debater_map
                ]
                if new_lineup:
                    session.debaters = new_lineup
                    debate_logger.info(
                        "Debater lineup updated by user",
                        event_type="lineup_updated",
                        debater_names=[d.name for d in new_lineup],
                    )

            # Set deadline now that debate is actually starting
            session.deadline_at = utc_now() + timedelta(seconds=session.time_limit_sec)
            session.state = SessionState.running
            session.error = None
            self.session_store.update(session)
            debate_logger.session_state_changed(
                session.session_id,
                old_state=SessionState.drafting.value,
                new_state=SessionState.running.value,
                reason="User confirmed lineup, starting debate",
            )

            selected_focus = (
                self._get_focus_option(
                    session, session.pre_debate_config.selected_focus_id
                )
                if session.pre_debate_config
                else None
            )

            try:
                debater_agents = self._build_debater_agents(
                    session.debaters,
                    debate_language=session.debate_language,
                )
                user_context = (
                    session.pre_debate_config.user_context
                    if session.pre_debate_config
                    else ""
                )
                intensity = (
                    session.pre_debate_config.intensity
                    if session.pre_debate_config
                    else "balanced"
                )

                # Execute debate stages using the stage pipeline
                debate_logger.info(
                    "Starting debate stages",
                    event_type="debate_stages_start",
                    stages=["opening", "free_debate", "closing", "summarizing"],
                )
                async for event in self._execute_debate_stages(
                    session=session,
                    debater_agents=debater_agents,
                    topic=session.topic,
                    brief=session.brief,
                    intensity=intensity,
                    selected_focus=selected_focus,
                    user_context=user_context,
                    max_turns=session.max_turns,
                    enable_search=session.enable_debater_search,
                ):
                    yield event

                duration_sec = int(monotonic() - start_clock)
                final_state = (
                    SessionState.done
                    if not session.stop_requested
                    else SessionState.stopped
                )
                old_state = session.state
                session.state = final_state
                self.session_store.update(session)
                debate_logger.session_state_changed(
                    session.session_id,
                    old_state=old_state.value,
                    new_state=final_state.value,
                    reason="Debate completed"
                    if final_state == SessionState.done
                    else "Debate stopped",
                )
                debate_logger.report_generated(
                    session_id=session.session_id,
                    path=str(session.report_path) if session.report_path else "",
                    duration_sec=duration_sec,
                    total_turns=len(session.messages),
                )

                yield SSEEvent(
                    event="done",
                    data=with_trace_metadata(
                        {
                            "session_id": session.session_id,
                            "report_path": str(session.report_path)
                            if session.report_path
                            else "",
                            "total_turns": len(session.messages),
                            "duration_sec": duration_sec,
                            "trace_journal_path": session.trace_journal_path,
                        }
                    ),
                )
            except Exception as exc:
                old_state = session.state
                session.state = SessionState.error
                session.error = str(exc)
                self.session_store.update(session)
                debate_logger.session_state_changed(
                    session.session_id,
                    old_state=old_state.value,
                    new_state=SessionState.error.value,
                    reason=f"Error during confirm: {str(exc)}",
                )
                debate_logger.exception(
                    "Error in confirm phase",
                    event_type="phase_error",
                    phase="confirm",
                    duration_sec=monotonic() - start_clock,
                )
                yield self._error_event(session.session_id, "confirm", str(exc))

    async def _execute_debate_stages(
        self,
        session: DebateSession,
        debater_agents: List[DebaterAgent],
        topic: str,
        brief: str,
        intensity: str,
        selected_focus: FocusOption | None,
        user_context: str,
        max_turns: int,
        enable_search: bool,
    ) -> AsyncGenerator[SSEEvent, None]:
        """Execute debate stages using the stage pipeline."""
        stages_start = monotonic()
        debate_logger.info(
            "Executing debate stages",
            event_type="execute_stages_start",
            session_id=session.session_id,
            stages=["opening", "free_debate", "closing", "summarizing"],
            max_turns=max_turns,
        )

        # Create stage pipeline
        stage_pipeline = self.stage_registry.create_pipeline(
            [
                "opening",
                "free_debate",
                "closing",
            ]
        )

        # Update free debate stage with max_turns and search settings
        for stage in stage_pipeline:
            if isinstance(stage, FreeDebateStageExecutor):
                stage.max_turns = max_turns
                stage._enable_search = enable_search
                stage._search_provider = self.search

        turn_id = 0

        for stage_executor in stage_pipeline:
            if session.stop_requested or self._deadline_passed(session):
                debate_logger.info(
                    "Stage execution interrupted",
                    event_type="stages_interrupted",
                    session_id=session.session_id,
                    reason="stop_requested"
                    if session.stop_requested
                    else "deadline_passed",
                )
                break

            stage_start = monotonic()
            async for event in self._execute_stage(
                stage_executor=stage_executor,
                session=session,
                debater_agents=debater_agents,
                turn_id=turn_id,
                topic=topic,
                brief=brief,
                intensity=intensity,
                selected_focus=selected_focus,
                user_context=user_context,
            ):
                yield event

            debate_logger.info(
                f"Stage completed: {stage_executor.stage_type}",
                event_type="stage_pipeline_complete",
                session_id=session.session_id,
                stage=stage_executor.stage_type,
                duration_sec=monotonic() - stage_start,
                turn_count=len(session.messages) - turn_id,
            )
            turn_id = len(session.messages)

        # Always execute the summary stage so early stop / timeout still produces a report.
        debate_logger.info(
            "Starting summary stage",
            event_type="summary_stage_start",
            session_id=session.session_id,
            total_messages=len(session.messages),
        )
        summary_start = monotonic()
        summary_stage = SummaryStageExecutor(self.llm, self.search, self.report_writer)
        async for event in self._execute_stage(
            stage_executor=summary_stage,
            session=session,
            debater_agents=debater_agents,
            turn_id=turn_id,
            topic=topic,
            brief=brief,
            intensity=intensity,
            selected_focus=selected_focus,
            user_context=user_context,
        ):
            yield event
        debate_logger.info(
            "Summary stage completed",
            event_type="summary_stage_complete",
            session_id=session.session_id,
            duration_sec=monotonic() - summary_start,
        )

        debate_logger.info(
            "All debate stages completed",
            event_type="execute_stages_complete",
            session_id=session.session_id,
            total_duration_sec=monotonic() - stages_start,
            total_turns=len(session.messages),
        )

    async def _execute_stage(
        self,
        stage_executor,
        session: DebateSession,
        debater_agents: List[DebaterAgent],
        turn_id: int,
        topic: str,
        brief: str,
        intensity: str,
        selected_focus: FocusOption | None,
        user_context: str,
    ) -> AsyncGenerator[SSEEvent, None]:
        """Execute a single debate stage."""
        stage_start = monotonic()
        stage_type_str = (
            stage_executor.stage_type
            if hasattr(stage_executor, "stage_type")
            else "unknown"
        )

        with debate_logger.stage_context(stage_type_str):
            debate_logger.stage_start(
                stage=stage_type_str,
                turn_id=turn_id,
                extra={"stage_name": stage_executor.stage_name},
            )

            # Update session stage
            if hasattr(stage_executor, "stage_type"):
                stage_type = stage_executor.stage_type
                if stage_type == "opening":
                    session.current_stage = DebateStage.opening
                elif stage_type == "free_debate":
                    session.current_stage = DebateStage.free_debate
                elif stage_type == "closing":
                    session.current_stage = DebateStage.closing
                elif stage_type == "summarizing":
                    session.current_stage = DebateStage.summary
                self.session_store.update(session)

            # Yield phase and stage change events
            yield self._phase_event(
                session.session_id,
                stage_executor.stage_type,
                stage_executor.stage_name,
                stage_executor.stage_description,
            )
            yield self._stage_change_event(
                session.session_id,
                stage_executor.stage_type,
                stage_executor.stage_name,
            )

            # Create stage context
            ctx = StageContext(
                session=session,
                debater_agents=debater_agents,
                topic=topic,
                brief=brief,
                intensity=intensity,
                selected_focus=selected_focus,
                user_context=user_context,
                start_turn_id=turn_id,
            )

            # Execute the stage
            try:
                async for event in stage_executor.execute(ctx):
                    yield event
            except Exception as exc:
                debate_logger.exception(
                    f"Stage execution failed: {stage_type_str}",
                    event_type="stage_error",
                    stage=stage_type_str,
                    duration_sec=monotonic() - stage_start,
                )
                raise

            debate_logger.stage_end(
                stage=stage_type_str,
                duration_sec=monotonic() - stage_start,
                turn_count=len(session.messages) - turn_id,
            )

    async def follow_up(
        self,
        session_id: str,
        target_role: str,
        question: str,
    ) -> AsyncGenerator[SSEEvent, None]:
        """Post-debate follow-up Q&A with host or specific debater."""
        session = self.session_store.get(session_id)
        if not session:
            debate_logger.error(
                "Follow-up: Session not found",
                event_type="follow_up_error",
                session_id=session_id,
                error="Session not found",
            )
            yield SSEEvent(
                event="error",
                data=with_trace_metadata(
                    {"session_id": session_id, "message": "Session not found"}
                ),
            )
            return

        with debate_logger.session_context(session.session_id, session.trace_id):
            if session.state not in (SessionState.done, SessionState.stopped):
                debate_logger.warning(
                    "Follow-up: Debate not complete",
                    event_type="follow_up_error",
                    session_id=session_id,
                    error="Debate not yet complete",
                    current_state=session.state.value,
                )
                yield SSEEvent(
                    event="error",
                    data=with_trace_metadata(
                        {"session_id": session_id, "message": "Debate not yet complete"}
                    ),
                )
                return

            debate_logger.follow_up_request(session_id, target_role, question)
            follow_up = FollowUpMessage(target_role=target_role, question=question)
            session.follow_up_messages.append(follow_up)
            self.session_store.update(session)

            follow_up_start = monotonic()
            try:
                if target_role == "host":
                    with debate_logger.span_context("follow_up:host"):
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
                                debate_language=session.debate_language,
                            )
                            break

                    if debater_agent:
                        with debate_logger.span_context(f"follow_up:{target_role}"):
                            async for event in self._follow_up_debater(
                                session, debater_agent, follow_up
                            ):
                                yield event
                    else:
                        debate_logger.error(
                            "Follow-up: Debater not found",
                            event_type="follow_up_error",
                            session_id=session_id,
                            target_role=target_role,
                            error=f"Debater {target_role} not found",
                        )
                        yield SSEEvent(
                            event="error",
                            data=with_trace_metadata(
                                {
                                    "session_id": session_id,
                                    "message": f"Debater {target_role} not found",
                                }
                            ),
                        )

                debate_logger.info(
                    "Follow-up completed",
                    event_type="follow_up_complete",
                    session_id=session_id,
                    target_role=target_role,
                    duration_sec=monotonic() - follow_up_start,
                )
            except Exception as exc:
                debate_logger.exception(
                    "Follow-up failed",
                    event_type="follow_up_error",
                    session_id=session_id,
                    target_role=target_role,
                    duration_sec=monotonic() - follow_up_start,
                )
                raise

            self.session_store.update(session)

    async def _follow_up_host(
        self,
        session: DebateSession,
        follow_up: FollowUpMessage,
    ) -> AsyncGenerator[SSEEvent, None]:
        """Handle follow-up question for the host."""
        host = HostAgent(self.llm, self.search, debate_language=session.debate_language)
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
                data=with_trace_metadata(
                    {
                        "session_id": session.session_id,
                        "follow_up_id": follow_up.id,
                        "target_role": "host",
                        "token": token,
                    }
                ),
            )

        follow_up.response = "".join(response_parts)
        yield SSEEvent(
            event="follow_up_end",
            data=with_trace_metadata(
                {
                    "session_id": session.session_id,
                    "follow_up_id": follow_up.id,
                    "target_role": "host",
                    "full_response": follow_up.response,
                }
            ),
        )

    async def _follow_up_debater(
        self,
        session: DebateSession,
        agent: DebaterAgent,
        follow_up: FollowUpMessage,
    ) -> AsyncGenerator[SSEEvent, None]:
        """Handle follow-up question for a debater."""
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
                data=with_trace_metadata(
                    {
                        "session_id": session.session_id,
                        "follow_up_id": follow_up.id,
                        "target_role": agent.config.name,
                        "token": token,
                    }
                ),
            )

        follow_up.response = "".join(response_parts)
        yield SSEEvent(
            event="follow_up_end",
            data=with_trace_metadata(
                {
                    "session_id": session.session_id,
                    "follow_up_id": follow_up.id,
                    "target_role": agent.config.name,
                    "full_response": follow_up.response,
                }
            ),
        )

    async def _generate_avatar_with_event(
        self, debater: DebaterConfig, session_id: str, debate_dir: str | None = None
    ) -> str | None:
        """Generate avatar for a debater."""
        debate_logger.image_generation_request(
            "avatar",
            {"debater_name": debater.name, "session_id": session_id},
        )
        start = monotonic()
        try:
            path = await self.image_service.generate_debater_avatar(
                debater.model_dump(), session_id, debate_dir=debate_dir
            )
            debate_logger.image_generation_response(
                "avatar",
                duration_sec=monotonic() - start,
                success=True,
                path=path,
            )
            return path
        except Exception as exc:
            debate_logger.image_generation_response(
                "avatar",
                duration_sec=monotonic() - start,
                success=False,
                error=str(exc),
            )
            debate_logger.warning(
                "Failed to generate avatar",
                event_type="avatar_generation_failed",
                debater_name=debater.name,
                error=str(exc),
            )
            return None

    def _build_debater_agents(
        self,
        debaters: List[DebaterConfig],
        debate_language,
    ) -> List[DebaterAgent]:
        """Build DebaterAgent instances from configurations."""
        return [
            DebaterAgent(
                config=debater,
                llm=self.llm,
                search=self.search,
                context_manager=ContextManager(),
                debate_language=debate_language,
            )
            for debater in debaters
        ]

    def _deadline_passed(self, session: DebateSession) -> bool:
        """Check if the debate deadline has passed."""
        return session.deadline_at is not None and utc_now() >= session.deadline_at

    def _get_focus_option(
        self, session: DebateSession, focus_id: str
    ) -> Optional[FocusOption]:
        """Get a focus option by ID from the session."""
        for option in session.focus_options:
            if option.id == focus_id:
                return option
        return None

    def _phase_event(
        self, session_id: str, phase: str, title: str, detail: str
    ) -> SSEEvent:
        """Create a phase event."""
        return SSEEvent(
            event="phase",
            data=with_trace_metadata(
                {
                    "session_id": session_id,
                    "phase": phase,
                    "title": title,
                    "detail": detail,
                }
            ),
        )

    def _stage_change_event(self, session_id: str, stage: str, title: str) -> SSEEvent:
        """Create a stage change event."""
        return SSEEvent(
            event="stage_change",
            data=with_trace_metadata(
                {"session_id": session_id, "stage": stage, "title": title}
            ),
        )

    def _error_event(self, session_id: str, stage: str, message: str) -> SSEEvent:
        """Create an error event."""
        return SSEEvent(
            event="error",
            data=with_trace_metadata(
                {
                    "session_id": session_id,
                    "stage": stage,
                    "message": message,
                    "retrying": False,
                }
            ),
        )

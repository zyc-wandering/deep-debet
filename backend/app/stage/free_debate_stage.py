from __future__ import annotations

from time import monotonic
from typing import AsyncGenerator, List

from app.execution.turn_executor import DebaterTurnExecutor
from app.models import DebateStage, SearchResult, SSEEvent
from app.providers.base import SearchProvider
from app.stage.base import DebateStageExecutor, StageContext
from app.utils.logger import debate_logger


class FreeDebateStageExecutor(DebateStageExecutor):
    """Multi-turn free debate where debaters directly contest each other."""

    def __init__(
        self,
        max_turns: int = 24,
        turn_executor: DebaterTurnExecutor | None = None,
        search_provider: SearchProvider | None = None,
        enable_search: bool = False,
    ) -> None:
        self.max_turns = max_turns
        self._turn_executor = turn_executor or DebaterTurnExecutor()
        self._search_provider = search_provider
        self._enable_search = enable_search

    @property
    def stage_type(self) -> str:
        return "free_debate"

    @property
    def stage_name(self) -> str:
        return "Free debate"

    @property
    def stage_description(self) -> str:
        return "Debaters contest each other while keeping the selected focus in play."

    async def execute(self, ctx: StageContext) -> AsyncGenerator[SSEEvent, None]:
        stage = DebateStage.free_debate
        turn_id = ctx.start_turn_id
        free_debate_turn = 0
        stage_start = monotonic()

        debate_logger.info(
            "Free debate stage started",
            event_type="free_debate_start",
            session_id=ctx.session.session_id,
            max_turns=self.max_turns,
            debater_count=len(ctx.debater_agents),
        )

        while free_debate_turn < self.max_turns:
            if ctx.session.stop_requested or self._deadline_passed(ctx):
                debate_logger.info(
                    "Free debate interrupted",
                    event_type="free_debate_interrupted",
                    session_id=ctx.session.session_id,
                    reason="stop_requested" if ctx.session.stop_requested else "deadline_passed",
                    completed_turns=free_debate_turn,
                )
                break

            for agent in ctx.debater_agents:
                if ctx.session.stop_requested or self._deadline_passed(ctx) or free_debate_turn >= self.max_turns:
                    break

                citations: List[SearchResult] = []
                if self._enable_search and self._search_provider:
                    query = f"{ctx.topic} {agent.config.stance}"
                    search_start = monotonic()
                    debate_logger.search_request(query, "tavily", 2)
                    try:
                        with debate_logger.span_context(f"search:{agent.config.name}:{turn_id}"):
                            citations = await self._search_provider.search(query, num_results=2)
                        debate_logger.search_response(
                            query=query,
                            provider="tavily",
                            duration_sec=monotonic() - search_start,
                            result_count=len(citations),
                            success=True,
                        )
                    except Exception as exc:
                        debate_logger.search_response(
                            query=query,
                            provider="tavily",
                            duration_sec=monotonic() - search_start,
                            result_count=0,
                            success=False,
                            error=str(exc),
                        )
                        citations = []

                try:
                    async for event in self._turn_executor.execute_turn(
                        agent=agent,
                        session=ctx.session,
                        topic=ctx.topic,
                        brief=ctx.brief,
                        turn_id=turn_id,
                        stage=stage,
                        intensity=ctx.intensity,
                        selected_focus=ctx.selected_focus,
                        user_context=ctx.user_context,
                        citations=citations,
                        emit_start_event=True,
                    ):
                        yield event
                except Exception:
                    debate_logger.exception(
                        f"Free debate turn failed for {agent.config.name}",
                        event_type="free_debate_turn_error",
                        session_id=ctx.session.session_id,
                        speaker=agent.config.name,
                        turn_id=turn_id,
                    )
                    raise

                turn_id += 1
                free_debate_turn += 1

                if free_debate_turn % 5 == 0:
                    debate_logger.heartbeat(
                        session_id=ctx.session.session_id,
                        stage="free_debate",
                        elapsed_sec=monotonic() - stage_start,
                    )

        debate_logger.info(
            "Free debate stage completed",
            event_type="free_debate_complete",
            session_id=ctx.session.session_id,
            duration_sec=monotonic() - stage_start,
            total_turns=free_debate_turn,
        )

    def should_advance(self, ctx: StageContext) -> bool:
        free_messages = ctx.session.stage_transcript.get(DebateStage.free_debate, [])
        return len(free_messages) >= self.max_turns

    def _deadline_passed(self, ctx: StageContext) -> bool:
        from app.models import utc_now

        return ctx.session.deadline_at is not None and utc_now() >= ctx.session.deadline_at

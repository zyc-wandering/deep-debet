from __future__ import annotations

from typing import AsyncGenerator, List

from app.models import DebateStage, DebateMessage, SSEEvent, SearchResult
from app.providers.base import SearchProvider
from app.stage.base import DebateStageExecutor, StageContext
from app.execution.turn_executor import DebaterTurnExecutor


class FreeDebateStageExecutor(DebateStageExecutor):
    """自由辩论阶段：多轮次交锋"""

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
        """执行自由辩论阶段"""
        stage = DebateStage.free_debate
        turn_id = ctx.start_turn_id
        free_debate_turn = 0

        while free_debate_turn < self.max_turns:
            if ctx.session.stop_requested or self._deadline_passed(ctx):
                break

            for agent in ctx.debater_agents:
                if ctx.session.stop_requested or self._deadline_passed(ctx) or free_debate_turn >= self.max_turns:
                    break

                citations: List[SearchResult] = []
                if self._enable_search and self._search_provider:
                    try:
                        citations = await self._search_provider.search(
                            f"{ctx.topic} {agent.config.stance}", num_results=2
                        )
                    except Exception:
                        citations = []

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
                ):
                    yield event

                turn_id += 1
                free_debate_turn += 1

    def should_advance(self, ctx: StageContext) -> bool:
        """自由辩论阶段达到最大回合数后结束"""
        free_messages = ctx.session.stage_transcript.get(DebateStage.free_debate, [])
        return len(free_messages) >= self.max_turns

    def _deadline_passed(self, ctx: StageContext) -> bool:
        from app.models import utc_now
        return ctx.session.deadline_at is not None and utc_now() >= ctx.session.deadline_at

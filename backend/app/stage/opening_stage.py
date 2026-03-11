from __future__ import annotations

from typing import AsyncGenerator

from app.models import DebateStage, DebateMessage, SSEEvent
from app.stage.base import DebateStageExecutor, StageContext
from app.execution.turn_executor import DebaterTurnExecutor


class OpeningStageExecutor(DebateStageExecutor):
    """开场陈述阶段：每个辩手依次进行开场陈述"""

    def __init__(self, turn_executor: DebaterTurnExecutor | None = None) -> None:
        self._turn_executor = turn_executor or DebaterTurnExecutor()

    @property
    def stage_type(self) -> str:
        return "opening"

    @property
    def stage_name(self) -> str:
        return "Opening statements"

    @property
    def stage_description(self) -> str:
        return "Each debater establishes a starting position and analysis frame."

    async def execute(self, ctx: StageContext) -> AsyncGenerator[SSEEvent, None]:
        """执行开场陈述阶段"""
        stage = DebateStage.opening
        turn_id = ctx.start_turn_id

        for agent in ctx.debater_agents:
            if ctx.session.stop_requested or self._deadline_passed(ctx):
                break

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
            ):
                yield event

            turn_id += 1

    def should_advance(self, ctx: StageContext) -> bool:
        """开场阶段：每个辩手发言一次后结束"""
        opening_messages = ctx.session.stage_transcript.get(DebateStage.opening, [])
        return len(opening_messages) >= len(ctx.debater_agents)

    def _deadline_passed(self, ctx: StageContext) -> bool:
        from app.models import utc_now
        return ctx.session.deadline_at is not None and utc_now() >= ctx.session.deadline_at

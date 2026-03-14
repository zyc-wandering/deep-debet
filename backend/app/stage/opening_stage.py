from __future__ import annotations

from time import monotonic
from typing import AsyncGenerator

from app.models import DebateMessage, DebateStage, SSEEvent
from app.stage.base import DebateStageExecutor, StageContext
from app.utils.formatting import with_trace_metadata
from app.utils.logger import debate_logger


class OpeningStageExecutor(DebateStageExecutor):
    """Opening statements are generated independently to avoid cross-contamination."""

    def __init__(self, turn_executor=None) -> None:
        self._unused_turn_executor = turn_executor

    @property
    def stage_type(self) -> str:
        return "opening"

    @property
    def stage_name(self) -> str:
        return "Opening statements"

    @property
    def stage_description(self) -> str:
        return "Each debater establishes a starting position and analysis frame independently."

    async def execute(self, ctx: StageContext) -> AsyncGenerator[SSEEvent, None]:
        stage_start = monotonic()
        stage = DebateStage.opening
        turn_id = ctx.start_turn_id

        debate_logger.info(
            "Opening stage started",
            event_type="opening_stage_start",
            session_id=ctx.session.session_id,
            debater_count=len(ctx.debater_agents),
        )

        opening_messages: list[DebateMessage] = []

        for agent in ctx.debater_agents:
            if ctx.session.stop_requested or self._deadline_passed(ctx):
                break

            base_messages = list(ctx.session.messages)
            content_parts: list[str] = []
            turn_started_at = monotonic()

            with debate_logger.span_context(f"turn:{stage.value}:{agent.config.name}:{turn_id}"):
                debate_logger.turn_start(
                    speaker=agent.config.name,
                    turn_id=turn_id,
                    stage=stage.value,
                    extra={"visibility": "isolated_opening"},
                )
                yield SSEEvent(
                    event="debate_turn_start",
                    data=with_trace_metadata(
                        {
                            "session_id": ctx.session.session_id,
                            "speaker": agent.config.name,
                            "turn_id": turn_id,
                            "stage": stage.value,
                        }
                    ),
                )

                async for token in agent.produce_turn_stream_stage(
                    topic=ctx.topic,
                    brief=ctx.brief,
                    messages=base_messages,
                    stage=stage,
                    intensity=ctx.intensity,
                    enable_search=False,
                    selected_focus=ctx.selected_focus,
                    user_context=ctx.user_context,
                ):
                    content_parts.append(token)
                    yield SSEEvent(
                        event="debate_token",
                        data=with_trace_metadata(
                            {
                                "session_id": ctx.session.session_id,
                                "speaker": agent.config.name,
                                "turn_id": turn_id,
                                "token": token,
                                "stage": stage.value,
                            }
                        ),
                    )

                content = "".join(content_parts)
                debate_logger.turn_end(
                    speaker=agent.config.name,
                    turn_id=turn_id,
                    duration_sec=monotonic() - turn_started_at,
                    token_count=len(content_parts),
                    content_length=len(content),
                    extra={"visibility": "isolated_opening"},
                )

            message = DebateMessage(
                speaker=agent.config.name,
                role="debater",
                content=content,
                turn_index=turn_id,
                citations=[],
                stage=stage,
            )
            opening_messages.append(message)

            yield SSEEvent(
                event="debate_turn_end",
                data=with_trace_metadata(
                    {
                        "session_id": ctx.session.session_id,
                        "speaker": agent.config.name,
                        "turn_id": turn_id,
                        "full_content": content,
                        "citations": [],
                        "stage": stage.value,
                    }
                ),
            )

            turn_id += 1

        ctx.session.messages.extend(opening_messages)
        ctx.session.stage_transcript.setdefault(stage, []).extend(opening_messages)

        debate_logger.info(
            "Opening stage completed",
            event_type="opening_stage_complete",
            session_id=ctx.session.session_id,
            duration_sec=monotonic() - stage_start,
            total_turns=len(opening_messages),
        )

    def should_advance(self, ctx: StageContext) -> bool:
        opening_messages = ctx.session.stage_transcript.get(DebateStage.opening, [])
        return len(opening_messages) >= len(ctx.debater_agents)

    def _deadline_passed(self, ctx: StageContext) -> bool:
        from app.models import utc_now

        return ctx.session.deadline_at is not None and utc_now() >= ctx.session.deadline_at

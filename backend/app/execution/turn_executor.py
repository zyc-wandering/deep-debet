from __future__ import annotations

from time import monotonic
from typing import AsyncGenerator, List, Optional

from app.agents.debater_agent import DebaterAgent
from app.models import (
    DebateMessage,
    DebateSession,
    DebateStage,
    FocusOption,
    SearchResult,
    SSEEvent,
)
from app.utils.formatting import with_trace_metadata
from app.utils.logger import debate_logger


class DebaterTurnExecutor:
    """Execute a full debater turn with consistent tracing and SSE events."""

    async def execute_turn(
        self,
        agent: DebaterAgent,
        session: DebateSession,
        topic: str,
        brief: str,
        turn_id: int,
        stage: DebateStage,
        intensity: str,
        selected_focus: FocusOption | None = None,
        user_context: str = "",
        citations: Optional[List[SearchResult]] = None,
        emit_start_event: bool = True,
    ) -> AsyncGenerator[SSEEvent, None]:
        turn_start = monotonic()
        content_parts: list[str] = []
        citations = citations or []

        with debate_logger.span_context(
            f"turn:{stage.value}:{agent.config.name}:{turn_id}"
        ):
            debate_logger.turn_start(
                speaker=agent.config.name,
                turn_id=turn_id,
                stage=stage.value,
                extra={"intensity": intensity},
            )

            if emit_start_event:
                yield SSEEvent(
                    event="debate_turn_start",
                    data=with_trace_metadata(
                        {
                            "session_id": session.session_id,
                            "speaker": agent.config.name,
                            "turn_id": turn_id,
                            "stage": stage.value,
                        }
                    ),
                )

            token_count = 0
            stop_check_counter = 0
            interrupted = False
            try:
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
                    # Cooperative cancellation: check stop_requested periodically
                    stop_check_counter += 1
                    if stop_check_counter % 20 == 0 and session.stop_requested:
                        debate_logger.info(
                            "Turn interrupted by stop request",
                            event_type="turn_interrupted",
                            speaker=agent.config.name,
                            turn_id=turn_id,
                            tokens_received=token_count,
                        )
                        interrupted = True
                        break

                    content_parts.append(token)
                    token_count += 1
                    if token_count % 50 == 0:
                        debate_logger.llm_stream_token(
                            agent=agent.config.name,
                            turn_id=turn_id,
                            token_index=token_count,
                            token=token,
                        )
                    yield SSEEvent(
                        event="debate_token",
                        data=with_trace_metadata(
                            {
                                "session_id": session.session_id,
                                "speaker": agent.config.name,
                                "turn_id": turn_id,
                                "token": token,
                                "stage": stage.value,
                            }
                        ),
                    )
            except Exception:
                debate_logger.exception(
                    f"Turn execution failed for {agent.config.name}",
                    event_type="turn_error",
                    speaker=agent.config.name,
                    turn_id=turn_id,
                    stage=stage.value,
                    duration_sec=monotonic() - turn_start,
                )
                raise
            content = "".join(content_parts)
            duration = monotonic() - turn_start
            debate_logger.turn_end(
                speaker=agent.config.name,
                turn_id=turn_id,
                duration_sec=duration,
                token_count=token_count,
                content_length=len(content),
                extra={"interrupted": interrupted} if interrupted else None,
            )

        # Skip saving message if turn was interrupted (partial content)
        if interrupted:
            return

        message = DebateMessage(
            speaker=agent.config.name,
            role="debater",
            content=content,
            turn_index=turn_id,
            citations=citations,
            stage=stage,
        )
        session.messages.append(message)
        session.stage_transcript.setdefault(stage, []).append(message)

        yield SSEEvent(
            event="debate_turn_end",
            data=with_trace_metadata(
                {
                    "session_id": session.session_id,
                    "speaker": agent.config.name,
                    "turn_id": turn_id,
                    "full_content": content,
                    "citations": [citation.model_dump() for citation in citations]
                    if citations
                    else [],
                    "stage": stage.value,
                }
            ),
        )

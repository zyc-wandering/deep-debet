from __future__ import annotations

from typing import AsyncGenerator, List, Optional

from app.agents.debater_agent import DebaterAgent
from app.models import DebateMessage, DebateSession, DebateStage, SearchResult, SSEEvent


class DebaterTurnExecutor:
    """辩手发言执行器 - 处理单个辩手的完整发言流程"""

    async def execute_turn(
        self,
        agent: DebaterAgent,
        session: DebateSession,
        topic: str,
        brief: str,
        turn_id: int,
        stage: DebateStage,
        intensity: str,
        selected_focus: str = "",
        user_context: str = "",
        citations: Optional[List[SearchResult]] = None,
    ) -> AsyncGenerator[SSEEvent, None]:
        """执行单个辩手的完整发言"""
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
            citations=citations,
            stage=stage,
        )
        session.messages.append(message)
        session.stage_transcript.setdefault(stage, []).append(message)

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

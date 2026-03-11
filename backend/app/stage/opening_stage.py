from __future__ import annotations

from typing import AsyncGenerator

from app.models import DebateStage, DebateMessage, SSEEvent
from app.stage.base import DebateStageExecutor, StageContext


class OpeningStageExecutor(DebateStageExecutor):
    """开场陈述阶段：每个辩手独立进行开场陈述，互不可见"""

    def __init__(self, turn_executor=None) -> None:
        # turn_executor 参数保留用于兼容性，但不再使用
        pass

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
        """执行开场陈述阶段

        关键设计：每个辩手的开场陈述是独立的，看不到其他辩手的开场陈述。
        这样可以避免后面的辩手攻击前面的辩手，保证公平性。
        所有开场陈述完成后，才一次性加入 session.messages。
        """
        stage = DebateStage.opening
        turn_id = ctx.start_turn_id

        # 收集所有开场陈述，最后一次性加入 session
        opening_messages: list[DebateMessage] = []

        for agent in ctx.debater_agents:
            if ctx.session.stop_requested or self._deadline_passed(ctx):
                break

            # 开场陈述阶段，每个辩手只能看到之前的辩论历史（如果有）
            # 看不到本轮其他辩手的开场陈述
            base_messages = list(ctx.session.messages)

            content_parts = []
            async for token in agent.produce_turn_stream_stage(
                topic=ctx.topic,
                brief=ctx.brief,
                messages=base_messages,  # 使用基础历史，不包含本轮开场陈述
                stage=stage,
                intensity=ctx.intensity,
                enable_search=False,
                selected_focus=ctx.selected_focus,
                user_context=ctx.user_context,
            ):
                content_parts.append(token)
                yield SSEEvent(
                    event="debate_token",
                    data={
                        "session_id": ctx.session.session_id,
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
                citations=[],
                stage=stage,
            )
            opening_messages.append(message)

            yield SSEEvent(
                event="debate_turn_end",
                data={
                    "session_id": ctx.session.session_id,
                    "speaker": agent.config.name,
                    "turn_id": turn_id,
                    "full_content": content,
                    "citations": [],
                    "stage": stage.value,
                },
            )

            turn_id += 1

        # 所有辩手完成开场陈述后，一次性加入 session
        ctx.session.messages.extend(opening_messages)
        ctx.session.stage_transcript.setdefault(stage, []).extend(opening_messages)

    def should_advance(self, ctx: StageContext) -> bool:
        """开场阶段：每个辩手发言一次后结束"""
        opening_messages = ctx.session.stage_transcript.get(DebateStage.opening, [])
        return len(opening_messages) >= len(ctx.debater_agents)

    def _deadline_passed(self, ctx: StageContext) -> bool:
        from app.models import utc_now
        return ctx.session.deadline_at is not None and utc_now() >= ctx.session.deadline_at

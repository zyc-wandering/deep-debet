from __future__ import annotations

import asyncio
from datetime import timedelta
from time import monotonic
from typing import AsyncGenerator, List

from app.agents.context_manager import ContextManager
from app.agents.debater_agent import DebaterAgent
from app.agents.host_agent import HostAgent
from app.models import (
    DebaterConfig,
    DebateMessage,
    DebateSession,
    DebateStartRequest,
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
        start_clock = monotonic()
        host = HostAgent(self.llm, self.search)
        session = DebateSession(
            topic=request.topic,
            deadline_at=utc_now(),
            max_turns=request.max_turns,
        )
        self.session_store.create(session)

        try:
            yield SSEEvent(
                event="phase",
                data={
                    "session_id": session.session_id,
                    "phase": "booting",
                    "title": "辩题已接收",
                    "detail": "正在初始化主持人工作区与本轮会话。",
                },
            )
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

            yield SSEEvent(
                event="phase",
                data={
                    "session_id": session.session_id,
                    "phase": "debating",
                    "title": "辩手已就位",
                    "detail": "倒计时开始，等待第一位辩手进入交锋。",
                },
            )

            debater_agents = self._build_debater_agents(debaters)
            turn_id = 0

            while True:
                if session.stop_requested:
                    break
                if utc_now() >= session.deadline_at:
                    break
                if turn_id >= session.max_turns:
                    break

                for agent in debater_agents:
                    if session.stop_requested or utc_now() >= session.deadline_at or turn_id >= session.max_turns:
                        break

                    # Stream tokens from LLM in real-time
                    content_parts = []
                    citations = []

                    # First get citations if search is enabled
                    if request.enable_debater_search:
                        try:
                            citations = await self.search.search(f"{request.topic} {agent.config.stance}", num_results=2)
                        except Exception:
                            citations = []

                    # Stream the content token by token
                    async for token in agent.produce_turn_stream(
                        topic=request.topic,
                        brief=session.brief,
                        messages=session.messages,
                        enable_search=False,  # Search already done above
                    ):
                        content_parts.append(token)
                        yield SSEEvent(
                            event="debate_token",
                            data={
                                "session_id": session.session_id,
                                "speaker": agent.config.name,
                                "turn_id": turn_id,
                                "token": token,
                            },
                        )

                    content = "".join(content_parts)
                    message = DebateMessage(
                        speaker=agent.config.name,
                        role="debater",
                        content=content,
                        turn_index=turn_id,
                        citations=citations,
                    )
                    session.messages.append(message)
                    self.session_store.update(session)

                    yield SSEEvent(
                        event="debate_turn_end",
                        data={
                            "session_id": session.session_id,
                            "speaker": agent.config.name,
                            "turn_id": turn_id,
                            "full_content": content,
                            "citations": [c.model_dump() for c in citations],
                        },
                    )
                    turn_id += 1

            yield SSEEvent(
                event="phase",
                data={
                    "session_id": session.session_id,
                    "phase": "summarizing",
                    "title": "主持人正在总结",
                    "detail": "收束分歧、整理证据，并生成最终报告。",
                },
            )
            report = await host.summarize_debate(request.topic, session.brief, session.messages, references)
            for chunk in chunk_text(report, chunk_size=44):
                yield SSEEvent(event="host_summary", data={"session_id": session.session_id, "chunk": chunk})
                await asyncio.sleep(0.01)

            report_path = self.report_writer.write_markdown(request.topic, report)

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
                    "report_path": str(report_path.resolve()),
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
            # Log but don't fail the debate if image generation fails
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

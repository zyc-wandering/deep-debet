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
    ) -> None:
        self.llm = llm
        self.search = search
        self.session_store = session_store
        self.report_writer = report_writer

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

                    content, citations = await agent.produce_turn(
                        topic=request.topic,
                        brief=session.brief,
                        messages=session.messages,
                        enable_search=request.enable_debater_search,
                    )
                    message = DebateMessage(
                        speaker=agent.config.name,
                        role="debater",
                        content=content,
                        turn_index=turn_id,
                        citations=citations,
                    )
                    session.messages.append(message)
                    self.session_store.update(session)

                    for token in chunk_text(content, chunk_size=20):
                        yield SSEEvent(
                            event="debate_token",
                            data={
                                "session_id": session.session_id,
                                "speaker": agent.config.name,
                                "turn_id": turn_id,
                                "token": token,
                            },
                        )
                        await asyncio.sleep(0.01)

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
            duration_sec = int(monotonic() - start_clock)
            session.state = SessionState.done if not session.stop_requested else SessionState.stopped
            self.session_store.update(session)

            yield SSEEvent(
                event="done",
                data={
                    "session_id": session.session_id,
                    "report_path": str(report_path.resolve()),
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

from datetime import timedelta

import pytest

from app.agents.context_manager import ContextManager
from app.agents.debater_agent import DebaterAgent
from app.models import DebaterConfig, DebateSession, DebateStage, utc_now
from app.orchestrator import DebateOrchestrator
from app.providers.base import LLMProvider, SearchProvider
from app.storage.report_writer import ReportWriter
from app.storage.session_store import SessionStore


class FakeLLM(LLMProvider):
    async def chat(self, system_prompt: str, user_prompt: str) -> str:
        return "stub"

    async def chat_stream(self, system_prompt: str, user_prompt: str):
        yield "closing"


class FakeSearch(SearchProvider):
    async def search(self, query: str, num_results: int = 5):
        return []


@pytest.mark.anyio
async def test_run_closing_emits_stage_change_without_model_init_error(tmp_path):
    session_store = SessionStore(sessions_dir=tmp_path / "sessions")
    report_writer = ReportWriter(reports_dir=tmp_path / "reports")
    orchestrator = DebateOrchestrator(
        llm=FakeLLM(),
        search=FakeSearch(),
        session_store=session_store,
        report_writer=report_writer,
    )

    session = DebateSession(
        topic="Test topic",
        deadline_at=utc_now() + timedelta(minutes=5),
        max_turns=4,
    )
    session_store.create(session)

    agents = [
        DebaterAgent(
            config=DebaterConfig(
                name="Alpha",
                background="Researcher",
                stance="Supports the motion",
                personality="Direct",
            ),
            llm=FakeLLM(),
            search=FakeSearch(),
            context_manager=ContextManager(),
        ),
        DebaterAgent(
            config=DebaterConfig(
                name="Beta",
                background="Operator",
                stance="Opposes the motion",
                personality="Analytical",
            ),
            llm=FakeLLM(),
            search=FakeSearch(),
            context_manager=ContextManager(),
        ),
    ]

    events = []
    async for event in orchestrator._run_closing(
        session=session,
        debater_agents=agents,
        topic=session.topic,
        brief="brief",
        host=None,
        intensity="balanced",
    ):
        events.append(event)

    assert session.current_stage == DebateStage.closing
    assert [event.event for event in events[:2]] == ["phase", "stage_change"]
    assert len([event for event in events if event.event == "debate_turn_end"]) == 2

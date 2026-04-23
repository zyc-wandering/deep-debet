import json
from datetime import timedelta
from pathlib import Path

import pytest

from app.agents.context_manager import ContextManager
from app.agents.debater_agent import DebaterAgent
from app.agents.host_agent import HostAgent
from app.execution.turn_executor import DebaterTurnExecutor
from app.models import (
    DebaterConfig,
    DebateLanguage,
    DebateConfigureRequest,
    DebateConfirmRequest,
    DebateSession,
    DebateStage,
    DebateStartRequest,
    FocusOption,
    PreDebateConfig,
    SessionState,
    StructuredReport,
    utc_now,
)
from app.orchestrator import DebateOrchestrator
from app.providers.base import LLMProvider, SearchProvider
from app.stage.closing_stage import ClosingStageExecutor
from app.stage.base import StageContext
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


class FakeImageService:
    def __init__(self):
        self.debater_avatar_calls = 0

    async def generate_debate_background(self, topic, debaters, session_id, debate_dir=None):
        return None

    async def generate_debater_avatar(self, debater, session_id, debate_dir=None):
        self.debater_avatar_calls += 1
        return None

    async def generate_summary_image(self, topic, debaters, session_id, debate_dir=None):
        return None


def make_orchestrator(tmp_path, monkeypatch=None):
    if monkeypatch:
        from app.config import settings
        debates_dir = tmp_path / "debates"
        debates_dir.mkdir(exist_ok=True)
        object.__setattr__(settings, "debates_dir", debates_dir)

        _counter = [0]
        def fake_create_debate_dir(topic: str):
            _counter[0] += 1
            d = debates_dir / f"test-debate-{_counter[0]}"
            d.mkdir(parents=True, exist_ok=True)
            (d / "images").mkdir(exist_ok=True)
            return d

        import app.orchestrator as orch_module
        monkeypatch.setattr(orch_module, "create_debate_dir", fake_create_debate_dir)

    return DebateOrchestrator(
        llm=FakeLLM(),
        search=FakeSearch(),
        session_store=SessionStore(),
        report_writer=ReportWriter(),
        image_service=FakeImageService(),
    )


@pytest.mark.anyio
async def test_closing_stage_emits_stage_change_without_model_init_error(tmp_path):
    """Test that ClosingStageExecutor correctly emits stage events."""
    debate_dir = tmp_path / "test-debate"
    debate_dir.mkdir()

    session = DebateSession(
        topic="Test topic",
        deadline_at=utc_now() + timedelta(minutes=5),
        max_turns=4,
        debate_dir=str(debate_dir),
    )
    store = SessionStore()
    store.create(session)

    turn_executor = DebaterTurnExecutor()
    closing_stage = ClosingStageExecutor(turn_executor)

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

    ctx = StageContext(
        session=session,
        debater_agents=agents,
        topic=session.topic,
        brief="brief",
        intensity="balanced",
        selected_focus=FocusOption(name="Execution risk", description="Reality of implementation and cost"),
        user_context="",
        start_turn_id=0,
    )

    events = []
    async for event in closing_stage.execute(ctx):
        events.append(event)
        if event.event == "debate_turn_end":
            store.update(session)

    assert len([e for e in events if e.event == "debate_turn_start"]) == 2
    assert len([e for e in events if e.event == "debate_token"]) > 0
    assert len([e for e in events if e.event == "debate_turn_end"]) == 2


@pytest.mark.anyio
async def test_start_stops_after_focus_options_ready_without_debaters(monkeypatch, tmp_path):
    orchestrator = make_orchestrator(tmp_path, monkeypatch)
    focus_options = [
        FocusOption(name="成长性", description="长期成长与积累"),
        FocusOption(name="执行风险", description="现实执行成本与风险"),
    ]

    async def fake_research(self, topic: str):
        return "brief", []

    async def fake_extract(self, topic: str, brief: str):
        return focus_options

    monkeypatch.setattr(HostAgent, "research_topic", fake_research)
    monkeypatch.setattr(HostAgent, "extract_focus_options", fake_extract)

    events = []
    async for event in orchestrator.start(
        DebateStartRequest(
            topic="Should I change jobs?",
            debater_count=4,
            time_limit_sec=360,
            max_turns=24,
            debate_language=DebateLanguage.en,
        )
    ):
        events.append(event)

    session_id = events[0].data["session_id"]
    session = orchestrator.session_store.get(session_id)

    assert session is not None
    assert session.state == "configuring"
    assert session.debate_language == DebateLanguage.en
    assert session.deadline_at is None
    assert session.debate_dir is not None
    assert [event.event for event in events] == ["phase", "phase", "host_research", "focus_options_ready", "phase"]
    assert all(event.event != "debaters_ready" for event in events)
    assert [option.name for option in session.focus_options] == ["成长性", "执行风险"]


@pytest.mark.anyio
async def test_configure_sets_deadline_persists_config_and_finishes_run(monkeypatch, tmp_path):
    orchestrator = make_orchestrator(tmp_path, monkeypatch)
    focus_options = [
        FocusOption(id="focus-growth", name="成长性", description="长期成长与积累"),
        FocusOption(id="focus-risk", name="执行风险", description="现实执行成本与风险"),
    ]
    create_debaters_calls = {}

    async def fake_research(self, topic: str):
        return "brief", []

    async def fake_extract(self, topic: str, brief: str):
        return focus_options

    async def fake_create_debaters(
        self,
        topic: str,
        debater_count: int,
        brief: str,
        selected_focus: FocusOption | None = None,
        intensity: str = "balanced",
        user_context: str = "",
    ):
        create_debaters_calls["selected_focus"] = selected_focus.name if selected_focus else ""
        create_debaters_calls["intensity"] = intensity
        create_debaters_calls["user_context"] = user_context
        return [
            DebaterConfig(
                name="Alpha",
                background="Researcher",
                stance=f"Prioritizes {selected_focus.name}",
                personality="Direct",
            ),
            DebaterConfig(
                name="Beta",
                background="Operator",
                stance="Opposes the motion",
                personality="Analytical",
            ),
        ]

    async def fake_structured_summary(self, topic: str, brief: str, messages, references):
        return StructuredReport(
            background_summary="background",
            synthesis="synthesis",
            host_conclusion="host conclusion",
        )

    async def fake_markdown_summary(self, topic: str, brief: str, messages, references):
        return "# report"

    monkeypatch.setattr(HostAgent, "research_topic", fake_research)
    monkeypatch.setattr(HostAgent, "extract_focus_options", fake_extract)
    monkeypatch.setattr(HostAgent, "create_debaters", fake_create_debaters)
    monkeypatch.setattr(HostAgent, "summarize_debate_structured", fake_structured_summary)
    monkeypatch.setattr(HostAgent, "summarize_debate", fake_markdown_summary)

    start_events = []
    async for event in orchestrator.start(DebateStartRequest(topic="Should I change jobs?")):
        start_events.append(event)

    session_id = start_events[0].data["session_id"]

    # Phase 1: configure — creates debaters and stops at drafting state
    configure_events = []
    async for event in orchestrator.configure(
        DebateConfigureRequest(
            session_id=session_id,
            pre_debate_config=PreDebateConfig(
                selected_focus_id="focus-growth",
                intensity="intense",
                user_context="I already have one offer in hand.",
            ),
        )
    ):
        configure_events.append(event)

    session = orchestrator.session_store.get(session_id)
    assert session is not None
    assert session.state == SessionState.drafting
    assert session.deadline_at is None  # deadline not set until confirm
    assert session.pre_debate_config is not None
    assert session.pre_debate_config.selected_focus_id == "focus-growth"
    assert create_debaters_calls == {
        "selected_focus": "成长性",
        "intensity": "intense",
        "user_context": "I already have one offer in hand.",
    }
    assert any(event.event == "debaters_ready" for event in configure_events)
    assert any(event.event == "avatars_ready" for event in configure_events)
    assert orchestrator.image_service.debater_avatar_calls == 0
    debaters_ready = next(event for event in configure_events if event.event == "debaters_ready")
    assert all(d["avatar_url"].startswith("avatar-library/") for d in debaters_ready.data["debaters"])
    # configure should NOT produce a "done" event — that's confirm's job
    assert all(event.event != "done" for event in configure_events)

    # Phase 2: confirm — user confirms lineup, debate runs to completion
    confirm_events = []
    async for event in orchestrator.confirm(
        DebateConfirmRequest(session_id=session_id)
    ):
        confirm_events.append(event)

    session = orchestrator.session_store.get(session_id)
    assert session.deadline_at is not None
    assert confirm_events[-1].event == "done"
    assert session.report_path is not None

    # Report should be in the debate directory
    debate_dir = Path(session.debate_dir)
    assert (debate_dir / "report.md").exists()

    # Session should be persisted in the debate directory
    persisted = json.loads((debate_dir / "session.json").read_text(encoding="utf-8"))
    assert persisted["pre_debate_config"]["selected_focus_id"] == "focus-growth"
    assert persisted["pre_debate_config"]["intensity"] == "intense"
    assert persisted["pre_debate_config"]["user_context"] == "I already have one offer in hand."


@pytest.mark.anyio
async def test_execute_debate_stages_still_runs_summary_after_stop_requested(monkeypatch, tmp_path):
    orchestrator = make_orchestrator(tmp_path, monkeypatch)

    debate_dir = tmp_path / "debates" / "test-stop-debate"
    debate_dir.mkdir(parents=True, exist_ok=True)

    session = DebateSession(
        topic="Should I change jobs?",
        max_turns=4,
        stop_requested=True,
        debate_dir=str(debate_dir),
    )

    async def fake_structured_summary(self, topic: str, brief: str, messages, references):
        return StructuredReport(
            background_summary="background",
            synthesis="synthesis",
            host_conclusion="host conclusion",
        )

    async def fake_markdown_summary(self, topic: str, brief: str, messages, references):
        return "# report"

    monkeypatch.setattr(HostAgent, "summarize_debate_structured", fake_structured_summary)
    monkeypatch.setattr(HostAgent, "summarize_debate", fake_markdown_summary)

    events = []
    async for event in orchestrator._execute_debate_stages(
        session=session,
        debater_agents=[],
        topic=session.topic,
        brief="brief",
        intensity="balanced",
        selected_focus=None,
        user_context="",
        max_turns=session.max_turns,
        enable_search=False,
    ):
        events.append(event)

    assert any(event.event == "host_summary" for event in events)
    assert any(event.event == "structured_report" for event in events)
    assert session.report_path is not None
    report_path = Path(session.report_path)
    assert report_path.exists()
    assert report_path.read_text(encoding="utf-8") == "# report"


# ============== Stage Extensibility Tests ==============

from typing import AsyncGenerator
from app.stage.base import DebateStageExecutor, StageContext
from app.models import SSEEvent


class CustomTestStage(DebateStageExecutor):
    """A custom stage implementation to demonstrate extensibility."""

    def __init__(self, message: str = "Custom stage executed") -> None:
        self.message = message
        self.executed = False

    @property
    def stage_type(self) -> str:
        return "custom_test"

    @property
    def stage_name(self) -> str:
        return "Custom Test Stage"

    @property
    def stage_description(self) -> str:
        return "A test stage to verify extensibility"

    async def execute(self, ctx: StageContext) -> AsyncGenerator[SSEEvent, None]:
        self.executed = True
        yield SSEEvent(
            event="custom_event",
            data={
                "session_id": ctx.session.session_id,
                "message": self.message,
                "debater_count": len(ctx.debater_agents),
            },
        )

    def should_advance(self, ctx: StageContext) -> bool:
        return True


@pytest.mark.anyio
async def test_stage_registry_extensibility():
    from app.stage.stage_registry import StageRegistry

    registry = StageRegistry()
    custom_stage = CustomTestStage("Test message")

    registry.register(custom_stage)

    assert "custom_test" in registry.list_stages()
    assert registry.get("custom_test") == custom_stage

    pipeline = registry.create_pipeline(["custom_test"])
    assert len(pipeline) == 1
    assert pipeline[0] == custom_stage


@pytest.mark.anyio
async def test_custom_stage_execution(tmp_path):
    debate_dir = tmp_path / "test-debate"
    debate_dir.mkdir()

    session = DebateSession(
        topic="Test extensibility",
        deadline_at=utc_now() + timedelta(minutes=5),
        max_turns=4,
        debate_dir=str(debate_dir),
    )
    store = SessionStore()
    store.create(session)

    custom_stage = CustomTestStage("Extensibility test")

    agents = [
        DebaterAgent(
            config=DebaterConfig(
                name="TestDebater",
                background="Tester",
                stance="Pro extensibility",
                personality="Enthusiastic",
            ),
            llm=FakeLLM(),
            search=FakeSearch(),
            context_manager=ContextManager(),
        ),
    ]

    ctx = StageContext(
        session=session,
        debater_agents=agents,
        topic=session.topic,
        brief="brief",
        intensity="balanced",
        selected_focus=FocusOption(name="Testing", description="Stage extensibility behavior"),
        user_context="",
        start_turn_id=0,
    )

    events = []
    async for event in custom_stage.execute(ctx):
        events.append(event)

    assert custom_stage.executed
    assert len(events) == 1
    assert events[0].event == "custom_event"
    assert events[0].data["message"] == "Extensibility test"
    assert events[0].data["debater_count"] == 1
    assert events[0].data["session_id"] == session.session_id


@pytest.mark.anyio
async def test_stage_registry_create_pipeline_with_missing_stages():
    from app.stage.stage_registry import StageRegistry

    registry = StageRegistry()
    custom_stage = CustomTestStage()
    registry.register(custom_stage)

    pipeline = registry.create_pipeline(["custom_test", "non_existent", "custom_test"])

    assert len(pipeline) == 2
    assert all(isinstance(stage, CustomTestStage) for stage in pipeline)

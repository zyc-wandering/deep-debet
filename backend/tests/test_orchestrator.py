import json
from datetime import timedelta

import pytest

from app.agents.context_manager import ContextManager
from app.agents.debater_agent import DebaterAgent
from app.agents.host_agent import HostAgent
from app.execution.turn_executor import DebaterTurnExecutor
from app.models import (
    DebaterConfig,
    DebateLanguage,
    DebateConfigureRequest,
    DebateSession,
    DebateStage,
    DebateStartRequest,
    FocusOption,
    PreDebateConfig,
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
    async def generate_debate_background(self, topic: str, debaters: list[dict], session_id: str):
        return None

    async def generate_debater_avatar(self, debater: dict, session_id: str):
        return None

    async def generate_summary_image(self, topic: str, debaters: list[dict], session_id: str):
        return None


def make_orchestrator(tmp_path):
    return DebateOrchestrator(
        llm=FakeLLM(),
        search=FakeSearch(),
        session_store=SessionStore(sessions_dir=tmp_path / "sessions"),
        report_writer=ReportWriter(reports_dir=tmp_path / "reports"),
        image_service=FakeImageService(),
    )


@pytest.mark.anyio
async def test_closing_stage_emits_stage_change_without_model_init_error(tmp_path):
    """Test that ClosingStageExecutor correctly emits stage events.

    This test verifies the new stage-based architecture where closing stage
    logic is encapsulated in ClosingStageExecutor rather than the orchestrator.
    """
    session = DebateSession(
        topic="Test topic",
        deadline_at=utc_now() + timedelta(minutes=5),
        max_turns=4,
    )
    store = SessionStore(sessions_dir=tmp_path / "sessions")
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
        # Update session from events (simulating what orchestrator does)
        if event.event == "debate_turn_end":
            store.update(session)

    # Verify that the stage executor produced the expected events
    assert len([e for e in events if e.event == "debate_token"]) > 0
    assert len([e for e in events if e.event == "debate_turn_end"]) == 2


@pytest.mark.anyio
async def test_start_stops_after_focus_options_ready_without_debaters(monkeypatch, tmp_path):
    orchestrator = make_orchestrator(tmp_path)
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
            debater_count=3,
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
    assert [event.event for event in events] == ["phase", "phase", "host_research", "focus_options_ready", "phase"]
    assert all(event.event != "debaters_ready" for event in events)
    assert [option.name for option in session.focus_options] == ["成长性", "执行风险"]


@pytest.mark.anyio
async def test_configure_sets_deadline_persists_config_and_finishes_run(monkeypatch, tmp_path):
    orchestrator = make_orchestrator(tmp_path)
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
    assert session.deadline_at is not None
    assert session.pre_debate_config is not None
    assert session.pre_debate_config.selected_focus_id == "focus-growth"
    assert create_debaters_calls == {
        "selected_focus": "成长性",
        "intensity": "intense",
        "user_context": "I already have one offer in hand.",
    }
    assert any(event.event == "debaters_ready" for event in configure_events)
    assert configure_events[-1].event == "done"

    persisted = json.loads((tmp_path / "sessions" / f"{session_id}.json").read_text(encoding="utf-8"))
    assert persisted["pre_debate_config"]["selected_focus_id"] == "focus-growth"
    assert persisted["pre_debate_config"]["intensity"] == "intense"
    assert persisted["pre_debate_config"]["user_context"] == "I already have one offer in hand."


# ============== Stage Extensibility Tests ==============

from typing import AsyncGenerator
from app.stage.base import DebateStageExecutor, StageContext
from app.models import SSEEvent


class CustomTestStage(DebateStageExecutor):
    """A custom stage implementation to demonstrate extensibility.

    This shows how new debate stages can be added by implementing
    the DebateStageExecutor interface.
    """

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
        """Execute the custom stage - emits a simple event."""
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
        """Always advance after custom stage."""
        return True


@pytest.mark.anyio
async def test_stage_registry_extensibility():
    """Test that new stages can be registered and executed."""
    from app.stage.stage_registry import StageRegistry

    registry = StageRegistry()
    custom_stage = CustomTestStage("Test message")

    # Register the custom stage
    registry.register(custom_stage)

    # Verify registration
    assert "custom_test" in registry.list_stages()
    assert registry.get("custom_test") == custom_stage

    # Create pipeline with custom stage
    pipeline = registry.create_pipeline(["custom_test"])
    assert len(pipeline) == 1
    assert pipeline[0] == custom_stage


@pytest.mark.anyio
async def test_custom_stage_execution(tmp_path):
    """Test that a custom stage can be executed within a debate context."""
    session = DebateSession(
        topic="Test extensibility",
        deadline_at=utc_now() + timedelta(minutes=5),
        max_turns=4,
    )
    store = SessionStore(sessions_dir=tmp_path / "sessions")
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

    # Verify custom stage executed correctly
    assert custom_stage.executed
    assert len(events) == 1
    assert events[0].event == "custom_event"
    assert events[0].data["message"] == "Extensibility test"
    assert events[0].data["debater_count"] == 1
    assert events[0].data["session_id"] == session.session_id


@pytest.mark.anyio
async def test_stage_registry_create_pipeline_with_missing_stages():
    """Test that pipeline creation gracefully handles missing stage types."""
    from app.stage.stage_registry import StageRegistry

    registry = StageRegistry()
    custom_stage = CustomTestStage()
    registry.register(custom_stage)

    # Request pipeline with both existing and non-existing stages
    pipeline = registry.create_pipeline(["custom_test", "non_existent", "custom_test"])

    # Only existing stages should be included
    assert len(pipeline) == 2
    assert all(isinstance(stage, CustomTestStage) for stage in pipeline)

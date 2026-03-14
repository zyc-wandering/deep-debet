import json

from fastapi.testclient import TestClient

from app.main import app
import app.main as main_module
from app.agents.host_agent import HostAgent
from app.models import DebateSession, FocusOption
from app.storage.session_store import SessionStore
from app.storage.trace_store import TraceStore


def _read_sse_events(response):
    event = None
    data_lines = []
    for raw_line in response.iter_lines():
        line = raw_line.decode("utf-8") if isinstance(raw_line, bytes) else raw_line
        if line == "":
            if event:
                yield event, json.loads("\n".join(data_lines)) if data_lines else {}
            event = None
            data_lines = []
            continue
        if line.startswith("event: "):
            event = line[7:]
        elif line.startswith("data: "):
            data_lines.append(line[6:])


def test_configure_returns_400_for_invalid_focus_option(tmp_path, monkeypatch):
    store = SessionStore(sessions_dir=tmp_path / "sessions")
    monkeypatch.setattr(main_module, "session_store", store)

    session = DebateSession(
        topic="Should I change jobs?",
        max_turns=24,
        focus_options=[
            FocusOption(id="focus-growth", name="成长性", description="长期成长与积累"),
            FocusOption(id="focus-risk", name="执行风险", description="现实执行成本与风险"),
        ],
    )
    store.create(session)

    client = TestClient(app)
    response = client.post(
        "/api/debate/configure",
        json={
            "session_id": session.session_id,
            "pre_debate_config": {
                "selected_focus_id": "invalid-focus",
                "intensity": "balanced",
                "user_context": "",
            },
        },
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Selected focus option is invalid"


def test_start_stream_includes_trace_metadata_and_journal(tmp_path, monkeypatch):
    store = SessionStore(sessions_dir=tmp_path / "sessions")
    traces = TraceStore(trace_dir=tmp_path / "traces")
    monkeypatch.setattr(main_module, "session_store", store)
    monkeypatch.setattr(main_module, "trace_store", traces)

    async def fake_research(self, topic: str):
        return "brief", []

    async def fake_extract(self, topic: str, brief: str):
        return [
            FocusOption(id="focus-1", name="Practicality", description="Implementation tradeoffs"),
            FocusOption(id="focus-2", name="Culture", description="Team habits and norms"),
        ]

    monkeypatch.setattr(HostAgent, "research_topic", fake_research)
    monkeypatch.setattr(HostAgent, "extract_focus_options", fake_extract)

    client = TestClient(app)
    with client.stream(
        "POST",
        "/api/debate/start",
        json={
            "topic": "Should remote teams default to async communication?",
            "debater_count": 2,
            "time_limit_sec": 120,
            "max_turns": 4,
            "debate_language": "en",
            "model_variant": "lite",
            "fun_mode": "persona_clash",
        },
    ) as response:
        assert response.status_code == 200
        events = list(_read_sse_events(response))

    phase_event = events[0][1]
    assert "_trace" in phase_event
    assert phase_event["_trace"]["trace_id"]
    assert phase_event["_trace"]["event_seq"] == 1
    assert phase_event["_trace"]["journal_path"]

    focus_event = next(data for event, data in events if event == "focus_options_ready")
    session = store.get(focus_event["session_id"])
    assert session is not None
    assert session.trace_journal_path == phase_event["_trace"]["journal_path"]

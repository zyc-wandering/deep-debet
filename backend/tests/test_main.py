from fastapi.testclient import TestClient

from app.main import app
import app.main as main_module
from app.models import DebateSession, FocusOption
from app.storage.session_store import SessionStore


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

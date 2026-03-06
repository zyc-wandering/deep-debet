import pytest

from app.models import DebateStartRequest


def test_start_request_defaults():
    req = DebateStartRequest(topic="AI should regulate AI?")
    assert req.debater_count == 3
    assert req.max_turns == 24
    assert req.enable_debater_search is False


def test_fun_mode_validation():
    ok = DebateStartRequest(topic="Will AI replace PMs?", fun_mode="persona_clash")
    assert ok.fun_mode == "persona_clash"


def test_invalid_fun_mode_raises():
    with pytest.raises(Exception):
        DebateStartRequest(topic="Will AI replace PMs?", fun_mode="anything")

from app.agents.context_manager import ContextManager
from app.models import DebateLanguage, DebateMessage


def test_context_window_limits_recent_messages():
    manager = ContextManager(recent_window_size=3)
    msgs = [
        DebateMessage(speaker=f"d{i}", role="debater", content=f"content-{i}", turn_index=i)
        for i in range(6)
    ]
    ctx = manager.build(
        current_speaker="d5",
        system_prompt="sys",
        brief="brief",
        rolling_summary="summary",
        messages=msgs,
        turn_instruction="say something",
    )
    assert len(ctx.recent_messages) == 3
    assert ctx.recent_messages[0].content == "content-3"


def test_rolling_summary_non_empty_when_exceed_window():
    manager = ContextManager(recent_window_size=2)
    msgs = [
        DebateMessage(speaker=f"d{i}", role="debater", content=f"content-{i}", turn_index=i)
        for i in range(5)
    ]
    summary = manager.refresh_rolling_summary(msgs)
    assert "较早轮次摘要" in summary


def test_rolling_summary_supports_english_language():
    manager = ContextManager(recent_window_size=2)
    msgs = [
        DebateMessage(speaker=f"d{i}", role="debater", content=f"content-{i}", turn_index=i)
        for i in range(5)
    ]

    summary = manager.refresh_rolling_summary(msgs, language=DebateLanguage.en)

    assert "Earlier rounds condensed by speaker" in summary


def test_context_window_keeps_latest_message_from_each_other_speaker():
    manager = ContextManager(recent_window_size=2, own_message_window_size=2)
    msgs = [
        DebateMessage(speaker="A", role="debater", content="A-0", turn_index=0),
        DebateMessage(speaker="B", role="debater", content="B-1", turn_index=1),
        DebateMessage(speaker="C", role="debater", content="C-2", turn_index=2),
        DebateMessage(speaker="A", role="debater", content="A-3", turn_index=3),
        DebateMessage(speaker="B", role="debater", content="B-4", turn_index=4),
    ]
    ctx = manager.build(
        current_speaker="A",
        system_prompt="sys",
        brief="brief",
        rolling_summary="summary",
        messages=msgs,
        turn_instruction="say something",
    )
    assert [msg.speaker for msg in ctx.latest_other_messages] == ["C", "B"]
    assert [msg.content for msg in ctx.own_recent_messages] == ["A-0", "A-3"]

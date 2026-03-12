from __future__ import annotations

from typing import Iterable, Mapping

from app.models import DebateMessage


def render_context_window(
    *,
    brief: str,
    rolling_summary: str,
    latest_other_messages: Iterable[DebateMessage],
    own_recent_messages: Iterable[DebateMessage],
    recent_messages: Iterable[DebateMessage],
    turn_instruction: str,
) -> str:
    lines = [
        "## Topic Brief",
        brief,
        "",
        "## Rolling Summary",
        rolling_summary or "No summary yet.",
        "",
        "## Latest Message From Each Other Debater",
    ]

    latest_other_messages = list(latest_other_messages)
    if not latest_other_messages:
        lines.append("No other debaters have spoken yet.")
    else:
        for msg in latest_other_messages:
            lines.append(f"- {msg.speaker}: {msg.content}")

    lines.extend(["", "## Your Own Recent Claims"])
    own_recent_messages = list(own_recent_messages)
    if not own_recent_messages:
        lines.append("You have not spoken yet.")
    else:
        for msg in own_recent_messages:
            lines.append(f"- Round {msg.turn_index + 1}: {msg.content}")

    lines.extend(["", "## Recent Messages"])
    recent_messages = list(recent_messages)
    if not recent_messages:
        lines.append("No messages yet.")
    else:
        for msg in recent_messages:
            lines.append(f"- Round {msg.turn_index + 1} | {msg.speaker}: {msg.content}")

    lines.extend(["", "## Turn Instruction", turn_instruction])
    return "\n".join(lines)


def render_rolling_summary(entries_by_speaker: Mapping[str, list[tuple[int, str]]]) -> str:
    lines = ["Earlier rounds condensed by speaker:"]
    for speaker, entries in entries_by_speaker.items():
        lines.append(f"- {speaker}:")
        for turn_index, excerpt in entries:
            lines.append(f"  Round {turn_index + 1}: {excerpt}")
    return "\n".join(lines)


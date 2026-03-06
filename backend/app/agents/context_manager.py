from __future__ import annotations

from dataclasses import dataclass
from textwrap import shorten
from typing import List

from app.models import DebateMessage


@dataclass
class ContextWindow:
    system_prompt: str
    brief: str
    rolling_summary: str
    latest_other_messages: List[DebateMessage]
    own_recent_messages: List[DebateMessage]
    recent_messages: List[DebateMessage]
    turn_instruction: str

    def to_prompt(self) -> str:
        lines = [
            "## Topic Brief",
            self.brief,
            "",
            "## Rolling Summary",
            self.rolling_summary or "No summary yet.",
            "",
            "## Latest Message From Each Other Debater",
        ]
        if not self.latest_other_messages:
            lines.append("No other debaters have spoken yet.")
        else:
            for msg in self.latest_other_messages:
                lines.append(f"- {msg.speaker}: {msg.content}")

        lines.extend(
            [
                "",
                "## Your Own Recent Claims",
            ]
        )
        if not self.own_recent_messages:
            lines.append("You have not spoken yet.")
        else:
            for msg in self.own_recent_messages:
                lines.append(f"- Round {msg.turn_index + 1}: {msg.content}")

        lines.extend(
            [
                "",
            "## Recent Messages",
            ]
        )
        if not self.recent_messages:
            lines.append("No messages yet.")
        else:
            for msg in self.recent_messages:
                lines.append(f"- Round {msg.turn_index + 1} | {msg.speaker}: {msg.content}")
        lines.extend(["", "## Turn Instruction", self.turn_instruction])
        return "\n".join(lines)


class ContextManager:
    def __init__(self, recent_window_size: int = 12, own_message_window_size: int = 2) -> None:
        self.recent_window_size = recent_window_size
        self.own_message_window_size = own_message_window_size

    def build(
        self,
        current_speaker: str,
        system_prompt: str,
        brief: str,
        rolling_summary: str,
        messages: List[DebateMessage],
        turn_instruction: str,
    ) -> ContextWindow:
        recent = messages[-self.recent_window_size :]
        latest_other_messages = self._latest_message_per_other_speaker(messages, current_speaker)
        own_recent_messages = [msg for msg in messages if msg.speaker == current_speaker][-self.own_message_window_size :]
        return ContextWindow(
            system_prompt=system_prompt,
            brief=brief,
            rolling_summary=rolling_summary,
            latest_other_messages=latest_other_messages,
            own_recent_messages=own_recent_messages,
            recent_messages=recent,
            turn_instruction=turn_instruction,
        )

    def refresh_rolling_summary(self, messages: List[DebateMessage]) -> str:
        if len(messages) <= self.recent_window_size:
            return ""

        old = messages[: -self.recent_window_size]
        by_speaker: dict[str, List[DebateMessage]] = {}
        for msg in old:
            by_speaker.setdefault(msg.speaker, []).append(msg)

        lines = ["Earlier rounds condensed by speaker:"]
        for speaker, speaker_messages in by_speaker.items():
            lines.append(f"- {speaker}:")
            for msg in speaker_messages[-2:]:
                excerpt = shorten(msg.content.replace("\n", " "), width=120, placeholder="...")
                lines.append(f"  Round {msg.turn_index + 1}: {excerpt}")
        return "\n".join(lines)

    def _latest_message_per_other_speaker(
        self,
        messages: List[DebateMessage],
        current_speaker: str,
    ) -> List[DebateMessage]:
        seen: set[str] = set()
        latest: List[DebateMessage] = []
        for msg in reversed(messages):
            if msg.speaker == current_speaker or msg.speaker in seen:
                continue
            latest.append(msg)
            seen.add(msg.speaker)
        latest.reverse()
        return latest

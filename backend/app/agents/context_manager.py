from __future__ import annotations

from dataclasses import dataclass
from textwrap import shorten
from typing import List

from app.models import DebateMessage
from app.prompts.context import render_context_window, render_rolling_summary


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
        return render_context_window(
            brief=self.brief,
            rolling_summary=self.rolling_summary,
            latest_other_messages=self.latest_other_messages,
            own_recent_messages=self.own_recent_messages,
            recent_messages=self.recent_messages,
            turn_instruction=self.turn_instruction,
        )


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

        entries_by_speaker: dict[str, list[tuple[int, str]]] = {}
        for speaker, speaker_messages in by_speaker.items():
            entries_by_speaker[speaker] = []
            for msg in speaker_messages[-2:]:
                excerpt = shorten(msg.content.replace("\n", " "), width=120, placeholder="...")
                entries_by_speaker[speaker].append((msg.turn_index, excerpt))
        return render_rolling_summary(entries_by_speaker)

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

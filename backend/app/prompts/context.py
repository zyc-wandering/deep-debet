from __future__ import annotations

from typing import Iterable, Mapping

from app.models import DebateLanguage, DebateMessage
from app.prompts.utils import normalize_prompt_language


def render_context_window(
    *,
    brief: str,
    rolling_summary: str,
    latest_other_messages: Iterable[DebateMessage],
    own_recent_messages: Iterable[DebateMessage],
    recent_messages: Iterable[DebateMessage],
    turn_instruction: str,
    language: DebateLanguage | str = DebateLanguage.zh,
) -> str:
    debate_language = normalize_prompt_language(language)
    if debate_language == DebateLanguage.en:
        labels = {
            "brief": "## Topic Brief",
            "summary": "## Rolling Summary",
            "others": "## Latest Message From Each Other Debater",
            "others_empty": "No other debaters have spoken yet.",
            "own": "## Your Own Recent Claims",
            "own_empty": "You have not spoken yet.",
            "recent": "## Recent Messages",
            "recent_empty": "No messages yet.",
            "instruction": "## Turn Instruction",
            "round": "Round",
            "summary_empty": "No summary yet.",
        }
    else:
        labels = {
            "brief": "## 话题简报",
            "summary": "## 滚动摘要",
            "others": "## 其他辩手最近一条发言",
            "others_empty": "其他辩手还没有发言。",
            "own": "## 你最近的主张",
            "own_empty": "你还没有发言。",
            "recent": "## 最近消息",
            "recent_empty": "暂时没有消息。",
            "instruction": "## 本轮指令",
            "round": "第",
            "summary_empty": "暂无摘要。",
        }

    lines = [
        labels["brief"],
        brief,
        "",
        labels["summary"],
        rolling_summary or labels["summary_empty"],
        "",
        labels["others"],
    ]

    latest_other_messages = list(latest_other_messages)
    if not latest_other_messages:
        lines.append(labels["others_empty"])
    else:
        for msg in latest_other_messages:
            lines.append(f"- {msg.speaker}: {msg.content}")

    lines.extend(["", labels["own"]])
    own_recent_messages = list(own_recent_messages)
    if not own_recent_messages:
        lines.append(labels["own_empty"])
    else:
        for msg in own_recent_messages:
            if debate_language == DebateLanguage.en:
                lines.append(f"- {labels['round']} {msg.turn_index + 1}: {msg.content}")
            else:
                lines.append(f"- {labels['round']}{msg.turn_index + 1}轮：{msg.content}")

    lines.extend(["", labels["recent"]])
    recent_messages = list(recent_messages)
    if not recent_messages:
        lines.append(labels["recent_empty"])
    else:
        for msg in recent_messages:
            if debate_language == DebateLanguage.en:
                lines.append(f"- {labels['round']} {msg.turn_index + 1} | {msg.speaker}: {msg.content}")
            else:
                lines.append(f"- {labels['round']}{msg.turn_index + 1}轮 | {msg.speaker}: {msg.content}")

    lines.extend(["", labels["instruction"], turn_instruction])
    return "\n".join(lines)


def render_rolling_summary(
    entries_by_speaker: Mapping[str, list[tuple[int, str]]],
    language: DebateLanguage | str = DebateLanguage.zh,
) -> str:
    debate_language = normalize_prompt_language(language)
    if debate_language == DebateLanguage.en:
        lines = ["Earlier rounds condensed by speaker:"]
    else:
        lines = ["较早轮次摘要（按发言人）："]
    for speaker, entries in entries_by_speaker.items():
        lines.append(f"- {speaker}:")
        for turn_index, excerpt in entries:
            if debate_language == DebateLanguage.en:
                lines.append(f"  Round {turn_index + 1}: {excerpt}")
            else:
                lines.append(f"  第{turn_index + 1}轮：{excerpt}")
    return "\n".join(lines)

from __future__ import annotations

from textwrap import dedent


def compact_prompt(text: str) -> str:
    return dedent(text).strip()


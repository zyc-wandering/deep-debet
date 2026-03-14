from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from app.models import DebateLanguage
from app.prompts.utils import compact_prompt, normalize_prompt_language

PROJECT_ROOT = Path(__file__).resolve().parents[3]
PROMPT_DOC_PATH = PROJECT_ROOT / "debate_room_prompts_v2.md"


@lru_cache(maxsize=1)
def _prompt_chunks() -> dict[int, str]:
    text = PROMPT_DOC_PATH.read_text(encoding="utf-8")
    chunks: dict[int, str] = {}
    for prompt_number in range(1, 15):
        start = text.index(f"## Prompt {prompt_number}:")
        if prompt_number < 14:
            end = text.index(f"## Prompt {prompt_number + 1}:")
        else:
            appendix_start = text.find("## 附录")
            end = appendix_start if appendix_start >= 0 else len(text)
        chunks[prompt_number] = text[start:end]
    return chunks


def get_prompt_section(prompt_number: int, language: DebateLanguage | str) -> str:
    chunk = _prompt_chunks()[prompt_number]
    debate_language = normalize_prompt_language(language)
    marker = "### 中文版本" if debate_language == DebateLanguage.zh else "### English Version"
    start = chunk.index(marker) + len(marker)
    return compact_prompt(chunk[start:])


def get_prompt_code_block(prompt_number: int, language: DebateLanguage | str) -> str:
    return _first_code_block(get_prompt_section(prompt_number, language))


def get_named_code_block(prompt_number: int, language: DebateLanguage | str, heading: str) -> str:
    section = get_prompt_section(prompt_number, language)
    start = section.index(heading)
    return _first_code_block(section[start:])


def _first_code_block(section: str) -> str:
    fence_start = section.index("```")
    content_start = fence_start + 3
    if section[content_start:content_start + 1].isalpha():
        newline = section.index("\n", content_start)
        content_start = newline + 1
    fence_end = section.index("```", content_start)
    return compact_prompt(section[content_start:fence_end])

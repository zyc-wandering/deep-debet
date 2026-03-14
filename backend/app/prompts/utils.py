from __future__ import annotations

from textwrap import dedent

from app.models import DebateLanguage


def compact_prompt(text: str) -> str:
    return dedent(text).strip()


def normalize_prompt_language(language: DebateLanguage | str) -> DebateLanguage:
    if isinstance(language, DebateLanguage):
        return language
    return DebateLanguage(language)


def apply_output_language_override(text: str, language: DebateLanguage | str) -> str:
    debate_language = normalize_prompt_language(language)
    if debate_language == DebateLanguage.en:
        override = """
        [LANGUAGE OVERRIDE]
        Ignore any conflicting language hints above.
        All natural-language output for this debate must be in English.
        Keep JSON keys, schema fields, and enum values unchanged.
        Where the template mentions Chinese-character limits, preserve the same relative brevity in concise English.
        """
    else:
        override = """
        [语言覆盖规则]
        如果上文存在冲突的语言提示，以本条为准。
        本场辩论的所有自然语言输出都必须使用中文。
        JSON 的字段名、schema 字段和枚举值保持不变。
        """
    return compact_prompt(f"{text}\n\n{override}")

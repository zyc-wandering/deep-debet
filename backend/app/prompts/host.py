from __future__ import annotations

from app.models import DebateLanguage, FocusOption
from app.prompts.catalog import get_prompt_code_block
from app.prompts.utils import apply_output_language_override, compact_prompt, normalize_prompt_language


def get_host_system_prompt(language: DebateLanguage | str = DebateLanguage.zh) -> str:
    return apply_output_language_override(get_prompt_code_block(1, language), language)


HOST_SYSTEM_PROMPT = get_host_system_prompt(DebateLanguage.zh)


def build_research_prompt(
    topic: str,
    citations_text: str,
    language: DebateLanguage | str = DebateLanguage.zh,
) -> str:
    template = get_prompt_code_block(2, language)
    prompt = (
        template.replace("{topic}", topic)
        .replace("{citations_text}", citations_text)
    )
    return apply_output_language_override(prompt, language)


def build_debater_generation_prompt(
    topic: str,
    debater_count: int,
    brief: str,
    intensity: str,
    selected_focus: FocusOption | None = None,
    user_context: str = "",
    language: DebateLanguage | str = DebateLanguage.zh,
) -> str:
    debate_language = normalize_prompt_language(language)
    template = get_prompt_code_block(4, debate_language)

    if debate_language == DebateLanguage.zh:
        focus_block = ""
        if selected_focus:
            focus_block = compact_prompt(
                f"""
                讨论焦点：{selected_focus.name} — {selected_focus.description}
                后续辩论将围绕此焦点展开，辩手的立场和论点应与此焦点高度相关。
                """
            )
        user_context_block = ""
        if user_context.strip():
            user_context_block = compact_prompt(
                f"""
                用户补充背景：{user_context.strip()}
                辩手设计时可参考此背景，但不得顺着用户预设答案造角色。
                """
            )
        prompt = (
            template.replace("{topic}", topic)
            .replace("{brief[:1500]}", brief[:1500])
            .replace("{debater_count}", str(debater_count))
            .replace("{intensity}", intensity)
            .replace("[可选焦点块]\n讨论焦点：{focus_name} — {focus_description}\n后续辩论将围绕此焦点展开，辩手的立场和论点应与此焦点高度相关。", focus_block)
            .replace("[可选用户上下文块]\n用户补充背景：{user_context}\n辩手设计时可参考此背景，但不得顺着用户预设答案造角色。", user_context_block)
        )
    else:
        focus_block = ""
        if selected_focus:
            focus_block = compact_prompt(
                f"""
                Discussion Focus: {selected_focus.name} — {selected_focus.description}
                The debate will center on this focus. Debaters' positions and arguments should be highly relevant to it.
                """
            )
        user_context_block = ""
        if user_context.strip():
            user_context_block = compact_prompt(
                f"""
                User-provided background: {user_context.strip()}
                May inform debater design, but do not create characters that simply confirm the user's presumed answer.
                """
            )
        prompt = (
            template.replace("{topic}", topic)
            .replace("{brief[:1500]}", brief[:1500])
            .replace("{debater_count}", str(debater_count))
            .replace("{intensity}", intensity)
            .replace("[OPTIONAL FOCUS BLOCK]\nDiscussion Focus: {focus_name} — {focus_description}\nThe debate will center on this focus. Debaters' positions and arguments should be highly relevant to it.", focus_block)
            .replace("[OPTIONAL USER CONTEXT BLOCK]\nUser-provided background: {user_context}\nMay inform debater design, but do not create characters that simply confirm the user's presumed answer.", user_context_block)
        )

    return apply_output_language_override(prompt, debate_language)


def build_focus_options_prompt(
    topic: str,
    brief: str,
    language: DebateLanguage | str = DebateLanguage.zh,
) -> str:
    template = get_prompt_code_block(3, language)
    prompt = template.replace("{topic}", topic).replace("{brief[:1500]}", brief[:1500])
    return apply_output_language_override(prompt, language)


def build_summary_prompt(
    topic: str,
    brief: str,
    transcript: str,
    language: DebateLanguage | str = DebateLanguage.zh,
) -> str:
    template = get_prompt_code_block(5, language)
    prompt = (
        template.replace("{topic}", topic)
        .replace("{brief}", brief)
        .replace("{transcript[:7000]}", transcript[:7000])
    )
    return apply_output_language_override(prompt, language)


def build_structured_summary_prompt(
    topic: str,
    brief: str,
    transcript: str,
    language: DebateLanguage | str = DebateLanguage.zh,
) -> str:
    template = get_prompt_code_block(6, language)
    prompt = (
        template.replace("{topic}", topic)
        .replace("{brief}", brief)
        .replace("{transcript[:7000]}", transcript[:7000])
    )
    return apply_output_language_override(prompt, language)


def build_follow_up_prompt(
    topic: str,
    brief: str,
    synthesis: str,
    transcript: str,
    question: str,
    language: DebateLanguage | str = DebateLanguage.zh,
) -> str:
    template = get_prompt_code_block(7, language)
    prompt = (
        template.replace("{topic}", topic)
        .replace("{brief[:800]}", brief[:800])
        .replace("{synthesis[:500]}", synthesis[:500])
        .replace("{transcript[:2000]}", transcript[:2000])
        .replace("{question}", question)
    )
    return apply_output_language_override(prompt, language)


def build_json_array_repair_prompt(
    schema_description: str,
    raw_output: str,
    language: DebateLanguage | str = DebateLanguage.zh,
) -> str:
    debate_language = normalize_prompt_language(language)
    if debate_language == DebateLanguage.en:
        prompt = f"""
        Your previous output did not satisfy the format requirements.
        Fix it into a valid JSON array.

        Requirements:
        {schema_description}

        Return only the JSON array. No explanation, no Markdown, no code fence.

        Original output:
        {raw_output}
        """
    else:
        prompt = f"""
        你上一轮的输出不符合要求。
        现在请只做一件事：把原输出修正为合法 JSON 数组。

        必须满足：
        {schema_description}

        只返回 JSON 数组，不要添加解释、Markdown、代码块。

        原输出：
        {raw_output}
        """
    return compact_prompt(prompt)


def build_json_object_repair_prompt(
    schema_description: str,
    raw_output: str,
    language: DebateLanguage | str = DebateLanguage.zh,
) -> str:
    debate_language = normalize_prompt_language(language)
    if debate_language == DebateLanguage.en:
        prompt = f"""
        Your previous output did not satisfy the format requirements.
        Fix it into a valid JSON object.

        Requirements:
        {schema_description}

        Return only the JSON object. No explanation, no Markdown, no code fence.

        Original output:
        {raw_output}
        """
    else:
        prompt = f"""
        你上一轮的输出不符合要求。
        现在请只做一件事：把原输出修正为合法 JSON 对象。

        必须满足：
        {schema_description}

        只返回 JSON 对象，不要添加解释、Markdown、代码块。

        原输出：
        {raw_output}
        """
    return compact_prompt(prompt)


def build_markdown_repair_prompt(
    requirements: str,
    raw_output: str,
    language: DebateLanguage | str = DebateLanguage.zh,
) -> str:
    debate_language = normalize_prompt_language(language)
    if debate_language == DebateLanguage.en:
        prompt = f"""
        Your previous output did not satisfy the format requirements.
        Preserve the original meaning, but rewrite it as Markdown that satisfies these hard requirements:

        {requirements}

        Return only the corrected Markdown. No explanation.

        Original output:
        {raw_output}
        """
    else:
        prompt = f"""
        你上一轮的输出未满足格式要求。
        请保留原意，但重写为满足以下硬性要求的 Markdown：

        {requirements}

        只返回修正后的 Markdown，不要解释。

        原输出：
        {raw_output}
        """
    return compact_prompt(prompt)

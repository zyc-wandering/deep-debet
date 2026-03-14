from __future__ import annotations

from app.models import DebaterConfig, DebateLanguage, DebateStage, FocusOption, SearchResult
from app.prompts.catalog import get_named_code_block, get_prompt_code_block
from app.prompts.utils import apply_output_language_override, compact_prompt, normalize_prompt_language


def _base_system_prompt_template(
    config: DebaterConfig,
    language: DebateLanguage | str,
) -> str:
    template = get_prompt_code_block(8, language)
    return (
        template.replace("{config.name}", config.name)
        .replace("{config.background}", config.background)
        .replace("{config.stance}", config.stance)
        .replace("{config.personality}", config.personality)
        .replace("{config.speaking_style}", config.speaking_style)
    )


def build_base_system_prompt(
    config: DebaterConfig,
    language: DebateLanguage | str = DebateLanguage.zh,
) -> str:
    prompt = _base_system_prompt_template(config, language)
    return apply_output_language_override(prompt, language)


def build_general_turn_instruction(
    language: DebateLanguage | str = DebateLanguage.zh,
) -> str:
    prompt = get_prompt_code_block(11, language)
    return apply_output_language_override(prompt, language)


def build_stage_system_prompt(
    config: DebaterConfig,
    stage: DebateStage,
    intensity: str,
    selected_focus: FocusOption | None = None,
    user_context: str = "",
    language: DebateLanguage | str = DebateLanguage.zh,
) -> str:
    debate_language = normalize_prompt_language(language)
    template = get_prompt_code_block(9, debate_language)
    base_prompt = _base_system_prompt_template(config, debate_language)
    stage_value = stage.value

    if debate_language == DebateLanguage.zh:
        focus_block = ""
        if selected_focus:
            focus_block = compact_prompt(
                f"""
                本场聚焦：{selected_focus.name} — {selected_focus.description}
                你的所有论证应紧扣此焦点展开。偏离焦点的论证，即使有道理，也会被判为降低得分。
                """
            )
        context_block = ""
        if user_context.strip():
            context_block = compact_prompt(
                f"""
                用户补充背景：{user_context.strip()}
                可以帮助你理解本场辩论的特殊情境。
                """
            )
        prompt = (
            template.replace("{base_system_prompt}", base_prompt)
            .replace("{stage}", stage_value)
            .replace("{intensity}", intensity)
            .replace("[可选焦点块]\n本场聚焦：{focus_name} — {focus_description}\n你的所有论证应紧扣此焦点展开。偏离焦点的论证，即使有道理，也会被判为降低得分。", focus_block)
            .replace("[可选用户上下文块]\n用户补充背景：{user_context}\n可以帮助你理解本场辩论的特殊情境。", context_block)
        )
    else:
        focus_block = ""
        if selected_focus:
            focus_block = compact_prompt(
                f"""
                This debate's focus: {selected_focus.name} — {selected_focus.description}
                All your arguments should tightly revolve around this focus. Arguments that deviate — even if valid — will be scored lower.
                """
            )
        context_block = ""
        if user_context.strip():
            context_block = compact_prompt(
                f"""
                User-provided background: {user_context.strip()}
                Can help you understand the specific context of this debate.
                """
            )
        prompt = (
            template.replace("{base_system_prompt}", base_prompt)
            .replace("{stage}", stage_value)
            .replace("{intensity}", intensity)
            .replace("[OPTIONAL FOCUS BLOCK]\nThis debate's focus: {focus_name} — {focus_description}\nAll your arguments should tightly revolve around this focus. Arguments that deviate — even if valid — will be scored lower.", focus_block)
            .replace("[OPTIONAL USER CONTEXT BLOCK]\nUser-provided background: {user_context}\nCan help you understand the specific context of this debate.", context_block)
        )

    return apply_output_language_override(prompt, debate_language)


def build_stage_turn_instruction(
    stage: DebateStage,
    selected_focus: FocusOption | None = None,
    user_context: str = "",
    language: DebateLanguage | str = DebateLanguage.zh,
) -> str:
    debate_language = normalize_prompt_language(language)
    if debate_language == DebateLanguage.zh:
        heading_map = {
            DebateStage.opening: "**开场陈词指令 (opening)**",
            DebateStage.free_debate: "**自由辩论指令 (free_debate)**",
            DebateStage.closing: "**总结陈词指令 (closing)**",
        }
    else:
        heading_map = {
            DebateStage.opening: "**Opening Statement Instruction (opening)**",
            DebateStage.free_debate: "**Free Debate Instruction (free_debate)**",
            DebateStage.closing: "**Closing Statement Instruction (closing)**",
        }
    prompt = get_named_code_block(10, debate_language, heading_map.get(stage, heading_map[DebateStage.free_debate]))

    if debate_language == DebateLanguage.zh:
        focus_instruction = ""
        if selected_focus:
            focus_instruction = f"请显式围绕讨论焦点“{selected_focus.name}”组织本轮发言。"
        context_instruction = ""
        if user_context.strip():
            context_instruction = f"请把以下场景背景纳入推理：{user_context.strip()}"
        prompt = (
            prompt.replace("[焦点指令]", focus_instruction)
            .replace("[场景指令]", context_instruction)
        )
    else:
        focus_instruction = ""
        if selected_focus:
            focus_instruction = f"Keep this turn explicitly centered on the selected focus: {selected_focus.name}."
        context_instruction = ""
        if user_context.strip():
            context_instruction = f"Incorporate this scenario background into your reasoning: {user_context.strip()}"
        prompt = (
            prompt.replace("[FOCUS INSTRUCTION]", focus_instruction)
            .replace("[CONTEXT INSTRUCTION]", context_instruction)
        )

    return apply_output_language_override(prompt, debate_language)


def build_follow_up_system_prompt(
    config: DebaterConfig,
    language: DebateLanguage | str = DebateLanguage.zh,
) -> str:
    template = get_prompt_code_block(12, language)
    prompt = (
        template.replace("{config.name}", config.name)
        .replace("{config.background}", config.background)
        .replace("{config.stance}", config.stance)
        .replace("{config.personality}", config.personality)
        .replace("{config.speaking_style}", config.speaking_style)
    )
    return apply_output_language_override(prompt, language)


def build_follow_up_user_prompt(
    topic: str,
    own_positions: str,
    question: str,
    language: DebateLanguage | str = DebateLanguage.zh,
) -> str:
    template = get_prompt_code_block(13, language)
    prompt = (
        template.replace("{topic}", topic)
        .replace("{own_positions}", own_positions)
        .replace("{question}", question)
    )
    return apply_output_language_override(prompt, language)


def append_optional_references(
    user_prompt: str,
    references: list[SearchResult],
    language: DebateLanguage | str = DebateLanguage.zh,
) -> str:
    if not references:
        return user_prompt

    refs_text = "\n".join(f"- {ref.title}: {ref.snippet[:120]}" for ref in references)
    debate_language = normalize_prompt_language(language)
    template = get_prompt_code_block(14, debate_language)
    if debate_language == DebateLanguage.zh:
        prompt = (
            template.replace("[原有提示词内容]", user_prompt)
            .replace("{ref.title}: {ref.snippet[:120]}\n（继续列出每条参考资料...）", refs_text)
        )
    else:
        prompt = (
            template.replace("[Original prompt content]", user_prompt)
            .replace("{ref.title}: {ref.snippet[:120]}\n(Continue listing each reference...)", refs_text)
        )
    return apply_output_language_override(prompt, debate_language)

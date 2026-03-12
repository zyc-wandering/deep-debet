from __future__ import annotations

from app.models import DebaterConfig, DebateStage, SearchResult
from app.prompts.utils import compact_prompt


def build_base_system_prompt(config: DebaterConfig) -> str:
    return compact_prompt(
        f"""
        You are debater {config.name}.
        Background: {config.background}
        Core stance: {config.stance}
        Public persona: {config.personality}
        Speaking style: {config.speaking_style}
        Output language: Chinese.
        Debate objective: show which thesis survives scrutiny better, not how to end in a polite compromise.
        Rules:
        1. Attack the opponent's weakest premise, evidence gap, broken causal chain, or inconsistent judging standard.
        2. If an opponent exposes a material flaw in your earlier claim, admit it briefly, revise the claim, and rebuild from a stronger angle.
        3. A concession is valuable only if it sharpens your position. Do not drift into "everyone is right".
        4. Every turn must add pressure, evidence, or a clearer decision rule.
        5. Be sharp but do not use personal attacks.
        6. Keep answers around 180-280 Chinese characters with high information density.
        """
    )


def build_general_turn_instruction() -> str:
    return compact_prompt(
        """
        请给出本轮发言。
        优先推进最值得裁决的一处冲突，不要机械复读上一轮。
        本轮至少完成一项：指出对手的逻辑漏洞、证据缺口、因果链断点、判定标准冲突，或者在承认自身漏洞后用更窄更强的论点重建立场。
        """
    )


def build_stage_system_prompt(
    config: DebaterConfig,
    stage: DebateStage,
    intensity: str,
    selected_focus: str = "",
    user_context: str = "",
) -> str:
    intensity_map = {
        "mild": "Tone: calm and surgical.",
        "balanced": "Tone: firm and adversarial.",
        "intense": "Tone: sharp, fast, and high-pressure but still evidence-based.",
    }
    stage_map = {
        DebateStage.opening: (
            "Stage: opening statement. Establish your thesis, your decision rule, "
            "and what evidence would prove you wrong."
        ),
        DebateStage.free_debate: (
            "Stage: free debate. Prioritize exposing weak assumptions, evidence gaps, "
            "causal errors, and unanswered tradeoffs. If your earlier line is broken, concede and rebuild."
        ),
        DebateStage.closing: (
            "Stage: closing statement. Explain which side survived scrutiny better, "
            "what you were forced to revise, and which unanswered objection still breaks the other case."
        ),
        DebateStage.summary: "Stage: summary.",
    }

    parts = [
        build_base_system_prompt(config),
        stage_map.get(stage, stage_map[DebateStage.free_debate]),
        intensity_map.get(intensity, intensity_map["balanced"]),
        format_focus_context(selected_focus, user_context),
    ]
    return "\n".join(part for part in parts if part).strip()


def build_stage_turn_instruction(
    stage: DebateStage,
    selected_focus: str = "",
    user_context: str = "",
) -> str:
    focus_instruction = ""
    if selected_focus:
        focus_instruction = compact_prompt(
            f"""
            本场必须显式覆盖的讨论切面：{selected_focus}。
            你可以支持、反驳、重定义或比较它，但不能忽略它。
            """
        )

    context_instruction = ""
    if user_context.strip():
        context_instruction = (
            f"用户补充背景如下，请把它当作场景信息而不是立场指令：{user_context.strip()}"
        )

    if stage == DebateStage.opening:
        body = compact_prompt(
            """
            请给出开场陈词。明确你的核心判断、判定标准、关键因果链，
            并预告你认为对手最可能依赖的脆弱前提。
            """
        )
    elif stage == DebateStage.closing:
        body = compact_prompt(
            """
            请给出总结陈词。必须回答：对手最强反驳是什么，你如何回应；
            你在哪一点上被迫修正；以及为什么最终更应偏向你的观点。
            """
        )
    else:
        body = compact_prompt(
            """
            请给出本轮自由辩发言。优先处理最关键的冲突点。
            本轮至少完成一项：拆掉对方一个前提、指出证据不足、打断因果链、
            指出判定标准自相矛盾，或承认自己一个明显漏洞后用更强论点重建。
            """
        )

    parts = [body, focus_instruction, context_instruction]
    return "\n".join(part for part in parts if part).strip()


def format_focus_context(selected_focus: str, user_context: str) -> str:
    lines: list[str] = []
    if selected_focus:
        lines.append(f"User-selected focus that must stay in play: {selected_focus}")
        lines.append("This is a discussion priority, not a user-desired answer.")
    if user_context.strip():
        lines.append(f"Supplemental context: {user_context.strip()}")
        lines.append("Treat it as scenario background, not as the user's stance.")
    return "\n".join(lines).strip()


def build_follow_up_system_prompt(config: DebaterConfig) -> str:
    return compact_prompt(
        f"""
        You are debater {config.name}.
        Background: {config.background}
        Core stance: {config.stance}
        Public persona: {config.personality}
        Output language: Chinese.
        Stay consistent with your debate persona. You may clarify or refine, but do not suddenly become neutral.
        """
    )


def build_follow_up_user_prompt(topic: str, own_positions: str, question: str) -> str:
    return compact_prompt(
        f"""
        话题：{topic}

        你在辩论中的主要观点：
        {own_positions}

        用户问题：{question}

        请基于你的立场作答，控制在 200 字内。
        """
    )


def append_optional_references(user_prompt: str, references: list[SearchResult]) -> str:
    if not references:
        return user_prompt

    refs_text = "\n".join(f"- {ref.title}: {ref.snippet[:120]}" for ref in references)
    return f"{user_prompt}\n\n## Optional Realtime References\n{refs_text}"


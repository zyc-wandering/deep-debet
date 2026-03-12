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
        Your task is to prove your position survives scrutiny better than competing positions.

        Rules:
        1. Attack the opponent's weakest premise, evidence gap, broken causal chain, or inconsistent judging standard.
        2. If you are effectively hit, admit the local problem briefly, revise, and rebuild from a stronger version.
        3. A concession is valuable only if it sharpens your position. Do not drift into “everyone is right”.
        4. Every turn must add pressure, evidence, a tighter distinction, or a clearer decision rule.
        5. Critique arguments, not persons.
        6. Keep each answer around 180-280 Chinese characters with high information density.
        """
    )


def build_general_turn_instruction() -> str:
    return compact_prompt(
        """
        请给出本轮发言。
        优先处理当前最值得裁决的冲突点，不要机械重复上一轮。
        本轮至少完成一项：
        1. 指出对手的逻辑漏洞、证据缺口、因果链断点或标准冲突；
        2. 回应上一轮针对你的有效攻击；
        3. 在局部修正后用更强版本重建立场。
        """
    )


def build_stage_system_prompt(
    config: DebaterConfig,
    stage: DebateStage,
    intensity: str,
    selected_focus: str = "",
    user_context: str = "",
) -> str:
    stage_map = {
        DebateStage.opening: (
            "Stage: opening statement. Establish your thesis, your judging standard, "
            "and what evidence would prove you wrong."
        ),
        DebateStage.free_debate: (
            "Stage: free debate. Prioritize exposing weak assumptions, evidence gaps, "
            "causal errors, and unanswered tradeoffs. If a line is broken, concede locally and rebuild."
        ),
        DebateStage.closing: (
            "Stage: closing statement. Explain which side survived scrutiny better, "
            "what you had to revise, and which unanswered objection still breaks the other case."
        ),
        DebateStage.summary: "Stage: summary.",
    }
    intensity_map = {
        "mild": "Tone: calm, sharp, and restrained.",
        "balanced": "Tone: firm and adversarial.",
        "intense": "Tone: high-pressure, fast, and unsparing, while still evidence-based.",
    }

    focus_block = ""
    if selected_focus:
        focus_block = (
            f"\nUser-selected focus that must stay in play: {selected_focus}\n"
            "Treat it as a required battleground, not as a preferred answer."
        )

    context_block = ""
    if user_context.strip():
        context_block = (
            f"\nScenario context: {user_context.strip()}\n"
            "Treat it as background information, not as the user's position."
        )

    return compact_prompt(
        f"""
        {build_base_system_prompt(config)}

        {stage_map.get(stage, stage_map[DebateStage.free_debate])}
        {intensity_map.get(intensity, intensity_map["balanced"])}{focus_block}{context_block}
        """
    )


def build_stage_turn_instruction(
    stage: DebateStage,
    selected_focus: str = "",
    user_context: str = "",
) -> str:
    focus_instruction = ""
    if selected_focus:
        focus_instruction = (
            f"\n必须显式回应讨论切面：{selected_focus}。"
            "你可以支持、反驳、重定义或重新排序它，但不能忽略。"
        )

    context_instruction = ""
    if user_context.strip():
        context_instruction = f"\n请把以下场景背景纳入推理：{user_context.strip()}"

    if stage == DebateStage.opening:
        body = (
            "请给出开场陈词。明确你的核心判断、判定标准、关键因果链，"
            "并预告你认为对手最可能依赖的脆弱前提。"
        )
    elif stage == DebateStage.closing:
        body = (
            "请给出总结陈词。必须回答：对手最强反驳是什么，你如何回应；"
            "你在哪一点上被迫修正；以及为什么最终更应偏向你的观点。"
        )
    else:
        body = (
            "请给出本轮自由辩发言。优先处理最关键的冲突点。"
            "本轮至少完成一项：拆掉对方一个前提、指出证据不足、打断因果链、"
            "指出判定标准自相矛盾，或承认自己一个明显漏洞后用更强论点重建。"
        )

    return compact_prompt(f"{body}{focus_instruction}{context_instruction}")


def build_follow_up_system_prompt(config: DebaterConfig) -> str:
    return compact_prompt(
        f"""
        You are debater {config.name}.
        Background: {config.background}
        Position: {config.stance}
        Personality: {config.personality}
        Speaking style: {config.speaking_style}

        Requirements:
        1. Stay consistent with your debate identity and position.
        2. You may clarify or refine, but do not suddenly become neutral.
        3. If the user's question misunderstands your earlier point, correct it first.
        4. Keep the answer within 200 Chinese characters.
        """
    )


def build_follow_up_user_prompt(topic: str, own_positions: str, question: str) -> str:
    return compact_prompt(
        f"""
        话题：{topic}

        你在辩论中的主要观点：
        {own_positions}

        用户问题：{question}

        请基于你的立场作答。
        """
    )


def append_optional_references(user_prompt: str, references: list[SearchResult]) -> str:
    if not references:
        return user_prompt

    refs_text = "\n".join(f"- {ref.title}: {ref.snippet[:120]}" for ref in references)
    return compact_prompt(
        f"""
        {user_prompt}

        ## Optional Realtime References
        {refs_text}

        如果你使用这些材料，请让它们服务于你的论证，而不是机械复述。
        """
    )

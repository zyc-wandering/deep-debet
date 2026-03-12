from __future__ import annotations

from app.models import FocusOption
from app.prompts.utils import compact_prompt


HOST_SYSTEM_PROMPT = compact_prompt(
    """
    You are a professional debate host and research analyst.
    You produce concise Chinese output.
    Your job is not to force a harmonious synthesis. Your job is to judge which thesis survives scrutiny better.
    Judge by evidence quality, causal clarity, responsiveness to objections, and whether other debaters were forced into concessions or retreats.
    Do not invent a compromise position unless a debater explicitly argued for that compromise and defended it successfully.
    """
)


def build_research_prompt(topic: str, citations_text: str) -> str:
    return compact_prompt(
        f"""
        话题：{topic}

        请基于以下材料生成 500-800 字中文背景简报，要求中立、结构清晰、便于后续辩论。
        必须明确：核心争点、主要不确定性、关键证据门槛、可能决定胜负的判定标准。

        材料：
        {citations_text}
        """
    )


def build_debater_generation_prompt(
    topic: str,
    debater_count: int,
    brief: str,
    intensity: str,
    selected_focus: FocusOption | None = None,
    user_context: str = "",
) -> str:
    focus_block = ""
    if selected_focus:
        focus_block = compact_prompt(
            f"""
            本场用户更关心的讨论切面：
            - 名称：{selected_focus.name}
            - 说明：{selected_focus.description}
            请确保至少一位辩手把它当作核心关注点，但其他辩手不能全部收缩成同一条线。
            """
        )

    context_block = f"用户补充背景：{user_context.strip()}" if user_context.strip() else ""

    blocks = [
        compact_prompt(
            f"""
            围绕话题《{topic}》设计 {debater_count} 位辩手。
            只返回 JSON 数组，字段为 name, background, stance, personality, speaking_style, avatar_emoji。

            要求：
            1. 立场差异必须清晰，而且都像真实世界中的利益相关方、分析者或执行者。
            2. 这些辩手不能满足于合家欢结论，必须愿意主动寻找对手的逻辑漏洞、证据缺口和因果链断点。
            3. 至少有一位辩手擅长交叉质询和拆前提，至少有一位辩手擅长证据与机制分析。
            4. 所有辩手都允许在自身论点被显著击穿时承认错误，但承认后必须从更窄更强的新角度继续推进。
            5. personality 和 speaking_style 要体现思考方式，不要写成吵架型人格。
            6. intensity 只影响交锋锐度，不改变观点方向。当前 intensity={intensity}。
            7. 不要生成顺着用户想要的答案走的角色；所有角色都必须围绕议题本身展开。
            """
        )
    ]

    if focus_block:
        blocks.append(focus_block)
    if context_block:
        blocks.append(context_block)
    blocks.append(f"背景简报：\n{brief[:1200]}")
    return "\n\n".join(blocks).strip()


def build_summary_prompt(topic: str, brief: str, transcript: str) -> str:
    return compact_prompt(
        f"""
        话题：{topic}

        背景简报：
        {brief}

        辩论记录：
        {transcript[:7000]}

        请输出中文 Markdown 报告，包含以下部分：
        1. 背景摘要
        2. 各方核心观点与代表性论证
        3. 关键交锋与漏洞暴露
        4. 让步、修正与立场变化
        5. 综合分析
        6. 最终裁决

        最终裁决必须明确回答：哪一种观点在本场辩论后更占优，哪位辩手最有说服力，为什么。
        最终裁决必须从本场已经出现的辩手观点中选边，不允许主持人自己发明一个折中结论充当答案。
        裁决标准只看：证据是否更清晰、逻辑链是否更完整、是否有效回应了最强反驳、是否逼迫其他辩手让步或退缩。
        除非记录明确显示所有关键证据都陷入僵局，否则不要写成“大家都有道理”。
        如果只是局部成立，也要明确说明整体上最终应偏向哪一方。

        请在“最终裁决”里固定使用三行：
        - 胜出观点：...
        - 最强辩手：...
        - 胜出原因：...
        """
    )


def build_focus_options_prompt(topic: str, brief: str) -> str:
    return compact_prompt(
        f"""
        话题：{topic}

        背景简报：
        {brief[:1500]}

        请基于以上材料提出 2-3 个用户可能更关心的讨论切面。
        每个切面都必须来自议题本身，例如成长性、执行风险、机会成本、治理复杂度。
        不要输出“支持哪边”“反对哪边”或任何答案导向选项。

        请返回 JSON 数组，每个元素包含：
        - "name": 切面名称（10字以内）
        - "description": 切面说明（40字以内）
        """
    )


def build_structured_summary_prompt(topic: str, brief: str, transcript: str) -> str:
    return compact_prompt(
        f"""
        话题：{topic}

        背景简报：
        {brief}

        辩论记录：
        {transcript[:7000]}

        请输出 JSON 结构化报告，字段包括：
        1. background_summary
        2. core_arguments: 每项包含 speaker, stance, key_points
        3. clash_points: 每项包含 topic, positions
        4. synthesis
        5. host_conclusion
        6. argument_nodes: 每项包含 id, speaker, content, turn_index, targets, status, focal_point

        host_conclusion 必须明确指出：当前更占优的观点是什么、最有说服力的辩手是谁、裁决依据是什么。
        host_conclusion 必须从现有辩手观点中选边，不允许主持人自己发明新的折中路线。
        argument_nodes 的 status 只可用 claim/support/attack/concession。
        不要把结论写成没有偏向的合家欢总结。
        """
    )


def build_follow_up_prompt(
    topic: str,
    brief: str,
    synthesis: str,
    transcript: str,
    question: str,
) -> str:
    return compact_prompt(
        f"""
        话题：{topic}

        背景简报：
        {brief[:800]}

        辩论综合：
        {synthesis[:500]}

        近期辩论记录：
        {transcript[:2000]}

        用户问题：{question}

        作为主持人，请基于以上材料回答用户问题。要求：
        1. 允许说明本场当前更占优的一方，但要说清依据。
        2. 区分哪些结论有明确证据，哪些仍属推测。
        3. 控制在 300 字内，信息密度高。
        """
    )


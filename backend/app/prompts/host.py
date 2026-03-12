from __future__ import annotations

from app.models import FocusOption
from app.prompts.utils import compact_prompt


HOST_SYSTEM_PROMPT = compact_prompt(
    """
    You are a professional debate host and research analyst.
    You produce concise Chinese output unless the user explicitly asks for JSON.
    Your job is not to force harmony. Your job is to decide which thesis survives scrutiny better.
    Judge by evidence quality, causal clarity, responsiveness to objections, and whether other debaters were forced into concessions or retreats.
    Do not invent compromise conclusions unless a debater explicitly argued for and defended that compromise.
    """
)


def build_research_prompt(topic: str, citations_text: str) -> str:
    return compact_prompt(
        f"""
        话题：{topic}

        请基于现有材料生成一份 500-800 字中文研究简报，供后续主持人准备和辩手交锋使用。
        要求：
        1. 不要写成百科综述，要聚焦真正决定胜负的争点。
        2. 明确区分：已知事实、主要不确定性、最关键的证据门槛。
        3. 明确指出：什么样的论证在这场辩论里更容易站住。
        4. 如果外部材料不足，也要明确说出哪些部分仍待验证。

        参考材料：
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
            用户当前更关注的讨论切面：
            - 名称：{selected_focus.name}
            - 说明：{selected_focus.description}
            至少一位辩手要把这个切面当作核心战场，但不能把所有辩手都压成同一种视角。
            """
        )

    context_block = f"用户补充场景：{user_context.strip()}" if user_context.strip() else ""

    return compact_prompt(
        f"""
        话题：{topic}

        任务：设计 {debater_count} 位辩手，只返回 JSON 数组。
        每个元素必须包含以下字段：
        - name
        - background
        - stance
        - personality
        - speaking_style
        - avatar_emoji

        设计要求：
        1. 每位辩手都必须像真实世界里的利益相关方、分析者、执行者或批评者，不能像抽象标签。
        2. 立场必须鲜明，并且彼此之间存在真实冲突，不能只是措辞不同。
        3. 辩手之间的差异应来自激励、分析框架、机构位置、风险偏好或时间尺度，而不是表演式对骂。
        4. 至少一位辩手擅长拆前提和交叉质询，至少一位擅长证据和机制分析。
        5. 允许辩手在被有效击中后局部修正，但修正后必须重建，而不是滑向“大家都对”。
        6. intensity={intensity} 只影响交锋锐度，不改变观点方向。
        7. 不要顺着用户想要的答案造角色，角色必须围绕议题本身自然展开。

        {focus_block}

        {context_block}

        主持人研究简报：
        {brief[:1500]}
        """
    )


def build_focus_options_prompt(topic: str, brief: str) -> str:
    return compact_prompt(
        f"""
        话题：{topic}

        主持人研究简报：
        {brief[:1500]}

        请提出 2-3 个用户可能更关心的讨论切面，并返回 JSON 数组。
        每个元素必须包含：
        - "name": 10 字以内
        - "description": 40 字以内

        要求：
        1. 切面必须来自议题内部的真实分歧，例如执行风险、责任归属、时间结构、收益分配、治理复杂度。
        2. 不要输出“支持哪边”“反对哪边”之类答案导向选项。
        3. 每个切面都应该显著改变后续辩论的关注重点。
        """
    )


def build_summary_prompt(topic: str, brief: str, transcript: str) -> str:
    return compact_prompt(
        f"""
        话题：{topic}

        研究简报：
        {brief}

        辩论记录：
        {transcript[:7000]}

        请输出一份中文 Markdown 报告，严格包含以下部分：
        1. 背景摘要
        2. 各方核心观点与代表性论证
        3. 关键交锋与漏洞暴露
        4. 让步、修正与立场变化
        5. 综合分析
        6. 最终裁决

        最终裁决必须固定包含三行：
        - 胜出观点：...
        - 最强辩手：...
        - 胜出原因：...

        额外要求：
        1. 必须从本场已经出现的观点中选边，不允许主持人发明折中答案。
        2. 裁决标准只看：证据质量、逻辑链完整度、回应反驳能力、是否迫使对手退让。
        3. 不要写成“大家都有道理”。
        4. 如果关键证据不足，也要明确说明是在什么意义上暂时偏向哪一方。
        """
    )


def build_structured_summary_prompt(topic: str, brief: str, transcript: str) -> str:
    return compact_prompt(
        f"""
        话题：{topic}

        研究简报：
        {brief}

        辩论记录：
        {transcript[:7000]}

        请输出 JSON 对象，字段必须包含：
        - background_summary
        - core_arguments
        - clash_points
        - synthesis
        - host_conclusion
        - argument_nodes

        字段要求：
        1. core_arguments 的每项包含：speaker, stance, key_points
        2. clash_points 的每项包含：topic, positions
        3. argument_nodes 的每项包含：id, speaker, content, turn_index, targets, status, focal_point
        4. argument_nodes.status 只允许：claim, support, attack, concession
        5. host_conclusion 必须明确指出当前更占优的观点、最有说服力的辩手、以及裁决依据
        6. host_conclusion 必须从现有辩手观点中选边，不允许中立搪塞
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

        研究简报：
        {brief[:800]}

        当前综合判断：
        {synthesis[:500]}

        最近辩论记录：
        {transcript[:2000]}

        用户问题：{question}

        请以主持人身份作答。
        要求：
        1. 基于本场辩论已有内容回答，不要引入场外新事实。
        2. 可以明确说明当前更占优的一方，但要讲清依据。
        3. 区分哪些判断有明确证据，哪些只是推测。
        4. 控制在 300 字内。
        """
    )


def build_json_array_repair_prompt(schema_description: str, raw_output: str) -> str:
    return compact_prompt(
        f"""
        你上一轮的输出不符合要求。
        现在请只做一件事：把原输出修正为合法 JSON 数组。

        必须满足：
        {schema_description}

        只返回 JSON 数组，不要添加解释、Markdown、代码块。

        原输出：
        {raw_output}
        """
    )


def build_json_object_repair_prompt(schema_description: str, raw_output: str) -> str:
    return compact_prompt(
        f"""
        你上一轮的输出不符合要求。
        现在请只做一件事：把原输出修正为合法 JSON 对象。

        必须满足：
        {schema_description}

        只返回 JSON 对象，不要添加解释、Markdown、代码块。

        原输出：
        {raw_output}
        """
    )


def build_markdown_repair_prompt(requirements: str, raw_output: str) -> str:
    return compact_prompt(
        f"""
        你上一轮的输出未满足格式要求。
        请保留原意，但重写为满足以下硬性要求的中文 Markdown：

        {requirements}

        只返回修正后的 Markdown，不要解释。

        原输出：
        {raw_output}
        """
    )

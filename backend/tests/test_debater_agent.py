import pytest

from app.agents.context_manager import ContextManager
from app.agents.debater_agent import DebaterAgent
from app.models import DebaterConfig, DebateMessage, DebateStage
from app.providers.base import LLMProvider, SearchProvider


class FailingLLM(LLMProvider):
    async def chat(self, system_prompt: str, user_prompt: str) -> str:
        raise RuntimeError("401 unauthorized")


class EmptySearch(SearchProvider):
    async def search(self, query: str, num_results: int = 5):
        return []


@pytest.mark.anyio
async def test_debater_fallback_uses_topic_signals_and_changes_across_turns():
    agent = DebaterAgent(
        config=DebaterConfig(
            name="制度审慎派 Zhou",
            background="公共政策研究者",
            stance="对 AI 是否应该替代初级分析师的部分工作 持审慎监管态度",
            personality="逻辑严谨，擅长追问边界条件和责任链",
            speaking_style="structured",
            avatar_emoji="衡",
        ),
        llm=FailingLLM(),
        search=EmptySearch(),
        context_manager=ContextManager(),
    )

    brief = """
    ## AI 是否应该替代初级分析师的部分工作 背景简报
    - 许多公司希望用模型替代重复的信息整理和初步分析任务。
    - 支持者强调效率提升、成本下降与 24 小时可用性。
    - 反对者担心错误累积、责任模糊以及新人培养断层。
    """

    first, _ = await agent.produce_turn(
        topic="AI 是否应该替代初级分析师的部分工作",
        brief=brief,
        messages=[],
        enable_search=False,
    )
    messages = [DebateMessage(speaker=agent.config.name, role="debater", content=first, turn_index=0)]
    messages.append(
        DebateMessage(
            speaker="技术推进派 Lin",
            role="debater",
            content="如果自动化能提升效率，为什么不先推进？",
            turn_index=1,
        )
    )
    second, _ = await agent.produce_turn(
        topic="AI 是否应该替代初级分析师的部分工作",
        brief=brief,
        messages=messages,
        enable_search=False,
    )

    assert "AI 是否应该替代初级分析师的部分工作" not in first
    assert any(keyword in first for keyword in ["效率", "责任", "成本", "标准", "培养"])
    assert "Lin" in second
    assert first != second


@pytest.mark.anyio
async def test_pragmatic_fallback_mentions_cost_or_exit_path():
    agent = DebaterAgent(
        config=DebaterConfig(
            name="落地经营派 Chen",
            background="互联网产品负责人",
            stance="对 AI 是否应该替代初级分析师的部分工作 持务实落地态度",
            personality="结果导向，善于算账",
            speaking_style="blunt",
            avatar_emoji="财",
        ),
        llm=FailingLLM(),
        search=EmptySearch(),
        context_manager=ContextManager(),
    )

    text, _ = await agent.produce_turn(
        topic="AI 是否应该替代初级分析师的部分工作",
        brief="- 自动化会影响团队的人力配置与培训成本\n- 需要定义错误责任与止损机制",
        messages=[],
        enable_search=False,
    )

    assert any(keyword in text for keyword in ["成本", "止损", "责任"])


@pytest.mark.anyio
async def test_fallback_does_not_default_to_agreement_template():
    agent = DebaterAgent(
        config=DebaterConfig(
            name="制度审慎派 Zhou",
            background="公共政策研究者",
            stance="对 AI 是否应该替代初级分析师的部分工作 持审慎监管态度",
            personality="逻辑严谨，擅长追问边界条件和责任链",
            speaking_style="structured",
            avatar_emoji="衡",
        ),
        llm=FailingLLM(),
        search=EmptySearch(),
        context_manager=ContextManager(),
    )

    text, _ = await agent.produce_turn(
        topic="AI 是否应该替代初级分析师的部分工作",
        brief="- 自动化会影响团队的人力配置与培训成本\n- 需要定义错误责任与止损机制",
        messages=[
            DebateMessage(
                speaker="技术推进派 Lin",
                role="debater",
                content="只要效率提升，就应该尽快替代低价值环节。",
                turn_index=0,
            )
        ],
        enable_search=False,
    )

    assert not text.startswith("我同意")
    assert any(keyword in text for keyword in ["边界", "责任", "成本", "止损", "标准", "代价", "条件", "证据"])


def test_stage_prompt_requires_concession_and_rebuild_when_broken():
    agent = DebaterAgent(
        config=DebaterConfig(
            name="交叉质询派 Xu",
            background="独立评论者",
            stance="对开放议题保持高压质疑立场",
            personality="擅长拆前提与追问漏洞",
            speaking_style="cross_exam",
            avatar_emoji="X",
        ),
        llm=FailingLLM(),
        search=EmptySearch(),
        context_manager=ContextManager(),
    )

    prompt = agent._system_prompt_stage(DebateStage.free_debate, "intense", "执行风险", "")
    instruction = agent._get_stage_instruction(DebateStage.free_debate, "执行风险", "")

    assert "concede" in prompt.lower()
    assert "重建" in instruction

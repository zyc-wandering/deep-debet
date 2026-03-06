import pytest

from app.agents.context_manager import ContextManager
from app.agents.debater_agent import DebaterAgent
from app.models import DebaterConfig, DebateMessage
from app.providers.base import LLMProvider, SearchProvider


class FailingLLM(LLMProvider):
    async def chat(self, system_prompt: str, user_prompt: str) -> str:
        raise RuntimeError("401 unauthorized")


class EmptySearch(SearchProvider):
    async def search(self, query: str, num_results: int = 5):
        return []


@pytest.mark.anyio
async def test_debater_fallback_uses_topic_and_changes_across_turns():
    agent = DebaterAgent(
        config=DebaterConfig(
            name="政策观察员 Zhou",
            background="公共政策研究者",
            stance="对 AI 是否应该替代初级分析师的部分工作 持审慎监管态度",
            personality="逻辑严谨、擅长追问边界条件",
            speaking_style="structured",
            avatar_emoji="🏛️",
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
            speaker="技术极客 Lin",
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
    assert any(keyword in first for keyword in ["分析任务", "效率", "责任", "培养"])
    assert "回应 技术极客 Lin" in second
    assert first != second


@pytest.mark.anyio
async def test_pragmatic_fallback_mentions_cost_or_exit_path():
    agent = DebaterAgent(
        config=DebaterConfig(
            name="商业操盘手 Chen",
            background="互联网产品负责人",
            stance="对 AI 是否应该替代初级分析师的部分工作 持务实落地态度",
            personality="结果导向、善于算账、吐槽直接",
            speaking_style="blunt",
            avatar_emoji="📈",
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

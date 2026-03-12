import pytest

from app.agents.context_manager import ContextManager
from app.agents.debater_agent import DebaterAgent
from app.models import DebaterConfig, DebateMessage, DebateStage
from app.providers.base import LLMProvider, SearchProvider


class StaticLLM(LLMProvider):
    def __init__(self, text: str) -> None:
        self.text = text

    async def chat(self, system_prompt: str, user_prompt: str) -> str:
        return self.text

    async def chat_stream(self, system_prompt: str, user_prompt: str):
        for token in self.text:
            yield token


class StreamFailChatOKLLM(LLMProvider):
    def __init__(self, text: str) -> None:
        self.text = text

    async def chat(self, system_prompt: str, user_prompt: str) -> str:
        return self.text

    async def chat_stream(self, system_prompt: str, user_prompt: str):
        raise RuntimeError("stream failed")
        yield  # pragma: no cover


class FailingLLM(LLMProvider):
    async def chat(self, system_prompt: str, user_prompt: str) -> str:
        raise RuntimeError("401 unauthorized")


class EmptySearch(SearchProvider):
    async def search(self, query: str, num_results: int = 5):
        return []


def make_agent(llm: LLMProvider) -> DebaterAgent:
    return DebaterAgent(
        config=DebaterConfig(
            name="Zhou",
            background="公共政策研究者",
            stance="对 AI 替代部分初级分析工作持审慎监管态度",
            personality="逻辑严谨，擅长追问前提、边界和责任链",
            speaking_style="structured",
            avatar_emoji="Z",
        ),
        llm=llm,
        search=EmptySearch(),
        context_manager=ContextManager(),
    )


@pytest.mark.anyio
async def test_produce_turn_returns_llm_output_directly():
    agent = make_agent(StaticLLM("这是模型生成的发言。"))

    text, references = await agent.produce_turn(
        topic="AI 应该替代部分初级分析工作吗",
        brief="brief",
        messages=[],
        enable_search=False,
    )

    assert text == "这是模型生成的发言。"
    assert references == []


@pytest.mark.anyio
async def test_produce_turn_raises_when_llm_fails_instead_of_using_hardcoded_fallback():
    agent = make_agent(FailingLLM())

    with pytest.raises(RuntimeError):
        await agent.produce_turn(
            topic="AI 应该替代部分初级分析工作吗",
            brief="brief",
            messages=[],
            enable_search=False,
        )


@pytest.mark.anyio
async def test_stream_stage_falls_back_to_non_stream_llm_response_only():
    agent = make_agent(StreamFailChatOKLLM("这是非流式模型返回。"))

    chunks = []
    async for token in agent.produce_turn_stream_stage(
        topic="AI 应该替代部分初级分析工作吗",
        brief="brief",
        messages=[DebateMessage(speaker="Lin", role="debater", content="上一轮发言", turn_index=0)],
        stage=DebateStage.free_debate,
        intensity="balanced",
        enable_search=False,
        selected_focus="执行风险",
        user_context="重点看责任边界。",
    ):
        chunks.append(token)

    assert "".join(chunks) == "这是非流式模型返回。"


def test_stage_prompt_requires_concession_and_rebuild_when_broken():
    agent = make_agent(StaticLLM("stub"))

    prompt = agent._system_prompt_stage(DebateStage.free_debate, "intense", "执行风险", "")
    instruction = agent._get_stage_instruction(DebateStage.free_debate, "执行风险", "")

    assert "concede" in prompt.lower()
    assert "重建" in instruction

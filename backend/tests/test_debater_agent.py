import pytest

from app.agents.context_manager import ContextManager
from app.agents.debater_agent import DebaterAgent
from app.models import DebaterConfig, DebateLanguage, DebateMessage, DebateStage, FocusOption
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
            background="Policy researcher",
            stance="Supports careful guardrails around agentic AI use",
            personality="Analytical and detail-oriented",
            speaking_style="structured",
            avatar_emoji="Z",
        ),
        llm=llm,
        search=EmptySearch(),
        context_manager=ContextManager(),
    )


def make_focus() -> FocusOption:
    return FocusOption(name="Execution risk", description="Prioritize delivery cost and accountability")


@pytest.mark.anyio
async def test_produce_turn_returns_llm_output_directly():
    agent = make_agent(StaticLLM("This is a plain debater answer."))

    text, references = await agent.produce_turn(
        topic="Should teams use async updates by default?",
        brief="brief",
        messages=[],
        enable_search=False,
    )

    assert text == "This is a plain debater answer."
    assert references == []


@pytest.mark.anyio
async def test_produce_turn_extracts_single_value_from_wrapped_json_object():
    agent = make_agent(StaticLLM('{"opening_statement":"Only the value should remain."}'))

    text, references = await agent.produce_turn(
        topic="Should teams use async updates by default?",
        brief="brief",
        messages=[],
        enable_search=False,
    )

    assert text == "Only the value should remain."
    assert references == []


@pytest.mark.anyio
async def test_produce_turn_raises_when_llm_fails_instead_of_using_hardcoded_fallback():
    agent = make_agent(FailingLLM())

    with pytest.raises(RuntimeError):
        await agent.produce_turn(
            topic="Should teams use async updates by default?",
            brief="brief",
            messages=[],
            enable_search=False,
        )


@pytest.mark.anyio
async def test_stream_stage_falls_back_to_non_stream_llm_response_only():
    agent = make_agent(StreamFailChatOKLLM("This is the fallback answer."))

    chunks = []
    async for token in agent.produce_turn_stream_stage(
        topic="Should teams use async updates by default?",
        brief="brief",
        messages=[DebateMessage(speaker="Lin", role="debater", content="Previous point", turn_index=0)],
        stage=DebateStage.free_debate,
        intensity="balanced",
        enable_search=False,
        selected_focus=make_focus(),
        user_context="Prefer practical tradeoffs.",
    ):
        chunks.append(token)

    assert "".join(chunks) == "This is the fallback answer."


@pytest.mark.anyio
async def test_stream_stage_extracts_value_from_wrapped_json_object():
    agent = make_agent(StaticLLM('{"free_debate_speech":"Attack the argument, not the wrapper."}'))

    chunks = []
    async for token in agent.produce_turn_stream_stage(
        topic="Should teams use async updates by default?",
        brief="brief",
        messages=[],
        stage=DebateStage.free_debate,
        intensity="balanced",
        enable_search=False,
        selected_focus=make_focus(),
        user_context="",
    ):
        chunks.append(token)

    assert "".join(chunks) == "Attack the argument, not the wrapper."


def test_stage_prompt_requires_concession_and_rebuild_when_broken():
    agent = make_agent(StaticLLM("stub"))

    prompt = agent._system_prompt_stage(DebateStage.free_debate, "intense", make_focus(), "")
    instruction = agent._get_stage_instruction(DebateStage.free_debate, make_focus(), "")

    assert "concession" in prompt.lower() or "承认" in prompt
    assert "rebuild" in instruction.lower() or "重建" in instruction


def test_english_mode_uses_english_output_override():
    agent = DebaterAgent(
        config=DebaterConfig(
            name="Zhou",
            background="Policy researcher",
            stance="AI should stay assistive rather than autonomous in high-risk review",
            personality="Analytical premise-deconstruction thinker",
            speaking_style="tight and direct",
            avatar_emoji="Z",
        ),
        llm=StaticLLM("stub"),
        search=EmptySearch(),
        context_manager=ContextManager(),
        debate_language=DebateLanguage.en,
    )

    prompt = agent._system_prompt_stage(DebateStage.free_debate, "balanced", None, "")

    assert "All natural-language output for this debate must be in English" in prompt

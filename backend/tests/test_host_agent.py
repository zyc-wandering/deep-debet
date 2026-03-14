import pytest

from app.agents.host_agent import HostAgent
from app.models import DebateMessage
from app.providers.base import LLMProvider, SearchProvider


class SequencedLLM(LLMProvider):
    def __init__(self, responses: list[str]) -> None:
        self._responses = list(responses)

    async def chat(self, system_prompt: str, user_prompt: str) -> str:
        if not self._responses:
            raise RuntimeError("No more responses")
        return self._responses.pop(0)


class EmptySearch(SearchProvider):
    async def search(self, query: str, num_results: int = 5):
        return []


@pytest.mark.anyio
async def test_create_debaters_parses_age_and_ethnicity_fields():
    llm = SequencedLLM(
        [
            """
            [
              {
                "name": "Amina Rahman",
                "age": "34岁",
                "ethnicity": "孟加拉裔英国人",
                "background": "伦敦能源政策分析师，长期研究转型成本",
                "stance": "支持渐进式推进",
                "personality": "冷静审慎，偏证据链追踪型",
                "speaking_style": "清晰克制",
                "avatar_emoji": "📊"
              },
              {
                "name": "Daniel Brooks",
                "age": "52岁",
                "ethnicity": "白人美国人",
                "background": "制造业工会顾问，关注就业与现实冲击",
                "stance": "反对激进改革",
                "personality": "直接强硬，偏前提解构型",
                "speaking_style": "锋利直接",
                "avatar_emoji": "🏭"
              }
            ]
            """
        ]
    )
    agent = HostAgent(llm=llm, search=EmptySearch())

    debaters = await agent.create_debaters(
        topic="Should governments adopt a rapid carbon tax?",
        debater_count=2,
        brief="brief",
    )

    assert debaters[0].age == "34岁"
    assert debaters[0].ethnicity == "孟加拉裔英国人"
    assert debaters[0].name == "Amina Rahman"
    assert debaters[1].age == "52岁"
    assert debaters[1].ethnicity == "白人美国人"


def test_normalize_structured_report_data_converts_argument_node_targets_to_strings():
    agent = HostAgent(llm=None, search=None)
    payload = {
        "background_summary": "summary",
        "argument_nodes": [
            {
                "id": 1,
                "speaker": "Host",
                "content": "Point",
                "turn_index": 0,
                "targets": [2, "3", None],
                "status": "claim",
            }
        ],
    }

    normalized = agent._normalize_structured_report_data(payload)

    assert normalized["argument_nodes"][0]["id"] == "1"
    assert normalized["argument_nodes"][0]["targets"] == ["2", "3"]


@pytest.mark.anyio
async def test_summarize_debate_repairs_missing_required_verdict_markers():
    llm = SequencedLLM(
        [
            "# 报告\n\n## 背景摘要\n略。\n\n## 最终裁决\n目前偏向 Alpha。",
            (
                "# 报告\n\n## 背景摘要\n略。\n\n## 最终裁决\n"
                "- 胜出观点：Alpha 的观点\n"
                "- 最强辩手：Alpha\n"
                "- 胜出原因：证据和逻辑都更完整。"
            ),
        ]
    )
    agent = HostAgent(llm=llm, search=EmptySearch())
    messages = [
        DebateMessage(speaker="Alpha", role="debater", content="Alpha speaks", turn_index=0),
        DebateMessage(speaker="Beta", role="debater", content="Beta speaks", turn_index=1),
    ]

    report = await agent.summarize_debate("Test topic", "brief", messages, [])

    assert "胜出观点" in report
    assert "最强辩手" in report
    assert "胜出原因" in report

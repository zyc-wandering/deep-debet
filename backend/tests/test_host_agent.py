from app.agents.host_agent import HostAgent
from app.models import DebateMessage


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


def test_fallback_report_makes_a_directional_verdict():
    agent = HostAgent(llm=None, search=None)
    messages = [
        DebateMessage(
            speaker="Alpha",
            role="debater",
            content="我的证据、数据和判定标准都指向同一件事：对方的因果链站不住。",
            turn_index=0,
        ),
        DebateMessage(
            speaker="Beta",
            role="debater",
            content="我觉得两边都有道理，可能都对，要看情况。",
            turn_index=1,
        ),
    ]

    report = agent._fallback_report("Test topic", "brief", messages, [])

    assert "最终裁决" in report
    assert "胜出观点：更接近 Alpha 所代表的论证路径。" in report
    assert "最强辩手：Alpha" in report
    assert "大家都有道理" not in report

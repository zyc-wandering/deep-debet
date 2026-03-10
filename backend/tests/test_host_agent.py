from app.agents.host_agent import HostAgent


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

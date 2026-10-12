"""
Tests for the main-session vs subagent split in GET /sessions/{uuid}/tools.
"""

import json

import pytest
from fastapi.testclient import TestClient

from main import app

SESSION_UUID = "tools-scope-session-uuid"


def _assistant_line(uuid: str, tool_name: str) -> dict:
    return {
        "type": "assistant",
        "uuid": uuid,
        "timestamp": "2024-01-01T10:01:00Z",
        "message": {
            "id": f"msg_{uuid}",
            "role": "assistant",
            "content": [
                {"type": "tool_use", "id": f"toolu_{uuid}", "name": tool_name, "input": {}}
            ],
        },
    }


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def session_with_subagent(mock_claude_base):
    """Session with one Read call and a subagent with one Bash call."""
    project_dir = mock_claude_base / "projects" / "-Users-test-toolsproject"
    project_dir.mkdir(parents=True, exist_ok=True)
    (project_dir / f"{SESSION_UUID}.jsonl").write_text(
        json.dumps(_assistant_line("main-1", "Read")) + "\n"
    )
    subagents_dir = project_dir / SESSION_UUID / "subagents"
    subagents_dir.mkdir(parents=True)
    (subagents_dir / "agent-a1.jsonl").write_text(
        json.dumps(_assistant_line("sub-1", "Bash")) + "\n"
    )
    return SESSION_UUID


def test_tools_split_session_and_subagent_counts(client, session_with_subagent):
    response = client.get(f"/sessions/{session_with_subagent}/tools")

    assert response.status_code == 200
    rows = {t["tool_name"]: (t["count"], t["by_session"]) for t in response.json()}
    # The Analytics tab shows by_session; Overview shows count
    assert rows == {"Read": (1, 1), "Bash": (1, 0)}

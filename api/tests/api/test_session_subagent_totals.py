"""
Tests for the subagent usage totals in GET /sessions/{uuid}.
"""

import json
import os

import pytest
from fastapi.testclient import TestClient

from main import app

SESSION_UUID = "subagent-totals-session-uuid"


def _assistant_line(uuid: str, usage: dict) -> dict:
    return {
        "type": "assistant",
        "uuid": uuid,
        "timestamp": "2024-01-01T10:01:00Z",
        "message": {
            "id": f"msg_{uuid}",
            "role": "assistant",
            "model": "claude-sonnet-4-6",
            "content": [{"type": "text", "text": "ok"}],
            "usage": usage,
        },
    }


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def session_with_nested_subagents(mock_claude_base):
    """Session with a subagent that spawned its own subagent (stored flat, like Claude Code)."""
    project_dir = mock_claude_base / "projects" / "-Users-test-totalsproject"
    project_dir.mkdir(parents=True, exist_ok=True)
    (project_dir / f"{SESSION_UUID}.jsonl").write_text(
        json.dumps(_assistant_line("main-1", {"input_tokens": 100, "output_tokens": 10})) + "\n"
    )
    subagents_dir = project_dir / SESSION_UUID / "subagents"
    subagents_dir.mkdir(parents=True)
    (subagents_dir / "agent-a1.jsonl").write_text(
        json.dumps(
            _assistant_line(
                "sub-1",
                {"input_tokens": 200, "output_tokens": 20, "cache_read_input_tokens": 50},
            )
        )
        + "\n"
    )
    (subagents_dir / "agent-a2.jsonl").write_text(
        json.dumps(
            _assistant_line(
                "sub-2",
                {
                    "input_tokens": 300,
                    "output_tokens": 30,
                    "cache_creation_input_tokens": 40,
                    "cache_read_input_tokens": 60,
                },
            )
        )
        + "\n"
    )
    (subagents_dir / "agent-a2.meta.json").write_text(
        json.dumps({"parentAgentId": "a1", "spawnDepth": 2})
    )
    return SESSION_UUID


def test_session_detail_reports_subagent_totals(client, session_with_nested_subagents):
    response = client.get(f"/sessions/{session_with_nested_subagents}")

    assert response.status_code == 200
    data = response.json()
    # Own totals stay the session's own work
    assert data["total_input_tokens"] == 100
    assert data["total_output_tokens"] == 10
    # Subagent totals cover every depth
    assert data["subagent_input_tokens"] == 200 + 300 + 40
    assert data["subagent_output_tokens"] == 50
    assert data["subagent_cache_read_tokens"] == 110
    assert data["subagent_cost"] > 0


def test_session_detail_without_subagents_reports_zero(client, mock_claude_base):
    project_dir = mock_claude_base / "projects" / "-Users-test-totalsproject"
    project_dir.mkdir(parents=True, exist_ok=True)
    (project_dir / "no-subagents-uuid.jsonl").write_text(
        json.dumps(_assistant_line("main-1", {"input_tokens": 100, "output_tokens": 10})) + "\n"
    )

    data = client.get("/sessions/no-subagents-uuid").json()

    assert data["total_input_tokens"] == 100
    assert data["subagent_input_tokens"] == 0
    assert data["subagent_output_tokens"] == 0
    assert data["subagent_cache_read_tokens"] == 0
    assert data["subagent_cost"] == 0.0


def test_etag_changes_when_a_subagent_writes(
    client, session_with_nested_subagents, mock_claude_base
):
    # A subagent can run for minutes while the main JSONL sits idle
    first = client.get(f"/sessions/{session_with_nested_subagents}")
    etag = first.headers["etag"]

    subagent = (
        mock_claude_base
        / "projects"
        / "-Users-test-totalsproject"
        / SESSION_UUID
        / "subagents"
        / "agent-a2.jsonl"
    )
    stat = subagent.stat()
    os.utime(subagent, ns=(stat.st_atime_ns, stat.st_mtime_ns + 5_000_000_000))

    second = client.get(
        f"/sessions/{session_with_nested_subagents}", headers={"If-None-Match": etag}
    )
    assert second.status_code == 200
    assert second.headers["etag"] != etag

    third = client.get(
        f"/sessions/{session_with_nested_subagents}",
        headers={"If-None-Match": second.headers["etag"]},
    )
    assert third.status_code == 304

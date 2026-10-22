"""
Conditional requests on the lazily loaded session tabs: /timeline, /file-activity, /subagents.
"""

import json
import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from main import app

SESSION_UUID = "tab-etag-session-uuid"
ENDPOINTS = ["timeline", "file-activity", "subagents"]


def _lines() -> str:
    user = {
        "type": "user",
        "uuid": "u-1",
        "timestamp": "2024-01-01T10:00:00Z",
        "message": {"role": "user", "content": "Read the README"},
    }
    assistant = {
        "type": "assistant",
        "uuid": "a-1",
        "parentUuid": "u-1",
        "timestamp": "2024-01-01T10:00:05Z",
        "message": {
            "id": "msg_a1",
            "role": "assistant",
            "model": "claude-sonnet-4-6",
            "content": [
                {
                    "type": "tool_use",
                    "id": "toolu_1",
                    "name": "Read",
                    "input": {"file_path": "/repo/README.md"},
                }
            ],
            "usage": {"input_tokens": 10, "output_tokens": 5},
        },
    }
    return "\n".join(json.dumps(line) for line in (user, assistant)) + "\n"


def _bump_mtime(path: Path) -> None:
    stat = path.stat()
    os.utime(path, ns=(stat.st_atime_ns, stat.st_mtime_ns + 5_000_000_000))


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def session_files(mock_claude_base):
    project_dir = mock_claude_base / "projects" / "-Users-test-tabetags"
    project_dir.mkdir(parents=True, exist_ok=True)
    jsonl = project_dir / f"{SESSION_UUID}.jsonl"
    jsonl.write_text(_lines())
    subagents_dir = project_dir / SESSION_UUID / "subagents"
    subagents_dir.mkdir(parents=True)
    agent = subagents_dir / "agent-a1.jsonl"
    agent.write_text(_lines())
    return jsonl, agent


@pytest.mark.parametrize("endpoint", ENDPOINTS)
def test_matching_etag_returns_304(client, session_files, endpoint):
    url = f"/sessions/{SESSION_UUID}/{endpoint}"
    first = client.get(url)
    assert first.status_code == 200
    assert first.headers["etag"]
    assert first.headers["last-modified"]

    second = client.get(url, headers={"If-None-Match": first.headers["etag"]})
    assert second.status_code == 304
    assert second.content == b""


@pytest.mark.parametrize("endpoint", ENDPOINTS)
def test_touched_jsonl_returns_200_with_new_etag(client, session_files, endpoint):
    jsonl, _ = session_files
    url = f"/sessions/{SESSION_UUID}/{endpoint}"
    etag = client.get(url).headers["etag"]

    _bump_mtime(jsonl)
    second = client.get(url, headers={"If-None-Match": etag})

    assert second.status_code == 200
    assert second.headers["etag"] != etag
    assert second.json() == client.get(url).json()


@pytest.mark.parametrize("endpoint", ENDPOINTS)
def test_subagent_write_changes_etag(client, session_files, endpoint):
    _, agent = session_files
    url = f"/sessions/{SESSION_UUID}/{endpoint}"
    etag = client.get(url).headers["etag"]

    _bump_mtime(agent)
    second = client.get(url, headers={"If-None-Match": etag})

    assert second.status_code == 200
    assert second.headers["etag"] != etag


@pytest.mark.parametrize("endpoint", ENDPOINTS)
def test_fresh_keeps_one_second_cache_and_sees_changes(client, session_files, endpoint):
    jsonl, _ = session_files
    url = f"/sessions/{SESSION_UUID}/{endpoint}?fresh=1"
    first = client.get(url)
    assert "max-age=1" in first.headers["cache-control"]

    unchanged = client.get(url, headers={"If-None-Match": first.headers["etag"]})
    assert unchanged.status_code == 304

    _bump_mtime(jsonl)
    changed = client.get(url, headers={"If-None-Match": first.headers["etag"]})
    assert changed.status_code == 200
    assert changed.headers["etag"] != first.headers["etag"]


def test_payloads_survive_the_cache_headers(client, session_files):
    files = client.get(f"/sessions/{SESSION_UUID}/file-activity").json()
    assert {a["path"] for a in files} == {"/repo/README.md"}

    subagents = client.get(f"/sessions/{SESSION_UUID}/subagents").json()
    assert [s["agent_id"] for s in subagents] == ["a1"]

    timeline = client.get(f"/sessions/{SESSION_UUID}/timeline").json()
    assert any(e["event_type"] == "tool_call" for e in timeline)

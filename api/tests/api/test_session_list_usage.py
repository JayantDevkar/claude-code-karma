"""Every SQLite-backed session list returns tokens and cost incl. subagents."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_api_dir = Path(__file__).resolve().parent.parent.parent
if str(_api_dir) not in sys.path:
    sys.path.insert(0, str(_api_dir))

from fastapi import FastAPI
from fastapi.testclient import TestClient

_PROJECT = "-home-alice-proj-a"

_SESSION_COLS = (
    "uuid, project_encoded_name, project_path, jsonl_mtime, start_time, message_count, "
    "input_tokens, output_tokens, cache_read_tokens, cache_creation_tokens, total_cost, "
    "subagent_input_tokens, subagent_output_tokens, subagent_cache_read_tokens, "
    "subagent_cache_creation_tokens, subagent_cost"
)

# a1 has subagent usage; a2 has NULL subagent columns like rows from before they existed.
_SESSIONS = [
    ("a1", _PROJECT, "/home/alice/proj-a", 0.0, "2026-01-02T10:00:00+00:00", 4,
     1000, 100, 5000, 200, 1.5, 300, 30, 700, 50, 0.5),
    ("a2", _PROJECT, "/home/alice/proj-a", 0.0, "2026-01-01T10:00:00+00:00", 2,
     10, 5, 0, 0, 0.01, None, None, None, None, None),
]  # fmt: skip


@pytest.fixture
def client(tmp_path, monkeypatch):
    import db.connection as connection

    monkeypatch.setattr(connection, "get_db_path", lambda: tmp_path / "karma.db")
    connection._writer = None  # type: ignore[attr-defined]
    conn = connection.get_writer_db()

    import db.indexer as indexer

    monkeypatch.setattr(indexer, "is_db_ready", lambda: True)

    from config import settings

    monkeypatch.setattr(settings, "claude_base", tmp_path)
    (tmp_path / "projects" / _PROJECT).mkdir(parents=True)

    conn.execute(
        "INSERT INTO projects (encoded_name, project_path, session_count) VALUES (?, ?, ?)",
        (_PROJECT, "/home/alice/proj-a", 2),
    )
    conn.executemany(
        f"INSERT INTO sessions ({_SESSION_COLS}) VALUES ({','.join('?' * 16)})", _SESSIONS
    )
    conn.execute(
        "INSERT INTO session_skills (session_uuid, skill_name) VALUES ('a1', 'demo-skill')"
    )
    conn.execute(
        "INSERT INTO session_commands (session_uuid, command_name) VALUES ('a1', 'demo-cmd')"
    )
    conn.execute(
        "INSERT INTO subagent_invocations (session_uuid, agent_id, subagent_type)"
        " VALUES ('a1', 'agent-1', 'Explore')"
    )
    conn.executemany(
        "INSERT INTO session_tools (session_uuid, tool_name, count) VALUES ('a1', ?, 1)",
        [("mcp__demo__ping",), ("Read",)],
    )
    conn.commit()

    from routers import agents, commands, projects, sessions, skills, tools

    app = FastAPI()
    app.include_router(projects.router, prefix="/projects")
    app.include_router(sessions.router, prefix="/sessions")
    app.include_router(agents.router)
    app.include_router(skills.router)
    app.include_router(commands.router)
    app.include_router(tools.router, prefix="/tools")
    yield TestClient(app)

    connection._writer = None  # type: ignore[attr-defined]


@pytest.mark.parametrize(
    "endpoint",
    [
        "/sessions/all",
        f"/projects/{_PROJECT}",
        "/agents/usage/Explore/sessions",
        "/skills/demo-skill/sessions",
        "/skills/demo-skill/detail",
        "/commands/demo-cmd/detail",
        "/tools/demo",
        "/tools/demo/ping",
        "/tools/builtin-file-ops",
        "/tools/builtin-file-ops/Read",
    ],
)
def test_session_list_carries_usage(client, endpoint):
    response = client.get(endpoint)
    assert response.status_code == 200, response.text
    a1 = next(s for s in response.json()["sessions"] if s["uuid"] == "a1")

    # Cache writes are already inside input_tokens, so they are not added again.
    assert a1["tokens_with_subagents"] == 7130
    assert a1["cost_with_subagents"] == pytest.approx(2.0)


def test_null_subagent_columns_count_as_zero(client):
    sessions = client.get("/sessions/all").json()["sessions"]
    a2 = next(s for s in sessions if s["uuid"] == "a2")

    assert a2["tokens_with_subagents"] == 15
    assert a2["cost_with_subagents"] == pytest.approx(0.01)

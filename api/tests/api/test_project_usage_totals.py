"""GET /projects returns per-project tokens and cost from the SQLite index."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_api_dir = Path(__file__).resolve().parent.parent.parent
if str(_api_dir) not in sys.path:
    sys.path.insert(0, str(_api_dir))

from fastapi import FastAPI
from fastapi.testclient import TestClient

_SESSION_COLS = (
    "uuid, project_encoded_name, jsonl_mtime, start_time, input_tokens, output_tokens, "
    "cache_read_tokens, cache_creation_tokens, total_cost, subagent_input_tokens, "
    "subagent_output_tokens, subagent_cache_read_tokens, subagent_cache_creation_tokens, "
    "subagent_cost"
)

# a1 has subagent usage; a2 has NULL subagent columns like rows from before they existed.
_SESSIONS = [
    ("a1", "-home-alice-proj-a", 0.0, "2026-01-02T10:00:00+00:00",
     1000, 100, 5000, 200, 1.5, 300, 30, 700, 50, 0.5),
    ("a2", "-home-alice-proj-a", 0.0, "2026-01-01T10:00:00+00:00",
     10, 5, 0, 0, 0.01, None, None, None, None, None),
    ("b1", "-home-alice-proj-b", 0.0, "2026-01-03T10:00:00+00:00",
     7, 3, 0, 0, 0.2, 0, 0, 0, 0, 0),
]  # fmt: skip


@pytest.fixture
def client(tmp_path, monkeypatch):
    import db.connection as connection

    monkeypatch.setattr(connection, "get_db_path", lambda: tmp_path / "karma.db")
    connection._writer = None  # type: ignore[attr-defined]
    conn = connection.get_writer_db()

    import db.indexer as indexer

    monkeypatch.setattr(indexer, "is_db_ready", lambda: True)

    # proj-c is in projects but has no session rows.
    conn.executemany(
        "INSERT INTO projects (encoded_name, project_path, session_count) VALUES (?, ?, ?)",
        [
            ("-home-alice-proj-a", "/home/alice/proj-a", 2),
            ("-home-alice-proj-b", "/home/alice/proj-b", 1),
            ("-home-alice-proj-c", "/home/alice/proj-c", 0),
        ],
    )
    conn.executemany(
        f"INSERT INTO sessions ({_SESSION_COLS}) VALUES ({','.join('?' * 14)})", _SESSIONS
    )
    conn.commit()

    from routers import projects

    app = FastAPI()
    app.include_router(projects.router, prefix="/projects")
    yield TestClient(app)

    connection._writer = None  # type: ignore[attr-defined]


def test_list_projects_returns_usage_totals(client):
    by_name = {p["encoded_name"]: p for p in client.get("/projects").json()}

    # Cache writes are already inside input_tokens, so they are not added again.
    assert by_name["-home-alice-proj-a"]["total_tokens"] == 7145
    assert by_name["-home-alice-proj-a"]["total_cost"] == pytest.approx(2.01)
    assert by_name["-home-alice-proj-b"]["total_tokens"] == 10
    assert by_name["-home-alice-proj-b"]["total_cost"] == pytest.approx(0.2)
    assert by_name["-home-alice-proj-c"]["total_tokens"] == 0
    assert by_name["-home-alice-proj-c"]["total_cost"] == 0

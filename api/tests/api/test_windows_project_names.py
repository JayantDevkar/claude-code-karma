"""Windows project paths are named by their last folder, not shown in full."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_api_dir = Path(__file__).resolve().parent.parent.parent
if str(_api_dir) not in sys.path:
    sys.path.insert(0, str(_api_dir))

from fastapi import FastAPI
from fastapi.testclient import TestClient

WINDOWS_PATH = "C:\\Users\\me\\ClaudKarma"
ENCODED = "C--Users-me-ClaudKarma"


@pytest.fixture
def seeded_db(tmp_path, monkeypatch):
    """Fresh temp DB holding one session from a Windows project that used Bash."""
    import db.connection as connection
    import db.indexer as indexer

    monkeypatch.setattr(connection, "get_db_path", lambda: tmp_path / "karma.db")
    monkeypatch.setattr(indexer, "is_db_ready", lambda: True)
    connection._writer = None  # type: ignore[attr-defined]
    conn = connection.get_writer_db()
    conn.execute(
        "INSERT INTO sessions (uuid, project_encoded_name, project_path, jsonl_mtime, start_time)"
        " VALUES (?, ?, ?, ?, ?)",
        ("s1", ENCODED, WINDOWS_PATH, 0.0, "2026-10-01T10:00:00+00:00"),
    )
    conn.execute(
        "INSERT INTO session_tools (session_uuid, tool_name, count) VALUES (?, ?, ?)",
        ("s1", "Bash", 3),
    )
    conn.execute(
        "INSERT INTO projects (encoded_name, project_path, session_count) VALUES (?, ?, ?)",
        (ENCODED, WINDOWS_PATH, 1),
    )
    conn.commit()
    yield conn
    connection._writer = None  # type: ignore[attr-defined]


def test_tool_sessions_name_windows_project_by_folder(seeded_db):
    # Bug: split("/") left the whole Windows path as the session's project name.
    from routers import tools

    app = FastAPI()
    app.include_router(tools.router, prefix="/tools")
    resp = TestClient(app).get("/tools/builtin-execution/Bash")

    assert resp.status_code == 200
    assert [s["project_display_name"] for s in resp.json()["sessions"]] == ["ClaudKarma"]


def test_project_filter_names_windows_project_by_folder(seeded_db):
    # Bug: Path(x).name on a POSIX API host returned the whole synced Windows path.
    from db.queries import query_all_sessions

    options = query_all_sessions(seeded_db)["project_options"]

    assert [o["name"] for o in options] == ["ClaudKarma"]

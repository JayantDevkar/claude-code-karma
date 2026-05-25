"""
Router-level tests for api/routers/background_shells.py.

Uses FastAPI's TestClient + a temp SQLite DB (same pattern as
test_tickets.py). Data is seeded via raw SQL — extraction logic is
covered by test_indexer_shells_cron.py.
"""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import pytest

_tests_dir = Path(__file__).resolve().parent.parent
_api_dir = _tests_dir.parent
if str(_api_dir) not in sys.path:
    sys.path.insert(0, str(_api_dir))

from fastapi import FastAPI
from fastapi.testclient import TestClient


# ---------------------------------------------------------------------------
# Fixture
# ---------------------------------------------------------------------------


@pytest.fixture
def client(tmp_path, monkeypatch):
    """Spin up a FastAPI app with the background_shells router + fresh DB."""
    db_path = tmp_path / "test_karma.db"

    import db.connection as connection

    monkeypatch.setattr(connection, "get_db_path", lambda: db_path)
    connection._writer = None  # type: ignore[attr-defined]

    from db.connection import get_writer_db

    get_writer_db()

    import db.indexer as indexer

    monkeypatch.setattr(indexer, "is_db_ready", lambda: True)

    from routers import background_shells

    app = FastAPI()
    app.include_router(background_shells.router)

    yield TestClient(app)

    connection._writer = None  # type: ignore[attr-defined]


# ---------------------------------------------------------------------------
# Seeding helpers
# ---------------------------------------------------------------------------


def _seed_session(conn: sqlite3.Connection, uuid: str, project: str = "-test-proj") -> None:
    conn.execute(
        "INSERT OR IGNORE INTO sessions (uuid, project_encoded_name, jsonl_mtime) VALUES (?, ?, ?)",
        (uuid, project, 0.0),
    )


def _seed_shell(
    conn: sqlite3.Connection,
    *,
    session_uuid: str,
    tool_use_id: str = "toolu_1",
    tool_name: str = "Bash",
    command: str = "sleep 10 &",
    spawned_at: str = "2026-05-25T00:00:00Z",
    terminated_at: str | None = None,
    terminated_by: str | None = None,
) -> int:
    cur = conn.execute(
        """
        INSERT INTO background_shells
            (session_uuid, tool_use_id, tool_name, command, spawned_at,
             terminated_at, terminated_by)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (session_uuid, tool_use_id, tool_name, command, spawned_at,
         terminated_at, terminated_by),
    )
    return cur.lastrowid  # type: ignore[return-value]


def _seed_poll(
    conn: sqlite3.Connection,
    shell_row_id: int,
    tool_use_id: str = "toolu_poll_1",
    polled_at: str = "2026-05-25T00:01:00Z",
    output_bytes: int = 100,
) -> None:
    conn.execute(
        """
        INSERT INTO shell_polls
            (shell_row_id, tool_use_id, polled_at, output_bytes)
        VALUES (?, ?, ?, ?)
        """,
        (shell_row_id, tool_use_id, polled_at, output_bytes),
    )


def _writer(client_fixture) -> sqlite3.Connection:
    import db.connection as connection

    return connection.get_writer_db()


# ---------------------------------------------------------------------------
# GET /shells — empty + seeded
# ---------------------------------------------------------------------------


class TestListShellsGlobal:
    def test_empty_db_returns_empty_list(self, client):
        r = client.get("/shells")
        assert r.status_code == 200
        body = r.json()
        assert body["shells"] == []
        assert body["count"] == 0

    def test_seeded_returns_expected_count(self, client):
        conn = _writer(client)
        _seed_session(conn, "s1")
        _seed_shell(conn, session_uuid="s1", tool_use_id="toolu_a")
        _seed_shell(conn, session_uuid="s1", tool_use_id="toolu_b", tool_name="Monitor", command="watch ls")
        conn.commit()

        r = client.get("/shells")
        assert r.status_code == 200
        body = r.json()
        assert body["count"] == 2
        assert len(body["shells"]) == 2

    def test_seeded_includes_project_denormalization(self, client):
        conn = _writer(client)
        conn.execute(
            "INSERT OR IGNORE INTO projects (encoded_name, display_name, slug) VALUES (?, ?, ?)",
            ("-test-proj", "Test Project", "test-proj-1"),
        )
        _seed_session(conn, "s2", project="-test-proj")
        _seed_shell(conn, session_uuid="s2", tool_use_id="toolu_c")
        conn.commit()

        r = client.get("/shells")
        body = r.json()
        assert body["count"] >= 1
        row = next(s for s in body["shells"] if s["session_uuid"] == "s2")
        assert row["project_encoded_name"] == "-test-proj"
        assert row["project_display_name"] == "Test Project"

    def test_filter_by_project(self, client):
        conn = _writer(client)
        _seed_session(conn, "sa", project="-proj-a")
        _seed_session(conn, "sb", project="-proj-b")
        _seed_shell(conn, session_uuid="sa", tool_use_id="toolu_pa")
        _seed_shell(conn, session_uuid="sb", tool_use_id="toolu_pb")
        conn.commit()

        r = client.get("/shells?project=-proj-a")
        body = r.json()
        assert body["count"] == 1
        assert body["shells"][0]["session_uuid"] == "sa"

    def test_filter_status_running(self, client):
        conn = _writer(client)
        _seed_session(conn, "sr")
        _seed_shell(conn, session_uuid="sr", tool_use_id="toolu_run", spawned_at="2026-05-25T00:00:00Z")
        _seed_shell(
            conn,
            session_uuid="sr",
            tool_use_id="toolu_closed",
            spawned_at="2026-05-25T00:01:00Z",
            terminated_at="2026-05-25T00:05:00Z",
            terminated_by="natural",
        )
        conn.commit()

        r = client.get("/shells?status=running")
        body = r.json()
        assert all(s["terminated_at"] is None for s in body["shells"])
        assert body["count"] == 1

    def test_filter_status_closed(self, client):
        conn = _writer(client)
        _seed_session(conn, "sc")
        _seed_shell(conn, session_uuid="sc", tool_use_id="toolu_run2")
        _seed_shell(
            conn,
            session_uuid="sc",
            tool_use_id="toolu_closed2",
            terminated_at="2026-05-25T00:05:00Z",
            terminated_by="kill",
        )
        conn.commit()

        r = client.get("/shells?status=closed")
        body = r.json()
        assert all(s["terminated_at"] is not None for s in body["shells"])
        assert body["count"] == 1

    def test_filter_tool_bash(self, client):
        conn = _writer(client)
        _seed_session(conn, "st")
        _seed_shell(conn, session_uuid="st", tool_use_id="toolu_bash", tool_name="Bash")
        _seed_shell(conn, session_uuid="st", tool_use_id="toolu_mon", tool_name="Monitor", command="tail -f /var/log/syslog")
        conn.commit()

        r = client.get("/shells?tool=Bash")
        body = r.json()
        assert all(s["tool_name"] == "Bash" for s in body["shells"])

    def test_filter_tool_monitor(self, client):
        conn = _writer(client)
        _seed_session(conn, "sm")
        _seed_shell(conn, session_uuid="sm", tool_use_id="toolu_bash2", tool_name="Bash")
        _seed_shell(conn, session_uuid="sm", tool_use_id="toolu_mon2", tool_name="Monitor", command="tail -f /var/log/syslog")
        conn.commit()

        r = client.get("/shells?tool=Monitor")
        body = r.json()
        assert all(s["tool_name"] == "Monitor" for s in body["shells"])

    def test_invalid_status_returns_422(self, client):
        r = client.get("/shells?status=invalid")
        assert r.status_code == 422

    def test_limit_respected(self, client):
        conn = _writer(client)
        _seed_session(conn, "sl")
        for i in range(5):
            _seed_shell(conn, session_uuid="sl", tool_use_id=f"toolu_lim_{i}")
        conn.commit()

        r = client.get("/shells?limit=2")
        body = r.json()
        assert len(body["shells"]) == 2
        assert body["count"] == 2


# ---------------------------------------------------------------------------
# GET /shells/project-rollup
# ---------------------------------------------------------------------------


class TestShellsProjectRollup:
    def test_empty_db_returns_empty(self, client):
        r = client.get("/shells/project-rollup")
        assert r.status_code == 200
        body = r.json()
        assert body["projects"] == []
        assert body["count"] == 0

    def test_rollup_shape(self, client):
        conn = _writer(client)
        conn.execute(
            "INSERT OR IGNORE INTO projects (encoded_name, display_name, slug) VALUES (?, ?, ?)",
            ("-rp", "Rollup Project", "rollup-1"),
        )
        _seed_session(conn, "rp1", project="-rp")
        _seed_shell(conn, session_uuid="rp1", tool_use_id="toolu_rp1")
        _seed_shell(
            conn,
            session_uuid="rp1",
            tool_use_id="toolu_rp2",
            terminated_at="2026-05-25T01:00:00Z",
            terminated_by="natural",
        )
        conn.commit()

        r = client.get("/shells/project-rollup")
        body = r.json()
        assert body["count"] == 1
        row = body["projects"][0]
        assert row["project_encoded_name"] == "-rp"
        assert row["shell_count"] == 2
        assert row["running_count"] == 1
        assert "total_output_bytes" in row


# ---------------------------------------------------------------------------
# GET /sessions/{uuid}/shells
# ---------------------------------------------------------------------------


class TestSessionShells:
    def test_nonexistent_session_returns_404(self, client):
        r = client.get("/sessions/does-not-exist/shells")
        assert r.status_code == 404

    def test_session_with_no_shells_returns_empty(self, client):
        conn = _writer(client)
        _seed_session(conn, "empty-sess")
        conn.commit()

        r = client.get("/sessions/empty-sess/shells")
        assert r.status_code == 200
        body = r.json()
        assert body["shells"] == []
        assert body["count"] == 0
        assert body["session_uuid"] == "empty-sess"

    def test_includes_polls_by_default(self, client):
        conn = _writer(client)
        _seed_session(conn, "with-polls")
        shell_id = _seed_shell(conn, session_uuid="with-polls", tool_use_id="toolu_wp")
        _seed_poll(conn, shell_id, tool_use_id="toolu_poll_wp")
        conn.commit()

        r = client.get("/sessions/with-polls/shells")
        body = r.json()
        assert body["count"] == 1
        shell = body["shells"][0]
        assert "polls" in shell
        assert len(shell["polls"]) == 1

    def test_include_polls_false_omits_poll_key(self, client):
        conn = _writer(client)
        _seed_session(conn, "no-polls-flag")
        shell_id = _seed_shell(conn, session_uuid="no-polls-flag", tool_use_id="toolu_npf")
        _seed_poll(conn, shell_id, tool_use_id="toolu_poll_npf")
        conn.commit()

        r = client.get("/sessions/no-polls-flag/shells?include_polls=false")
        body = r.json()
        assert body["count"] == 1
        # With include_polls=False, the 'polls' key should not be set
        shell = body["shells"][0]
        assert "polls" not in shell

"""
Router-level tests for api/routers/cron.py.

Uses FastAPI's TestClient + a temp SQLite DB (same pattern as
test_tickets.py). Data is seeded via raw SQL — extraction logic is
covered by test_indexer_shells_cron.py.
"""

from __future__ import annotations

import sqlite3
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

_tests_dir = Path(__file__).resolve().parent.parent
_api_dir = _tests_dir.parent
if str(_api_dir) not in sys.path:
    sys.path.insert(0, str(_api_dir))

from fastapi import FastAPI
from fastapi.testclient import TestClient

# ---------------------------------------------------------------------------
# Time helpers
# ---------------------------------------------------------------------------

_FAR_FUTURE = "2099-01-01T00:00:00Z"
_FAR_PAST = "2020-01-01T00:00:00Z"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _ttl(delta_days: int = 7) -> str:
    dt = datetime.now(timezone.utc) + timedelta(days=delta_days)
    return dt.isoformat().replace("+00:00", "Z")


# ---------------------------------------------------------------------------
# Fixture
# ---------------------------------------------------------------------------


@pytest.fixture
def client(tmp_path, monkeypatch):
    """Spin up a FastAPI app with the cron router + fresh DB."""
    db_path = tmp_path / "test_karma.db"

    import db.connection as connection

    monkeypatch.setattr(connection, "get_db_path", lambda: db_path)
    connection._writer = None  # type: ignore[attr-defined]

    from db.connection import get_writer_db

    get_writer_db()

    import db.indexer as indexer

    monkeypatch.setattr(indexer, "is_db_ready", lambda: True)

    # Cron router uses settings.claude_base for fire inference; point at tmp.
    from config import settings

    monkeypatch.setattr(settings, "claude_base", tmp_path)

    from routers import cron

    app = FastAPI()
    app.include_router(cron.router)

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


def _seed_cron(
    conn: sqlite3.Connection,
    *,
    session_uuid: str,
    tool_use_id: str = "toolu_cron_1",
    cron_expression: str = "*/5 * * * *",
    prompt: str = "Check logs",
    recurring: int = 1,
    created_at: str | None = None,
    deleted_at: str | None = None,
    deleted_via: str | None = None,
    ttl_expires_at: str | None = None,
) -> int:
    created_at = created_at or _now_iso()
    ttl_expires_at = ttl_expires_at or _ttl(7)
    cur = conn.execute(
        """
        INSERT INTO cron_jobs
            (session_uuid, tool_use_id, cron_expression, prompt, recurring,
             created_at, deleted_at, deleted_via, ttl_expires_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (session_uuid, tool_use_id, cron_expression, prompt, recurring,
         created_at, deleted_at, deleted_via, ttl_expires_at),
    )
    return cur.lastrowid  # type: ignore[return-value]


def _writer(client_fixture) -> sqlite3.Connection:
    import db.connection as connection

    return connection.get_writer_db()


# ---------------------------------------------------------------------------
# GET /cron — empty + seeded
# ---------------------------------------------------------------------------


class TestListCronGlobal:
    def test_empty_db_returns_empty_list(self, client):
        r = client.get("/cron")
        assert r.status_code == 200
        body = r.json()
        assert body["jobs"] == []
        assert body["count"] == 0

    def test_seeded_returns_jobs_with_denormalization(self, client):
        conn = _writer(client)
        conn.execute(
            "INSERT OR IGNORE INTO projects (encoded_name, display_name, slug) VALUES (?, ?, ?)",
            ("-test-proj", "Test Project", "test-proj-slug"),
        )
        _seed_session(conn, "s1", project="-test-proj")
        _seed_cron(conn, session_uuid="s1", tool_use_id="toolu_c1")
        conn.commit()

        r = client.get("/cron")
        body = r.json()
        assert body["count"] == 1
        job = body["jobs"][0]
        assert job["session_uuid"] == "s1"
        assert job["project_encoded_name"] == "-test-proj"
        assert job["project_display_name"] == "Test Project"

    def test_filter_by_project(self, client):
        conn = _writer(client)
        _seed_session(conn, "sa", project="-proj-a")
        _seed_session(conn, "sb", project="-proj-b")
        _seed_cron(conn, session_uuid="sa", tool_use_id="toolu_ca")
        _seed_cron(conn, session_uuid="sb", tool_use_id="toolu_cb")
        conn.commit()

        r = client.get("/cron?project=-proj-a")
        body = r.json()
        assert body["count"] == 1
        assert body["jobs"][0]["session_uuid"] == "sa"

    def test_active_only_excludes_deleted_and_expired(self, client):
        conn = _writer(client)
        _seed_session(conn, "sact")
        # Active job
        _seed_cron(conn, session_uuid="sact", tool_use_id="toolu_active", ttl_expires_at=_ttl(7))
        # Deleted job
        _seed_cron(
            conn,
            session_uuid="sact",
            tool_use_id="toolu_deleted",
            deleted_at=_now_iso(),
            deleted_via="CronDelete",
            ttl_expires_at=_ttl(7),
        )
        # Expired job (TTL in the past)
        _seed_cron(conn, session_uuid="sact", tool_use_id="toolu_expired", ttl_expires_at=_FAR_PAST)
        conn.commit()

        r = client.get("/cron?active_only=true")
        body = r.json()
        assert body["count"] == 1
        assert body["jobs"][0]["tool_use_id"] == "toolu_active"

    def test_active_only_false_returns_all(self, client):
        conn = _writer(client)
        _seed_session(conn, "sall")
        _seed_cron(conn, session_uuid="sall", tool_use_id="toolu_all1", ttl_expires_at=_ttl(7))
        _seed_cron(
            conn,
            session_uuid="sall",
            tool_use_id="toolu_all2",
            deleted_at=_now_iso(),
            deleted_via="CronDelete",
            ttl_expires_at=_ttl(7),
        )
        conn.commit()

        r = client.get("/cron?active_only=false")
        body = r.json()
        assert body["count"] == 2

    def test_limit_respected(self, client):
        conn = _writer(client)
        _seed_session(conn, "slim")
        for i in range(5):
            _seed_cron(conn, session_uuid="slim", tool_use_id=f"toolu_lim_{i}")
        conn.commit()

        r = client.get("/cron?limit=2")
        body = r.json()
        assert len(body["jobs"]) == 2
        assert body["count"] == 2


# ---------------------------------------------------------------------------
# GET /cron/project-rollup
# ---------------------------------------------------------------------------


class TestCronProjectRollup:
    def test_empty_db_returns_empty(self, client):
        r = client.get("/cron/project-rollup")
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
        _seed_cron(conn, session_uuid="rp1", tool_use_id="toolu_rp1", ttl_expires_at=_ttl(7))
        _seed_cron(
            conn,
            session_uuid="rp1",
            tool_use_id="toolu_rp2",
            deleted_at=_now_iso(),
            deleted_via="CronDelete",
            ttl_expires_at=_ttl(7),
        )
        conn.commit()

        r = client.get("/cron/project-rollup")
        body = r.json()
        assert body["count"] == 1
        row = body["projects"][0]
        assert row["project_encoded_name"] == "-rp"
        assert row["cron_count"] == 2
        assert row["active_count"] == 1


# ---------------------------------------------------------------------------
# GET /sessions/{uuid}/cron
# ---------------------------------------------------------------------------


class TestSessionCron:
    def test_nonexistent_session_returns_404(self, client):
        r = client.get("/sessions/does-not-exist/cron")
        assert r.status_code == 404

    def test_session_with_no_cron_returns_empty(self, client):
        conn = _writer(client)
        _seed_session(conn, "empty-sess")
        conn.commit()

        r = client.get("/sessions/empty-sess/cron")
        assert r.status_code == 200
        body = r.json()
        assert body["jobs"] == []
        assert body["count"] == 0
        assert body["session_uuid"] == "empty-sess"

    def test_includes_fires_field_and_latest_state(self, client):
        conn = _writer(client)
        _seed_session(conn, "sess-fires")
        _seed_cron(conn, session_uuid="sess-fires", tool_use_id="toolu_f1")
        conn.commit()

        r = client.get("/sessions/sess-fires/cron")
        body = r.json()
        assert body["count"] == 1
        job = body["jobs"][0]
        assert "fires" in job
        assert isinstance(job["fires"], list)
        assert "latest_state" in job

    def test_include_fires_false_returns_empty_fires(self, client):
        conn = _writer(client)
        _seed_session(conn, "sess-nofire")
        _seed_cron(conn, session_uuid="sess-nofire", tool_use_id="toolu_nf")
        conn.commit()

        r = client.get("/sessions/sess-nofire/cron?include_fires=false")
        body = r.json()
        assert body["count"] == 1
        job = body["jobs"][0]
        assert job["fires"] == []

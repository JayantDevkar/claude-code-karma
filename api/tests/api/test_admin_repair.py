"""
Tests for the admin `repair-github-urls` endpoint.

This endpoint repairs the v0.1.x parser bug that stored every GitHub
ticket URL as `/issues/N` even when the ticket was a pull request. The
repair targets the unambiguous case: a github ticket with status='MERGED'
(unique to PRs) and a URL still pointing at `/issues/`. Open or
closed-unmerged PRs are NOT auto-detectable from status and will
self-heal when re-linked.
"""

import sys
from pathlib import Path

import pytest

_tests_dir = Path(__file__).resolve().parent.parent
_api_dir = _tests_dir.parent
if str(_api_dir) not in sys.path:
    sys.path.insert(0, str(_api_dir))

from fastapi import FastAPI
from fastapi.testclient import TestClient


@pytest.fixture
def client(tmp_path, monkeypatch):
    db_path = tmp_path / "test_karma.db"

    import db.connection as connection

    monkeypatch.setattr(connection, "get_db_path", lambda: db_path)
    connection._writer = None  # type: ignore[attr-defined]

    from db.connection import get_writer_db

    get_writer_db()

    from routers import admin

    app = FastAPI()
    app.include_router(admin.router)

    yield TestClient(app)

    connection._writer = None  # type: ignore[attr-defined]


def _insert_ticket(conn, *, provider, external_key, url, status):
    conn.execute(
        "INSERT INTO tickets (provider, external_key, url, status) VALUES (?, ?, ?, ?)",
        (provider, external_key, url, status),
    )
    conn.commit()


def test_repair_rewrites_merged_pr_with_issues_url(client):
    """The diagnostic case: status=MERGED proves it's a PR. Rewrite."""
    import db.connection as connection

    conn = connection.get_writer_db()
    _insert_ticket(
        conn,
        provider="github",
        external_key="octocat/repo#36",
        url="https://github.com/octocat/repo/issues/36",
        status="MERGED",
    )

    r = client.post("/admin/repair-github-urls")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["rewritten"] == 1

    new_url = conn.execute(
        "SELECT url FROM tickets WHERE external_key = ?",
        ("octocat/repo#36",),
    ).fetchone()["url"]
    assert new_url == "https://github.com/octocat/repo/pull/36"


def test_repair_leaves_unambiguous_issues_alone(client):
    """A closed/open issue (not status=MERGED) is not repaired — it
    truly is an issue, or we can't tell. Either way: don't touch."""
    import db.connection as connection

    conn = connection.get_writer_db()
    _insert_ticket(
        conn,
        provider="github",
        external_key="octocat/repo#10",
        url="https://github.com/octocat/repo/issues/10",
        status="open",
    )
    _insert_ticket(
        conn,
        provider="github",
        external_key="octocat/repo#11",
        url="https://github.com/octocat/repo/issues/11",
        status="closed",
    )

    r = client.post("/admin/repair-github-urls")
    assert r.json()["rewritten"] == 0

    rows = conn.execute("SELECT external_key, url FROM tickets ORDER BY external_key").fetchall()
    assert all("/issues/" in r["url"] for r in rows)


def test_repair_is_idempotent(client):
    """Run twice; second run finds nothing to repair (URLs already
    rewritten to /pull/) and reports 0."""
    import db.connection as connection

    conn = connection.get_writer_db()
    _insert_ticket(
        conn,
        provider="github",
        external_key="octocat/repo#36",
        url="https://github.com/octocat/repo/issues/36",
        status="MERGED",
    )

    assert client.post("/admin/repair-github-urls").json()["rewritten"] == 1
    assert client.post("/admin/repair-github-urls").json()["rewritten"] == 0


def test_repair_does_not_touch_linear_or_jira(client):
    """The endpoint is github-specific. Linear/Jira rows with /issues/
    paths in their URLs (which doesn't happen in practice but could) are
    left alone."""
    import db.connection as connection

    conn = connection.get_writer_db()
    _insert_ticket(
        conn,
        provider="linear",
        external_key="ABC-1",
        # Pathological: a Linear URL that happens to contain /issues/.
        # The repair query is restricted to provider='github' so this
        # row should be untouched.
        url="https://linear.app/team/issue/ABC-1",
        status="Done",
    )

    r = client.post("/admin/repair-github-urls")
    assert r.json()["rewritten"] == 0

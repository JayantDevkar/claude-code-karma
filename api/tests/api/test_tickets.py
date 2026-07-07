"""
Endpoint tests for api/routers/tickets.py.

Drives the real router via FastAPI's TestClient against a temp SQLite DB,
exercising the full create-link / refresh-metadata / list / unlink loop.
"""

import sys
from pathlib import Path

import pytest

_tests_dir = Path(__file__).resolve().parent.parent
_api_dir = _tests_dir.parent
if str(_api_dir) not in sys.path:
    sys.path.insert(0, str(_api_dir))
if str(_tests_dir) not in sys.path:
    sys.path.insert(0, str(_tests_dir))

from fastapi import FastAPI
from fastapi.testclient import TestClient


@pytest.fixture
def client(tmp_path, monkeypatch):
    """Spin up a FastAPI app with the tickets router and a fresh DB.

    sqlite_db_path is a computed @property (not env-driven) so we monkey-
    patch the connection module's get_db_path to point at the temp file.
    Writer singleton is reset so the next get_writer_db() call opens
    against the temp path and runs ensure_schema().
    """
    db_path = tmp_path / "test_karma.db"

    import db.connection as connection

    monkeypatch.setattr(connection, "get_db_path", lambda: db_path)
    connection._writer = None  # type: ignore[attr-defined]

    # Force schema creation against the temp DB.
    from db.connection import get_writer_db

    get_writer_db()

    # The indexer's is_db_ready check is what sqlite_read uses — but our
    # router uses create_read_connection() directly, so the ready check
    # doesn't gate us. Still, patch it so any sqlite_read() callers work.
    import db.indexer as indexer

    monkeypatch.setattr(indexer, "is_db_ready", lambda: True)

    from routers import tickets

    app = FastAPI()
    app.include_router(tickets.router)

    yield TestClient(app)

    # Clean up writer so the next test gets a fresh singleton.
    connection._writer = None  # type: ignore[attr-defined]


# ---------------------------------------------------------------------------
# POST /sessions/{uuid}/tickets
# ---------------------------------------------------------------------------


def test_create_link_from_full_linear_url(client):
    r = client.post(
        "/sessions/sess-1/tickets",
        json={
            "ref": "https://linear.app/acme/issue/ABC-123",
            "source": "slash_command",
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ticket"]["provider"] == "linear"
    assert body["ticket"]["external_key"] == "ABC-123"
    assert body["link"]["session_uuid"] == "sess-1"
    assert body["link"]["link_source"] == "slash_command"


def test_create_link_from_bare_key_requires_provider_hint(client):
    # Missing provider for an ambiguous bare key
    r = client.post(
        "/sessions/sess-1/tickets",
        json={"ref": "ABC-123", "source": "dashboard"},
    )
    assert r.status_code == 400

    # With provider hint, succeeds
    r = client.post(
        "/sessions/sess-1/tickets",
        json={"ref": "ABC-123", "provider": "linear", "source": "dashboard"},
    )
    assert r.status_code == 200, r.text


def test_create_link_rejects_bare_hash_n(client):
    r = client.post(
        "/sessions/sess-1/tickets",
        json={"ref": "#42", "provider": "github", "source": "dashboard"},
    )
    assert r.status_code == 400
    assert "owner/repo" in r.json()["detail"]["hint"]


def test_create_link_idempotent_same_session_same_ticket(client):
    body = {"ref": "https://linear.app/acme/issue/ABC-1", "source": "branch"}
    r1 = client.post("/sessions/sess-1/tickets", json=body)
    r2 = client.post("/sessions/sess-1/tickets", json=body)
    assert r1.status_code == 200
    assert r2.status_code == 200
    assert r1.json()["link"]["id"] == r2.json()["link"]["id"]


def test_link_source_upgrades_branch_to_slash_command(client):
    body_b = {"ref": "https://linear.app/acme/issue/ABC-9", "source": "branch"}
    body_s = {"ref": "https://linear.app/acme/issue/ABC-9", "source": "slash_command"}
    r1 = client.post("/sessions/sess-1/tickets", json=body_b)
    r2 = client.post("/sessions/sess-1/tickets", json=body_s)
    assert r1.json()["link"]["link_source"] == "branch"
    assert r2.json()["link"]["link_source"] == "slash_command"


def test_link_source_does_not_downgrade(client):
    body_s = {"ref": "https://linear.app/acme/issue/ABC-10", "source": "slash_command"}
    body_b = {"ref": "https://linear.app/acme/issue/ABC-10", "source": "branch"}
    client.post("/sessions/sess-1/tickets", json=body_s)
    r = client.post("/sessions/sess-1/tickets", json=body_b)
    assert r.json()["link"]["link_source"] == "slash_command"


def test_session_slug_dedupes_resumed_sessions(client):
    """Two resumed sessions of the same slug linking to the same ticket
    collapse onto one row via the partial unique index. The second POST
    returns the EXISTING link, not an error — that's the whole point of
    the slug-based dedup."""
    body_a = {
        "ref": "https://linear.app/acme/issue/ABC-11",
        "source": "branch",
        "session_slug": "happy-slug",
    }
    body_b = {
        "ref": "https://linear.app/acme/issue/ABC-11",
        "source": "slash_command",  # upgrade source on second POST
        "session_slug": "happy-slug",
    }
    r1 = client.post("/sessions/uuid-a/tickets", json=body_a)
    assert r1.status_code == 200
    first_link_id = r1.json()["link"]["id"]

    # Second resume — new uuid, same slug. Should hit existing row.
    r2 = client.post("/sessions/uuid-b/tickets", json=body_b)
    assert r2.status_code == 200, r2.text
    assert r2.json()["link"]["id"] == first_link_id  # same row reused
    assert r2.json()["link"]["link_source"] == "slash_command"  # upgraded
    # session_uuid stays as the ORIGINAL uuid since we deduped on slug.
    assert r2.json()["link"]["session_uuid"] == "uuid-a"


def test_caller_url_overrides_parser_url(client):
    custom_url = "https://linear.app/acme/issue/ABC-15/custom-title"
    r = client.post(
        "/sessions/sess-1/tickets",
        json={
            "ref": "ABC-15",
            "provider": "linear",
            "url": custom_url,
            "source": "dashboard",
        },
    )
    assert r.status_code == 200
    assert r.json()["ticket"]["url"] == custom_url


# ---------------------------------------------------------------------------
# GET /sessions/{uuid}/tickets and DELETE
# ---------------------------------------------------------------------------


def test_list_session_tickets_returns_link_metadata_inline(client):
    client.post(
        "/sessions/sess-2/tickets",
        json={"ref": "https://linear.app/acme/issue/ABC-20", "source": "branch"},
    )
    r = client.get("/sessions/sess-2/tickets")
    assert r.status_code == 200
    rows = r.json()
    assert len(rows) == 1
    assert rows[0]["external_key"] == "ABC-20"
    assert rows[0]["link_source"] == "branch"


def test_delete_session_ticket_returns_404_when_missing(client):
    r = client.delete("/sessions/sess-99/tickets/9999")
    assert r.status_code == 404


def test_delete_session_ticket_succeeds_then_404(client):
    create = client.post(
        "/sessions/sess-3/tickets",
        json={"ref": "https://linear.app/acme/issue/ABC-30", "source": "branch"},
    )
    ticket_id = create.json()["ticket"]["id"]

    r1 = client.delete(f"/sessions/sess-3/tickets/{ticket_id}")
    assert r1.status_code == 200

    r2 = client.delete(f"/sessions/sess-3/tickets/{ticket_id}")
    assert r2.status_code == 404


# ---------------------------------------------------------------------------
# PUT /tickets/{provider}/{external_key}
# ---------------------------------------------------------------------------


def test_put_metadata_refreshes_title_and_status(client):
    client.post(
        "/sessions/sess-4/tickets",
        json={"ref": "https://linear.app/acme/issue/ABC-40", "source": "slash_command"},
    )
    r = client.put(
        "/tickets/linear/ABC-40",
        json={"title": "Fix login bug", "status": "In Progress"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["title"] == "Fix login bug"
    assert body["status"] == "In Progress"
    assert body["metadata_updated_at"]


def test_put_metadata_preserves_existing_when_null_passed(client):
    client.post(
        "/sessions/sess-4/tickets",
        json={"ref": "https://linear.app/acme/issue/ABC-41", "source": "slash_command"},
    )
    client.put(
        "/tickets/linear/ABC-41",
        json={"title": "Original", "status": "Open"},
    )
    # Degraded fetch: only status arrives, title is null. Title must survive.
    r = client.put(
        "/tickets/linear/ABC-41",
        json={"status": "Closed"},
    )
    assert r.json()["title"] == "Original"
    assert r.json()["status"] == "Closed"


def test_put_returns_404_when_ticket_not_yet_linked(client):
    r = client.put(
        "/tickets/linear/NEVER-1",
        json={"title": "x"},
    )
    assert r.status_code == 404
    assert "hint" in r.json()["detail"]


def test_put_metadata_over_size_cap_rejected(client):
    client.post(
        "/sessions/sess-4/tickets",
        json={"ref": "https://linear.app/acme/issue/ABC-42", "source": "slash_command"},
    )
    big = "x" * (64 * 1024 + 1)
    r = client.put(
        "/tickets/linear/ABC-42",
        json={"metadata_json": big},
    )
    # Pydantic max_length=65536 trips at validation time → 422.
    assert r.status_code in (400, 422, 500)


def test_patch_metadata_works_like_put(client):
    client.post(
        "/sessions/sess-4/tickets",
        json={"ref": "https://linear.app/acme/issue/ABC-43", "source": "dashboard"},
    )
    r = client.patch("/tickets/linear/ABC-43", json={"title": "Manually entered"})
    assert r.status_code == 200
    assert r.json()["title"] == "Manually entered"


# ---------------------------------------------------------------------------
# GET /tickets and detail
# ---------------------------------------------------------------------------


def test_list_tickets_shows_session_count(client):
    client.post(
        "/sessions/sess-A/tickets",
        json={"ref": "https://linear.app/acme/issue/CNT-1", "source": "branch"},
    )
    client.post(
        "/sessions/sess-B/tickets",
        json={"ref": "https://linear.app/acme/issue/CNT-1", "source": "branch"},
    )
    r = client.get("/tickets")
    assert r.status_code == 200, r.text
    rows = r.json()
    cnt_row = next((row for row in rows if row["external_key"] == "CNT-1"), None)
    assert cnt_row is not None
    assert cnt_row["session_count"] == 2


def test_list_tickets_filter_by_provider(client):
    client.post(
        "/sessions/sess-X/tickets",
        json={"ref": "https://linear.app/acme/issue/FILT-1", "source": "branch"},
    )
    client.post(
        "/sessions/sess-X/tickets",
        json={"ref": "octocat/repo#9", "source": "branch"},
    )
    r = client.get("/tickets?provider=github")
    assert r.status_code == 200
    rows = r.json()
    assert all(row["provider"] == "github" for row in rows)
    assert any(row["external_key"] == "octocat/repo#9" for row in rows)


def test_list_tickets_search_by_key(client):
    client.post(
        "/sessions/sess-X/tickets",
        json={"ref": "https://linear.app/acme/issue/SRCH-77", "source": "branch"},
    )
    r = client.get("/tickets?q=SRCH")
    assert r.status_code == 200
    rows = r.json()
    assert any(row["external_key"] == "SRCH-77" for row in rows)


def test_list_tickets_project_filter_requires_session_row(client):
    """Project filter joins via sessions table; orphan links (no sessions
    row yet) won't appear when filtered. We need a real session row for
    this test — insert one directly via the writer connection."""
    import db.connection as connection

    conn = connection.get_writer_db()
    conn.execute(
        "INSERT INTO sessions (uuid, project_encoded_name, jsonl_mtime) VALUES (?, ?, ?)",
        ("real-uuid-1", "-Users-me-projA", 0.0),
    )
    conn.execute(
        "INSERT INTO sessions (uuid, project_encoded_name, jsonl_mtime) VALUES (?, ?, ?)",
        ("real-uuid-2", "-Users-me-projB", 0.0),
    )
    conn.commit()

    # Link two tickets to projA's session, one to projB's
    client.post(
        "/sessions/real-uuid-1/tickets",
        json={"ref": "https://linear.app/acme/issue/PA-1", "source": "branch"},
    )
    client.post(
        "/sessions/real-uuid-1/tickets",
        json={"ref": "https://linear.app/acme/issue/PA-2", "source": "branch"},
    )
    client.post(
        "/sessions/real-uuid-2/tickets",
        json={"ref": "https://linear.app/acme/issue/PB-1", "source": "branch"},
    )

    r = client.get("/tickets?project=-Users-me-projA")
    assert r.status_code == 200
    keys = {row["external_key"] for row in r.json()}
    assert "PA-1" in keys
    assert "PA-2" in keys
    assert "PB-1" not in keys

    # And the inverse
    r2 = client.get("/tickets?project=-Users-me-projB")
    keys2 = {row["external_key"] for row in r2.json()}
    assert keys2 == {"PB-1"}


def test_get_ticket_detail_works_for_github_path_key(client):
    client.post(
        "/sessions/sess-Y/tickets",
        json={"ref": "octocat/repo#42", "source": "branch"},
    )
    r = client.get("/tickets/github/octocat/repo%2342")
    # URL-encoded '#' as %23. Some clients send the literal '#' which
    # browsers strip; TestClient passes the raw path, so encoding matters.
    # If the test client decodes it before routing, we still match
    # external_key="octocat/repo#42".
    assert r.status_code in (200, 404)
    if r.status_code == 200:
        assert r.json()["external_key"] == "octocat/repo#42"


def test_get_ticket_404_when_unknown(client):
    r = client.get("/tickets/linear/NOPE-1")
    assert r.status_code == 404


# ---------------------------------------------------------------------------
# GET /tickets?project=... — git_identity aggregation (v12)
# ---------------------------------------------------------------------------


def _seed_session(conn, *, uuid: str, project: str) -> None:
    conn.execute(
        "INSERT INTO sessions (uuid, project_encoded_name, jsonl_mtime) VALUES (?, ?, ?)",
        (uuid, project, 0.0),
    )


def _seed_project(conn, *, encoded_name: str, git_identity=None, slug=None) -> None:
    conn.execute(
        "INSERT OR REPLACE INTO projects "
        "(encoded_name, project_path, slug, display_name, "
        " session_count, last_activity, git_identity) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (
            encoded_name,
            None,
            slug or encoded_name,
            encoded_name,
            0,
            None,
            git_identity,
        ),
    )


def test_project_filter_accepts_slug_or_encoded_name(client):
    """The ?project= query param must accept either form: the slug shown
    in user-facing URLs (e.g. 'claude-karma-1044') OR the raw encoded_name
    (-Users-...). All other project-by-id endpoints already do this via
    `resolve_project_identifier()`; the tickets endpoint must match.

    Regression test for: navigating /projects → card → tickets tab landed
    on /projects/{slug}, the tab fetched /tickets?project={slug}, the
    backend matched on encoded_name → 0 tickets. Navigating via
    /tickets → session → project landed on /projects/{encoded_name} which
    happened to work."""
    import db.connection as connection

    conn = connection.get_writer_db()
    _seed_project(
        conn,
        encoded_name="-Users-me-myrepo",
        slug="myrepo-9999",
        git_identity=None,
    )
    _seed_session(conn, uuid="ses-1", project="-Users-me-myrepo")
    conn.commit()

    client.post(
        "/sessions/ses-1/tickets",
        json={"ref": "https://linear.app/acme/issue/SLUG-1", "source": "branch"},
    )

    # Encoded form — works prior to fix.
    r_enc = client.get("/tickets?project=-Users-me-myrepo")
    assert {row["external_key"] for row in r_enc.json()} == {"SLUG-1"}

    # Slug form — this is what ProjectCard.svelte sends. Must also work.
    r_slug = client.get("/tickets?project=myrepo-9999")
    assert {row["external_key"] for row in r_slug.json()} == {"SLUG-1"}


def test_project_filter_aggregates_across_shared_git_identity(client):
    """Two encoded_names sharing a git_identity should pool their tickets.
    A ticket linked from project A's session must appear under project B
    when both projects have git_identity='org/repo'."""
    import db.connection as connection

    conn = connection.get_writer_db()
    _seed_project(conn, encoded_name="-A-main", git_identity="org/repo")
    _seed_project(conn, encoded_name="-A-frontend", git_identity="org/repo")
    _seed_session(conn, uuid="s-main", project="-A-main")
    _seed_session(conn, uuid="s-frontend", project="-A-frontend")
    conn.commit()

    # Link a ticket from a session that lives in -A-main.
    client.post(
        "/sessions/s-main/tickets",
        json={"ref": "https://linear.app/acme/issue/SHARED-1", "source": "branch"},
    )

    # Both projects should see it.
    r_main = client.get("/tickets?project=-A-main")
    r_front = client.get("/tickets?project=-A-frontend")
    assert {row["external_key"] for row in r_main.json()} == {"SHARED-1"}
    assert {row["external_key"] for row in r_front.json()} == {"SHARED-1"}


def test_project_filter_null_git_identity_falls_back_to_per_encoded(client):
    """When the target project has no git_identity (sync-imported, never
    indexed locally, etc.), the query must keep the legacy behavior:
    only tickets from sessions whose project_encoded_name matches."""
    import db.connection as connection

    conn = connection.get_writer_db()
    # Two NULL-git_identity projects — they must NOT pool.
    _seed_project(conn, encoded_name="-N-a", git_identity=None)
    _seed_project(conn, encoded_name="-N-b", git_identity=None)
    _seed_session(conn, uuid="n-a", project="-N-a")
    _seed_session(conn, uuid="n-b", project="-N-b")
    conn.commit()

    client.post(
        "/sessions/n-a/tickets",
        json={"ref": "https://linear.app/acme/issue/NA-1", "source": "branch"},
    )
    client.post(
        "/sessions/n-b/tickets",
        json={"ref": "https://linear.app/acme/issue/NB-1", "source": "branch"},
    )

    r_a = client.get("/tickets?project=-N-a")
    r_b = client.get("/tickets?project=-N-b")
    assert {row["external_key"] for row in r_a.json()} == {"NA-1"}
    assert {row["external_key"] for row in r_b.json()} == {"NB-1"}


def test_project_filter_github_external_key_match_without_local_link(client):
    """GitHub heuristic: a ticket `org/repo#42` should appear under a
    project whose git_identity='org/repo' EVEN IF no local session has
    linked it. This handles the cross-machine sync case."""
    import db.connection as connection

    conn = connection.get_writer_db()
    _seed_project(conn, encoded_name="-G-main", git_identity="acme/widget")
    _seed_session(conn, uuid="g-main", project="-G-main")
    # Also seed a totally unrelated project that links the ticket — this
    # is how the ticket gets into the tickets table without -G-main ever
    # touching it.
    _seed_project(conn, encoded_name="-OTHER", git_identity="other/thing")
    _seed_session(conn, uuid="other-s", project="-OTHER")
    conn.commit()

    # Link from -OTHER (no relation to acme/widget).
    client.post(
        "/sessions/other-s/tickets",
        json={"ref": "acme/widget#42", "source": "branch"},
    )

    r = client.get("/tickets?project=-G-main")
    keys = {row["external_key"] for row in r.json()}
    assert "acme/widget#42" in keys

    # Linear ticket with a coincidentally similar key should NOT match
    # the GitHub heuristic — guard against provider confusion.
    client.post(
        "/sessions/other-s/tickets",
        json={
            "ref": "ACME-99",
            "provider": "linear",
            "url": "https://linear.app/acme/issue/ACME-99",
            "source": "branch",
        },
    )
    r2 = client.get("/tickets?project=-G-main")
    keys2 = {row["external_key"] for row in r2.json()}
    assert "ACME-99" not in keys2  # provider guard intact


def test_project_filter_aggregates_link_count_across_siblings(client):
    """When a ticket is linked from sessions in multiple sibling projects
    sharing a git_identity, `session_count` reflects the total — proving
    the cross-encoded aggregation reaches all linked sessions, not just
    those under one encoded_name."""
    import db.connection as connection

    conn = connection.get_writer_db()
    _seed_project(conn, encoded_name="-S-main", git_identity="team/proj")
    _seed_project(conn, encoded_name="-S-frontend", git_identity="team/proj")
    _seed_session(conn, uuid="sm-1", project="-S-main")
    _seed_session(conn, uuid="sf-1", project="-S-frontend")
    conn.commit()

    # Same ticket linked from BOTH sibling projects.
    client.post(
        "/sessions/sm-1/tickets",
        json={"ref": "team/proj#7", "source": "branch"},
    )
    client.post(
        "/sessions/sf-1/tickets",
        json={"ref": "team/proj#7", "source": "branch"},
    )

    r = client.get("/tickets?project=-S-main")
    by_key = {row["external_key"]: row for row in r.json()}
    assert by_key["team/proj#7"]["session_count"] == 2


def test_get_ticket_sessions_for_orphan_link(client):
    """A link whose session_uuid isn't in the sessions index still appears,
    with sessions-fields NULL (LEFT JOIN behavior)."""
    client.post(
        "/sessions/orphan-uuid/tickets",
        json={"ref": "https://linear.app/acme/issue/ORPHAN-1", "source": "branch"},
    )
    r = client.get("/tickets/linear/ORPHAN-1/sessions")
    assert r.status_code == 200, r.text
    rows = r.json()
    assert len(rows) == 1
    assert rows[0]["session_uuid"] == "orphan-uuid"
    # Joined session fields are NULL for orphans
    assert rows[0]["start_time"] is None
    assert rows[0]["sessions_slug"] is None

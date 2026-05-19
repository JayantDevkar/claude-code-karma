"""
Schema migration tests for v11 (tickets + session_tickets) and forward.

Verifies that:
 1. Fresh install (current_version == 0) applies SCHEMA_SQL and both
    ticket tables + indices + CHECK constraints exist.
 2. v10 → v11 upgrade applies the incremental migration block.
 3. Replay is idempotent (no-op).

Version assertions use the live `SCHEMA_VERSION` constant rather than
literals so future migrations (v12+) don't require touching this file.
"""

import sqlite3
import sys
from pathlib import Path

import pytest

_api_dir = Path(__file__).resolve().parent.parent
if str(_api_dir) not in sys.path:
    sys.path.insert(0, str(_api_dir))

from db.schema import SCHEMA_VERSION, ensure_schema


def _make_db() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (name,),
    ).fetchone()
    return row is not None


def _index_exists(conn: sqlite3.Connection, name: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='index' AND name=?",
        (name,),
    ).fetchone()
    return row is not None


def _get_version(conn: sqlite3.Connection) -> int:
    return conn.execute("SELECT MAX(version) FROM schema_version").fetchone()[0]


def test_schema_version_is_at_least_eleven():
    # v11 introduced the ticket tables this test file covers.
    # Higher versions are fine — they layer on top.
    assert SCHEMA_VERSION >= 11


def test_fresh_install_creates_both_ticket_tables():
    conn = _make_db()
    ensure_schema(conn)

    assert _table_exists(conn, "tickets")
    assert _table_exists(conn, "session_tickets")
    assert _index_exists(conn, "idx_tickets_provider")
    assert _index_exists(conn, "idx_session_tickets_session")
    assert _index_exists(conn, "idx_session_tickets_slug")
    assert _index_exists(conn, "idx_session_tickets_ticket")
    assert _index_exists(conn, "uniq_session_tickets_slug_ticket")
    assert _get_version(conn) == SCHEMA_VERSION


def test_fresh_install_check_constraints_fire():
    conn = _make_db()
    ensure_schema(conn)

    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO tickets (provider, external_key, url) VALUES (?, ?, ?)",
            ("bitbucket", "X-1", "https://example.com"),  # not in CHECK whitelist
        )

    # metadata_json size cap (just over 64 KB)
    too_big = "x" * (64 * 1024 + 1)
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO tickets (provider, external_key, url, metadata_json) VALUES (?, ?, ?, ?)",
            ("linear", "ABC-1", "https://linear.app/x/issue/ABC-1", too_big),
        )


def test_link_source_check_constraint_fires():
    conn = _make_db()
    ensure_schema(conn)
    ticket_id = conn.execute(
        "INSERT INTO tickets (provider, external_key, url) VALUES (?, ?, ?) RETURNING id",
        ("linear", "ABC-1", "https://linear.app/x/issue/ABC-1"),
    ).fetchone()["id"]

    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO session_tickets (session_uuid, ticket_id, link_source) VALUES (?, ?, ?)",
            ("sess-1", ticket_id, "magic"),
        )


def test_migration_from_v10_creates_ticket_tables():
    """Simulate an existing v10 install upgrading to v11."""
    conn = _make_db()

    # Build the minimum needed to pass ensure_schema's incremental path:
    # a schema_version row at v10 and the tables that earlier migrations
    # reference. We only need the schema_version row — the v11 step
    # references no prior tables for its CREATE work.
    conn.execute(
        "CREATE TABLE IF NOT EXISTS schema_version "
        "(version INTEGER PRIMARY KEY, applied_at TEXT DEFAULT (datetime('now')))"
    )
    conn.execute("INSERT INTO schema_version (version) VALUES (10)")
    conn.commit()

    assert not _table_exists(conn, "tickets")
    assert not _table_exists(conn, "session_tickets")

    ensure_schema(conn)

    assert _table_exists(conn, "tickets")
    assert _table_exists(conn, "session_tickets")
    assert _index_exists(conn, "uniq_session_tickets_slug_ticket")
    assert _get_version(conn) == SCHEMA_VERSION


def test_replay_is_idempotent():
    conn = _make_db()
    ensure_schema(conn)
    ensure_schema(conn)  # should not raise

    assert _get_version(conn) == SCHEMA_VERSION
    # Tables still exist
    assert _table_exists(conn, "tickets")
    assert _table_exists(conn, "session_tickets")


def test_ensure_schema_creates_ticket_tables_on_cross_branch_higher_version():
    """Regression test for the live-meta-test bug.

    A karma DB used on a parallel branch may have its schema_version
    advanced past ours (e.g., 22 because that branch added different
    tables). The version-gated early-return in ensure_schema() then
    skips our v10 → v11 migration block, leaving the ticket tables
    missing and every ticket endpoint 500'ing.

    Fix: unconditional `executescript(_TICKETS_SCHEMA_SQL)` at the top
    of ensure_schema() guarantees our tables exist regardless of
    version-tracking drift across branches.
    """
    conn = _make_db()

    # Simulate a karma DB at v99 from a parallel branch.
    conn.execute(
        "CREATE TABLE IF NOT EXISTS schema_version "
        "(version INTEGER PRIMARY KEY, applied_at TEXT DEFAULT (datetime('now')))"
    )
    conn.execute("INSERT INTO schema_version (version) VALUES (99)")
    conn.commit()

    assert not _table_exists(conn, "tickets")
    assert not _table_exists(conn, "session_tickets")

    ensure_schema(conn)

    # Tables must be present even though we never ran our v11 migration block.
    assert _table_exists(conn, "tickets")
    assert _table_exists(conn, "session_tickets")
    assert _index_exists(conn, "uniq_session_tickets_slug_ticket")

    # Version is NOT bumped — we never tried to migrate from v99 to v11.
    # The recorded version stays at 99 because the unconditional path
    # only creates missing tables; it doesn't pretend we ran a migration.
    assert _get_version(conn) == 99


def test_partial_unique_index_dedupes_by_slug_when_present():
    conn = _make_db()
    ensure_schema(conn)
    ticket_id = conn.execute(
        "INSERT INTO tickets (provider, external_key, url) VALUES (?, ?, ?) RETURNING id",
        ("linear", "ABC-1", "https://linear.app/x/issue/ABC-1"),
    ).fetchone()["id"]

    # First resume — slug populated
    conn.execute(
        "INSERT INTO session_tickets (session_uuid, session_slug, ticket_id, link_source) "
        "VALUES (?, ?, ?, ?)",
        ("uuid-a", "happy-slug", ticket_id, "branch"),
    )
    # Second resume of the SAME slug to the SAME ticket — should fail
    # the partial unique index even though session_uuid differs.
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO session_tickets (session_uuid, session_slug, ticket_id, link_source) "
            "VALUES (?, ?, ?, ?)",
            ("uuid-b", "happy-slug", ticket_id, "branch"),
        )


def test_partial_unique_index_allows_null_slug_duplicates():
    """NULL session_slug rows are NOT covered by the partial unique index,
    so two different UUIDs can both link to the same ticket without slug."""
    conn = _make_db()
    ensure_schema(conn)
    ticket_id = conn.execute(
        "INSERT INTO tickets (provider, external_key, url) VALUES (?, ?, ?) RETURNING id",
        ("linear", "ABC-1", "https://linear.app/x/issue/ABC-1"),
    ).fetchone()["id"]

    conn.execute(
        "INSERT INTO session_tickets (session_uuid, ticket_id, link_source) VALUES (?, ?, ?)",
        ("uuid-a", ticket_id, "branch"),
    )
    conn.execute(
        "INSERT INTO session_tickets (session_uuid, ticket_id, link_source) VALUES (?, ?, ?)",
        ("uuid-b", ticket_id, "branch"),
    )
    # No exception — slug-based dedup didn't fire on NULL slugs.


def test_fk_cascade_deletes_session_tickets_when_ticket_removed():
    conn = _make_db()
    ensure_schema(conn)
    ticket_id = conn.execute(
        "INSERT INTO tickets (provider, external_key, url) VALUES (?, ?, ?) RETURNING id",
        ("linear", "ABC-1", "https://linear.app/x/issue/ABC-1"),
    ).fetchone()["id"]
    conn.execute(
        "INSERT INTO session_tickets (session_uuid, ticket_id, link_source) VALUES (?, ?, ?)",
        ("uuid-a", ticket_id, "branch"),
    )
    conn.execute("DELETE FROM tickets WHERE id = ?", (ticket_id,))
    count = conn.execute("SELECT COUNT(*) FROM session_tickets").fetchone()[0]
    assert count == 0

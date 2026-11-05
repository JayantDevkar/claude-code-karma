"""Tests for the always-run sessions_fts guard in ensure_schema (issue #145)."""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from db.queries import query_all_sessions
from db.schema import _SESSIONS_FTS_SQL, _ensure_sessions_fts, ensure_schema

_TRIGGERS = ("sessions_fts_insert", "sessions_fts_delete", "sessions_fts_update")


def _fresh_db() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    ensure_schema(conn)
    conn.execute(
        "INSERT INTO projects (encoded_name, display_name, slug) VALUES ('-foo', 'foo', 'foo')"
    )
    conn.commit()
    return conn


def _add_session(conn: sqlite3.Connection, uuid: str, prompt: str) -> None:
    conn.execute(
        "INSERT INTO sessions (uuid, project_encoded_name, initial_prompt, start_time, "
        "end_time, jsonl_mtime) VALUES (?, '-foo', ?, '2026-10-01T00:00:00Z', "
        "'2026-10-01T01:00:00Z', 1.0)",
        (uuid, prompt),
    )
    conn.commit()


def _found(conn: sqlite3.Connection, term: str) -> set[str]:
    return {s["uuid"] for s in query_all_sessions(conn, search=term)["sessions"]}


def _triggers(conn: sqlite3.Connection) -> set[str]:
    return {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='trigger'")}


def _broken_db(drop_fts_table: bool) -> sqlite3.Connection:
    """A DB whose sessions_fts triggers vanished after some rows were indexed."""
    conn = _fresh_db()
    _add_session(conn, "old", "fix the karma search")
    _add_session(conn, "gone", "karma session that gets deleted")
    for name in _TRIGGERS:
        conn.execute(f"DROP TRIGGER {name}")
    if drop_fts_table:
        conn.execute("DROP TABLE sessions_fts")
    # Writes the index never sees once the triggers are gone.
    conn.execute("DELETE FROM sessions WHERE uuid = 'gone'")
    conn.execute("UPDATE sessions SET initial_prompt = 'karma rename' WHERE uuid = 'old'")
    conn.commit()
    _add_session(conn, "unindexed", "karma rows added while broken")
    return conn


@pytest.mark.parametrize("drop_fts_table", [False, True], ids=["triggers", "triggers+table"])
def test_restores_triggers_and_rebuilds_index(drop_fts_table):
    conn = _broken_db(drop_fts_table)
    if not drop_fts_table:
        assert _found(conn, "rows") == set()

    ensure_schema(conn)

    assert _triggers(conn) == set(_TRIGGERS)
    assert _found(conn, "karma") == {"old", "unindexed"}
    assert _found(conn, "rename") == {"old"}
    assert _found(conn, "search") == set()

    _add_session(conn, "after", "karma session indexed by the restored trigger")
    assert _found(conn, "karma") == {"old", "unindexed", "after"}
    conn.execute("INSERT INTO sessions_fts(sessions_fts, rank) VALUES('integrity-check', 1)")


def test_only_the_table_missing():
    conn = _fresh_db()
    conn.execute("DROP TABLE sessions_fts")
    conn.commit()

    ensure_schema(conn)

    _add_session(conn, "s1", "karma")
    assert _found(conn, "karma") == {"s1"}


def test_rebuilds_a_stale_index_when_triggers_exist():
    conn = _fresh_db()
    for name in _TRIGGERS:
        conn.execute(f"DROP TRIGGER {name}")
    _add_session(conn, "unindexed", "karma rows added while broken")
    conn.executescript(_SESSIONS_FTS_SQL)
    assert _found(conn, "karma") == set()

    assert _ensure_sessions_fts(conn) is True
    assert _found(conn, "karma") == {"unindexed"}


def test_healthy_db_is_left_alone():
    conn = _fresh_db()
    _add_session(conn, "s1", "karma")
    statements: list[str] = []
    conn.set_trace_callback(statements.append)

    ensure_schema(conn)
    assert _ensure_sessions_fts(conn) is False

    conn.set_trace_callback(None)
    assert not any("'rebuild'" in s for s in statements)
    assert not any("CREATE TRIGGER" in s for s in statements)
    assert not conn.in_transaction
    assert _found(conn, "karma") == {"s1"}


def test_skips_a_db_without_sessions():
    conn = sqlite3.connect(":memory:")
    assert _ensure_sessions_fts(conn) is False
    assert _triggers(conn) == set()

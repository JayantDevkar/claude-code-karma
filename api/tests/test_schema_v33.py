"""Tests for the v33 migration: sessions.session_name and a re-index for agent types and files."""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from db.schema import SCHEMA_SQL, SCHEMA_VERSION, ensure_schema


def _db_at(version: int, drop_column: bool = True) -> sqlite3.Connection:
    """Current schema stamped at `version`, with one session; v32 had no session_name column."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA_SQL)
    if drop_column:
        conn.execute("DROP INDEX IF EXISTS idx_sessions_session_name")
        conn.execute("ALTER TABLE sessions DROP COLUMN session_name")
    conn.execute("DELETE FROM schema_version")
    conn.execute("INSERT INTO schema_version (version) VALUES (?)", (version,))
    conn.execute(
        "INSERT INTO projects (encoded_name, display_name, slug) VALUES ('-foo', 'foo', 'foo')"
    )
    conn.execute(
        "INSERT INTO sessions (uuid, project_encoded_name, jsonl_mtime) VALUES ('s1', '-foo', 100.0)"
    )
    conn.commit()
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def _columns(conn: sqlite3.Connection) -> set[str]:
    return {r[1] for r in conn.execute("PRAGMA table_info(sessions)")}


def _mtime(conn: sqlite3.Connection) -> float:
    return conn.execute("SELECT jsonl_mtime FROM sessions WHERE uuid='s1'").fetchone()[0]


def _version(conn: sqlite3.Connection) -> int:
    return conn.execute("SELECT MAX(version) FROM schema_version").fetchone()[0]


def _has_name_index(conn: sqlite3.Connection) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='index' AND name='idx_sessions_session_name'"
    ).fetchone()
    return row is not None


def test_schema_version_is_at_least_33():
    assert SCHEMA_VERSION >= 33


def test_fresh_db_has_the_session_name_column_and_index():
    conn = sqlite3.connect(":memory:")
    ensure_schema(conn)
    assert "session_name" in _columns(conn)
    assert _has_name_index(conn)
    assert _version(conn) == SCHEMA_VERSION


def test_v32_upgrade_adds_the_column_and_reindexes_once():
    conn = _db_at(32)
    ensure_schema(conn)
    assert "session_name" in _columns(conn)
    assert _has_name_index(conn)
    assert _version(conn) == SCHEMA_VERSION
    assert _mtime(conn) == 99.0


def test_v32_db_that_already_has_the_column_still_reindexes():
    conn = _db_at(32, drop_column=False)
    ensure_schema(conn)
    assert _mtime(conn) == 99.0


def test_upgrade_is_idempotent():
    conn = _db_at(32)
    ensure_schema(conn)
    ensure_schema(conn)
    assert _mtime(conn) == 99.0


def test_db_already_at_v33_is_not_reindexed():
    conn = _db_at(33, drop_column=False)
    ensure_schema(conn)
    assert _mtime(conn) == 100.0

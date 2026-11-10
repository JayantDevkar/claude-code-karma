"""Tests for the v28 migration adding session_usage_buckets and forcing a reindex."""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from db.schema import SCHEMA_SQL, SCHEMA_VERSION, ensure_schema


def _db_at(version: int) -> sqlite3.Connection:
    """Current schema stamped at `version`, minus the usage buckets table, with one session."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA_SQL)
    conn.execute("DROP TABLE session_usage_buckets")
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


def _has_table(conn: sqlite3.Connection) -> bool:
    return (
        conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='session_usage_buckets'"
        ).fetchone()
        is not None
    )


def _mtime(conn: sqlite3.Connection) -> float:
    return conn.execute("SELECT jsonl_mtime FROM sessions WHERE uuid='s1'").fetchone()[0]


def test_fresh_db_has_usage_buckets_table():
    conn = sqlite3.connect(":memory:")
    ensure_schema(conn)
    assert _has_table(conn)
    cols = [r[1] for r in conn.execute("PRAGMA table_info(session_usage_buckets)")]
    assert cols == [
        "session_uuid",
        "bucket_start",
        "model",
        "input_tokens",
        "output_tokens",
        "cache_creation_tokens",
        "cache_read_tokens",
        "cost_usd",
    ]


def test_v27_upgrade_creates_table_and_forces_reindex():
    conn = _db_at(27)
    ensure_schema(conn)
    assert _has_table(conn)
    assert _mtime(conn) == 99.0


def test_db_ahead_missing_table_gets_table_and_reindex():
    conn = _db_at(SCHEMA_VERSION + 1)
    ensure_schema(conn)
    assert _has_table(conn)
    assert _mtime(conn) == 99.0


def test_db_ahead_with_table_is_not_reindexed():
    conn = _db_at(SCHEMA_VERSION + 1)
    ensure_schema(conn)
    ensure_schema(conn)
    assert _mtime(conn) == 99.0


def test_upgrade_is_idempotent():
    conn = _db_at(27)
    ensure_schema(conn)
    ensure_schema(conn)
    assert _mtime(conn) == 99.0

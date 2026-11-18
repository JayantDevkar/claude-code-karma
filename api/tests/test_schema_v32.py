"""Tests for the v32 migration: re-index after user entries are parsed differently."""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from db.schema import SCHEMA_SQL, SCHEMA_VERSION, ensure_schema


def _db_at(version: int) -> sqlite3.Connection:
    """Current schema stamped at `version`, with one session."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA_SQL)
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


def _mtime(conn: sqlite3.Connection) -> float:
    return conn.execute("SELECT jsonl_mtime FROM sessions WHERE uuid='s1'").fetchone()[0]


def _version(conn: sqlite3.Connection) -> int:
    return conn.execute("SELECT MAX(version) FROM schema_version").fetchone()[0]


def test_schema_version_is_at_least_32():
    assert SCHEMA_VERSION >= 32


def test_v31_upgrade_forces_reindex():
    conn = _db_at(31)
    ensure_schema(conn)
    assert _version(conn) == SCHEMA_VERSION
    assert _mtime(conn) == 99.0


def test_upgrade_is_idempotent():
    conn = _db_at(31)
    ensure_schema(conn)
    ensure_schema(conn)
    assert _mtime(conn) == 99.0


def test_db_already_at_v32_is_not_reindexed():
    conn = _db_at(32)
    ensure_schema(conn)
    assert _mtime(conn) == 100.0


def test_fresh_db_is_stamped_current():
    conn = sqlite3.connect(":memory:")
    ensure_schema(conn)
    assert _version(conn) == SCHEMA_VERSION

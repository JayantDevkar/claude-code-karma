"""Indexer persistence of API-error summaries (schema v28)."""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from db import indexer
from db.schema import SCHEMA_VERSION, ensure_schema
from models.session import Session

from .api_error_fixtures import (
    SESSION_ID,
    limit_line,
    reply_line,
    user_line,
    write_jsonl,
)

_NEW_COLUMNS = ("ended_by", "ended_resets_at", "limit_hit_count")


def _ts(n):
    return f"2026-01-10T10:{n:02d}:00.000Z"


def _u(n):
    return user_line(f"u{n}", None, _ts(n), "go")


@pytest.fixture
def mem_db():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    ensure_schema(conn)
    return conn


def _session_path(tmp_path):
    return tmp_path / "projects" / "-home-alice-project" / f"{SESSION_ID}.jsonl"


def _index(conn, jsonl_path):
    Session.clear_all_caches()
    stat = jsonl_path.stat()
    indexer._index_session(conn, jsonl_path, jsonl_path.parent.name, stat.st_mtime, stat.st_size)
    conn.commit()


def test_index_writes_ended_by(mem_db, tmp_path):
    p = write_jsonl(
        _session_path(tmp_path),
        [
            _u(1),
            limit_line("a1", "u1", _ts(2)),
            _u(3),
            reply_line("a3", "u3", _ts(4), "ok"),
            _u(5),
            limit_line("a5", "u5", _ts(6)),
        ],
    )
    _index(mem_db, p)
    row = mem_db.execute(
        "SELECT ended_by, ended_resets_at, limit_hit_count, models_used FROM sessions"
    ).fetchone()
    assert row["ended_by"] == "limit" and row["limit_hit_count"] == 2
    assert row["ended_resets_at"].startswith("2026-01-10T12:00:00")
    assert "<synthetic>" not in (row["models_used"] or "")


def test_healed_session_indexes_null(mem_db, tmp_path):
    p = write_jsonl(
        _session_path(tmp_path),
        [
            _u(1),
            limit_line("a1", "u1", _ts(2)),
            _u(3),
            reply_line("a3", "u3", _ts(4), "ok"),
        ],
    )
    _index(mem_db, p)
    row = mem_db.execute(
        "SELECT ended_by, ended_resets_at, limit_hit_count FROM sessions"
    ).fetchone()
    assert row["ended_by"] is None and row["ended_resets_at"] is None
    assert row["limit_hit_count"] == 1


def test_index_writes_subagent_ended_by(mem_db, tmp_path):
    p = _session_path(tmp_path)
    task_use = reply_line("a1", "u1", _ts(2), "spawn")
    task_use["message"]["content"] = [
        {"type": "tool_use", "id": "toolu_a", "name": "Task", "input": {"subagent_type": "worker"}},
        {"type": "tool_use", "id": "toolu_b", "name": "Task", "input": {"subagent_type": "worker"}},
    ]
    result = user_line("u3", "a1", _ts(3), "x")
    result["message"]["content"] = [
        {"type": "tool_result", "tool_use_id": "toolu_a", "content": "done\nagentId: aaa1"},
        {"type": "tool_result", "tool_use_id": "toolu_b", "content": "done\nagentId: bbb2"},
    ]
    write_jsonl(p, [_u(1), task_use, result, reply_line("a4", "u3", _ts(4), "fin")])
    sub_dir = p.parent / SESSION_ID / "subagents"
    write_jsonl(
        sub_dir / "agent-aaa1.jsonl",
        [_u(5), limit_line("s1", "u5", _ts(6))],
    )
    write_jsonl(
        sub_dir / "agent-bbb2.jsonl",
        [_u(7), reply_line("s2", "u7", _ts(8), "ok")],
    )
    _index(mem_db, p)
    rows = {
        r["agent_id"]: r
        for r in mem_db.execute(
            "SELECT agent_id, ended_by, ended_resets_at, limit_hit_count FROM subagent_invocations"
        )
    }
    assert rows["aaa1"]["ended_by"] == "limit"
    assert rows["aaa1"]["limit_hit_count"] == 1
    assert rows["aaa1"]["ended_resets_at"].startswith("2026-01-10T12:00:00")
    assert rows["bbb2"]["ended_by"] is None and rows["bbb2"]["limit_hit_count"] == 0


def _cols(conn, table):
    return {r[1] for r in conn.execute(f"PRAGMA table_info({table})")}


def test_v27_db_migrates_and_reindexes():
    conn = sqlite3.connect(":memory:")
    ensure_schema(conn)
    for table in ("sessions", "subagent_invocations"):
        for col in _NEW_COLUMNS:
            conn.execute(f"ALTER TABLE {table} DROP COLUMN {col}")
    conn.execute("DELETE FROM schema_version")
    conn.execute("INSERT INTO schema_version (version) VALUES (27)")
    conn.execute("INSERT INTO projects (encoded_name, project_path) VALUES ('-p', '/home/alice/p')")
    conn.execute(
        "INSERT INTO sessions (uuid, project_encoded_name, jsonl_mtime) VALUES ('s1', '-p', 100)"
    )
    conn.commit()

    ensure_schema(conn)

    for table in ("sessions", "subagent_invocations"):
        assert set(_NEW_COLUMNS) <= _cols(conn, table)
    assert conn.execute("SELECT MAX(version) FROM schema_version").fetchone()[0] == SCHEMA_VERSION
    assert conn.execute("SELECT jsonl_mtime FROM sessions").fetchone()[0] == 99


def test_db_stamped_28_without_subagent_columns_gains_them():
    conn = sqlite3.connect(":memory:")
    ensure_schema(conn)
    for col in _NEW_COLUMNS:
        conn.execute(f"ALTER TABLE subagent_invocations DROP COLUMN {col}")
    conn.execute("INSERT INTO projects (encoded_name, project_path) VALUES ('-p', '/home/alice/p')")
    conn.execute(
        "INSERT INTO sessions (uuid, project_encoded_name, jsonl_mtime) VALUES ('s1', '-p', 100)"
    )
    conn.commit()
    assert conn.execute("SELECT MAX(version) FROM schema_version").fetchone()[0] == 28

    ensure_schema(conn)

    assert set(_NEW_COLUMNS) <= _cols(conn, "subagent_invocations")
    assert conn.execute("SELECT jsonl_mtime FROM sessions").fetchone()[0] == 99

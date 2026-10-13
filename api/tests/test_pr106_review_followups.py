"""Regression tests for the PR #106 review: schema guard, total scopes, pricing, active time."""

from __future__ import annotations

import json
import logging
import sqlite3
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from db import indexer
from db.queries import query_analytics, query_dashboard_stats
from db.schema import SCHEMA_SQL, ensure_schema
from models.agent import Agent
from models.session_index import SessionIndexEntry
from models.usage import TokenUsage

SUBAGENT_COLUMNS = [
    "subagent_cost",
    "subagent_input_tokens",
    "subagent_output_tokens",
    "subagent_cache_read_tokens",
    "subagent_cache_creation_tokens",
]
T0 = datetime(2026, 10, 1, 9, 0, tzinfo=timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.isoformat().replace("+00:00", "Z")


def _assistant(uuid: str, ts: datetime, *, usage: dict | None = None, tool: str = "Read") -> dict:
    return {
        "type": "assistant",
        "uuid": uuid,
        "timestamp": _iso(ts),
        "sessionId": "s1",
        "message": {
            "id": f"msg_{uuid}",
            "role": "assistant",
            "model": "claude-opus-4-5-20251101",
            "content": [{"type": "tool_use", "id": f"toolu_{uuid}", "name": tool, "input": {}}],
            "usage": usage or {"input_tokens": 1, "output_tokens": 1},
        },
    }


def _write_jsonl(path: Path, lines: list[dict]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(line) + "\n" for line in lines))
    return path


def _columns(conn: sqlite3.Connection) -> set[str]:
    return {r[1] for r in conn.execute("PRAGMA table_info(sessions)").fetchall()}


# Three messages: 10 minutes apart, then a 3-hour idle gap capped at 30 minutes -> 40 minutes active.
GAPPED_TIMESTAMPS = [T0, T0 + timedelta(minutes=10), T0 + timedelta(hours=3, minutes=10)]
GAPPED_ACTIVE_SECONDS = 40 * 60


# ============================================================================
# Item 1: new sessions columns must not depend on the schema version
# ============================================================================


@pytest.fixture
def db_ahead_without_columns():
    """A DB stamped by a parallel branch at v24 whose sessions table predates this PR."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    conn.executescript(SCHEMA_SQL)
    for column in SUBAGENT_COLUMNS:
        if column in _columns(conn):
            conn.execute(f"ALTER TABLE sessions DROP COLUMN {column}")
    conn.execute("DELETE FROM schema_version")
    conn.execute("INSERT INTO schema_version (version) VALUES (24)")
    conn.execute(
        "INSERT INTO sessions (uuid, project_encoded_name, jsonl_mtime) VALUES ('old', '-p', 100.0)"
    )
    conn.commit()
    return conn


def test_columns_added_when_db_version_is_ahead(db_ahead_without_columns):
    ensure_schema(db_ahead_without_columns)

    assert set(SUBAGENT_COLUMNS) <= _columns(db_ahead_without_columns)


def test_adding_columns_forces_one_reindex(db_ahead_without_columns):
    ensure_schema(db_ahead_without_columns)
    ensure_schema(db_ahead_without_columns)

    mtime = db_ahead_without_columns.execute(
        "SELECT jsonl_mtime FROM sessions WHERE uuid = 'old'"
    ).fetchone()[0]
    assert mtime == 99.0


def test_indexing_works_on_db_version_ahead(db_ahead_without_columns, sample_session_jsonl):
    ensure_schema(db_ahead_without_columns)
    stat = sample_session_jsonl.stat()

    indexer._index_session(
        db_ahead_without_columns,
        sample_session_jsonl,
        sample_session_jsonl.parent.name,
        stat.st_mtime,
        stat.st_size,
    )
    db_ahead_without_columns.commit()

    assert (
        db_ahead_without_columns.execute(
            "SELECT COUNT(*) FROM sessions WHERE uuid = ?", (sample_session_jsonl.stem,)
        ).fetchone()[0]
        == 1
    )


# ============================================================================
# Item 3: project/global totals use one scope for cost and tokens
# ============================================================================


@pytest.fixture
def mem_db():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    ensure_schema(conn)
    return conn


def _insert_session(conn, uuid: str, **values) -> None:
    row = {
        "uuid": uuid,
        "project_encoded_name": "-p",
        "jsonl_mtime": 1.0,
        "start_time": "2026-10-01T10:00:00+00:00",
        "input_tokens": 100,
        "output_tokens": 10,
        "cache_read_tokens": 1000,
        "cache_creation_tokens": 5,
        "total_cost": 1.0,
        "subagent_cost": 2.0,
        "subagent_input_tokens": 200,
        "subagent_output_tokens": 20,
        "subagent_cache_read_tokens": 2000,
        "subagent_cache_creation_tokens": 7,
        **values,
    }
    cols = ", ".join(row)
    conn.execute(
        f"INSERT INTO sessions ({cols}) VALUES ({', '.join('?' * len(row))})", list(row.values())
    )
    conn.commit()


def test_analytics_totals_include_subagent_tokens(mem_db):
    _insert_session(mem_db, "a")
    _insert_session(mem_db, "b")

    totals = query_analytics(mem_db)["totals"]

    assert totals["total_cost"] == pytest.approx(6.0)
    assert totals["total_input"] == 600
    assert totals["total_output"] == 60
    assert totals["total_cache_read"] == 6000
    assert totals["total_cache_creation"] == 24


def test_dashboard_tokens_include_subagent_tokens(mem_db):
    _insert_session(mem_db, "a")

    stats = query_dashboard_stats(
        mem_db,
        datetime(2026, 10, 1, tzinfo=timezone.utc),
        datetime(2026, 10, 2, tzinfo=timezone.utc),
    )

    assert stats["total_tokens"] == (100 + 10 + 1000) + (200 + 20 + 2000)
    assert stats["total_cost"] == pytest.approx(3.0)


def test_indexer_stores_subagent_tokens(mem_db, tmp_path, monkeypatch):
    project = tmp_path / "-p"
    session_path = _write_jsonl(project / "s1.jsonl", [_assistant("m1", T0)])
    _write_jsonl(
        project / "s1" / "subagents" / "agent-a1.jsonl",
        [
            _assistant(
                "sub1",
                T0,
                usage={
                    "input_tokens": 100,
                    "output_tokens": 50,
                    "cache_read_input_tokens": 1000,
                    "cache_creation_input_tokens": 10,
                },
            )
        ],
    )
    monkeypatch.setattr(
        "services.subagent_types.get_all_subagent_types", lambda *a, **k: {"a1": "Explore"}
    )
    stat = session_path.stat()

    indexer._index_session(mem_db, session_path, "-p", stat.st_mtime, stat.st_size)
    mem_db.commit()

    row = mem_db.execute("SELECT * FROM sessions WHERE uuid = 's1'").fetchone()
    # input_tokens follows the main-session convention: input + cache creation
    assert row["subagent_input_tokens"] == 110
    assert row["subagent_output_tokens"] == 50
    assert row["subagent_cache_read_tokens"] == 1000
    assert row["subagent_cache_creation_tokens"] == 10


# ============================================================================
# Item 4: unknown versions stay within their major version, with a warning
# ============================================================================


def test_unknown_minor_resolves_within_major():
    usage = TokenUsage(input_tokens=1_000_000, output_tokens=1_000_000)
    assert usage.calculate_cost("claude-haiku-4") == pytest.approx(
        usage.calculate_cost("claude-haiku-4-5-20251001")
    )


def test_guessed_price_logs_one_warning(caplog):
    usage = TokenUsage(input_tokens=1, output_tokens=1)
    with caplog.at_level(logging.WARNING, logger="models.usage"):
        usage.calculate_cost("claude-sonnet-4-9")
        usage.calculate_cost("claude-sonnet-4-9")

    warnings = [r for r in caplog.records if "claude-sonnet-4-9" in r.getMessage()]
    assert len(warnings) == 1


# ============================================================================
# Item 5: every reported duration is active time
# ============================================================================


def _gapped_jsonl(path: Path) -> Path:
    return _write_jsonl(path, [_assistant(f"g{i}", ts) for i, ts in enumerate(GAPPED_TIMESTAMPS)])


def test_agent_duration_is_active_time(tmp_path):
    agent = Agent.from_path(_gapped_jsonl(tmp_path / "subagents" / "agent-g1.jsonl"))

    assert agent.duration_seconds == GAPPED_ACTIVE_SECONDS


def test_indexer_subagent_duration_is_active_time(mem_db, tmp_path, monkeypatch):
    project = tmp_path / "-p"
    session_path = _write_jsonl(project / "s1.jsonl", [_assistant("m1", T0)])
    _gapped_jsonl(project / "s1" / "subagents" / "agent-g1.jsonl")
    monkeypatch.setattr(
        "services.subagent_types.get_all_subagent_types", lambda *a, **k: {"g1": "Explore"}
    )
    stat = session_path.stat()

    indexer._index_session(mem_db, session_path, "-p", stat.st_mtime, stat.st_size)
    mem_db.commit()

    duration = mem_db.execute(
        "SELECT duration_seconds FROM subagent_invocations WHERE agent_id = 'g1'"
    ).fetchone()[0]
    assert duration == GAPPED_ACTIVE_SECONDS


def test_active_duration_parses_file_when_span_exceeds_idle_cap(tmp_path):
    from models.session import active_duration_seconds

    path = _gapped_jsonl(tmp_path / "s.jsonl")

    assert active_duration_seconds(path, GAPPED_TIMESTAMPS[0], GAPPED_TIMESTAMPS[-1]) == (
        GAPPED_ACTIVE_SECONDS
    )


def test_active_duration_short_span_needs_no_file(tmp_path):
    from models.session import active_duration_seconds

    # Under the idle cap no gap can be trimmed, so the wall clock is exact
    assert active_duration_seconds(tmp_path / "missing.jsonl", T0, T0 + timedelta(minutes=20)) == (
        20 * 60
    )


def test_active_duration_unknown_without_file(tmp_path):
    from models.session import active_duration_seconds

    assert active_duration_seconds(tmp_path / "missing.jsonl", T0, T0 + timedelta(hours=5)) is None


def test_index_entry_duration_is_active_time(tmp_path):
    path = _gapped_jsonl(tmp_path / "s.jsonl")
    entry = SessionIndexEntry(
        sessionId="s",
        fullPath=str(path),
        fileMtime=0,
        created=GAPPED_TIMESTAMPS[0],
        modified=GAPPED_TIMESTAMPS[-1],
    )

    assert entry.duration_seconds == GAPPED_ACTIVE_SECONDS

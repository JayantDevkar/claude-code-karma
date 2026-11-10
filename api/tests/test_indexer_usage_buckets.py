"""Indexer writes per-bucket usage rows for a session and all its subagents."""

from __future__ import annotations

import json
import sqlite3
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from db import indexer
from db.schema import ensure_schema

T0 = datetime(2026, 10, 1, 9, 0, tzinfo=timezone.utc)
UUID = "11111111-2222-3333-4444-555555555555"


def _iso(dt: datetime) -> str:
    return dt.isoformat().replace("+00:00", "Z")


def _assistant(uuid: str, ts: datetime, usage: dict) -> dict:
    return {
        "type": "assistant",
        "uuid": uuid,
        "timestamp": _iso(ts),
        "sessionId": "s1",
        "message": {
            "id": f"msg_{uuid}",
            "role": "assistant",
            "model": "claude-opus-4-5-20251101",
            "content": [{"type": "tool_use", "id": f"toolu_{uuid}", "name": "Read", "input": {}}],
            "usage": usage,
        },
    }


def _write_jsonl(path: Path, lines: list[dict]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(line) + "\n" for line in lines))
    return path


@pytest.fixture
def mem_db():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    ensure_schema(conn)
    return conn


@pytest.fixture
def session_path(tmp_path, monkeypatch):
    from services import subagent_types

    monkeypatch.setattr(subagent_types, "get_all_subagent_types", lambda *a, **k: {"a1": "Explore"})
    main = _write_jsonl(
        tmp_path / "-home-alice-project" / f"{UUID}.jsonl",
        [
            _assistant(
                "m1",
                T0,
                {
                    "input_tokens": 100,
                    "output_tokens": 50,
                    "cache_creation_input_tokens": 30,
                    "cache_read_input_tokens": 20,
                },
            ),
            _assistant(
                "m2",
                T0 + timedelta(minutes=20),
                {"input_tokens": 10, "output_tokens": 5, "cache_read_input_tokens": 7},
            ),
        ],
    )
    sub_dir = main.parent / UUID / "subagents"
    _write_jsonl(
        sub_dir / "agent-a1.jsonl",
        [_assistant("s1", T0 + timedelta(minutes=5), {"input_tokens": 40, "output_tokens": 8})],
    )
    _write_jsonl(
        sub_dir / "agent-a2.jsonl",
        [
            _assistant(
                "s2",
                T0 + timedelta(minutes=40),
                {"input_tokens": 3, "output_tokens": 2, "cache_creation_input_tokens": 9},
            )
        ],
    )
    return main


def _index(conn, path):
    stat = path.stat()
    indexer._index_session(conn, path, path.parent.name, stat.st_mtime, stat.st_size)
    conn.commit()


def _bucket_sums(conn):
    return conn.execute(
        """SELECT COUNT(*) AS n, COALESCE(SUM(cost_usd), 0) AS cost,
                  COALESCE(SUM(input_tokens + output_tokens + cache_creation_tokens
                               + cache_read_tokens), 0) AS tokens
           FROM session_usage_buckets WHERE session_uuid = ?""",
        (UUID,),
    ).fetchone()


def _session_totals(conn):
    r = conn.execute("SELECT * FROM sessions WHERE uuid = ?", (UUID,)).fetchone()
    return (
        r["total_cost"] + r["subagent_cost"],
        r["input_tokens"]
        + r["cache_read_tokens"]
        + r["output_tokens"]
        + r["subagent_input_tokens"]
        + r["subagent_cache_read_tokens"]
        + r["subagent_output_tokens"],
    )


def test_bucket_sums_equal_session_totals(mem_db, session_path):
    _index(mem_db, session_path)

    sums = _bucket_sums(mem_db)
    cost, tokens = _session_totals(mem_db)
    assert sums["n"] > 0
    assert sums["cost"] == pytest.approx(cost)
    assert sums["tokens"] == tokens


def test_reindex_replaces_rows(mem_db, session_path):
    _index(mem_db, session_path)
    before = _bucket_sums(mem_db)["n"]

    with session_path.open("a") as f:
        f.write(
            json.dumps(
                _assistant("m3", T0 + timedelta(hours=2), {"input_tokens": 4, "output_tokens": 1})
            )
            + "\n"
        )
    _index(mem_db, session_path)

    sums = _bucket_sums(mem_db)
    cost, tokens = _session_totals(mem_db)
    assert sums["n"] == before + 1
    assert sums["cost"] == pytest.approx(cost)
    assert sums["tokens"] == tokens


def test_buckets_removed_with_session(mem_db, session_path):
    _index(mem_db, session_path)
    indexer._delete_session_rows(mem_db, [UUID])
    mem_db.commit()
    assert _bucket_sums(mem_db)["n"] == 0


def test_buckets_cleared_when_session_becomes_empty(mem_db, session_path):
    _index(mem_db, session_path)
    assert _bucket_sums(mem_db)["n"] > 0

    session_path.write_text("")
    _index(mem_db, session_path)

    assert _bucket_sums(mem_db)["n"] == 0

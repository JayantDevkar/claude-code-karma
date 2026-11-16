"""JSONL-fallback analytics totals cover the session plus its subagents, like the SQLite path."""

import json
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from db import indexer
from db.queries import query_analytics
from db.schema import ensure_schema
from models.session import Session
from routers.analytics import _calculate_analytics_from_sessions, usage_breakdown

BREAKDOWN_FIELDS = (
    "tokens_by_date",
    "cost_by_date",
    "models_categorized_tokens",
    "models_categorized_cost",
)


def _assistant_line(uuid: str) -> str:
    return json.dumps(
        {
            "type": "assistant",
            "uuid": uuid,
            "timestamp": "2026-10-01T09:00:00Z",
            "message": {
                "id": f"msg_{uuid}",
                "role": "assistant",
                "model": "claude-opus-4-5-20251101",
                "content": [{"type": "text", "text": "ok"}],
                "usage": {"input_tokens": 100, "output_tokens": 50},
            },
        }
    )


def test_fallback_analytics_totals_include_subagents(tmp_path: Path):
    project = tmp_path / "-p"
    (project / "s1" / "subagents").mkdir(parents=True)
    session_path = project / "s1.jsonl"
    session_path.write_text(_assistant_line("m1") + "\n")
    (project / "s1" / "subagents" / "agent-a1.jsonl").write_text(_assistant_line("x1") + "\n")

    analytics = _calculate_analytics_from_sessions(
        [Session.from_path(session_path, claude_base_dir=tmp_path)], use_index=False
    )

    assert analytics.total_input_tokens == 200
    assert analytics.total_output_tokens == 100


def _usage_line(uuid: str, ts: datetime, model: str, usage: dict) -> str:
    return json.dumps(
        {
            "type": "assistant",
            "uuid": uuid,
            "timestamp": ts.isoformat().replace("+00:00", "Z"),
            "message": {
                "id": f"msg_{uuid}",
                "role": "assistant",
                "model": model,
                "content": [{"type": "text", "text": "ok"}],
                "usage": usage,
            },
        }
    )


@pytest.fixture
def indexed_session(tmp_path, monkeypatch):
    from services import subagent_types

    monkeypatch.setattr(subagent_types, "get_all_subagent_types", lambda *a, **k: {"a1": "Explore"})
    t0 = datetime(2026, 10, 1, 20, 10, tzinfo=timezone.utc)
    project = tmp_path / "-home-alice-project"
    (project / "s1" / "subagents").mkdir(parents=True)
    session_path = project / "s1.jsonl"
    session_path.write_text(
        _usage_line(
            "m1",
            t0,
            "claude-opus-4-5-20251101",
            {"input_tokens": 100, "output_tokens": 50, "cache_creation_input_tokens": 30},
        )
        + "\n"
        + _usage_line(
            "m2",
            t0 + timedelta(hours=3),
            "claude-sonnet-4-5-20250929",
            {"input_tokens": 10, "output_tokens": 5, "cache_read_input_tokens": 7},
        )
        + "\n"
    )
    (project / "s1" / "subagents" / "agent-a1.jsonl").write_text(
        _usage_line(
            "x1",
            t0 + timedelta(minutes=2),
            "claude-opus-4-5-20251101",
            {"input_tokens": 40, "output_tokens": 8},
        )
        + "\n"
    )
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    ensure_schema(conn)
    stat = session_path.stat()
    indexer._index_session(conn, session_path, project.name, stat.st_mtime, stat.st_size)
    conn.commit()
    return conn, session_path, tmp_path, t0


def _sqlite_breakdown(conn, **kwargs):
    return usage_breakdown(query_analytics(conn, tz_offset_minutes=-120, **kwargs)["usage_rows"])


def test_fallback_matches_sqlite_breakdown(indexed_session):
    conn, session_path, base, _ = indexed_session
    expected = _sqlite_breakdown(conn)
    assert len(expected["tokens_by_date"]) == 2

    analytics = _calculate_analytics_from_sessions(
        [Session.from_path(session_path, claude_base_dir=base)],
        tz_offset_minutes=-120,
        use_index=False,
    )

    for field in BREAKDOWN_FIELDS:
        assert getattr(analytics, field) == expected[field], field


def test_fallback_window_matches_sqlite_breakdown(indexed_session):
    conn, session_path, base, t0 = indexed_session
    start, end = t0 - timedelta(minutes=5), t0 + timedelta(hours=1)
    expected = _sqlite_breakdown(conn, start_dt=start, end_dt=end)
    assert expected["tokens_by_date"]

    analytics = _calculate_analytics_from_sessions(
        [Session.from_path(session_path, claude_base_dir=base)],
        tz_offset_minutes=-120,
        use_index=False,
        start_dt=start,
        end_dt=end,
    )

    for field in BREAKDOWN_FIELDS:
        assert getattr(analytics, field) == expected[field], field


def test_fallback_handles_index_entries_mixed_with_sessions(tmp_path: Path):
    """Global fallback mixes index entries (projects with sessions-index.json) with full
    sessions (projects without); every item must be counted, not crash on Session methods."""
    from models.session_index import SessionIndexEntry

    indexed = tmp_path / "-indexed"
    plain = tmp_path / "-plain"
    (plain / "s1" / "subagents").mkdir(parents=True)
    indexed.mkdir()
    plain_path = plain / "s1.jsonl"
    plain_path.write_text(_assistant_line("m1") + "\n")
    (plain / "s1" / "subagents" / "agent-a1.jsonl").write_text(_assistant_line("x1") + "\n")
    indexed_path = indexed / "s2.jsonl"
    indexed_path.write_text(_assistant_line("m2") + "\n")

    def entry(path: Path) -> SessionIndexEntry:
        t = datetime(2026, 10, 1, 9, 0, tzinfo=timezone.utc)
        return SessionIndexEntry(
            session_id=path.stem, full_path=str(path), file_mtime=0, created=t, modified=t
        )

    analytics = _calculate_analytics_from_sessions(
        [
            Session.from_path(plain_path, claude_base_dir=tmp_path),
            entry(indexed_path),
            # sessions-index.json can still list a session whose JSONL was deleted
            entry(indexed / "gone.jsonl"),
        ],
        use_index=True,
    )

    # s1 (100) + its subagent (100) + s2 (100); the deleted session is skipped
    assert analytics.total_input_tokens == 300
    assert analytics.total_output_tokens == 150
    assert analytics.total_sessions == 2

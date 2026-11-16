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


def _write_index(project_dir: Path, *session_ids: str) -> None:
    ts = "2026-02-06T09:00:00Z"
    entries = [
        {
            "sessionId": sid,
            "fullPath": str(project_dir / f"{sid}.jsonl"),
            "fileMtime": 0,
            "created": ts,
            "modified": ts,
        }
        for sid in session_ids
    ]
    (project_dir / "sessions-index.json").write_text(json.dumps({"version": 1, "entries": entries}))


def _transcript(project_dir: Path, sid: str, usage: dict) -> None:
    t = datetime(2026, 10, 1, 9, 0, tzinfo=timezone.utc)
    line = _usage_line(f"m-{sid}", t, "claude-opus-4-5-20251101", usage)
    (project_dir / f"{sid}.jsonl").write_text(line + "\n")


def _project(base: Path, encoded: str):
    from models.project import Project

    (base / encoded).mkdir(parents=True, exist_ok=True)
    return Project.from_encoded_name(encoded, claude_projects_dir=base)


def test_current_index_entries_ignores_a_stale_index(tmp_path: Path):
    from routers.analytics import _current_index_entries

    project = _project(tmp_path, "-stale")
    _write_index(project.project_dir, "old")
    _transcript(project.project_dir, "new", {"input_tokens": 1, "output_tokens": 1})

    assert _current_index_entries(project) == []


def test_current_index_entries_keeps_an_index_covering_the_transcripts(tmp_path: Path):
    from routers.analytics import _current_index_entries

    project = _project(tmp_path, "-fresh")
    _write_index(project.project_dir, "a", "b")
    _transcript(project.project_dir, "a", {"input_tokens": 1, "output_tokens": 1})
    _transcript(project.project_dir, "b", {"input_tokens": 1, "output_tokens": 1})
    (project.project_dir / "agent-x.jsonl").write_text(_assistant_line("x") + "\n")

    assert {e.session_id for e in _current_index_entries(project)} == {"a", "b"}


def test_current_index_entries_keeps_an_index_listing_deleted_transcripts(tmp_path: Path):
    from routers.analytics import _current_index_entries

    project = _project(tmp_path, "-shrunk")
    _write_index(project.project_dir, "kept", "gone")
    _transcript(project.project_dir, "kept", {"input_tokens": 1, "output_tokens": 1})

    assert {e.session_id for e in _current_index_entries(project)} == {"kept", "gone"}


@pytest.fixture
def stale_index_claude(mock_claude_base, monkeypatch):
    """Fallback mode: SQLite off, one project with a stale index, one without any index."""
    from config import settings
    from utils import clear_project_cache

    monkeypatch.setattr(settings, "use_sqlite", False)
    projects = mock_claude_base / "projects"
    stale = _project(projects, "-Users-test-stale")
    _write_index(stale.project_dir, "old")
    _transcript(stale.project_dir, "new", {"input_tokens": 100, "output_tokens": 50})
    plain = _project(projects, "-Users-test-plain")
    _transcript(plain.project_dir, "only", {"input_tokens": 10, "output_tokens": 5})
    clear_project_cache()
    yield
    clear_project_cache()


def test_global_fallback_counts_transcripts_missing_from_a_stale_index(stale_index_claude):
    from fastapi.testclient import TestClient

    from main import app

    body = TestClient(app).get("/analytics").json()

    assert body["total_sessions"] == 2
    assert body["total_input_tokens"] == 110
    assert body["total_output_tokens"] == 55


def test_project_fallback_counts_transcripts_missing_from_a_stale_index(stale_index_claude):
    from fastapi.testclient import TestClient

    from main import app

    body = TestClient(app).get("/analytics/projects/-Users-test-stale").json()

    assert body["sessions_by_date"] == {"2026-10-01": 1}
    assert body["total_sessions"] == 1
    assert body["total_input_tokens"] == 100
    assert body["total_output_tokens"] == 50

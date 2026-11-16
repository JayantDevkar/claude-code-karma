"""/analytics returns tokens and cost by local day and by model family (SQLite path)."""

from __future__ import annotations

import sqlite3
import sys
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from db.schema import ensure_schema
from routers.analytics import _get_analytics_sqlite

OPUS = "claude-opus-4-6"
SONNET = "claude-sonnet-4-5-20250929"


@pytest.fixture
def mem_db(monkeypatch):
    # The endpoint runs in a worker thread, so the connection must be shareable
    conn = sqlite3.connect(":memory:", check_same_thread=False)
    conn.row_factory = sqlite3.Row
    ensure_schema(conn)

    @contextmanager
    def fake_read():
        yield conn

    monkeypatch.setattr("db.connection.sqlite_read", fake_read)
    return conn


def _utc(s: str) -> datetime:
    return datetime.fromisoformat(s).replace(tzinfo=timezone.utc)


def _session(conn, uuid: str, start: str, project: str = "-home-alice-project") -> None:
    conn.execute(
        "INSERT INTO sessions (uuid, project_encoded_name, jsonl_mtime, start_time)"
        " VALUES (?, ?, 1.0, ?)",
        (uuid, project, start + "+00:00"),
    )
    conn.commit()


def _bucket(conn, uuid: str, at: str, tokens: int, cost: float, model: str = OPUS) -> None:
    conn.execute(
        "INSERT INTO session_usage_buckets (session_uuid, bucket_start, model, output_tokens,"
        " cost_usd) VALUES (?, ?, ?, ?, ?)",
        (uuid, int(_utc(at).timestamp()), model, tokens, cost),
    )
    conn.commit()


def test_day_split_respects_tz_offset(mem_db):
    _session(mem_db, "s1", "2026-10-01T21:00:00")
    _bucket(mem_db, "s1", "2026-10-01T21:45:00", 100, 1.0)
    _bucket(mem_db, "s1", "2026-10-01T22:15:00", 50, 0.5)

    plus2 = _get_analytics_sqlite(None, None, None, -120)
    assert plus2.tokens_by_date == {"2026-10-01": 100, "2026-10-02": 50}
    assert plus2.cost_by_date == {"2026-10-01": 1.0, "2026-10-02": 0.5}

    utc = _get_analytics_sqlite(None, None, None, 0)
    assert utc.tokens_by_date == {"2026-10-01": 150}

    india = _get_analytics_sqlite(None, None, None, -330)
    assert india.tokens_by_date == {"2026-10-02": 150}


def test_window_uses_bucket_time(mem_db):
    _session(mem_db, "s1", "2026-09-20T09:00:00")
    _bucket(mem_db, "s1", "2026-09-20T09:00:00", 7, 0.1)
    _bucket(mem_db, "s1", "2026-10-01T10:00:00", 30, 0.3)
    _bucket(mem_db, "s1", "2026-10-05T10:00:00", 90, 0.9)

    result = _get_analytics_sqlite(
        None, _utc("2026-09-30T10:07:00"), _utc("2026-10-02T00:00:00"), 0
    )

    assert result.tokens_by_date == {"2026-10-01": 30}


def test_families_by_tokens_and_cost(mem_db):
    _session(mem_db, "s1", "2026-10-01T10:00:00")
    _bucket(mem_db, "s1", "2026-10-01T10:00:00", 100, 1.0, OPUS)
    _bucket(mem_db, "s1", "2026-10-01T10:15:00", 40, 0.25, SONNET)
    _bucket(mem_db, "s1", "2026-10-01T10:30:00", 5, 0.0125, "")
    _bucket(mem_db, "s1", "2026-10-01T10:45:00", 10, 0.5, OPUS)

    result = _get_analytics_sqlite(None, None, None, 0)

    assert result.models_categorized_tokens == {"Opus": 110, "Sonnet": 40, "Other": 5}
    assert result.models_categorized_cost == {"Opus": 1.5, "Sonnet": 0.25, "Other": 0.0125}


def test_all_token_kinds_count(mem_db):
    _session(mem_db, "s1", "2026-10-01T10:00:00")
    mem_db.execute(
        "INSERT INTO session_usage_buckets VALUES ('s1', ?, ?, 1, 2, 4, 8, 0.5)",
        (int(_utc("2026-10-01T10:00:00").timestamp()), OPUS),
    )
    mem_db.commit()

    result = _get_analytics_sqlite(None, None, None, 0)

    assert result.tokens_by_date == {"2026-10-01": 15}


def test_project_endpoint_scopes_buckets(mem_db):
    _session(mem_db, "a", "2026-10-01T10:00:00", "-home-alice-one")
    _session(mem_db, "b", "2026-10-01T10:00:00", "-home-alice-two")
    _bucket(mem_db, "a", "2026-10-01T10:00:00", 11, 0.11)
    _bucket(mem_db, "b", "2026-10-01T10:00:00", 22, 0.22)

    one = _get_analytics_sqlite("-home-alice-one", None, None, 0)
    both = _get_analytics_sqlite(None, None, None, 0)

    assert one.tokens_by_date == {"2026-10-01": 11}
    assert both.tokens_by_date == {"2026-10-01": 33}


def test_global_endpoint_returns_new_fields(mem_db):
    from fastapi.testclient import TestClient

    from main import app

    _session(mem_db, "s1", "2026-10-01T10:00:00")
    _bucket(mem_db, "s1", "2026-10-01T10:00:00", 5, 0.05)

    body = TestClient(app).get("/analytics").json()

    assert body["tokens_by_date"] == {"2026-10-01": 5}
    assert body["cost_by_date"] == {"2026-10-01": 0.05}
    assert body["models_categorized_tokens"] == {"Opus": 5}
    assert body["models_categorized_cost"] == {"Opus": 0.05}

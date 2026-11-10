"""Compute DNA counts sessions per model family, not model versions."""

from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from db.queries import query_analytics
from db.schema import ensure_schema
from models.session import Session
from routers.analytics import _calculate_analytics_from_sessions, count_models


@pytest.fixture
def mem_db():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    ensure_schema(conn)
    return conn


def _insert(conn, uuid: str, models: list[str]) -> None:
    conn.execute(
        "INSERT INTO sessions (uuid, project_encoded_name, jsonl_mtime, start_time, models_used)"
        " VALUES (?, '-home-alice-project', 1.0, '2026-10-01T10:00:00+00:00', ?)",
        (uuid, json.dumps(models)),
    )
    conn.commit()


def _assistant(n: int, model: str) -> dict:
    return {
        "type": "assistant",
        "uuid": f"a{n}",
        "timestamp": f"2026-10-01T10:0{n}:00Z",
        "sessionId": "s1",
        "message": {
            "id": f"msg_{n}",
            "role": "assistant",
            "model": model,
            "content": [{"type": "text", "text": "ok"}],
            "usage": {"input_tokens": 1, "output_tokens": 1},
        },
    }


def test_sqlite_counts_sessions_per_family(mem_db):
    _insert(mem_db, "a", ["claude-opus-4-5-20251101", "claude-opus-4-6"])
    _insert(mem_db, "b", ["claude-sonnet-4-5-20250929"])
    _insert(mem_db, "c", ["claude-haiku-4-5-20251001"])
    _insert(mem_db, "d", ["claude-sonnet-4-5-20250929"])

    used, families = count_models(query_analytics(mem_db)["session_models"])

    assert families == {"Opus": 1, "Sonnet": 2, "Haiku": 1}
    assert used["claude-sonnet-4-5-20250929"] == 2


def test_fallback_counts_family_once_per_session(tmp_path):
    path = tmp_path / "s1.jsonl"
    lines = [_assistant(1, "claude-opus-4-5-20251101"), _assistant(2, "claude-opus-4-6")]
    path.write_text("".join(json.dumps(line) + "\n" for line in lines))
    session = Session.from_path(path, claude_base_dir=tmp_path)

    analytics = _calculate_analytics_from_sessions([session], 0, use_index=False)

    assert analytics.models_categorized == {"Opus": 1}

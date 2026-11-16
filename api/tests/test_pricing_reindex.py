"""Stored session costs follow the effective model pricing."""

from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from config import settings
from db import indexer
from db.schema import ensure_schema
from models.session import Session
from models.usage import MODEL_PRICING

PROJECT = "-home-alice-shop"
MODEL = "claude-sonnet-4-5-20250929"


def _write_session(project_dir: Path, uuid: str) -> None:
    project_dir.mkdir(parents=True, exist_ok=True)
    lines = [
        {
            "type": "user",
            "uuid": f"{uuid}-u",
            "sessionId": uuid,
            "cwd": "/home/alice/shop",
            "timestamp": "2026-11-02T10:00:00.000Z",
            "message": {"role": "user", "content": "Add a checkout button"},
        },
        {
            "type": "assistant",
            "uuid": f"{uuid}-a",
            "parentUuid": f"{uuid}-u",
            "sessionId": uuid,
            "cwd": "/home/alice/shop",
            "timestamp": "2026-11-02T10:00:05.000Z",
            "message": {
                "id": f"msg-{uuid}",
                "role": "assistant",
                "model": MODEL,
                "content": [{"type": "text", "text": "Done."}],
                "usage": {
                    "input_tokens": 1000,
                    "output_tokens": 500,
                    "cache_read_input_tokens": 20000,
                },
            },
        },
    ]
    text = "\n".join(json.dumps(line) for line in lines) + "\n"
    (project_dir / f"{uuid}.jsonl").write_text(text, encoding="utf-8")


@pytest.fixture
def projects(tmp_path, monkeypatch):
    claude = tmp_path / ".claude"
    (claude / "projects").mkdir(parents=True)
    monkeypatch.setattr(settings, "claude_base", claude)
    monkeypatch.setattr(settings, "use_sqlite", True)
    monkeypatch.setattr(settings, "extra_roots", [])
    return claude / "projects"


@pytest.fixture
def mem_db():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    ensure_schema(conn)
    return conn


def _cost(conn) -> float:
    return conn.execute("SELECT total_cost FROM sessions WHERE uuid = 's1'").fetchone()[0]


def test_price_change_reprices_stored_session_cost(projects, mem_db, monkeypatch):
    _write_session(projects / PROJECT, "s1")
    indexer.sync_all_projects(mem_db)
    before = _cost(mem_db)
    assert before > 0

    doubled = {k: v * 2 for k, v in MODEL_PRICING[MODEL].items() if k != "long_context_threshold"}
    doubled["long_context_threshold"] = MODEL_PRICING[MODEL]["long_context_threshold"]
    monkeypatch.setitem(MODEL_PRICING, MODEL, doubled)
    # Prices load at startup, and a restarted API has no cached sessions
    Session.clear_all_caches()
    indexer.sync_all_projects(mem_db)

    assert _cost(mem_db) == pytest.approx(before * 2)


def test_unchanged_pricing_does_not_force_reparse(projects, mem_db):
    _write_session(projects / PROJECT, "s1")
    indexer.sync_all_projects(mem_db)

    stats = indexer.sync_all_projects(mem_db)

    assert stats["indexed"] == 0

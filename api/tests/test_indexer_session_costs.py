"""Indexer behaviour around per-session subagent cost (PR #106 review follow-ups)."""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from db import indexer
from db.schema import ensure_schema
from models.session import Session


@pytest.fixture
def mem_db():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    ensure_schema(conn)
    return conn


def _index(conn, jsonl_path):
    stat = jsonl_path.stat()
    indexer._index_session(conn, jsonl_path, jsonl_path.parent.name, stat.st_mtime, stat.st_size)
    conn.commit()


def test_reindex_overwrites_stale_subagent_cost(mem_db, sample_session_jsonl):
    uuid = sample_session_jsonl.stem
    _index(mem_db, sample_session_jsonl)
    mem_db.execute("UPDATE sessions SET subagent_cost = 99.0 WHERE uuid = ?", (uuid,))
    mem_db.commit()

    _index(mem_db, sample_session_jsonl)

    row = mem_db.execute("SELECT subagent_cost FROM sessions WHERE uuid = ?", (uuid,)).fetchone()
    assert row["subagent_cost"] == 0.0


def test_subagents_are_listed_once_per_index(mem_db, sample_session_with_subagents, monkeypatch):
    calls = {"list": 0, "cost": 0}
    real_list = Session.list_subagents

    def counting_list(self):
        calls["list"] += 1
        return real_list(self)

    def counting_cost(self):
        calls["cost"] += 1
        return 0.0

    monkeypatch.setattr(Session, "list_subagents", counting_list)
    monkeypatch.setattr(Session, "get_subagent_total_cost", counting_cost)

    _index(mem_db, sample_session_with_subagents)

    # One listing feeds both the cost sum and the invocation rows; no separate cost pass.
    assert calls == {"list": 1, "cost": 0}

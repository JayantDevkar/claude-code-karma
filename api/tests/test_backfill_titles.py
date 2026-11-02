"""backfill_titles.py: picking which untitled sessions to title."""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

import backfill_titles
from backfill_titles import get_titleless_sessions

from db.schema import ensure_schema
from services import synced_titles


def _db_with_sessions(db_path: Path, rows) -> None:
    conn = sqlite3.connect(db_path)
    ensure_schema(conn)
    for uuid, root, prompt in rows:
        conn.execute(
            "INSERT INTO sessions (uuid, project_encoded_name, message_count, jsonl_mtime,"
            " initial_prompt, source_root) VALUES (?, '-home-alice-shop', 1, 0, ?, ?)",
            (uuid, prompt, root),
        )
    conn.commit()
    conn.close()


def test_synced_filter_selects_only_synced_rows(tmp_path):
    db_path = tmp_path / "metadata.db"
    _db_with_sessions(
        db_path, [("local-1", None, "Add a cart page"), ("synced-1", "vps", "Add a cart page")]
    )

    rows = get_titleless_sessions(db_path, synced_only=True)

    assert [r[0] for r in rows] == ["synced-1"]
    assert len(get_titleless_sessions(db_path)) == 2


def test_synced_run_uses_indexed_prompt_and_skips_fallback(tmp_path, monkeypatch):
    karma = tmp_path / "home" / ".claude_karma"
    karma.mkdir(parents=True)
    _db_with_sessions(
        karma / "metadata.db",
        [("synced-1", "vps", "Add a cart page"), ("synced-2", "vps", "Fix the login redirect")],
    )
    calls, posted = [], []

    def fake_generate(prompt, response, git):
        calls.append((prompt, response, git))
        return ("Add cart page", "haiku") if "cart" in prompt else ("Fix the lo", "fallback")

    monkeypatch.setattr(Path, "home", staticmethod(lambda: tmp_path / "home"))
    monkeypatch.setattr(synced_titles, "load_title_generator", lambda: fake_generate)
    monkeypatch.setattr(
        backfill_titles, "post_title", lambda uuid, title: posted.append((uuid, title)) or True
    )
    monkeypatch.setattr(backfill_titles.time, "sleep", lambda s: None)
    monkeypatch.setattr(sys, "argv", ["backfill_titles.py", "--synced"])

    backfill_titles.main()

    assert sorted(calls) == [
        ("Add a cart page", None, None),
        ("Fix the login redirect", None, None),
    ]
    assert posted == [("synced-1", "Add cart page")]

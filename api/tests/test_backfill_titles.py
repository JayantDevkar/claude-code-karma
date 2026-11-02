"""backfill_titles.py: picking which untitled sessions to title."""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from backfill_titles import get_titleless_sessions

from db.schema import ensure_schema


def test_synced_filter_selects_only_synced_rows(tmp_path):
    db_path = tmp_path / "metadata.db"
    conn = sqlite3.connect(db_path)
    ensure_schema(conn)
    for uuid, root in (("local-1", None), ("synced-1", "vps")):
        conn.execute(
            "INSERT INTO sessions (uuid, project_encoded_name, message_count, jsonl_mtime,"
            " initial_prompt, source_root) VALUES (?, '-home-alice-shop', 1, 0, 'Add a cart page', ?)",
            (uuid, root),
        )
    conn.commit()
    conn.close()

    rows = get_titleless_sessions(db_path, synced_only=True)

    assert [r[0] for r in rows] == ["synced-1"]
    assert len(get_titleless_sessions(db_path)) == 2

"""Haiku titles for sessions synced from other machines, opt-in per extra root.

The SessionEnd title hook runs on the machine that ran the session, where no
Karma API listens, so synced sessions arrive untitled. Roots with
``"auto_titles": true`` get their cleanly ended sessions titled here, at most
one Haiku call per session, only for sessions that ended in the last day.
"""

from __future__ import annotations

import importlib.util
import json
import logging
import os
import sqlite3
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Callable, Optional

from services.session_roots import get_extra_roots, session_jsonl_path
from services.session_title_store import store_session_title

logger = logging.getLogger(__name__)

AUTO_TITLE_WINDOW_HOURS = 24
AUTO_TITLE_BATCH = 20
_TAIL_BYTES = 64 * 1024
_HOOK_PATH = Path(__file__).resolve().parents[2] / "hooks" / "session_title_generator.py"

TitleGenerator = Callable[[str, Optional[str], Optional[str]], "tuple[Optional[str], str]"]


@lru_cache(maxsize=1)
def load_title_generator() -> Optional[TitleGenerator]:
    """The hook's ``generate_title``, loaded by path; None (one warning) if unavailable."""
    try:
        spec = importlib.util.spec_from_file_location("_karma_session_title_hook", _HOOK_PATH)
        if spec is None or spec.loader is None:
            raise ImportError(f"no loader for {_HOOK_PATH}")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module.generate_title
    except Exception as e:
        logger.warning("Synced titles off: cannot load session_title_generator (%s)", e)
        return None


def _ended_cleanly(path: Path) -> Optional[bool]:
    """True if the JSONL's last line is a cost-state record; None if unreadable."""
    try:
        with open(path, "rb") as f:
            f.seek(0, os.SEEK_END)
            f.seek(max(0, f.tell() - _TAIL_BYTES))
            tail = f.read()
    except OSError:
        return None
    lines = [line for line in tail.splitlines() if line.strip()]
    if not lines:
        return False
    try:
        record = json.loads(lines[-1])
    except ValueError:
        return False
    return isinstance(record, dict) and record.get("type") == "cost-state"


def title_synced_sessions(conn: sqlite3.Connection, now: Optional[datetime] = None) -> int:
    """Title recently ended sessions from roots with auto_titles on; returns how many."""
    enabled = [root.name for root in get_extra_roots() if root.auto_titles]
    if not enabled:
        return 0
    now_iso = (now or datetime.now(timezone.utc)).isoformat()
    marks = ",".join("?" * len(enabled))
    rows = conn.execute(
        f"""
        SELECT uuid, project_encoded_name, initial_prompt FROM sessions
        WHERE source_root IN ({marks})
          AND (session_titles IS NULL OR session_titles IN ('', '[]'))
          AND title_attempted_at IS NULL
          AND end_time IS NOT NULL
          AND julianday(?) - julianday(end_time) <= ? / 24.0
        ORDER BY end_time DESC
        """,
        (*enabled, now_iso, AUTO_TITLE_WINDOW_HOURS),
    ).fetchall()
    if not rows:
        return 0
    generate = load_title_generator()
    if generate is None:
        return 0

    # No SQL LIMIT: unended sessions stay candidates and would crowd out ended ones
    titled = attempted = 0
    for uuid, encoded_name, prompt in rows:
        if attempted >= AUTO_TITLE_BATCH:
            break
        if not _ended_cleanly(session_jsonl_path(encoded_name, uuid)):
            continue
        # Mark before the Haiku call so a crash or reindex never causes a second call
        conn.execute("UPDATE sessions SET title_attempted_at = ? WHERE uuid = ?", (now_iso, uuid))
        conn.commit()
        attempted += 1
        if not prompt:
            continue
        title, _source = generate(prompt, None, None)
        if title:
            store_session_title(encoded_name, uuid, title, conn=conn)
            titled += 1
    return titled

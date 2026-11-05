"""Haiku titles for sessions synced from other machines, opt-in per extra root."""

from __future__ import annotations

import importlib.util
import json
import logging
import os
import shutil
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
# Bookkeeping records (file-history-snapshot, system, ...) can follow cost-state
_END_LOOKBACK = 8
_HOOK_PATH = Path(__file__).resolve().parents[2] / "hooks" / "session_title_generator.py"
# launchd/autostart PATH is /usr/bin:/bin:/usr/sbin:/sbin, so also try the usual install dirs
_CLAUDE_DIRS = (
    Path.home() / ".local" / "bin",
    Path.home() / ".claude" / "local",
    Path("/opt/homebrew/bin"),
    Path("/usr/local/bin"),
)
# Haiku fallbacks per session before it is marked attempted for good
MAX_FALLBACKS = 3

TitleGenerator = Callable[..., "tuple[Optional[str], str]"]

_fallbacks: dict[str, int] = {}
_warned_no_cli = False


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


def find_claude_cli() -> Optional[str]:
    """Path to the claude CLI: PATH first, then common install dirs."""
    found = shutil.which("claude")
    if found:
        return found
    for directory in _CLAUDE_DIRS:
        candidate = directory / "claude"
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return str(candidate)
    return None


def _ended_cleanly(path: Path) -> Optional[bool]:
    """True if a cost-state record ends the JSONL, past trailing bookkeeping; None if unreadable."""
    try:
        with open(path, "rb") as f:
            f.seek(0, os.SEEK_END)
            f.seek(max(0, f.tell() - _TAIL_BYTES))
            tail = f.read()
    except OSError:
        return None
    lines = [line for line in tail.splitlines() if line.strip()]
    for line in reversed(lines[-_END_LOOKBACK:]):
        try:
            record = json.loads(line)
        except ValueError:
            return False
        kind = record.get("type") if isinstance(record, dict) else None
        if kind == "cost-state":
            return True
        if kind in ("user", "assistant"):
            return False
    return False


def title_synced_sessions(conn: sqlite3.Connection, now: Optional[datetime] = None) -> int:
    """Title recently ended sessions from roots with auto_titles on; returns how many."""
    global _warned_no_cli
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
    claude = find_claude_cli()
    if claude is None:
        if not _warned_no_cli:
            dirs = ", ".join(str(d) for d in _CLAUDE_DIRS)
            logger.warning("Synced titles skipped: claude CLI not on PATH or in %s", dirs)
            _warned_no_cli = True
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
        title, source = generate(prompt, None, None, claude_bin=claude)
        # The truncated-prompt fallback would block a real title from backfill later
        if title and source != "fallback":
            store_session_title(encoded_name, uuid, title, conn=conn)
            titled += 1
            _fallbacks.pop(uuid, None)
            continue
        _fallbacks[uuid] = tries = _fallbacks.get(uuid, 0) + 1
        logger.warning(
            "Haiku title failed for synced session %s (try %d of %d)", uuid, tries, MAX_FALLBACKS
        )
        if tries < MAX_FALLBACKS:
            conn.execute("UPDATE sessions SET title_attempted_at = NULL WHERE uuid = ?", (uuid,))
            conn.commit()
        # A fallback usually means the CLI is failing for everyone; stop until the next pass
        break
    return titled

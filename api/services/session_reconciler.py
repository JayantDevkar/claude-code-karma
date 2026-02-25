"""
Live session reconciler — detects and resolves stuck live sessions.

When Claude Code hands off to a new session, the parent session no longer fires
a SessionEnd hook. This leaves the parent's live session state stuck at LIVE.

This background task periodically checks for stuck sessions by looking for newer
JSONL files in the same project directory — concrete filesystem evidence that
the session was replaced.
"""

import asyncio
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from models.live_session import LiveSessionState, list_live_session_files

logger = logging.getLogger(__name__)


def _get_session_mtime(transcript_path: str) -> Optional[float]:
    """Get mtime of a session's JSONL file. Returns None if file doesn't exist."""
    try:
        return Path(transcript_path).expanduser().stat().st_mtime
    except (OSError, ValueError):
        return None


def _has_newer_jsonl(project_dir: Path, session_mtime: float, own_stem: str) -> bool:
    """Check if any non-subagent JSONL in project_dir has a newer mtime."""
    try:
        for f in project_dir.glob("*.jsonl"):
            # Skip subagent files and our own file
            if f.name.startswith("agent-") or f.stem == own_stem:
                continue
            try:
                if f.stat().st_mtime > session_mtime:
                    return True
            except OSError:
                continue
    except OSError:
        pass
    return False


def _mark_session_ended(state_file: Path, state_data: dict) -> None:
    """Update a state file to mark the session as ENDED via reconciler."""
    state_data["state"] = "ENDED"
    state_data["end_reason"] = "session_handoff"
    state_data["last_hook"] = "Reconciler"
    state_data["updated_at"] = datetime.now(timezone.utc).isoformat()

    with open(state_file, "w", encoding="utf-8") as f:
        json.dump(state_data, f, indent=2, default=str)


def _reconcile_once(idle_threshold: int) -> int:
    """
    Run one reconciliation pass. Returns count of sessions reconciled.

    This is a synchronous function meant to be called via asyncio.to_thread().
    """
    reconciled = 0
    state_files = list_live_session_files()

    for state_file in state_files:
        try:
            # Load raw JSON (we need to write it back, so keep as dict)
            with open(state_file, "r", encoding="utf-8") as f:
                state_data = json.load(f)

            state = state_data.get("state", "")
            if state not in ("LIVE", "STOPPED", "STALE"):
                continue

            # Check idle time
            session = LiveSessionState.from_file(state_file)
            if session.idle_seconds < idle_threshold:
                continue

            # Get transcript path and derive project dir
            transcript_path = state_data.get("transcript_path", "")
            if not transcript_path:
                continue

            transcript = Path(transcript_path).expanduser()
            project_dir = transcript.parent

            if not project_dir.is_dir():
                continue

            # Get session's own mtime
            session_mtime = _get_session_mtime(transcript_path)
            if session_mtime is None:
                continue

            # Check for newer JSONL in same project directory
            if _has_newer_jsonl(project_dir, session_mtime, transcript.stem):
                slug = state_data.get("slug", state_data.get("session_id", "unknown"))
                idle_secs = int(session.idle_seconds)
                logger.info(
                    "Reconciler: ended session %s (idle %ds, replaced by newer JSONL)",
                    slug,
                    idle_secs,
                )
                _mark_session_ended(state_file, state_data)
                reconciled += 1

        except (json.JSONDecodeError, ValueError, KeyError, OSError) as e:
            logger.warning("Reconciler: error processing %s: %s", state_file.name, e)
            continue

    return reconciled


async def run_session_reconciler(check_interval: int = 60, idle_threshold: int = 120) -> None:
    """
    Background task that periodically reconciles stuck live sessions.

    Args:
        check_interval: Seconds between reconciliation checks.
        idle_threshold: Seconds of idle before considering a session for reconciliation.
    """
    logger.info(
        "Session reconciler running (interval=%ds, threshold=%ds)",
        check_interval,
        idle_threshold,
    )

    while True:
        try:
            await asyncio.sleep(check_interval)
            count = await asyncio.to_thread(_reconcile_once, idle_threshold)
            if count > 0:
                logger.info("Reconciler: ended %d stuck session(s)", count)
        except asyncio.CancelledError:
            logger.info("Session reconciler stopped")
            return
        except Exception as e:
            logger.error("Reconciler error: %s", e)
            # Continue running despite errors

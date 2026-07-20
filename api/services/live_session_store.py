"""
Live session state store — the single supported writer for
``~/.claude_karma/live-sessions/*.json``.

All mutations to live-session JSON files MUST go through this module so
fcntl-based locking remains uncontested. Direct ``open(path, "w")`` calls
elsewhere defeat the cross-process lock and create the race conditions this
module exists to prevent.

Concurrent writers exist:
  - hooks/live_session_tracker.py (one process per hook event)
  - api/services/session_reconciler.py (background task)
  - api/routers/live_sessions.py cleanup endpoints
  - this module's purge helpers

Read endpoints stay side-effect-free; only ``purge_old_files`` deletes
state files, and it is only invoked from the reconciler background task.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

try:
    import fcntl

    HAS_FCNTL = True
except ImportError:  # pragma: no cover - non-Unix fallback
    HAS_FCNTL = False

try:
    import msvcrt
    import time

    HAS_MSVCRT = True
except ImportError:
    HAS_MSVCRT = False

logger = logging.getLogger(__name__)


def get_live_sessions_dir() -> Path:
    """Return the live-sessions directory (``~/.claude_karma/live-sessions``)."""
    return Path.home() / ".claude_karma" / "live-sessions"


def _state_path(session_id: str) -> Path:
    return get_live_sessions_dir() / f"{session_id}.json"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _read_locked(f: Any) -> Dict[str, Any]:
    try:
        f.seek(0)
        return json.load(f)
    except json.JSONDecodeError:
        return {}


def _write_under_lock(path: Path, updates: Dict[str, Any]) -> Dict[str, Any]:
    """Read-modify-write the state file with an exclusive lock.

    Returns the final state dict written to disk.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.write_text("{}")

    if HAS_FCNTL:
        with open(path, "r+", encoding="utf-8") as f:
            fcntl.flock(f, fcntl.LOCK_EX)
            try:
                existing = _read_locked(f)
                existing.update(updates)
                existing["updated_at"] = updates.get("updated_at") or _now_iso()
                f.seek(0)
                json.dump(existing, f, indent=2, default=str)
                f.truncate()
                return existing
            finally:
                fcntl.flock(f, fcntl.LOCK_UN)

    if HAS_MSVCRT:  # pragma: no cover - exercised on Windows only
        max_retries = 5
        for attempt in range(max_retries):
            try:
                with open(path, "r+", encoding="utf-8") as f:
                    msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)
                    try:
                        existing = _read_locked(f)
                        existing.update(updates)
                        existing["updated_at"] = updates.get("updated_at") or _now_iso()
                        f.seek(0)
                        f.truncate()
                        json.dump(existing, f, indent=2, default=str)
                        return existing
                    finally:
                        f.seek(0)
                        msvcrt.locking(f.fileno(), msvcrt.LK_UNLCK, 1)
            except OSError:
                if attempt < max_retries - 1:
                    time.sleep(0.1 * (attempt + 1))
                    continue
                raise
        return {}

    # Fallback: no locking primitive available. Best effort.
    try:
        with open(path, "r", encoding="utf-8") as f:
            existing = json.load(f)
    except (json.JSONDecodeError, FileNotFoundError):
        existing = {}
    existing.update(updates)
    existing["updated_at"] = updates.get("updated_at") or _now_iso()
    path.write_text(json.dumps(existing, indent=2, default=str))
    return existing


def write_state(session_id: str, **updates: Any) -> Dict[str, Any]:
    """Atomically merge ``updates`` into the session's state file.

    Returns the full state dict after the write. Always stamps
    ``session_id`` so newly-created files carry the identifier even if
    the caller passed only secondary fields.
    """
    if not session_id:
        raise ValueError("session_id is required")
    updates.setdefault("session_id", session_id)
    return _write_under_lock(_state_path(session_id), updates)


def mark_ended(session_id: str, *, end_reason: str, last_hook: str) -> None:
    """Convenience wrapper to mark a session ENDED with reason + hook source."""
    write_state(
        session_id,
        state="ENDED",
        end_reason=end_reason,
        last_hook=last_hook,
        updated_at=_now_iso(),
    )


def delete_state(session_id: str) -> bool:
    """Delete a state file by session_id (or other identifier). Returns True on success."""
    path = _state_path(session_id)
    if path.exists():
        try:
            path.unlink()
            return True
        except OSError as e:
            logger.warning("Failed to delete live session %s: %s", session_id, e)
            return False
    return False


def _iter_state_files():
    """Yield ``(path, data)`` for every readable state file; skips malformed ones."""
    live_dir = get_live_sessions_dir()
    if not live_dir.exists():
        return
    for path in live_dir.glob("*.json"):
        try:
            with open(path, "r", encoding="utf-8") as f:
                yield path, json.load(f)
        except (OSError, json.JSONDecodeError):
            continue


def _parse_timestamp(value: Any) -> Optional[datetime]:
    """Parse an ISO timestamp from state JSON; None when missing/invalid."""
    if not value:
        return None
    try:
        ts = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None
    return ts.replace(tzinfo=timezone.utc) if ts.tzinfo is None else ts


def purge_old_files(
    *,
    ended_max_age_sec: int = 600,
    starting_max_age_sec: int = 600,
) -> int:
    """Delete ENDED/STARTING state files older than the given thresholds.

    Replaces the side-effecting auto-cleanup that previously lived inside
    ``load_all_live_sessions_async``. Intended to run from a background
    timer (e.g. the session reconciler), not from request handlers.

    Returns the number of files deleted.
    """
    now = datetime.now(timezone.utc)
    deleted = 0

    for path, data in _iter_state_files():
        state = data.get("state")
        if state not in ("ENDED", "STARTING"):
            continue
        ts = _parse_timestamp(data.get("updated_at"))
        if ts is None:
            continue

        max_age = ended_max_age_sec if state == "ENDED" else starting_max_age_sec
        idle_sec = (now - ts).total_seconds()
        if idle_sec <= max_age:
            continue

        try:
            path.unlink()
            deleted += 1
            logger.debug(
                "purge_old_files: deleted %s (state=%s idle=%ds)",
                path.name,
                state,
                int(idle_sec),
            )
        except OSError as e:
            logger.warning("purge_old_files: failed to delete %s: %s", path, e)

    if deleted:
        logger.info("purge_old_files: deleted %d stale state file(s)", deleted)
    return deleted


# States that mean "the session is (supposedly) still going".
_NON_TERMINAL_STATES = ("LIVE", "WAITING", "STOPPED", "STALE", "STARTING")

# Files younger than this are never reaped — protects freshly-written state
# from racing its own hook events (and pathological clock skew).
_REAP_MIN_AGE_SEC = 30

# Non-terminal files with no captured pid can't be probed; end them once
# they've been silent this long (dead sessions used to linger forever).
_PIDLESS_MAX_AGE_SEC = 24 * 3600


def reap_dead_sessions() -> int:
    """Mark non-terminal sessions whose claude process is gone as ENDED.

    Sessions killed without a SessionEnd hook (SIGKILL, crash, closed
    terminal window) previously lingered in STOPPED/STALE/WAITING forever —
    no cleanup path covered those states. The captured pid gives direct
    evidence: dead, or recycled onto a non-claude process, means the session
    is over. Pid-less legacy files fall back to a 24h silence threshold.

    Marks ENDED (end_reason="process_died") rather than deleting, so the
    normal ENDED display window and ``purge_old_files`` lifecycle apply.
    Runs from the reconciler background timer. Returns sessions reaped.
    """
    # Deferred import: services.terminal_focus owns the pid probing logic.
    from services.terminal_focus import pid_is_live_claude

    now = datetime.now(timezone.utc)
    reaped = 0

    for path, data in _iter_state_files():
        if data.get("state") not in _NON_TERMINAL_STATES:
            continue

        ts = _parse_timestamp(data.get("updated_at"))
        if ts is None:
            continue
        age_sec = (now - ts).total_seconds()
        if age_sec < _REAP_MIN_AGE_SEC:
            continue

        pid = (data.get("terminal") or {}).get("pid")
        if pid:
            # Probing only works on the machine the session ran on; both the
            # API and the hooks run locally, so that's always this host.
            if pid_is_live_claude(pid):
                continue
            reason = "process_died"
        elif age_sec > _PIDLESS_MAX_AGE_SEC:
            reason = "reaped_stale"
        else:
            continue

        session_id = data.get("session_id") or path.stem
        # Write to the exact file we probed (legacy slug-named files would
        # otherwise get a fresh session_id-named file and linger unreaped).
        _write_under_lock(
            path,
            {
                "session_id": session_id,
                "state": "ENDED",
                "end_reason": reason,
                "last_hook": "Reaper",
                "updated_at": _now_iso(),
            },
        )
        reaped += 1
        logger.info(
            "reap_dead_sessions: ended %s (state=%s reason=%s pid=%s)",
            session_id,
            data.get("state"),
            reason,
            pid,
        )

    return reaped


def find_state_file_for(identifier: str) -> Optional[Path]:
    """Locate the state file for a slug, session_id, or filename stem.

    Returns the Path if found, else None. Used by routers that may receive
    either a slug-named file (legacy) or a session_id-named file (current).
    """
    direct = _state_path(identifier)
    if direct.exists():
        return direct

    for path, data in _iter_state_files():
        if (
            data.get("session_id") == identifier
            or data.get("slug") == identifier
            or identifier in data.get("session_ids", [])
        ):
            return path
    return None


def delete_by_identifier(identifier: str) -> bool:
    """Delete a state file by slug, session_id, or filename stem."""
    path = find_state_file_for(identifier)
    if path is None:
        return False
    try:
        path.unlink()
        return True
    except OSError as e:
        logger.warning("delete_by_identifier(%s): %s", identifier, e)
        return False


__all__ = [
    "get_live_sessions_dir",
    "write_state",
    "mark_ended",
    "delete_state",
    "delete_by_identifier",
    "purge_old_files",
    "reap_dead_sessions",
    "find_state_file_for",
]

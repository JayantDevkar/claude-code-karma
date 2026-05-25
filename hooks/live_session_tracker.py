#!/usr/bin/env python3
"""
Live session state tracker for Claude Code Karma.

Writes session state to ``~/.claude_karma/live-sessions/{session_id}.json``
based on Claude Code hook events.

Session states:
- STARTING: Session started, waiting for first message
- LIVE: Session actively running (tool execution)
- WAITING: Claude needs user input (AskUserQuestion, permission dialog)
- STOPPED: Agent finished but session still open
- STALE: User has been idle for 60+ seconds
- ENDED: Session terminated

Hook → state mapping:
- SessionStart → STARTING
- UserPromptSubmit → LIVE
- PostToolUse → LIVE
- Notification(permission_prompt) → WAITING
- Notification(idle_prompt) → STALE (unless already WAITING)
- Stop (stop_hook_active=false) → STOPPED
- SessionEnd → ENDED (with end_reason)

Files are always keyed by ``session_id``. The legacy slug-based filename
scheme was removed — Claude Code never emits a top-level ``slug`` field
outside SummaryMessage, so every state file on disk had ``slug=null``.
The ``slug`` field on the schema is preserved but never written by this
hook (older files with a populated slug remain readable).
"""

from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, Optional

# Vendored captain-hook subset — self-contained, no /api or /captain-hook deps.
from _captain_hook_lite import parse_hook_event

# Platform-specific file locking
try:
    import fcntl

    HAS_FCNTL = True
except ImportError:
    HAS_FCNTL = False

try:
    import msvcrt
    import time

    HAS_MSVCRT = True
except ImportError:
    HAS_MSVCRT = False

LIVE_SESSIONS_DIR = Path.home() / ".claude_karma" / "live-sessions"


def resolve_git_root(cwd: str) -> Optional[str]:
    """Resolve the real git root from cwd.

    For worktrees, ``--show-toplevel`` returns the worktree root (not the
    main repo). We use ``--git-common-dir`` to find the shared .git
    directory, whose parent is the actual repository root.
    """
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel", "--git-common-dir"],
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode != 0:
            return None

        lines = result.stdout.strip().splitlines()
        toplevel = lines[0]
        common_dir = lines[1] if len(lines) > 1 else None

        if common_dir:
            common_path = Path(common_dir)
            if not common_path.is_absolute():
                common_path = (Path(cwd) / common_path).resolve()
            real_root = str(common_path.parent)
            if real_root != toplevel:
                return real_root

        return toplevel
    except (subprocess.TimeoutExpired, OSError):
        pass
    return None


def write_state_atomic(path: Path, update_fn: Callable[[dict], dict]) -> None:
    """
    Atomically update state file with locking.

    Uses ``fcntl.LOCK_EX`` on Unix, ``msvcrt.locking`` on Windows.
    Falls back to read-modify-write without locking when neither is
    available (race conditions possible).
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.write_text("{}")

    if HAS_FCNTL:
        with open(path, "r+", encoding="utf-8") as f:
            fcntl.flock(f, fcntl.LOCK_EX)
            try:
                try:
                    existing = json.load(f)
                except json.JSONDecodeError:
                    existing = {}

                updated = update_fn(existing)

                f.seek(0)
                json.dump(updated, f, indent=2, default=str)
                f.truncate()
            finally:
                fcntl.flock(f, fcntl.LOCK_UN)
    elif HAS_MSVCRT:
        max_retries = 5
        for attempt in range(max_retries):
            try:
                with open(path, "r+", encoding="utf-8") as f:
                    msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)
                    try:
                        try:
                            existing = json.load(f)
                        except json.JSONDecodeError:
                            existing = {}

                        updated = update_fn(existing)

                        f.seek(0)
                        f.truncate()
                        json.dump(updated, f, indent=2, default=str)
                    finally:
                        f.seek(0)
                        msvcrt.locking(f.fileno(), msvcrt.LK_UNLCK, 1)
                break
            except OSError:
                if attempt < max_retries - 1:
                    time.sleep(0.1 * (attempt + 1))
                else:
                    raise
    else:
        try:
            with open(path, "r", encoding="utf-8") as f:
                existing = json.load(f)
        except (json.JSONDecodeError, FileNotFoundError):
            existing = {}
        updated = update_fn(existing)
        path.write_text(json.dumps(updated, indent=2, default=str))


def get_state_path(session_id: str) -> Path:
    """Return the canonical state-file path for a session."""
    return LIVE_SESSIONS_DIR / f"{session_id}.json"


def read_existing_state(session_id: str) -> tuple[Optional[Path], dict]:
    """Read the existing state file for a session, if any."""
    state_file = get_state_path(session_id)
    if state_file.exists():
        try:
            return state_file, json.loads(state_file.read_text())
        except (json.JSONDecodeError, OSError):
            pass
    return None, {}


def _parse_iso(ts: Optional[str]) -> Optional[datetime]:
    if not ts:
        return None
    try:
        dt = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except ValueError:
        return None


def add_subagent(
    session_id: str,
    agent_id: str,
    agent_type: str,
) -> None:
    """Record a new running subagent on the session state."""
    now = datetime.now(timezone.utc).isoformat()

    existing_path, existing = read_existing_state(session_id)
    if not existing:
        # Session doesn't exist yet, wait for SessionStart.
        return

    target_path = existing_path or get_state_path(session_id)

    def update_fn(state: dict) -> dict:
        subagents = state.get("subagents", {})
        subagents[agent_id] = {
            "agent_id": agent_id,
            "agent_type": agent_type,
            "status": "running",
            "transcript_path": None,
            "started_at": now,
            "completed_at": None,
            "duration_ms": None,
        }
        state["subagents"] = subagents
        state["updated_at"] = now
        state["last_hook"] = "SubagentStart"
        return state

    write_state_atomic(target_path, update_fn)


def complete_subagent(
    session_id: str,
    agent_id: str,
    agent_transcript_path: Optional[str],
) -> None:
    """Mark a subagent as completed.

    Fixes the always-0-duration bug: if SubagentStart was never seen for
    this agent (e.g. tracker started mid-flight), record ``started_at=None``
    and ``duration_ms=None`` instead of falling back to ``now`` (which would
    yield duration 0 once the start hook arrived).
    """
    now_dt = datetime.now(timezone.utc)
    now = now_dt.isoformat()

    existing_path, existing = read_existing_state(session_id)
    if not existing:
        return

    target_path = existing_path or get_state_path(session_id)

    def update_fn(state: dict) -> dict:
        subagents = state.get("subagents", {})
        record = subagents.get(agent_id)
        if record is None:
            # SubagentStart was never observed for this agent — record the
            # completion but leave started_at/duration null instead of
            # creating a fake zero-duration entry.
            subagents[agent_id] = {
                "agent_id": agent_id,
                "agent_type": "unknown",
                "status": "completed",
                "transcript_path": agent_transcript_path,
                "started_at": None,
                "completed_at": now,
                "duration_ms": None,
            }
        else:
            record["status"] = "completed"
            record["completed_at"] = now
            if agent_transcript_path:
                record["transcript_path"] = agent_transcript_path
            started_dt = _parse_iso(record.get("started_at"))
            if started_dt is not None:
                record["duration_ms"] = int(
                    (now_dt - started_dt).total_seconds() * 1000
                )
            else:
                record["duration_ms"] = None
        state["subagents"] = subagents
        state["updated_at"] = now
        state["last_hook"] = "SubagentStop"
        return state

    write_state_atomic(target_path, update_fn)


def write_state(
    session_id: str,
    state: str,
    hook_data: Dict[str, Any],
    end_reason: Optional[str] = None,
    git_root: Optional[str] = None,
    source: Optional[str] = None,
    claude_model: Optional[str] = None,
    agent_type: Optional[str] = None,
    last_notification_message: Optional[str] = None,
    pending_permission_message: Optional[str] = None,
) -> None:
    """Write session state to disk under an exclusive lock.

    Files are always keyed by ``session_id``. Preserves ``started_at``,
    ``subagents``, and previously-resolved fields across updates.
    """
    now = datetime.now(timezone.utc).isoformat()
    target_path = get_state_path(session_id)

    def update_fn(existing: dict) -> dict:
        # NB: keep `slug` writable so legacy callers don't lose it, but we
        # never SET it here — the field stays whatever it was (usually None).
        new_data = {
            "session_id": session_id,
            "slug": existing.get("slug"),
            "state": state,
            "cwd": hook_data.get("cwd", existing.get("cwd", "")),
            "transcript_path": hook_data.get(
                "transcript_path", existing.get("transcript_path", "")
            ),
            "permission_mode": hook_data.get(
                "permission_mode", existing.get("permission_mode", "default")
            ),
            "last_hook": hook_data.get("hook_event_name", ""),
            "updated_at": now,
            "started_at": existing.get("started_at", now),
            "end_reason": end_reason if end_reason is not None else existing.get("end_reason"),
            "git_root": git_root or existing.get("git_root"),
            "source": source or existing.get("source"),
            "claude_model": claude_model or existing.get("claude_model"),
            "agent_type": agent_type or existing.get("agent_type"),
        }

        # Pending permission text is sticky until cleared by a non-WAITING transition.
        if pending_permission_message is not None:
            new_data["pending_permission_message"] = pending_permission_message
        elif state == "WAITING":
            new_data["pending_permission_message"] = existing.get("pending_permission_message")
        else:
            # Leaving WAITING clears the pending message.
            new_data["pending_permission_message"] = None

        if last_notification_message is not None:
            new_data["last_notification_message"] = last_notification_message
        else:
            new_data["last_notification_message"] = existing.get("last_notification_message")

        session_ids = existing.get("session_ids", [])
        if session_id not in session_ids:
            session_ids.append(session_id)
        new_data["session_ids"] = session_ids

        # Preserve subagents (parallel SubagentStart/Stop hooks may race with
        # SessionEnd; do not stomp the running list).
        new_data["subagents"] = existing.get("subagents", {})

        return new_data

    write_state_atomic(target_path, update_fn)


def _get(obj: Any, name: str, default: Any = None) -> Any:
    """Read a field from either a pydantic model or raw dict."""
    if obj is None:
        return default
    if hasattr(obj, name):
        val = getattr(obj, name, default)
        if val is not None:
            return val
    if isinstance(obj, dict):
        return obj.get(name, default)
    # Pydantic models with extra="allow" expose extras via model_extra.
    extra = getattr(obj, "model_extra", None)
    if isinstance(extra, dict) and name in extra:
        return extra[name]
    return default


def main() -> None:
    """Entry point — read hook JSON from stdin and update state."""
    try:
        data = json.loads(sys.stdin.read())
    except json.JSONDecodeError:
        return

    if not isinstance(data, dict):
        return

    hook_name = data.get("hook_event_name")
    session_id = data.get("session_id")
    if not hook_name or not session_id:
        return

    # Prefer parsed/typed view; fall back to the raw dict if parsing fails so
    # a captain-hook schema drift never breaks live tracking.
    try:
        hook = parse_hook_event(data)
    except Exception:
        hook = data  # type: ignore[assignment]

    if hook_name == "SessionStart":
        cwd = _get(hook, "cwd", "") or ""
        git_root = resolve_git_root(cwd) if cwd else None
        source = _get(hook, "source")
        model = _get(hook, "model")
        agent_type = _get(hook, "agent_type")
        write_state(
            session_id,
            "STARTING",
            data,
            git_root=git_root,
            source=source,
            claude_model=model,
            agent_type=agent_type,
        )

    elif hook_name == "UserPromptSubmit":
        write_state(session_id, "LIVE", data)

    elif hook_name == "PostToolUse":
        write_state(session_id, "LIVE", data)

    elif hook_name == "Notification":
        notification_type = _get(hook, "notification_type", "") or ""
        message = _get(hook, "message")
        if notification_type == "permission_prompt":
            write_state(
                session_id,
                "WAITING",
                data,
                pending_permission_message=message,
                last_notification_message=message,
            )
        elif notification_type == "idle_prompt":
            _, existing = read_existing_state(session_id)
            if existing.get("state") != "WAITING":
                write_state(
                    session_id,
                    "STALE",
                    data,
                    last_notification_message=message,
                )

    elif hook_name == "PermissionRequest":
        # Permission requests are essentially a richer WAITING signal.
        message = _get(hook, "message")
        write_state(
            session_id,
            "WAITING",
            data,
            pending_permission_message=message,
            last_notification_message=message,
        )

    elif hook_name == "Stop":
        # Only mark STOPPED if agent finished naturally (not forced continue).
        if not _get(hook, "stop_hook_active", True):
            write_state(session_id, "STOPPED", data)

    elif hook_name == "SubagentStart":
        agent_id = _get(hook, "agent_id")
        agent_type = _get(hook, "agent_type", "unknown") or "unknown"
        if agent_id:
            add_subagent(session_id, agent_id, agent_type)

    elif hook_name == "SubagentStop":
        agent_id = _get(hook, "agent_id")
        agent_transcript_path = _get(hook, "agent_transcript_path")
        if agent_id:
            complete_subagent(session_id, agent_id, agent_transcript_path)

    elif hook_name == "SessionEnd":
        reason = _get(hook, "reason")
        write_state(session_id, "ENDED", data, end_reason=reason)


if __name__ == "__main__":
    main()

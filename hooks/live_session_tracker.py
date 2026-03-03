#!/usr/bin/env python3
"""
Live session state tracker for Claude Code Karma.

Writes session state to ~/.claude_karma/live-sessions/{slug}.json
based on Claude Code hook events. Uses slug (human-readable session name)
as the primary identifier so resumed sessions update the same file.

Session States:
- STARTING: Session started, waiting for first message
- LIVE: Session actively running (tool execution)
- WAITING: Claude needs user input (AskUserQuestion, permission dialog)
- STOPPED: Agent finished but session still open
- STALE: User has been idle for 60+ seconds
- ENDED: Session terminated

Hook → State Mapping:
- SessionStart → STARTING (session started, JSONL may not exist yet)
- UserPromptSubmit → LIVE (prompt submitted, actively processing)
- PostToolUse → LIVE (indicates active work)
- Notification → WAITING (when permission_prompt - needs user input)
- Notification → STALE (when idle_prompt, only if not WAITING)
- Stop → STOPPED (when stop_hook_active=false)
- SessionEnd → ENDED (always, includes end_reason)

Note: WAITING persists until user responds or session ends. idle_prompt
does not overwrite WAITING state.

Slug-based tracking:
- Sessions are tracked by slug (e.g., "serene-meandering-scott")
- When a session is resumed, it gets a new UUID but keeps the same slug
- This allows us to track resumed sessions as one continuous entry
- If slug is not available (very early in session), falls back to session_id
"""

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

# Platform-specific file locking
# fcntl is Unix-only; on Windows we use msvcrt
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


def resolve_git_root(cwd: str) -> str | None:
    """Resolve the real git root from cwd.

    For worktrees, --show-toplevel returns the worktree root (not the main repo).
    We use --git-common-dir to find the shared .git directory, whose parent is
    the actual repository root.
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
            # For worktrees, common_dir points to the main repo's .git dir.
            # Its parent is the real repo root.
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

    Prevents race conditions when parallel subagents write to the same file.
    On Unix: Uses exclusive file lock (fcntl.LOCK_EX) to ensure only one process
    modifies the file at a time.
    On Windows: Uses msvcrt.locking() with retry logic for file locking.
    Fallback: If neither is available, uses non-locking writes (race conditions possible).

    Args:
        path: Path to state file
        update_fn: Function that takes existing state dict and returns updated dict
    """
    # Ensure parent directory exists
    path.parent.mkdir(parents=True, exist_ok=True)

    # Create file if it doesn't exist
    if not path.exists():
        path.write_text("{}")

    if HAS_FCNTL:
        # Unix: Use file locking for atomic updates
        with open(path, "r+", encoding="utf-8") as f:
            fcntl.flock(f, fcntl.LOCK_EX)  # Exclusive lock - blocks other writers
            try:
                # Read fresh data after acquiring lock
                try:
                    existing = json.load(f)
                except json.JSONDecodeError:
                    existing = {}

                # Apply update function
                updated = update_fn(existing)

                # Write updated data back
                f.seek(0)
                json.dump(updated, f, indent=2)
                f.truncate()
            finally:
                fcntl.flock(f, fcntl.LOCK_UN)  # Explicit unlock (also released on close)
    elif HAS_MSVCRT:
        # Windows: Use msvcrt file locking with retry logic
        max_retries = 5
        for attempt in range(max_retries):
            try:
                with open(path, "r+", encoding="utf-8") as f:
                    # Lock the file (non-blocking lock on first byte)
                    msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)
                    try:
                        # Read fresh data after acquiring lock
                        try:
                            existing = json.load(f)
                        except json.JSONDecodeError:
                            existing = {}

                        # Apply update function
                        updated = update_fn(existing)

                        # Write updated data back
                        f.seek(0)
                        f.truncate()
                        json.dump(updated, f, indent=2)
                    finally:
                        # Unlock the file
                        f.seek(0)
                        msvcrt.locking(f.fileno(), msvcrt.LK_UNLCK, 1)
                break  # Success, exit retry loop
            except OSError:
                if attempt < max_retries - 1:
                    time.sleep(0.1 * (attempt + 1))  # Exponential backoff
                else:
                    raise
    else:
        # Fallback: Read-modify-write without locking (no fcntl or msvcrt)
        # Race conditions are possible but this should be rare
        try:
            with open(path, "r", encoding="utf-8") as f:
                existing = json.load(f)
        except (json.JSONDecodeError, FileNotFoundError):
            existing = {}

        updated = update_fn(existing)
        path.write_text(json.dumps(updated, indent=2))


def extract_slug_from_jsonl(transcript_path: str) -> str | None:
    """
    Extract the slug from a session's JSONL file.

    The slug is stored in message entries and is consistent across
    all messages in a session. We read the first few lines to find it.
    """
    try:
        jsonl_file = Path(transcript_path)
        if not jsonl_file.exists():
            return None

        with open(jsonl_file, "r", encoding="utf-8") as f:
            # Read first 20 lines to find slug (usually in first few messages)
            for i, line in enumerate(f):
                if i >= 20:
                    break
                try:
                    entry = json.loads(line.strip())
                    slug = entry.get("slug")
                    if slug:
                        return slug
                except json.JSONDecodeError:
                    continue
    except (OSError, IOError):
        pass
    return None


def get_state_path_by_slug(slug: str) -> Path:
    """Get the path to a session's state file by slug."""
    return LIVE_SESSIONS_DIR / f"{slug}.json"


def get_state_path_by_session_id(session_id: str) -> Path:
    """Get the path to a session's state file by session_id (fallback)."""
    return LIVE_SESSIONS_DIR / f"{session_id}.json"


def find_existing_state_by_slug(slug: str) -> tuple[Path | None, dict]:
    """Find existing state file by slug and return (path, data)."""
    state_file = get_state_path_by_slug(slug)
    if state_file.exists():
        try:
            return state_file, json.loads(state_file.read_text())
        except (json.JSONDecodeError, OSError):
            pass
    return None, {}


def find_existing_state_by_session_id(session_id: str) -> tuple[Path | None, dict]:
    """Find existing state file by session_id (fallback) and return (path, data)."""
    state_file = get_state_path_by_session_id(session_id)
    if state_file.exists():
        try:
            return state_file, json.loads(state_file.read_text())
        except (json.JSONDecodeError, OSError):
            pass
    return None, {}


def read_existing_state(slug: str | None, session_id: str) -> tuple[Path | None, dict]:
    """
    Read existing state file, preferring slug-based lookup.

    Returns (state_file_path, data) tuple.
    """
    # First try slug-based lookup
    if slug:
        path, data = find_existing_state_by_slug(slug)
        if path:
            return path, data

    # Fallback to session_id-based lookup
    return find_existing_state_by_session_id(session_id)


def add_subagent(
    session_id: str,
    agent_id: str,
    agent_type: str,
    hook_data: dict,
    slug: str | None = None,
) -> None:
    """Add a new running subagent to the session state."""
    now = datetime.now(timezone.utc).isoformat()

    # Find existing state to get the target path
    existing_path, existing = read_existing_state(slug, session_id)

    if not existing:
        # Session doesn't exist yet, wait for SessionStart
        return

    # Determine target path
    target_path = existing_path or (
        get_state_path_by_slug(slug) if slug else get_state_path_by_session_id(session_id)
    )

    def update_fn(state: dict) -> dict:
        """Update function for atomic write."""
        subagents = state.get("subagents", {})
        subagents[agent_id] = {
            "agent_id": agent_id,
            "agent_type": agent_type,
            "status": "running",
            "transcript_path": None,
            "started_at": now,
            "completed_at": None,
        }
        state["subagents"] = subagents
        state["updated_at"] = now
        state["last_hook"] = "SubagentStart"
        return state

    write_state_atomic(target_path, update_fn)


def complete_subagent(
    session_id: str,
    agent_id: str,
    agent_transcript_path: str | None,
    hook_data: dict,
    slug: str | None = None,
) -> None:
    """Mark a subagent as completed."""
    now = datetime.now(timezone.utc).isoformat()

    # Find existing state to get the target path
    existing_path, existing = read_existing_state(slug, session_id)

    if not existing:
        return

    # Determine target path
    target_path = existing_path or (
        get_state_path_by_slug(slug) if slug else get_state_path_by_session_id(session_id)
    )

    def update_fn(state: dict) -> dict:
        """Update function for atomic write."""
        subagents = state.get("subagents", {})
        if agent_id in subagents:
            subagents[agent_id]["status"] = "completed"
            subagents[agent_id]["completed_at"] = now
            if agent_transcript_path:
                subagents[agent_id]["transcript_path"] = agent_transcript_path
        state["subagents"] = subagents
        state["updated_at"] = now
        state["last_hook"] = "SubagentStop"
        return state

    write_state_atomic(target_path, update_fn)


def write_state(
    session_id: str,
    state: str,
    hook_data: dict,
    slug: str | None = None,
    end_reason: str | None = None,
    git_root: str | None = None,
    source: str | None = None,
) -> None:
    """
    Write session state to disk using atomic file locking.

    Uses slug as the primary identifier (filename). Falls back to session_id
    if slug is not available. Preserves started_at and subagents from existing state.

    If we previously tracked by session_id and now have a slug, migrates
    to slug-based tracking by deleting the old session_id-based file.
    """
    now = datetime.now(timezone.utc).isoformat()

    # Determine the target file path
    if slug:
        target_path = get_state_path_by_slug(slug)
    else:
        target_path = get_state_path_by_session_id(session_id)

    # Check for migration (session_id file to slug file)
    old_path_to_delete: Path | None = None
    if slug:
        session_id_path = get_state_path_by_session_id(session_id)
        if session_id_path.exists() and session_id_path != target_path:
            old_path_to_delete = session_id_path

    def update_fn(existing: dict) -> dict:
        """Update function for atomic write."""
        # Build the new state data, preserving certain fields from existing
        new_data = {
            "session_id": session_id,
            "slug": slug,
            "state": state,
            "cwd": hook_data.get("cwd", ""),
            "transcript_path": hook_data.get("transcript_path", ""),
            "permission_mode": hook_data.get("permission_mode", "default"),
            "last_hook": hook_data.get("hook_event_name", ""),
            "updated_at": now,
            "started_at": existing.get("started_at", now),
            "end_reason": end_reason,
            # Preserve git_root from existing state, or use newly provided value
            "git_root": git_root or existing.get("git_root"),
            # Preserve source from existing state, or use newly provided value
            "source": source or existing.get("source"),
        }

        # Preserve session history if resuming
        session_ids = existing.get("session_ids", [])
        if session_id not in session_ids:
            session_ids.append(session_id)
        new_data["session_ids"] = session_ids

        # Preserve subagents from existing state (critical for race condition)
        new_data["subagents"] = existing.get("subagents", {})

        return new_data

    write_state_atomic(target_path, update_fn)

    # Migration: delete old session_id-based file after successful write
    if old_path_to_delete:
        try:
            old_path_to_delete.unlink()
        except OSError:
            pass


def main() -> None:
    """Main entry point - reads hook data from stdin and updates state."""
    try:
        data = json.loads(sys.stdin.read())
    except json.JSONDecodeError:
        # Silently exit on malformed input
        return

    hook_name = data.get("hook_event_name")
    session_id = data.get("session_id")
    transcript_path = data.get("transcript_path", "")

    if not hook_name or not session_id:
        return

    # Try to extract slug from the JSONL file
    # This will be available for resumed sessions and after first message
    slug = extract_slug_from_jsonl(transcript_path)

    if hook_name == "SessionStart":
        # New or resumed session - mark as STARTING
        # For resumed sessions, slug will be available from existing JSONL
        # For new sessions, slug won't be available yet (JSONL doesn't exist)
        # Resolve git root once at session start for submodule→parent mapping
        cwd = data.get("cwd", "")
        git_root = resolve_git_root(cwd) if cwd else None
        source = data.get("source")  # startup, resume, clear, compact
        write_state(session_id, "STARTING", data, slug=slug, git_root=git_root, source=source)

    elif hook_name == "UserPromptSubmit":
        # User submitted a prompt - mark as LIVE (actively processing)
        # This is when the .jsonl file gets created, slug should be available now
        write_state(session_id, "LIVE", data, slug=slug)

    elif hook_name == "PostToolUse":
        # Tool completed - session is actively working
        write_state(session_id, "LIVE", data, slug=slug)

    elif hook_name == "Notification":
        notification_type = data.get("notification_type", "")
        if notification_type == "permission_prompt":
            # Claude needs user input (AskUserQuestion, tool permission dialog)
            write_state(session_id, "WAITING", data, slug=slug)
        elif notification_type == "idle_prompt":
            # User has been idle for 60+ seconds
            # Only transition to STALE if not already WAITING
            # WAITING persists until user responds or session ends
            _, existing = read_existing_state(slug, session_id)
            if existing.get("state") != "WAITING":
                write_state(session_id, "STALE", data, slug=slug)

    elif hook_name == "Stop":
        # Only mark STOPPED if agent finished naturally (not forced continue)
        if not data.get("stop_hook_active", True):
            write_state(session_id, "STOPPED", data, slug=slug)

    elif hook_name == "SubagentStart":
        agent_id = data.get("agent_id")
        agent_type = data.get("agent_type", "unknown")
        if agent_id:
            add_subagent(session_id, agent_id, agent_type, data, slug=slug)

    elif hook_name == "SubagentStop":
        agent_id = data.get("agent_id")
        agent_transcript_path = data.get("agent_transcript_path")
        if agent_id:
            complete_subagent(session_id, agent_id, agent_transcript_path, data, slug=slug)

    elif hook_name == "SessionEnd":
        # Session terminated - mark ENDED with reason
        reason = data.get("reason")
        write_state(session_id, "ENDED", data, slug=slug, end_reason=reason)


if __name__ == "__main__":
    main()

"""
Live session state model.

Reads JSON state files from ~/.claude_karma/live-sessions/{slug}.json
written by Claude Code hooks during active sessions.

Sessions are tracked by slug (human-readable name like "serene-meandering-scott")
rather than session_id, so resumed sessions update the same file instead of
creating new entries.

Session states:
- STARTING: Session started, waiting for first message
- LIVE: Session actively running (tool execution)
- WAITING: Claude needs user input (AskUserQuestion, permission dialog)
- STOPPED: Agent finished but session still open
- STALE: User has been idle for 60+ seconds
- ENDED: Session terminated
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from enum import Enum
from functools import cached_property
from pathlib import Path
from typing import Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field

try:
    import aiofiles

    AIOFILES_AVAILABLE = True
except ImportError:
    AIOFILES_AVAILABLE = False

logger = logging.getLogger(__name__)


def _parse_iso_timestamp(ts: str) -> datetime:
    """Parse ISO timestamp, handling Z suffix for UTC."""
    return datetime.fromisoformat(ts.replace("Z", "+00:00"))


class SessionState(str, Enum):
    """Current state of a live session."""

    STARTING = "STARTING"  # Session started, waiting for first message
    LIVE = "LIVE"
    WAITING = "WAITING"
    STOPPED = "STOPPED"
    STALE = "STALE"
    ENDED = "ENDED"


class SessionStatus(str, Enum):
    """Computed status based on state and activity."""

    STARTING = "starting"  # Session started, waiting for first user prompt
    ACTIVE = "active"  # State is LIVE and recent activity (< 30s idle)
    IDLE = "idle"  # State is LIVE but no recent activity (> 30s idle)
    WAITING_INPUT = "waiting"  # Claude needs user input (AskUserQuestion, permission)
    STOPPED = "stopped"  # Agent stopped but session open
    STALE = "stale"  # User has been idle for 60+ seconds
    ENDED = "ended"  # Session terminated


class SubagentStatus(str, Enum):
    """Status of a subagent."""

    RUNNING = "running"
    COMPLETED = "completed"
    ERROR = "error"


class SubagentState(BaseModel):
    """
    State of an individual subagent within a session.

    Tracked by agent_id, updated by SubagentStart and SubagentStop hooks.
    """

    model_config = ConfigDict(frozen=True, extra="allow")

    agent_id: str = Field(..., description="Unique subagent identifier")
    agent_type: str = Field(..., description="Type of subagent (Bash, Explore, Plan, etc.)")
    status: SubagentStatus = Field(..., description="Current subagent status")
    transcript_path: Optional[str] = Field(None, description="Path to subagent's JSONL transcript")
    started_at: Optional[datetime] = Field(
        None,
        description=(
            "When subagent started. May be null if SubagentStop fired without a prior "
            "SubagentStart (e.g. tracker started mid-flight)."
        ),
    )
    completed_at: Optional[datetime] = Field(
        None, description="When subagent finished (if completed)"
    )
    duration_ms: Optional[int] = Field(
        None,
        description=(
            "Duration in ms between SubagentStart and SubagentStop. Null when started_at is "
            "unknown."
        ),
    )


class LiveSessionState(BaseModel):
    """
    State of a currently running Claude Code session.

    Written by hooks to ~/.claude_karma/live-sessions/{slug}.json
    Sessions are tracked by slug so resumed sessions update the same file.
    """

    model_config = ConfigDict(frozen=True, extra="allow", ignored_types=(cached_property,))

    # Core identifiers
    session_id: str = Field(..., description="Current active session UUID")
    slug: Optional[str] = Field(
        None, description="Human-readable session name (e.g., 'serene-meandering-scott')"
    )
    session_ids: List[str] = Field(
        default_factory=list,
        description="All session UUIDs that have been part of this slug's lifecycle",
    )
    state: SessionState = Field(..., description="Current session state")

    # Project context
    cwd: str = Field(..., description="Current working directory")
    transcript_path: str = Field(..., description="Path to session JSONL file")
    permission_mode: str = Field("default", description="Current permission mode")

    # Hook tracking
    last_hook: str = Field(..., description="Last hook that updated state")
    updated_at: datetime = Field(..., description="Last state update timestamp")
    started_at: datetime = Field(..., description="When session started")

    # End state
    end_reason: Optional[str] = Field(
        None, description="Reason for session end (only set when state=ENDED)"
    )

    # Git context (resolved at SessionStart for submodule→parent mapping)
    git_root: Optional[str] = Field(
        None, description="Git repository root path (resolved from cwd at SessionStart)"
    )

    # SessionStart source (startup, resume, clear, compact)
    source: Optional[str] = Field(
        None, description="SessionStart source: startup, resume, clear, compact"
    )

    # Surfaced from hook payloads (optional, added by hooks/live_session_tracker.py)
    claude_model: Optional[str] = Field(
        None, description="Model identifier from SessionStart (e.g. claude-sonnet-4-...)"
    )
    agent_type: Optional[str] = Field(
        None, description="Agent type if started with --agent flag (Explore, Plan, ...)"
    )
    pending_permission_message: Optional[str] = Field(
        None,
        description=(
            "Latest permission_prompt message while state=WAITING. Cleared on transition out."
        ),
    )
    last_notification_message: Optional[str] = Field(
        None, description="Last Notification or PermissionRequest message text"
    )

    # Subagent tracking
    subagents: Dict[str, SubagentState] = Field(
        default_factory=dict, description="Active and completed subagents keyed by agent_id"
    )

    @classmethod
    def from_file(cls, path: Path) -> "LiveSessionState":
        """Load live session state from a JSON file."""
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)

        # Parse datetime strings using helper
        if isinstance(data.get("updated_at"), str):
            data["updated_at"] = _parse_iso_timestamp(data["updated_at"])
        if isinstance(data.get("started_at"), str):
            data["started_at"] = _parse_iso_timestamp(data["started_at"])

        # Parse subagent datetime strings
        if "subagents" in data and isinstance(data["subagents"], dict):
            for _agent_id, subagent_data in data["subagents"].items():
                if not isinstance(subagent_data, dict):
                    continue
                # Simplified datetime extraction
                if isinstance(subagent_data.get("started_at"), str):
                    subagent_data["started_at"] = _parse_iso_timestamp(subagent_data["started_at"])
                if isinstance(subagent_data.get("completed_at"), str):
                    subagent_data["completed_at"] = _parse_iso_timestamp(
                        subagent_data["completed_at"]
                    )

        return cls(**data)

    @classmethod
    async def from_file_async(cls, path: Path) -> "LiveSessionState":
        """Load live session state from a JSON file asynchronously."""
        if not AIOFILES_AVAILABLE:
            raise ImportError("aiofiles is required for async file operations")

        async with aiofiles.open(path, "r", encoding="utf-8") as f:
            content = await f.read()
        data = json.loads(content)

        # Parse datetime strings using helper
        if isinstance(data.get("updated_at"), str):
            data["updated_at"] = _parse_iso_timestamp(data["updated_at"])
        if isinstance(data.get("started_at"), str):
            data["started_at"] = _parse_iso_timestamp(data["started_at"])

        # Parse subagent datetime strings
        if "subagents" in data and isinstance(data["subagents"], dict):
            for _agent_id, subagent_data in data["subagents"].items():
                if not isinstance(subagent_data, dict):
                    continue
                if isinstance(subagent_data.get("started_at"), str):
                    subagent_data["started_at"] = _parse_iso_timestamp(subagent_data["started_at"])
                if isinstance(subagent_data.get("completed_at"), str):
                    subagent_data["completed_at"] = _parse_iso_timestamp(
                        subagent_data["completed_at"]
                    )

        return cls(**data)

    @property
    def duration_seconds(self) -> float:
        """Calculate current session duration."""
        return (self.updated_at - self.started_at).total_seconds()

    @property
    def idle_seconds(self) -> float:
        """Seconds since last activity."""
        now = datetime.now(timezone.utc)
        last = self.updated_at
        if last.tzinfo is None:
            last = last.replace(tzinfo=timezone.utc)
        return (now - last).total_seconds()

    @property
    def project_encoded_name(self) -> Optional[str]:
        """Extract encoded project name from transcript path."""
        try:
            # transcript_path: ~/.claude/projects/{encoded-name}/{uuid}.jsonl
            path = Path(self.transcript_path)
            if "projects" in path.parts:
                projects_idx = path.parts.index("projects")
                if projects_idx + 1 < len(path.parts):
                    return path.parts[projects_idx + 1]
        except Exception:
            pass
        return None

    @cached_property
    def transcript_exists(self) -> bool:
        """Check if the transcript JSONL file actually exists on disk.

        For worktree sessions, the transcript_path may point to the worktree's
        encoded project dir, but Claude Code may store the JSONL under the real
        project's dir (using git_root). Check both locations.
        """
        if not self.transcript_path:
            return False
        tp = Path(self.transcript_path)
        if tp.exists():
            return True

        # Fallback: check under the git_root-derived project dir
        # e.g., transcript_path encodes worktree cwd, but JSONL is under git_root project
        if self.git_root and self.session_id:
            git_encoded = "-" + self.git_root.lstrip("/").replace("/", "-")
            fallback = tp.parent.parent / git_encoded / tp.name
            if fallback.exists():
                return True

        return False

    @property
    def resolved_project_encoded_name(self) -> Optional[str]:
        """Project encoded name with git-root fallback for worktree/submodule sessions.

        When a session starts from a worktree or submodule, the transcript_path
        may encode the worktree/submodule path. This property falls back to
        git_root to find the correct parent project.
        """
        primary = self.project_encoded_name

        # For worktree sessions, resolve to the real project.
        # The transcript may exist at the worktree path (e.g., .claude/worktrees/
        # inside the repo creates a valid JSONL under the worktree-encoded dir),
        # but the session should still roll up to the real project.
        if primary:
            from services.desktop_sessions import (
                _extract_project_prefix_from_worktree,
                is_worktree_project,
            )

            if is_worktree_project(primary):
                # Primary strategy: extract project prefix from the encoded name.
                # This is purely string-based and handles all worktree patterns
                # (CLI, Desktop, superpowers) without depending on git_root.
                prefix = _extract_project_prefix_from_worktree(primary)
                if prefix:
                    return prefix

        # If transcript exists at the primary (cwd-derived) path, use it
        if primary and self.transcript_path and Path(self.transcript_path).exists():
            return primary

        # Fallback: use git_root to compute parent project name
        # This handles submodule sessions (JSONL stored under parent repo)
        if self.git_root:
            encoded = "-" + self.git_root.lstrip("/").replace("/", "-")
            return encoded

        return primary  # Best effort

    @cached_property
    def active_subagent_count(self) -> int:
        """Count of currently running subagents."""
        return sum(1 for s in self.subagents.values() if s.status == SubagentStatus.RUNNING)

    @cached_property
    def total_subagent_count(self) -> int:
        """Total number of subagents (running + completed)."""
        return len(self.subagents)


def get_live_sessions_dir() -> Path:
    """Get the ~/.claude_karma/live-sessions directory."""
    return Path.home() / ".claude_karma" / "live-sessions"


def list_live_session_files() -> List[Path]:
    """List all live session JSON files."""
    live_dir = get_live_sessions_dir()
    if not live_dir.exists():
        return []
    return list(live_dir.glob("*.json"))


def load_live_session(identifier: str) -> Optional[LiveSessionState]:
    """
    Load a specific live session by slug or session_id.

    First tries to find a file named {identifier}.json (works for both slug and session_id).
    If not found by direct match, searches all files for a matching session_id.
    """
    live_dir = get_live_sessions_dir()

    # Try direct file lookup (works for slug-based files and legacy session_id files)
    state_file = live_dir / f"{identifier}.json"
    if state_file.exists():
        try:
            return LiveSessionState.from_file(state_file)
        except (json.JSONDecodeError, ValueError, KeyError) as e:
            logger.warning(f"Failed to parse live session {identifier}: {e}")
            return None

    # If not found, search for session_id in all files
    # This handles the case where we're looking up by session_id but file is named by slug
    for state_file in list_live_session_files():
        try:
            session = LiveSessionState.from_file(state_file)
            if session.session_id == identifier or identifier in session.session_ids:
                return session
        except (json.JSONDecodeError, ValueError, KeyError):
            continue

    return None


def load_live_session_by_slug(slug: str) -> Optional[LiveSessionState]:
    """Load a specific live session by slug."""
    live_dir = get_live_sessions_dir()
    state_file = live_dir / f"{slug}.json"
    if not state_file.exists():
        return None
    try:
        return LiveSessionState.from_file(state_file)
    except (json.JSONDecodeError, ValueError, KeyError) as e:
        logger.warning(f"Failed to parse live session {slug}: {e}")
        return None


def load_all_live_sessions() -> List[LiveSessionState]:
    """Load all live session states.

    Tolerates per-file failures (corruption, partial writes, files
    deleted between glob and open) so a single bad file doesn't abort
    the whole batch — important for callers like the ticket-session
    enrichment service that depend on best-effort coverage.
    """
    sessions = []
    for state_file in list_live_session_files():
        try:
            sessions.append(LiveSessionState.from_file(state_file))
        except (json.JSONDecodeError, ValueError, KeyError, OSError, UnicodeDecodeError) as e:
            logger.warning(f"Failed to parse live session {state_file.stem}: {e}")
            continue
    return sessions


async def load_all_live_sessions_async(
    auto_cleanup_seconds: int = 600,  # retained for backward compat, ignored
) -> List[LiveSessionState]:
    """Load all live session states asynchronously in parallel.

    This function is now strictly side-effect-free — it never deletes
    files. Stale-file cleanup is owned by
    :func:`services.live_session_store.purge_old_files`, which the
    session reconciler invokes on a timer.

    The ``auto_cleanup_seconds`` parameter is kept for ABI compatibility
    with callers that still pass it, but is no longer honored.
    """
    import asyncio

    state_files = list_live_session_files()
    if not state_files:
        return []

    async def load_one(path: Path) -> Optional[LiveSessionState]:
        try:
            return await LiveSessionState.from_file_async(path)
        except (json.JSONDecodeError, ValueError, KeyError) as e:
            logger.warning(f"Failed to parse live session {path.stem}: {e}")
            return None

    results = await asyncio.gather(*[load_one(p) for p in state_files])
    return [r for r in results if r is not None]


def delete_live_session(identifier: str) -> bool:
    """
    Delete a live session state file by slug or session_id.

    Delegates to :func:`services.live_session_store.delete_by_identifier`
    so all delete paths go through the same lock-aware code.
    """
    # Late import: live_session_store imports nothing from this module,
    # but keeping the import local avoids accidental circulars at startup.
    from services.live_session_store import delete_by_identifier

    return delete_by_identifier(identifier)


def cleanup_old_session_files() -> dict:
    """
    Delete stale ENDED/STARTING state files.

    Slug-based filenames are no longer written, so the old duplicate-slug
    dedup logic is obsolete. This function now delegates to
    :func:`services.live_session_store.purge_old_files` for a single
    lock-aware path, and reports the count via the legacy return shape.
    """
    from services.live_session_store import purge_old_files

    before = len(list_live_session_files())
    deleted = purge_old_files()
    after = len(list_live_session_files())
    return {"deleted": deleted, "kept": after, "errors": max(0, before - after - deleted)}

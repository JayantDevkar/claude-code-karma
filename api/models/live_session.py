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
    started_at: datetime = Field(..., description="When subagent started")
    completed_at: Optional[datetime] = Field(
        None, description="When subagent finished (if completed)"
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
    """Load all live session states."""
    sessions = []
    for state_file in list_live_session_files():
        try:
            sessions.append(LiveSessionState.from_file(state_file))
        except (json.JSONDecodeError, ValueError, KeyError) as e:
            logger.warning(f"Failed to parse live session {state_file.stem}: {e}")
            continue
    return sessions


async def load_all_live_sessions_async(
    auto_cleanup_seconds: int = 600,
) -> List[LiveSessionState]:
    """Load all live session states asynchronously in parallel.

    Args:
        auto_cleanup_seconds: Auto-delete ENDED session files older than this many
            seconds (default 600 = 10 minutes). Set to 0 to disable auto-cleanup.
            This prevents stale ENDED files from accumulating and slowing down
            all live-session endpoints.
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
    sessions = [r for r in results if r is not None]

    # Auto-cleanup: delete old ENDED session files to prevent accumulation
    if auto_cleanup_seconds > 0:
        kept: List[LiveSessionState] = []
        for state in sessions:
            if (
                state.state in (SessionState.ENDED, SessionState.STARTING)
                and state.idle_seconds > auto_cleanup_seconds
            ):
                # Delete the stale file
                try:
                    identifier = state.slug or state.session_id
                    live_dir = get_live_sessions_dir()
                    state_file = live_dir / f"{identifier}.json"
                    if state_file.exists():
                        state_file.unlink()
                        logger.debug(
                            f"Auto-cleaned {state.state.value.lower()} session: {identifier}"
                        )
                    else:
                        # Fallback: try session_id-named file
                        state_file = live_dir / f"{state.session_id}.json"
                        if state_file.exists():
                            state_file.unlink()
                            logger.debug(
                                f"Auto-cleaned {state.state.value.lower()} session: {state.session_id}"
                            )
                except OSError as e:
                    logger.warning(f"Failed to auto-clean session {state.session_id}: {e}")
                    kept.append(state)  # Keep if deletion fails
            else:
                kept.append(state)
        if len(kept) < len(sessions):
            logger.info(
                f"Auto-cleaned {len(sessions) - len(kept)} old ended/starting sessions "
                f"(kept {len(kept)})"
            )
        sessions = kept

    return sessions


def delete_live_session(identifier: str) -> bool:
    """
    Delete a live session state file by slug or session_id.

    First tries direct file lookup, then searches for matching session_id.
    """
    live_dir = get_live_sessions_dir()

    # Try direct file lookup
    state_file = live_dir / f"{identifier}.json"
    if state_file.exists():
        try:
            state_file.unlink()
            return True
        except OSError as e:
            logger.error(f"Failed to delete live session {identifier}: {e}")
            return False

    # Search for session_id match in all files
    for state_file in list_live_session_files():
        try:
            with open(state_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            if data.get("session_id") == identifier or identifier in data.get("session_ids", []):
                state_file.unlink()
                return True
        except (json.JSONDecodeError, OSError):
            continue

    return False


def cleanup_old_session_files() -> dict:
    """
    Clean up old session_id-based files that have been superseded by slug-based files.

    When a session is resumed, the tracker creates a new slug-based file and tries
    to delete the old session_id-based file. This function cleans up any that were missed.

    Returns:
        dict with counts: {"deleted": N, "kept": N, "errors": N}
    """
    live_dir = get_live_sessions_dir()
    if not live_dir.exists():
        return {"deleted": 0, "kept": 0, "errors": 0}

    # First, load all sessions and build a map of slug -> state files
    slug_to_files: dict = {}  # slug -> list of (path, data)
    session_id_files: list = []  # files without slugs

    for state_file in list_live_session_files():
        try:
            with open(state_file, "r", encoding="utf-8") as f:
                data = json.load(f)

            slug = data.get("slug")
            if slug:
                if slug not in slug_to_files:
                    slug_to_files[slug] = []
                slug_to_files[slug].append((state_file, data))
            else:
                session_id_files.append((state_file, data))
        except (json.JSONDecodeError, OSError) as e:
            logger.warning(f"Error reading {state_file}: {e}")
            continue

    deleted = 0
    kept = 0
    errors = 0

    # For each slug, keep only the most recently updated file
    for _slug, files in slug_to_files.items():
        if len(files) <= 1:
            kept += 1
            continue

        # Sort by updated_at, keep the most recent
        def get_updated_at(item: tuple) -> str:
            return item[1].get("updated_at", "")

        files.sort(key=get_updated_at, reverse=True)

        # Keep the first (most recent), delete the rest
        kept += 1
        for path, _data in files[1:]:
            try:
                path.unlink()
                deleted += 1
                logger.info(f"Deleted duplicate slug file: {path.name}")
            except OSError as e:
                logger.error(f"Failed to delete {path}: {e}")
                errors += 1

    # Keep session_id files that don't have a corresponding slug file
    for path, data in session_id_files:
        # Check if there's a slug-based file that includes this session_id
        session_id = data.get("session_id", "")
        is_duplicate = False

        for _slug, files in slug_to_files.items():
            for _, slug_data in files:
                if session_id in slug_data.get("session_ids", []):
                    is_duplicate = True
                    break
            if is_duplicate:
                break

        if is_duplicate:
            try:
                path.unlink()
                deleted += 1
                logger.info(f"Deleted superseded session_id file: {path.name}")
            except OSError as e:
                logger.error(f"Failed to delete {path}: {e}")
                errors += 1
        else:
            kept += 1

    return {"deleted": deleted, "kept": kept, "errors": errors}

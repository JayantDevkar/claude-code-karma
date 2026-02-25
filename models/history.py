"""
History model for parsing ~/.claude/history.jsonl

This file contains prompts from all sessions, including those that have been
cleaned up. We use this to show "archived" prompts where the session file
no longer exists.
"""

import json
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional


@dataclass
class HistoryEntry:
    """A single entry from history.jsonl."""

    display: str
    timestamp: datetime
    project: str
    session_id: Optional[str] = None

    @classmethod
    def from_dict(cls, data: dict) -> Optional["HistoryEntry"]:
        """Parse a history entry from JSON dict."""
        try:
            display = data.get("display", "")
            timestamp_ms = data.get("timestamp")
            project = data.get("project", "")

            if not timestamp_ms or not project:
                return None

            # Skip command entries like /exit, /model, etc.
            if display.startswith("/"):
                return None

            # Skip empty prompts
            if not display.strip():
                return None

            timestamp = datetime.fromtimestamp(timestamp_ms / 1000)

            return cls(
                display=display,
                timestamp=timestamp,
                project=project,
                session_id=data.get("sessionId"),
            )
        except Exception:
            return None


@dataclass
class ArchivedPrompt:
    """A prompt from an archived/deleted session."""

    timestamp: datetime
    display: str
    session_id: Optional[str] = None


@dataclass
class ArchivedSession:
    """An archived session with its prompts."""

    session_id: str  # UUID or "orphan-{timestamp}" for ungrouped
    prompts: list[ArchivedPrompt]
    first_prompt_preview: str  # First 150 chars of first prompt
    prompt_count: int
    date_range_start: datetime
    date_range_end: datetime
    is_orphan: bool  # True if prompts were grouped by time proximity


@dataclass
class ArchivedProject:
    """Archived sessions grouped by project."""

    project_path: str
    project_name: str
    encoded_name: str
    sessions: list[ArchivedSession]
    date_range_start: datetime
    date_range_end: datetime

    @property
    def session_count(self) -> int:
        return len(self.sessions)

    @property
    def prompt_count(self) -> int:
        return sum(s.prompt_count for s in self.sessions)


def encode_path(path: str) -> str:
    """Encode a path to Claude's format: /Users/me/repo -> -Users-me-repo"""
    if path.startswith("/"):
        return "-" + path[1:].replace("/", "-")
    return path.replace("/", "-")


def get_project_name(path: str) -> str:
    """Extract a readable project name from a full path."""
    # Get last 2 path components for context
    parts = path.rstrip("/").split("/")
    if len(parts) >= 2:
        return "/".join(parts[-2:])
    return parts[-1] if parts else path


def list_existing_session_ids(projects_dir: Path) -> set[str]:
    """Get set of all existing session UUIDs (sessions that have .jsonl files)."""
    session_ids = set()

    if not projects_dir.exists():
        return session_ids

    for project_dir in projects_dir.iterdir():
        if not project_dir.is_dir():
            continue
        for jsonl_file in project_dir.glob("*.jsonl"):
            # Skip agent files
            if jsonl_file.name.startswith("agent-"):
                continue
            # Extract UUID from filename (remove .jsonl)
            session_ids.add(jsonl_file.stem)

    return session_ids


def parse_history_file(history_path: Path) -> list[HistoryEntry]:
    """Parse all entries from history.jsonl."""
    entries = []

    if not history_path.exists():
        return entries

    with open(history_path, "r") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                data = json.loads(line)
                entry = HistoryEntry.from_dict(data)
                if entry:
                    entries.append(entry)
            except json.JSONDecodeError:
                continue

    return entries


def _create_archived_session(
    session_id: str,
    entries: list[HistoryEntry],
    is_orphan: bool,
) -> ArchivedSession:
    """Create an ArchivedSession from a list of entries."""
    prompts = [
        ArchivedPrompt(
            timestamp=e.timestamp,
            display=e.display,
            session_id=e.session_id,
        )
        for e in entries
    ]

    first_prompt = prompts[0].display if prompts else ""
    preview = first_prompt[:150] + "..." if len(first_prompt) > 150 else first_prompt

    return ArchivedSession(
        session_id=session_id,
        prompts=prompts,
        first_prompt_preview=preview,
        prompt_count=len(prompts),
        date_range_start=prompts[0].timestamp,
        date_range_end=prompts[-1].timestamp,
        is_orphan=is_orphan,
    )


def _group_by_time_proximity(
    entries: list[HistoryEntry],
    gap_minutes: int,
) -> list[ArchivedSession]:
    """Group entries that are within gap_minutes of each other."""
    if not entries:
        return []

    sessions = []
    current_group = [entries[0]]

    for i in range(1, len(entries)):
        prev_ts = entries[i - 1].timestamp
        curr_ts = entries[i].timestamp
        gap = (curr_ts - prev_ts).total_seconds() / 60

        if gap <= gap_minutes:
            current_group.append(entries[i])
        else:
            # Start new group
            sessions.append(
                _create_archived_session(
                    session_id=f"orphan-{int(current_group[0].timestamp.timestamp())}",
                    entries=current_group,
                    is_orphan=True,
                )
            )
            current_group = [entries[i]]

    # Don't forget last group
    if current_group:
        sessions.append(
            _create_archived_session(
                session_id=f"orphan-{int(current_group[0].timestamp.timestamp())}",
                entries=current_group,
                is_orphan=True,
            )
        )

    return sessions


def group_prompts_into_sessions(
    entries: list[HistoryEntry],
    time_gap_minutes: int = 30,
) -> list[ArchivedSession]:
    """
    Group history entries into sessions.

    - Entries with sessionId are grouped by that ID
    - Entries without sessionId are grouped by time proximity
    """
    # Group entries with session_id
    by_session: dict[str, list[HistoryEntry]] = defaultdict(list)
    orphans: list[HistoryEntry] = []

    for entry in entries:
        if entry.session_id:
            by_session[entry.session_id].append(entry)
        else:
            orphans.append(entry)

    sessions = []

    # Create sessions from known session_ids
    for session_id, session_entries in by_session.items():
        session_entries.sort(key=lambda e: e.timestamp)
        sessions.append(
            _create_archived_session(
                session_id=session_id,
                entries=session_entries,
                is_orphan=False,
            )
        )

    # Group orphans by time proximity
    if orphans:
        orphans.sort(key=lambda e: e.timestamp)
        orphan_sessions = _group_by_time_proximity(orphans, time_gap_minutes)
        sessions.extend(orphan_sessions)

    # Sort by most recent activity
    sessions.sort(key=lambda s: s.date_range_end, reverse=True)

    return sessions


def get_archived_prompts(
    claude_base: Path,
    project_filter: Optional[str] = None,
) -> tuple[list[ArchivedProject], int, int]:
    """
    Get archived prompts (prompts where session file no longer exists).

    Args:
        claude_base: Path to ~/.claude directory
        project_filter: Optional encoded project name to filter by

    Returns:
        Tuple of (list of ArchivedProject, total_session_count, total_prompt_count)
    """
    history_path = claude_base / "history.jsonl"
    projects_dir = claude_base / "projects"

    # Parse all history entries
    all_entries = parse_history_file(history_path)

    # Get existing session IDs
    existing_sessions = list_existing_session_ids(projects_dir)

    # Filter to entries without session_id (older entries) or with session that no longer exists
    archived_entries = []
    for entry in all_entries:
        # Entries without sessionId are definitely archived (older format)
        if entry.session_id is None:
            archived_entries.append(entry)
        # Entries with sessionId that no longer exists are archived
        elif entry.session_id not in existing_sessions:
            archived_entries.append(entry)

    # Group by project
    by_project: dict[str, list[HistoryEntry]] = defaultdict(list)
    for entry in archived_entries:
        by_project[entry.project].append(entry)

    # Convert to ArchivedProject objects
    archived_projects = []
    total_session_count = 0
    total_prompt_count = 0

    for project_path, entries in by_project.items():
        encoded_name = encode_path(project_path)

        # Apply project filter if provided
        if project_filter and encoded_name != project_filter:
            continue

        # Group entries into sessions
        sessions = group_prompts_into_sessions(entries)

        if sessions:
            # Calculate date range from all sessions
            all_timestamps = [s.date_range_start for s in sessions] + [
                s.date_range_end for s in sessions
            ]
            date_range_start = min(all_timestamps)
            date_range_end = max(all_timestamps)

            archived_projects.append(
                ArchivedProject(
                    project_path=project_path,
                    project_name=get_project_name(project_path),
                    encoded_name=encoded_name,
                    sessions=sessions,
                    date_range_start=date_range_start,
                    date_range_end=date_range_end,
                )
            )
            total_session_count += len(sessions)
            total_prompt_count += sum(s.prompt_count for s in sessions)

    # Sort projects by most recent activity (descending)
    archived_projects.sort(key=lambda p: p.date_range_end, reverse=True)

    return archived_projects, total_session_count, total_prompt_count

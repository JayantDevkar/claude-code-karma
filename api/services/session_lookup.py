"""
Centralized session lookup utilities.

Phase 2 refactor: Consolidates ~50+ lines of duplicated session lookup logic
from sessions.py, subagent_sessions.py, and live_sessions.py into a single
service with consistent error handling and return types.
"""

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from config import settings
from models import Agent, Session

logger = logging.getLogger(__name__)


@dataclass
class SessionLookupResult:
    """Result of looking up a session by UUID."""

    session: Session
    project_encoded_name: str


@dataclass
class SubagentLookupResult:
    """Result of looking up a subagent."""

    agent: Agent
    parent_session: Session
    project_encoded_name: str


def _is_valid_session_filename(path: Path) -> bool:
    """
    Check if a JSONL file path looks like a valid session file.

    Valid session files have UUID-like stems with dashes and alphanumeric characters.
    This filters out non-session files like sessions-index.json.

    Args:
        path: Path to check

    Returns:
        True if the filename looks like a valid session file
    """
    stem = path.stem
    # Must contain dashes (UUID format)
    if "-" not in stem:
        return False
    # After removing dashes/underscores, should be alphanumeric
    if not stem.replace("-", "").replace("_", "").isalnum():
        return False
    return True


def find_session_with_project(uuid: str) -> Optional[SessionLookupResult]:
    """
    Find a session by UUID and return both session and project encoded name.

    Uses DB for O(1) project lookup when available, falls back to O(n) directory scan.

    Args:
        uuid: Session UUID to find

    Returns:
        SessionLookupResult with session and project info, or None if not found.
    """
    projects_dir = settings.projects_dir

    # DB fast path: O(1) project lookup instead of scanning all directories
    try:
        from db.connection import sqlite_read

        with sqlite_read() as conn:
            if conn is not None:
                row = conn.execute(
                    "SELECT project_encoded_name, source_encoded_name FROM sessions WHERE uuid = ?",
                    (uuid,),
                ).fetchone()
                if row:
                    source_enc = row["source_encoded_name"] or row["project_encoded_name"]
                    jsonl_path = projects_dir / source_enc / f"{uuid}.jsonl"
                    if jsonl_path.exists():
                        return SessionLookupResult(
                            session=Session.from_path(jsonl_path),
                            project_encoded_name=row["project_encoded_name"],
                        )
    except Exception:
        logger.debug("DB fast path failed for session %s, falling back to dir scan", uuid, exc_info=True)

    # JSONL fallback: O(n) directory scan
    if projects_dir.exists():
        for encoded_dir in projects_dir.iterdir():
            if encoded_dir.is_dir() and encoded_dir.name.startswith("-"):
                jsonl_path = encoded_dir / f"{uuid}.jsonl"
                if jsonl_path.exists():
                    return SessionLookupResult(
                        session=Session.from_path(jsonl_path),
                        project_encoded_name=encoded_dir.name,
                    )

    # Remote fallback: search synced remote sessions
    from services.remote_sessions import find_remote_session

    remote = find_remote_session(uuid)
    if remote:
        return SessionLookupResult(
            session=remote.session,
            project_encoded_name=remote.local_encoded_name,
        )

    return None


def find_session(uuid: str) -> Optional[Session]:
    """
    Find a session by UUID across all projects.

    Convenience wrapper around find_session_with_project() that returns
    just the Session object.

    Args:
        uuid: Session UUID to find

    Returns:
        Session if found, None otherwise.
    """
    result = find_session_with_project(uuid)
    return result.session if result else None


def find_session_by_message_uuid(message_uuid: str) -> Optional[SessionLookupResult]:
    """
    Find a session that contains a message with the given UUID.

    Uses DB message_uuids table for O(1) lookup when available,
    falls back to O(n*m) JSONL scan.

    Args:
        message_uuid: The UUID of a message to search for

    Returns:
        SessionLookupResult with session and project info, or None if not found.
    """
    projects_dir = settings.projects_dir

    # DB fast path: O(1) lookup via message_uuids table
    try:
        from db.connection import sqlite_read
        from db.queries import query_session_by_message_uuid as db_lookup

        with sqlite_read() as conn:
            if conn is not None:
                row = db_lookup(conn, message_uuid)
                if row:
                    source_enc = row.get("source_encoded_name") or row["project_encoded_name"]
                    jsonl_path = projects_dir / source_enc / f"{row['session_uuid']}.jsonl"
                    if jsonl_path.exists():
                        return SessionLookupResult(
                            session=Session.from_path(jsonl_path),
                            project_encoded_name=row["project_encoded_name"],
                        )
    except Exception:
        logger.debug("DB fast path failed for message UUID %s, falling back to scan", message_uuid, exc_info=True)

    # JSONL fallback: O(n*m) scan of all sessions
    if not projects_dir.exists():
        return None

    for encoded_dir in projects_dir.iterdir():
        if not encoded_dir.is_dir() or not encoded_dir.name.startswith("-"):
            continue

        for jsonl_path in encoded_dir.glob("*.jsonl"):
            if not _is_valid_session_filename(jsonl_path):
                continue

            try:
                session = Session.from_path(jsonl_path)
                for msg in session.iter_messages():
                    if hasattr(msg, "uuid") and msg.uuid == message_uuid:
                        return SessionLookupResult(
                            session=session,
                            project_encoded_name=encoded_dir.name,
                        )
            except Exception:
                continue

    return None


def _find_session_jsonl(projects_dir: Path, encoded_name: str, session_uuid: str) -> Optional[Path]:
    """
    Find a session JSONL file, searching the project dir and its worktree dirs.

    For worktree-grouped sessions, the JSONL lives in the worktree-encoded
    directory (e.g., -Users-...-worktrees-karma-focused-jepsen/) but the UI
    routes through the real project's encoded_name. This function handles
    the fallback transparently.

    Args:
        projects_dir: Root ~/.claude/projects/ directory
        encoded_name: Encoded project directory name (may be the real project)
        session_uuid: Session UUID to find

    Returns:
        Path to the session JSONL file, or None if not found.
    """
    # Primary: check the project directory itself
    session_jsonl = projects_dir / encoded_name / f"{session_uuid}.jsonl"
    if session_jsonl.exists():
        return session_jsonl

    # Worktree fallback: session may live in a worktree dir grouped under this project
    from utils import get_worktree_mappings_for_project

    for wt_enc in get_worktree_mappings_for_project(encoded_name):
        wt_jsonl = projects_dir / wt_enc / f"{session_uuid}.jsonl"
        if wt_jsonl.exists():
            return wt_jsonl

    return None


def find_subagent(
    encoded_name: str, session_uuid: str, agent_id: str
) -> Optional[SubagentLookupResult]:
    """
    Find a subagent by project, session, and agent ID.

    Supports worktree-grouped sessions: when the UI navigates via the real
    project's encoded_name but the session JSONL lives in a worktree directory,
    this function searches worktree dirs as a fallback.

    Args:
        encoded_name: Encoded project directory name
        session_uuid: Parent session UUID
        agent_id: Short hex agent ID

    Returns:
        SubagentLookupResult with agent, parent session, and project info,
        or None if not found.
    """
    projects_dir = settings.projects_dir

    # Find parent session (searches worktree dirs if needed)
    session_jsonl = _find_session_jsonl(projects_dir, encoded_name, session_uuid)
    if not session_jsonl:
        return None

    parent_session = Session.from_path(session_jsonl)

    # Find subagent
    subagents_dir = parent_session.subagents_dir
    agent_jsonl = subagents_dir / f"agent-{agent_id}.jsonl"

    if not agent_jsonl.exists():
        return None

    agent = Agent.from_path(agent_jsonl)

    return SubagentLookupResult(
        agent=agent,
        parent_session=parent_session,
        project_encoded_name=encoded_name,
    )

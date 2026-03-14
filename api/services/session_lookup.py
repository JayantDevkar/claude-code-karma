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
    remote_user_id: Optional[str] = None


@dataclass
class _ResolvedPath:
    """Resolved JSONL path with source metadata."""

    jsonl_path: Path
    project_encoded_name: str
    remote_user_id: Optional[str] = None


def _is_valid_session_filename(path: Path) -> bool:
    """
    Check if a JSONL file path looks like a valid session file.

    Valid session files have UUID-like stems with dashes and alphanumeric characters.
    This filters out non-session files like sessions-index.json.
    """
    stem = path.stem
    if "-" not in stem:
        return False
    if not stem.replace("-", "").replace("_", "").isalnum():
        return False
    return True


def _resolve_from_db(uuid: str) -> Optional[_ResolvedPath]:
    """
    Resolve a session's JSONL path using the DB.

    The DB stores `source` ('local' or 'remote') and `remote_user_id`,
    so we can construct the correct path directly without scanning.
    """
    try:
        from db.connection import sqlite_read

        with sqlite_read() as conn:
            if conn is None:
                return None
            row = conn.execute(
                "SELECT project_encoded_name, source_encoded_name, "
                "source, remote_user_id FROM sessions WHERE uuid = ?",
                (uuid,),
            ).fetchone()
            if not row:
                return None

            project_enc = row["project_encoded_name"]
            source = row["source"] or "local"

            if source == "remote":
                remote_uid = row["remote_user_id"]
                if not remote_uid:
                    logger.warning(
                        "Session %s has source=remote but no remote_user_id", uuid
                    )
                    return None
                jsonl_path = (
                    settings.karma_base
                    / "remote-sessions"
                    / remote_uid
                    / project_enc
                    / "sessions"
                    / f"{uuid}.jsonl"
                )
                if jsonl_path.exists():
                    return _ResolvedPath(jsonl_path, project_enc, remote_uid)
            else:
                source_enc = row["source_encoded_name"] or project_enc
                jsonl_path = settings.projects_dir / source_enc / f"{uuid}.jsonl"
                if jsonl_path.exists():
                    return _ResolvedPath(jsonl_path, project_enc)
    except Exception:
        logger.debug(
            "DB path resolution failed for session %s", uuid, exc_info=True
        )

    return None


def _resolve_from_filesystem(
    uuid: str, encoded_name: Optional[str] = None
) -> Optional[_ResolvedPath]:
    """
    Fallback: find a session JSONL by scanning the filesystem.

    Used when DB is unavailable or session isn't indexed yet.
    Searches the specific project dir first (with worktree fallback),
    then all project dirs, then remote-sessions.
    """
    projects_dir = settings.projects_dir

    # If we have a hint, check that project dir first (+ worktrees)
    if encoded_name:
        path = _find_session_jsonl(projects_dir, encoded_name, uuid)
        if path:
            return _ResolvedPath(path, encoded_name)

    # Scan all project dirs
    if projects_dir.exists():
        for encoded_dir in projects_dir.iterdir():
            if encoded_dir.is_dir() and encoded_dir.name.startswith("-"):
                jsonl_path = encoded_dir / f"{uuid}.jsonl"
                if jsonl_path.exists():
                    return _ResolvedPath(jsonl_path, encoded_dir.name)

    # Scan remote-sessions dirs
    from services.remote_sessions import find_remote_session

    remote = find_remote_session(uuid)
    if remote:
        return _ResolvedPath(
            remote.session.jsonl_path,
            remote.local_encoded_name,
            remote.user_id,
        )

    return None


def _resolve_session(
    uuid: str, encoded_name: Optional[str] = None
) -> Optional[_ResolvedPath]:
    """
    Resolve a session's JSONL path. DB first, filesystem fallback.

    This is the single entry point for all session path resolution.
    """
    return _resolve_from_db(uuid) or _resolve_from_filesystem(uuid, encoded_name)


def find_session_with_project(uuid: str) -> Optional[SessionLookupResult]:
    """
    Find a session by UUID and return both session and project encoded name.

    Uses DB for O(1) lookup, falls back to filesystem scan.
    """
    resolved = _resolve_session(uuid)
    if not resolved:
        return None

    # For remote sessions, set claude_base_dir to the project-level dir
    # so that todos_dir, tasks_dir, debug_log, etc. resolve correctly.
    # Path layout: .../remote-sessions/{user}/{encoded}/sessions/{uuid}.jsonl
    # claude_base_dir should be: .../remote-sessions/{user}/{encoded}/
    claude_base = None
    if resolved.remote_user_id:
        claude_base = resolved.jsonl_path.parent.parent

    session = Session.from_path(resolved.jsonl_path, claude_base_dir=claude_base)
    return SessionLookupResult(
        session=session,
        project_encoded_name=resolved.project_encoded_name,
    )


def find_session(uuid: str) -> Optional[Session]:
    """
    Find a session by UUID across all projects.

    Convenience wrapper around find_session_with_project() that returns
    just the Session object.
    """
    result = find_session_with_project(uuid)
    return result.session if result else None


def find_session_by_message_uuid(message_uuid: str) -> Optional[SessionLookupResult]:
    """
    Find a session that contains a message with the given UUID.

    Uses DB message_uuids table for O(1) lookup when available,
    falls back to O(n*m) JSONL scan.
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
                    session_uuid = row["session_uuid"]
                    resolved = _resolve_session(session_uuid)
                    if resolved:
                        return SessionLookupResult(
                            session=Session.from_path(resolved.jsonl_path),
                            project_encoded_name=resolved.project_encoded_name,
                        )
    except Exception:
        logger.debug(
            "DB fast path failed for message UUID %s, falling back to scan",
            message_uuid,
            exc_info=True,
        )

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


def _find_session_jsonl(
    projects_dir: Path, encoded_name: str, session_uuid: str
) -> Optional[Path]:
    """
    Find a session JSONL file, searching the project dir and its worktree dirs.

    For worktree-grouped sessions, the JSONL lives in the worktree-encoded
    directory (e.g., -Users-...-worktrees-karma-focused-jepsen/) but the UI
    routes through the real project's encoded_name. This function handles
    the fallback transparently.
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

    Uses DB to determine session source (local vs remote) and resolve
    the correct JSONL path directly. Falls back to filesystem scan
    when DB is unavailable.
    """
    resolved = _resolve_session(session_uuid, encoded_name)
    if not resolved:
        return None

    parent_session = Session.from_path(resolved.jsonl_path)

    # Find subagent in the parent session's subagents dir
    subagents_dir = parent_session.subagents_dir
    agent_jsonl = subagents_dir / f"agent-{agent_id}.jsonl"

    if not agent_jsonl.exists():
        return None

    agent = Agent.from_path(agent_jsonl)

    return SubagentLookupResult(
        agent=agent,
        parent_session=parent_session,
        project_encoded_name=resolved.project_encoded_name,
        remote_user_id=resolved.remote_user_id,
    )

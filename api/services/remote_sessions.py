"""
Remote sessions service for Syncthing-synced session data.

Directory structure (written by CLI packager, synced by Syncthing):
  ~/.claude_karma/remote-sessions/{user_id}/{encoded_name}/
    sessions/{uuid}.jsonl
    sessions/{uuid}/subagents/...
    todos/{uuid}-*.json
    manifest.json

The inbox path on the receiving machine uses the LOCAL encoded name,
so no path mapping is needed — the encoded_name in the directory IS
the local project's encoded name.

The local user's directory is the outbox (sendonly) and should be skipped.
"""

import json
import logging
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterator, Optional

from config import settings
from models import Session
from services.session_filter import SessionMetadata

logger = logging.getLogger(__name__)

# Cache for local user_id (TTL-based)
_local_user_cache: Optional[str] = None
_local_user_cache_time: float = 0.0
_LOCAL_USER_TTL = 30.0  # seconds

# Cache for project mapping (TTL-based)
_project_mapping_cache: Optional[dict] = None
_project_mapping_cache_time: float = 0.0
_PROJECT_MAPPING_TTL = 30.0  # seconds


@dataclass
class RemoteSessionResult:
    """Result of finding a remote session."""

    session: Session
    user_id: str
    machine_id: str
    local_encoded_name: str


def _read_sync_config() -> Optional[dict]:
    """Read sync-config.json from karma base directory."""
    config_path = settings.karma_base / "sync-config.json"
    if not config_path.exists():
        return None
    try:
        with open(config_path) as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        logger.warning("Failed to read sync-config.json: %s", e)
        return None


def _get_local_user_id() -> Optional[str]:
    """Get local user_id from sync-config.json (cached with TTL)."""
    global _local_user_cache, _local_user_cache_time

    now = time.monotonic()
    if _local_user_cache is not None and (now - _local_user_cache_time) < _LOCAL_USER_TTL:
        return _local_user_cache

    config = _read_sync_config()
    _local_user_cache = config.get("user_id") if config else None
    _local_user_cache_time = now
    return _local_user_cache


def get_project_mapping() -> dict[tuple[str, str], str]:
    """
    Build mapping from (user_id, remote_encoded) -> local_encoded_name.

    Supports two config formats:

    1. Legacy "paths" format (used in tests):
       teams.{team}.projects.{name}.paths = {user_id: encoded_name}

    2. Syncthing format (real config):
       teams.{team}.projects.{name}.encoded_name = local_encoded
       teams.{team}.syncthing_members = {member_name: {...}}
       Inbox directories already use local encoded name, so mapping is identity.

    Returns:
        Dict mapping (user_id, encoded_name) to local_encoded_name.
    """
    global _project_mapping_cache, _project_mapping_cache_time

    now = time.monotonic()
    if (
        _project_mapping_cache is not None
        and (now - _project_mapping_cache_time) < _PROJECT_MAPPING_TTL
    ):
        return _project_mapping_cache

    config = _read_sync_config()
    if not config:
        _project_mapping_cache = {}
        _project_mapping_cache_time = now
        return _project_mapping_cache

    mapping: dict[tuple[str, str], str] = {}
    local_user_id = config.get("user_id", config.get("local_user_id", ""))

    teams = config.get("teams", {})
    for _team_name, team_config in teams.items():
        projects = team_config.get("projects", {})
        for _project_name, project_config in projects.items():
            # Legacy format: paths dict mapping user_id -> encoded_name
            paths = project_config.get("paths", {})
            if paths:
                local_encoded = paths.get(local_user_id)
                if not local_encoded:
                    continue
                for user_id, encoded_path in paths.items():
                    if user_id != local_user_id:
                        mapping[(user_id, encoded_path)] = local_encoded
                continue

            # Syncthing format: encoded_name is the local encoded name
            local_encoded = project_config.get("encoded_name", "")
            if not local_encoded:
                continue

            # Map each syncthing member to this project
            syncthing_members = team_config.get("syncthing_members", {})
            for member_name in syncthing_members:
                if member_name != local_user_id:
                    mapping[(member_name, local_encoded)] = local_encoded

    _project_mapping_cache = mapping
    _project_mapping_cache_time = now
    return mapping


def _get_remote_sessions_dir() -> Path:
    """Get the remote-sessions base directory."""
    return settings.karma_base / "remote-sessions"


def find_remote_session(uuid: str) -> Optional[RemoteSessionResult]:
    """
    Search for a session UUID in remote-sessions directories.

    Searches: remote-sessions/{user_id}/{encoded_name}/sessions/{uuid}.jsonl

    Skips the local user's outbox directory.

    Args:
        uuid: Session UUID to find.

    Returns:
        RemoteSessionResult if found, None otherwise.
    """
    remote_base = _get_remote_sessions_dir()
    if not remote_base.exists():
        return None

    local_user = _get_local_user_id()

    for user_dir in remote_base.iterdir():
        if not user_dir.is_dir():
            continue
        user_id = user_dir.name

        # Skip local user's outbox
        if user_id == local_user:
            continue

        for encoded_dir in user_dir.iterdir():
            if not encoded_dir.is_dir():
                continue
            encoded_name = encoded_dir.name

            sessions_dir = encoded_dir / "sessions"
            if not sessions_dir.exists():
                continue

            jsonl_path = sessions_dir / f"{uuid}.jsonl"
            if not jsonl_path.exists():
                continue

            try:
                session = Session.from_path(
                    jsonl_path,
                    claude_base_dir=encoded_dir,
                )
                return RemoteSessionResult(
                    session=session,
                    user_id=user_id,
                    machine_id=user_id,
                    local_encoded_name=encoded_name,
                )
            except Exception as e:
                logger.warning(
                    "Failed to load remote session %s from %s: %s",
                    uuid,
                    jsonl_path,
                    e,
                )
                continue

    return None


def list_remote_sessions_for_project(local_encoded: str) -> list[SessionMetadata]:
    """
    Find remote sessions that map to a local project.

    Walks remote-sessions/{user_id}/{local_encoded}/sessions/ for all
    remote users (skipping local user's outbox).

    Args:
        local_encoded: Local project encoded name.

    Returns:
        List of SessionMetadata with source="remote".
    """
    remote_base = _get_remote_sessions_dir()
    if not remote_base.exists():
        return []

    local_user = _get_local_user_id()
    results: list[SessionMetadata] = []

    for user_dir in remote_base.iterdir():
        if not user_dir.is_dir():
            continue
        user_id = user_dir.name

        # Skip local user's outbox
        if user_id == local_user:
            continue

        sessions_dir = user_dir / local_encoded / "sessions"
        if not sessions_dir.exists():
            continue

        for jsonl_path in sessions_dir.glob("*.jsonl"):
            uuid = jsonl_path.stem
            if uuid.startswith("agent-"):
                continue

            meta = _build_remote_metadata(
                jsonl_path=jsonl_path,
                uuid=uuid,
                local_encoded=local_encoded,
                project_dir=sessions_dir,
                user_id=user_id,
                machine_id=user_id,
            )
            if meta:
                results.append(meta)

    return results


def iter_all_remote_session_metadata() -> Iterator[SessionMetadata]:
    """
    Iterate over all remote session metadata.

    Walks remote-sessions/{user_id}/{encoded_name}/sessions/ for all
    remote users. Used for global /sessions/all endpoint.

    Yields:
        SessionMetadata with source="remote" for each remote session.
    """
    remote_base = _get_remote_sessions_dir()
    if not remote_base.exists():
        return

    local_user = _get_local_user_id()

    for user_dir in remote_base.iterdir():
        if not user_dir.is_dir():
            continue
        user_id = user_dir.name

        # Skip local user's outbox
        if user_id == local_user:
            continue

        for encoded_dir in user_dir.iterdir():
            if not encoded_dir.is_dir():
                continue
            encoded_name = encoded_dir.name

            sessions_dir = encoded_dir / "sessions"
            if not sessions_dir.exists():
                continue

            for jsonl_path in sessions_dir.glob("*.jsonl"):
                uuid = jsonl_path.stem
                if uuid.startswith("agent-"):
                    continue

                meta = _build_remote_metadata(
                    jsonl_path=jsonl_path,
                    uuid=uuid,
                    local_encoded=encoded_name,
                    project_dir=sessions_dir,
                    user_id=user_id,
                    machine_id=user_id,
                )
                if meta:
                    yield meta


def _parse_timestamp(ts: Optional[str]) -> Optional[datetime]:
    """Parse an ISO timestamp string to datetime."""
    if not ts:
        return None
    try:
        from utils import normalize_timezone

        dt = datetime.fromisoformat(ts)
        return normalize_timezone(dt)
    except (ValueError, TypeError):
        return None


def _build_remote_metadata(
    *,
    jsonl_path: Path,
    uuid: str,
    local_encoded: str,
    project_dir: Path,
    user_id: str,
    machine_id: str,
) -> Optional[SessionMetadata]:
    """
    Build SessionMetadata from a remote JSONL file.

    Reads only the first and last lines of the JSONL for timestamps,
    avoiding full session parsing for performance (lazy loading pattern).
    """
    try:
        # Read first and last lines only — avoid full parse
        with open(jsonl_path) as f:
            first_line = f.readline().strip()
            if not first_line:
                return None

            # Count lines and find last
            message_count = 1
            last_line = first_line
            for line in f:
                stripped = line.strip()
                if stripped:
                    last_line = stripped
                    message_count += 1

        first = json.loads(first_line)
        last = json.loads(last_line)

        start_time = _parse_timestamp(first.get("timestamp"))
        end_time = _parse_timestamp(last.get("timestamp"))
        slug = first.get("sessionId")

        return SessionMetadata(
            uuid=uuid,
            encoded_name=local_encoded,
            project_path=str(project_dir),
            message_count=message_count,
            start_time=start_time,
            end_time=end_time,
            slug=slug,
            initial_prompt=None,  # Skip for performance
            git_branch=None,
            source="remote",
            remote_user_id=user_id,
            remote_machine_id=machine_id,
        )
    except Exception as e:
        logger.warning("Failed to build metadata for remote session %s: %s", uuid, e)
        return None

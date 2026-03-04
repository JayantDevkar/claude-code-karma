"""
Remote sessions service for Syncthing-synced session data.

Reads session JSONL files from ~/.claude_karma/remote-sessions/{user_id}/{machine_id}/
and maps them to local projects using sync-config.json.
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


def get_project_mapping() -> dict[tuple[str, str], str]:
    """
    Build mapping from (user_id, remote_encoded) -> local_encoded_name.

    Reads sync-config.json which has structure:
    {
        "teams": {
            "team-name": {
                "projects": {
                    "project-name": {
                        "paths": {
                            "user-id": "encoded-path"
                        }
                    }
                }
            }
        }
    }

    Projects are joined by name key — all paths under the same project
    map to each other. The local user's encoded path is the canonical one.

    Returns:
        Dict mapping (user_id, remote_encoded) to local_encoded_name.
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
    local_user_id = config.get("local_user_id", "")

    teams = config.get("teams", {})
    for _team_name, team_config in teams.items():
        projects = team_config.get("projects", {})
        for _project_name, project_config in projects.items():
            paths = project_config.get("paths", {})
            # Find local user's encoded path
            local_encoded = paths.get(local_user_id)
            if not local_encoded:
                continue
            # Map all remote users' paths to local
            for user_id, encoded_path in paths.items():
                if user_id != local_user_id:
                    mapping[(user_id, encoded_path)] = local_encoded

    _project_mapping_cache = mapping
    _project_mapping_cache_time = now
    return mapping


def _get_remote_sessions_dir() -> Path:
    """Get the remote-sessions base directory."""
    return settings.karma_base / "remote-sessions"


def find_remote_session(uuid: str) -> Optional[RemoteSessionResult]:
    """
    Search for a session UUID in remote-sessions directories.

    Searches: remote-sessions/{user_id}/{machine_id}/sessions/{uuid}.jsonl

    Args:
        uuid: Session UUID to find.

    Returns:
        RemoteSessionResult if found, None otherwise.
    """
    remote_base = _get_remote_sessions_dir()
    if not remote_base.exists():
        return None

    mapping = get_project_mapping()

    for user_dir in remote_base.iterdir():
        if not user_dir.is_dir():
            continue
        user_id = user_dir.name

        for machine_dir in user_dir.iterdir():
            if not machine_dir.is_dir():
                continue
            machine_id = machine_dir.name

            # Check each project dir for the session
            sessions_base = machine_dir / "sessions"
            if not sessions_base.exists():
                continue

            for project_dir in sessions_base.iterdir():
                if not project_dir.is_dir():
                    continue
                remote_encoded = project_dir.name

                jsonl_path = project_dir / f"{uuid}.jsonl"
                if not jsonl_path.exists():
                    continue

                # Resolve local project name
                local_encoded = mapping.get((user_id, remote_encoded), remote_encoded)

                try:
                    session = Session.from_path(
                        jsonl_path,
                        claude_base_dir=project_dir,
                    )
                    return RemoteSessionResult(
                        session=session,
                        user_id=user_id,
                        machine_id=machine_id,
                        local_encoded_name=local_encoded,
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

    Args:
        local_encoded: Local project encoded name.

    Returns:
        List of SessionMetadata with source="remote".
    """
    remote_base = _get_remote_sessions_dir()
    if not remote_base.exists():
        return []

    mapping = get_project_mapping()
    results: list[SessionMetadata] = []

    # Build reverse lookup: local_encoded -> set of (user_id, remote_encoded)
    remote_dirs: list[tuple[str, str]] = []
    for (user_id, remote_encoded), mapped_local in mapping.items():
        if mapped_local == local_encoded:
            remote_dirs.append((user_id, remote_encoded))

    if not remote_dirs:
        return []

    for user_id, remote_encoded in remote_dirs:
        # Walk all machine dirs for this user
        user_dir = remote_base / user_id
        if not user_dir.exists():
            continue

        for machine_dir in user_dir.iterdir():
            if not machine_dir.is_dir():
                continue
            machine_id = machine_dir.name

            project_dir = machine_dir / "sessions" / remote_encoded
            if not project_dir.exists():
                continue

            for jsonl_path in project_dir.glob("*.jsonl"):
                uuid = jsonl_path.stem
                # Skip non-UUID filenames (e.g. agent files)
                if uuid.startswith("agent-"):
                    continue

                meta = _build_remote_metadata(
                    jsonl_path=jsonl_path,
                    uuid=uuid,
                    local_encoded=local_encoded,
                    project_dir=project_dir,
                    user_id=user_id,
                    machine_id=machine_id,
                )
                if meta:
                    results.append(meta)

    return results


def iter_all_remote_session_metadata() -> Iterator[SessionMetadata]:
    """
    Iterate over all remote session metadata.

    Walks all remote-sessions directories and yields SessionMetadata
    for each session found. Used for global /sessions/all endpoint.

    Yields:
        SessionMetadata with source="remote" for each remote session.
    """
    remote_base = _get_remote_sessions_dir()
    if not remote_base.exists():
        return

    mapping = get_project_mapping()

    for user_dir in remote_base.iterdir():
        if not user_dir.is_dir():
            continue
        user_id = user_dir.name

        for machine_dir in user_dir.iterdir():
            if not machine_dir.is_dir():
                continue
            machine_id = machine_dir.name

            sessions_base = machine_dir / "sessions"
            if not sessions_base.exists():
                continue

            for project_dir in sessions_base.iterdir():
                if not project_dir.is_dir():
                    continue
                remote_encoded = project_dir.name
                local_encoded = mapping.get((user_id, remote_encoded), remote_encoded)

                for jsonl_path in project_dir.glob("*.jsonl"):
                    uuid = jsonl_path.stem
                    if uuid.startswith("agent-"):
                        continue

                    meta = _build_remote_metadata(
                        jsonl_path=jsonl_path,
                        uuid=uuid,
                        local_encoded=local_encoded,
                        project_dir=project_dir,
                        user_id=user_id,
                        machine_id=machine_id,
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

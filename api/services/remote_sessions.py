"""
Remote sessions service for Syncthing-synced session data.

Directory structure (written by CLI packager, synced by Syncthing):
  ~/.claude_karma/remote-sessions/{member_tag}/{encoded_name}/
    sessions/{uuid}.jsonl
    sessions/{uuid}/subagents/...
    todos/{uuid}-*.json
    manifest.json

The top-level directory under remote-sessions/ may be a bare ``user_id``
(legacy) or a ``member_tag`` in ``{user_id}.{machine_tag}`` format.
Both formats are supported; ``parse_member_tag()`` extracts the user_id.

The inbox path on the receiving machine uses the LOCAL encoded name,
so no path mapping is needed — the encoded_name in the directory IS
the local project's encoded name.

The local user's directory is the outbox (sendonly) and should be skipped.
"""

import json
import logging
import re
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterator, Optional

from config import settings
from models import Session
from services.syncthing.folder_manager import parse_member_tag
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

# Cache for manifest worktree lookups (keyed by (user_id, encoded_name))
_manifest_worktree_cache: dict[tuple[str, str], tuple[float, dict[str, Optional[str]]]] = {}
_MANIFEST_WORKTREE_TTL = 30.0  # seconds

# Cache for remote titles (keyed by (user_id, encoded_name))
_titles_cache: dict[tuple[str, str], tuple[float, dict[str, str]]] = {}
_TITLES_TTL = 30.0  # seconds

# Cache for resolved user_id from manifest (keyed by dir_name)
_resolved_user_cache: dict[str, tuple[float, str]] = {}
_RESOLVED_USER_TTL = 60.0  # seconds


def invalidate_caches() -> None:
    """Clear all in-memory caches. Called on sync reset."""
    global _local_user_cache, _local_user_cache_time
    global _project_mapping_cache, _project_mapping_cache_time
    global _manifest_worktree_cache, _titles_cache, _resolved_user_cache
    _local_user_cache = None
    _local_user_cache_time = 0.0
    _project_mapping_cache = None
    _project_mapping_cache_time = 0.0
    _manifest_worktree_cache.clear()
    _titles_cache.clear()
    _resolved_user_cache.clear()


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


def _is_local_user(dir_name: str, local_user_id: Optional[str]) -> bool:
    """Check if a directory name belongs to the local user.

    Handles both bare user_id directories (e.g. ``jayant``) and
    member_tag directories (e.g. ``jayant.mac-mini``) by extracting
    the user_id portion via :func:`parse_member_tag`.
    """
    if not local_user_id:
        return False
    if dir_name == local_user_id:
        return True
    # member_tag format: user_id.machine_tag
    parsed_uid, _ = parse_member_tag(dir_name)
    return parsed_uid == local_user_id


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

    # Augment mapping with git_identity-based matching from SQLite + manifests
    try:
        from db.connection import create_read_connection

        db_conn = create_read_connection()
        try:
            rows = db_conn.execute(
                "SELECT encoded_name, git_identity FROM projects"
                " WHERE git_identity IS NOT NULL ORDER BY encoded_name"
            ).fetchall()
            # When multiple projects share the same git_identity (e.g. monorepo
            # and old submodule dirs), prefer the one registered in sync_team_projects.
            # Secondary tiebreaker: shorter encoded_name (typically the monorepo root).
            team_projects = {
                r[0]
                for r in db_conn.execute(
                    "SELECT project_encoded_name FROM sync_team_projects"
                ).fetchall()
            }
            git_lookup: dict[str, str] = {}
            for row in rows:
                encoded, git_id = row[0], row[1]
                existing = git_lookup.get(git_id)
                if existing is None:
                    git_lookup[git_id] = encoded
                elif encoded in team_projects and existing not in team_projects:
                    git_lookup[git_id] = encoded
                elif encoded in team_projects and existing in team_projects:
                    # Both in team — prefer shorter name (monorepo root)
                    if len(encoded) < len(existing):
                        git_lookup[git_id] = encoded
        finally:
            db_conn.close()

        if git_lookup:
            remote_base = _get_remote_sessions_dir()
            if remote_base.exists():
                for user_dir in remote_base.iterdir():
                    if not user_dir.is_dir():
                        continue
                    dir_name = user_dir.name
                    if _is_local_user(dir_name, local_user_id):
                        continue
                    for encoded_dir in user_dir.iterdir():
                        if not encoded_dir.is_dir():
                            continue
                        manifest_path = encoded_dir / "manifest.json"
                        if not manifest_path.exists():
                            continue
                        try:
                            with open(manifest_path) as f:
                                manifest = json.load(f)
                            remote_git_id = manifest.get("git_identity")
                            if remote_git_id and remote_git_id in git_lookup:
                                remote_encoded = encoded_dir.name
                                local_encoded = git_lookup[remote_git_id]
                                if (dir_name, remote_encoded) not in mapping:
                                    mapping[(dir_name, remote_encoded)] = local_encoded
                        except (json.JSONDecodeError, OSError):
                            continue

            # Also scan v4 karma-out--* inbox directories for manifests
            karma_base = settings.karma_base
            local_member_tag = None
            machine_tag = config.get("machine_tag", "")
            if local_user_id and machine_tag:
                local_member_tag = f"{local_user_id}.{machine_tag}"

            for inbox_dir in karma_base.iterdir():
                if not inbox_dir.is_dir():
                    continue
                dname = inbox_dir.name
                if not dname.startswith("karma-out--"):
                    continue
                rest = dname[len("karma-out--"):]
                parts = rest.split("--", 1)
                if len(parts) != 2:
                    continue
                inbox_tag, _suffix = parts
                # Skip our own outbox
                if local_member_tag and inbox_tag == local_member_tag:
                    continue
                manifest_path = inbox_dir / "manifest.json"
                if not manifest_path.exists():
                    continue
                try:
                    with open(manifest_path) as f:
                        manifest = json.load(f)
                    remote_git_id = manifest.get("git_identity")
                    remote_encoded = manifest.get("project_encoded_name", "")
                    if remote_git_id and remote_git_id in git_lookup:
                        local_enc = git_lookup[remote_git_id]
                        if remote_encoded and (inbox_tag, remote_encoded) not in mapping:
                            mapping[(inbox_tag, remote_encoded)] = local_enc
                except (json.JSONDecodeError, OSError):
                    continue
    except Exception as e:
        logger.debug("git_identity augmentation failed: %s", e)

    _project_mapping_cache = mapping
    _project_mapping_cache_time = now
    return mapping


def _get_remote_sessions_dir() -> Path:
    """Get the remote-sessions base directory."""
    return settings.karma_base / "remote-sessions"


def _resolve_user_id(user_dir: Path, conn=None) -> str:
    """
    Resolve a clean user_id for a remote-sessions user directory.

    # NOTE: remote_user_id should always be member_tag format (e.g., "jay.mac"), not bare user_id.

    The directory name may be a machine hostname (e.g. 'Jayants-Mac-mini.local')
    when Syncthing creates the folder. The manifest.json inside each project
    subdirectory contains the canonical user_id set by the sender.

    Resolution order (most reliable first):
      1. manifest.device_id → sync_members DB lookup (DB is authoritative —
         handshake healing keeps it current, while manifest may be stale)
      2. manifest.user_id (canonical sender identity, fallback when no DB match)
      3. directory name (last resort)

    Reads the first manifest.json found under the user_dir, caches the result.
    Falls back to directory name if no manifest is available.

    Args:
        user_dir: Path to a user directory under remote-sessions/.
        conn: Optional SQLite connection for device_id → member lookup.
    """
    dir_name = user_dir.name
    now = time.monotonic()

    cached = _resolved_user_cache.get(dir_name)
    if cached is not None:
        cache_time, cached_id = cached
        if (now - cache_time) < _RESOLVED_USER_TTL:
            return cached_id

    # Scan project subdirs for a manifest
    resolved = dir_name
    try:
        for project_dir in user_dir.iterdir():
            if not project_dir.is_dir():
                continue
            manifest_path = project_dir / "manifest.json"
            if manifest_path.exists():
                with open(manifest_path) as f:
                    manifest = json.load(f)

                manifest_uid = manifest.get("user_id")
                device_id = manifest.get("device_id")

                # Priority 1: DB lookup via device_id — DB is authoritative
                # because handshake healing keeps member names current,
                # while manifest user_id may be stale (written at package time).
                if device_id and conn is not None:
                    try:
                        from repositories.member_repo import MemberRepository
                        members = MemberRepository().get_by_device(conn, device_id)
                        if members:
                            db_name = members[0].member_tag
                            if manifest_uid and db_name != manifest_uid:
                                logger.debug(
                                    "DB name '%s' differs from manifest '%s' for device %s "
                                    "— trusting DB (handshake-healed)",
                                    db_name, manifest_uid, device_id[:20],
                                )
                            resolved = db_name
                            break
                    except Exception:
                        pass

                # Priority 2: manifest user_id (no DB match by device_id)
                if manifest_uid:
                    resolved = manifest_uid
                    # Normalize bare user_id to full member_tag via DB
                    if conn is not None and "." not in manifest_uid:
                        try:
                            from repositories.member_repo import MemberRepository
                            members = MemberRepository().get_by_user_id(conn, manifest_uid)
                            if members:
                                resolved = members[0].member_tag
                        except Exception:
                            pass
                break
    except (json.JSONDecodeError, OSError) as e:
        logger.debug("Failed to resolve user_id from manifest in %s: %s", dir_name, e)

    # If still unresolved (equals dir_name) and dir_name looks like a
    # member_tag (contains a dot), extract the user_id portion.
    # Guard: only treat as member_tag if the machine_tag part is a valid
    # sanitized tag ([a-z0-9-]+). Hostname suffixes like ".local" contain
    # no uppercase or special chars but ARE valid — so also check that the
    # user_id part looks like a karma username (no dots, no uppercase).
    if resolved == dir_name and "." in dir_name:
        parsed_uid, machine_part = parse_member_tag(dir_name)
        # Valid member_tag: user_id has no dots AND machine_tag matches [a-z0-9-]+
        # Hostnames like "Bobs-Mac.local" fail because the user_id part has uppercase
        # or the machine_tag is a known hostname suffix.
        _HOSTNAME_SUFFIXES = ("local", "lan", "home", "internal", "localdomain")
        if (parsed_uid and machine_part
                and machine_part not in _HOSTNAME_SUFFIXES
                and re.match(r"^[a-z0-9][a-z0-9-]*$", machine_part)):
            resolved = parsed_uid

    # Final normalization: if resolved is a bare user_id (no dot),
    # attempt to resolve to full member_tag via DB lookup.
    if conn is not None and "." not in resolved:
        try:
            from repositories.member_repo import MemberRepository
            members = MemberRepository().get_by_user_id(conn, resolved)
            if members:
                resolved = members[0].member_tag
        except Exception:
            pass

    _resolved_user_cache[dir_name] = (now, resolved)
    return resolved


def _load_manifest_worktree_map(
    user_id: str, encoded_name: str
) -> dict[str, Optional[str]]:
    """
    Load manifest.json for a (user_id, encoded_name) pair and return
    a mapping of uuid -> worktree_name.

    Results are cached with a TTL to avoid re-reading the manifest
    for every session in the same project.

    Args:
        user_id: Remote user identifier.
        encoded_name: Encoded project directory name.

    Returns:
        Dict mapping session UUID to worktree_name (may be None per session).
    """
    cache_key = (user_id, encoded_name)
    now = time.monotonic()

    cached = _manifest_worktree_cache.get(cache_key)
    if cached is not None:
        cache_time, cache_data = cached
        if (now - cache_time) < _MANIFEST_WORKTREE_TTL:
            return cache_data

    result: dict[str, Optional[str]] = {}
    manifest_path = (
        _get_remote_sessions_dir() / user_id / encoded_name / "manifest.json"
    )
    if manifest_path.exists():
        try:
            with open(manifest_path) as f:
                manifest = json.load(f)
            for entry in manifest.get("sessions", []):
                uuid = entry.get("uuid")
                if uuid:
                    result[uuid] = entry.get("worktree_name")
        except (json.JSONDecodeError, OSError) as e:
            logger.debug(
                "Failed to load manifest for %s/%s: %s",
                user_id,
                encoded_name,
                e,
            )

    _manifest_worktree_cache[cache_key] = (now, result)
    return result


def _load_remote_titles(
    user_id: str, encoded_name: str
) -> dict[str, str]:
    """
    Load titles.json for a (user_id, encoded_name) pair and return
    a mapping of uuid -> title_string.

    Results are cached with a TTL to avoid re-reading the file
    for every session in the same project.

    Args:
        user_id: Remote user identifier.
        encoded_name: Encoded project directory name.

    Returns:
        Dict mapping session UUID to title string.
    """
    cache_key = (user_id, encoded_name)
    now = time.monotonic()

    cached = _titles_cache.get(cache_key)
    if cached is not None:
        cache_time, cache_data = cached
        if (now - cache_time) < _TITLES_TTL:
            return cache_data

    result: dict[str, str] = {}
    titles_path = (
        _get_remote_sessions_dir() / user_id / encoded_name / "titles.json"
    )
    if titles_path.exists():
        try:
            with open(titles_path) as f:
                data = json.load(f)
            if data.get("version") == 1:
                titles = data.get("titles", {})
                for uuid, entry in titles.items():
                    if isinstance(entry, dict):
                        title_str = entry.get("title")
                        if title_str:
                            result[uuid] = title_str
                    elif isinstance(entry, str):
                        result[uuid] = entry
        except (json.JSONDecodeError, OSError) as e:
            logger.debug(
                "Failed to load titles for %s/%s: %s",
                user_id,
                encoded_name,
                e,
            )

    _titles_cache[cache_key] = (now, result)
    return result


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
        dir_name = user_dir.name
        user_id = _resolve_user_id(user_dir)

        # Skip local user's outbox (check dir name, resolved id, and member_tag)
        if _is_local_user(dir_name, local_user) or user_id == local_user:
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
                    machine_id=dir_name,
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
        dir_name = user_dir.name
        user_id = _resolve_user_id(user_dir)

        # Skip local user's outbox (check dir name, resolved id, and member_tag)
        if _is_local_user(dir_name, local_user) or user_id == local_user:
            continue

        sessions_dir = user_dir / local_encoded / "sessions"
        if not sessions_dir.exists():
            continue

        # Load manifest once per (dir_name, project) for worktree attribution
        wt_map = _load_manifest_worktree_map(dir_name, local_encoded)
        # Load titles once per (dir_name, project)
        titles_map = _load_remote_titles(dir_name, local_encoded)

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
                machine_id=dir_name,
                worktree_name=wt_map.get(uuid),
                title=titles_map.get(uuid),
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
        dir_name = user_dir.name
        user_id = _resolve_user_id(user_dir)

        # Skip local user's outbox (check dir name, resolved id, and member_tag)
        if _is_local_user(dir_name, local_user) or user_id == local_user:
            continue

        for encoded_dir in user_dir.iterdir():
            if not encoded_dir.is_dir():
                continue
            encoded_name = encoded_dir.name

            sessions_dir = encoded_dir / "sessions"
            if not sessions_dir.exists():
                continue

            # Load manifest once per (dir_name, project) for worktree attribution
            wt_map = _load_manifest_worktree_map(dir_name, encoded_name)
            # Load titles once per (dir_name, project)
            titles_map = _load_remote_titles(dir_name, encoded_name)

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
                    machine_id=dir_name,
                    worktree_name=wt_map.get(uuid),
                    title=titles_map.get(uuid),
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
    worktree_name: Optional[str] = None,
    title: Optional[str] = None,
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
            session_titles=[title] if title else None,
            worktree_name=worktree_name,
            source="remote",
            remote_user_id=user_id,
            remote_machine_id=machine_id,
        )
    except Exception as e:
        logger.warning("Failed to build metadata for remote session %s: %s", uuid, e)
        return None

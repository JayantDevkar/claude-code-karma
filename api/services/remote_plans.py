"""
Remote plans service for Syncthing-synced plan files.

Directory structure (written by CLI packager, synced by Syncthing):
  ~/.claude_karma/remote-sessions/{user_id}/{encoded_name}/
    plans/{slug}.md
    plans-index.json

Discovers plans from all remote users and provides plan-to-session linkage
via the plans-index.json sidecar written by the sender's packager.
"""

import json
import logging
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from config import settings
from services.folder_id import parse_member_tag

logger = logging.getLogger(__name__)

# Cache for plans-index.json (keyed by (user_id, encoded_name))
_plans_index_cache: dict[tuple[str, str], tuple[float, dict]] = {}
_PLANS_INDEX_TTL = 30.0  # seconds


def _get_remote_sessions_dir() -> Path:
    """Get the remote-sessions base directory."""
    return settings.karma_base / "remote-sessions"


def _get_local_user_id() -> Optional[str]:
    """Get local user_id from sync-config.json (cached)."""
    config_path = settings.karma_base / "sync-config.json"
    if not config_path.is_file():
        return None
    try:
        data = json.loads(config_path.read_text(encoding="utf-8"))
        return data.get("user_id")
    except (json.JSONDecodeError, OSError):
        return None


def _is_local_user(dir_name: str, local_user_id: Optional[str]) -> bool:
    """Check if a remote-sessions directory belongs to the local user.

    Handles both bare user_id ("jayant") and member_tag ("jayant.mac-mini").
    """
    if not local_user_id:
        return False
    if dir_name == local_user_id:
        return True
    parsed_uid, _ = parse_member_tag(dir_name)
    return parsed_uid == local_user_id


def _load_plans_index(user_id: str, encoded_name: str) -> dict:
    """
    Load plans-index.json for a (user_id, encoded_name) pair.

    Returns the "plans" dict: {slug: {"sessions": {uuid: operation}}}.
    Cached with TTL.
    """
    cache_key = (user_id, encoded_name)
    now = time.monotonic()

    cached = _plans_index_cache.get(cache_key)
    if cached is not None:
        cache_time, cache_data = cached
        if (now - cache_time) < _PLANS_INDEX_TTL:
            return cache_data

    result: dict = {}
    index_path = (
        _get_remote_sessions_dir() / user_id / encoded_name / "plans-index.json"
    )
    if index_path.is_file():
        try:
            data = json.loads(index_path.read_text(encoding="utf-8"))
            if data.get("version") == 1:
                result = data.get("plans", {})
        except (json.JSONDecodeError, OSError) as e:
            logger.debug(
                "Failed to load plans-index for %s/%s: %s",
                user_id, encoded_name, e,
            )

    _plans_index_cache[cache_key] = (now, result)
    return result


@dataclass
class RemotePlan:
    """A plan file discovered from a remote user's synced outbox."""
    slug: str
    title: Optional[str]
    content: str
    preview: str
    word_count: int
    size_bytes: int
    created: datetime
    modified: datetime
    remote_user_id: str
    project_encoded_name: str
    linked_sessions: list[dict]  # [{uuid, operation}, ...]


def discover_remote_plans() -> list[RemotePlan]:
    """
    Discover all plan files from remote users' synced outboxes.

    Walks ~/.claude_karma/remote-sessions/{user_id}/{encoded}/plans/*.md
    Skips the local user's directory (that's our outbox).
    Returns plans from all remote users, supporting multi-user scenarios.
    """
    remote_dir = _get_remote_sessions_dir()
    if not remote_dir.is_dir():
        return []

    local_user = _get_local_user_id()
    plans: list[RemotePlan] = []

    for user_dir in remote_dir.iterdir():
        if not user_dir.is_dir():
            continue
        dir_name = user_dir.name

        # Skip our own outbox (handles both bare user_id and member_tag)
        if _is_local_user(dir_name, local_user):
            continue

        # Resolve to clean user_id (strip machine_tag if present)
        remote_user_id = parse_member_tag(dir_name)[0]

        for encoded_dir in user_dir.iterdir():
            if not encoded_dir.is_dir():
                continue
            encoded_name = encoded_dir.name

            plans_dir = encoded_dir / "plans"
            if not plans_dir.is_dir():
                continue

            # Load the plans-index for session linkage
            plans_index = _load_plans_index(dir_name, encoded_name)

            for plan_file in plans_dir.glob("*.md"):
                try:
                    slug = plan_file.stem
                    stat = plan_file.stat()
                    content = plan_file.read_text(encoding="utf-8")

                    # Extract title (first h1 heading)
                    title = None
                    for line in content.split("\n"):
                        stripped = line.strip()
                        if stripped.startswith("# "):
                            title = stripped[2:].strip()
                            break

                    # Build linked sessions from plans-index
                    linked_sessions = []
                    if slug in plans_index:
                        sessions_map = plans_index[slug].get("sessions", {})
                        for session_uuid, operation in sessions_map.items():
                            linked_sessions.append({
                                "uuid": session_uuid,
                                "operation": operation,
                                "remote_user_id": remote_user_id,
                            })

                    plans.append(RemotePlan(
                        slug=slug,
                        title=title,
                        content=content,
                        preview=content[:500] if content else "",
                        word_count=len(content.split()) if content else 0,
                        size_bytes=stat.st_size,
                        created=datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc),
                        modified=datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc),
                        remote_user_id=remote_user_id,
                        project_encoded_name=encoded_name,
                        linked_sessions=linked_sessions,
                    ))
                except (PermissionError, OSError, UnicodeDecodeError) as e:
                    logger.debug("Failed to read remote plan %s: %s", plan_file, e)
                    continue

    # Sort by modified time (newest first)
    plans.sort(key=lambda p: p.modified, reverse=True)
    return plans


def _find_user_dir(remote_dir: Path, user_id: str) -> Optional[Path]:
    """Find the remote-sessions directory for a user_id.

    Handles both bare user_id dirs (``jayant``) and member_tag dirs
    (``jayant.mac-mini``) by matching the user_id portion.
    """
    # Direct match first (fast path)
    direct = remote_dir / user_id
    if direct.is_dir():
        return direct
    # Search for member_tag dirs where user_id matches
    if not remote_dir.is_dir():
        return None
    for candidate in remote_dir.iterdir():
        if not candidate.is_dir():
            continue
        parsed_uid, _ = parse_member_tag(candidate.name)
        if parsed_uid == user_id:
            return candidate
    return None


def get_remote_plan(slug: str, user_id: str) -> Optional[RemotePlan]:
    """
    Get a specific remote plan by slug and user_id.

    Searches all encoded directories for the user to find the plan.
    Handles both bare user_id and member_tag directory names.
    """
    remote_dir = _get_remote_sessions_dir()
    user_dir = _find_user_dir(remote_dir, user_id)
    if user_dir is None:
        return None

    # Use actual dir name for filesystem ops, clean user_id for display
    dir_name = user_dir.name
    clean_user_id = parse_member_tag(dir_name)[0]

    for encoded_dir in user_dir.iterdir():
        if not encoded_dir.is_dir():
            continue
        plan_file = encoded_dir / "plans" / f"{slug}.md"
        if plan_file.is_file():
            try:
                stat = plan_file.stat()
                content = plan_file.read_text(encoding="utf-8")
                encoded_name = encoded_dir.name

                title = None
                for line in content.split("\n"):
                    stripped = line.strip()
                    if stripped.startswith("# "):
                        title = stripped[2:].strip()
                        break

                plans_index = _load_plans_index(dir_name, encoded_name)
                linked_sessions = []
                if slug in plans_index:
                    sessions_map = plans_index[slug].get("sessions", {})
                    for session_uuid, operation in sessions_map.items():
                        linked_sessions.append({
                            "uuid": session_uuid,
                            "operation": operation,
                            "remote_user_id": clean_user_id,
                        })

                return RemotePlan(
                    slug=slug,
                    title=title,
                    content=content,
                    preview=content[:500] if content else "",
                    word_count=len(content.split()) if content else 0,
                    size_bytes=stat.st_size,
                    created=datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc),
                    modified=datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc),
                    remote_user_id=clean_user_id,
                    project_encoded_name=encoded_name,
                    linked_sessions=linked_sessions,
                )
            except (PermissionError, OSError, UnicodeDecodeError) as e:
                logger.debug("Failed to read remote plan %s/%s: %s", user_id, slug, e)

    return None


def clear_caches() -> None:
    """Clear all remote plan caches. Used during testing."""
    _plans_index_cache.clear()

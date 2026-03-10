"""Sync identity, singletons, and input validation.

Shared infrastructure for all sync router modules. Contains:
- Proxy and watcher singletons
- Identity loading with TTL cache
- Input validation helpers
- Project suffix computation
"""

import logging
import re
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any, Optional

from fastapi import HTTPException

from db.connection import get_writer_db
from services.syncthing_proxy import SyncthingProxy, run_sync
from services.watcher_manager import WatcherManager

logger = logging.getLogger(__name__)

# Input validation
ALLOWED_PROJECT_NAME = re.compile(r"^[a-zA-Z0-9_\-]+$")
ALLOWED_MEMBER_NAME = re.compile(r"^[a-zA-Z0-9_\-\.]+$")  # hostnames have dots
ALLOWED_DEVICE_ID = re.compile(r"^[A-Z0-9\-]+$")
_VALID_EVENT_TYPES = frozenset({
    "team_created", "team_deleted", "team_left",
    "member_added", "member_removed", "member_auto_accepted",
    "member_joined", "project_shared",
    "project_added", "project_removed",
    "folders_shared", "pending_accepted",
    "sync_now", "watcher_started", "watcher_stopped",
    "session_packaged", "session_received",
    "file_rejected", "sync_paused",
    "settings_changed",
})


def validate_project_name(name: str) -> str:
    if not ALLOWED_PROJECT_NAME.match(name) or len(name) > 512:
        raise HTTPException(400, "Invalid project name")
    return name


def validate_device_id(device_id: str) -> str:
    if not ALLOWED_DEVICE_ID.match(device_id) or len(device_id) > 72:
        raise HTTPException(400, "Invalid device ID")
    return device_id


def validate_user_id(user_id: str) -> str:
    if not ALLOWED_MEMBER_NAME.match(user_id) or len(user_id) > 128:
        raise HTTPException(400, "Invalid user_id")
    return user_id


def validate_project_path(path: str) -> str:
    """Validate project path — reject traversal and non-absolute paths."""
    if not path:
        return path  # empty path is allowed (uses encoded_name instead)
    resolved = Path(path).resolve()
    # Must not contain .. in any part
    if ".." in Path(path).parts:
        raise HTTPException(400, "Invalid project path: traversal not allowed")
    # Must be under user's home directory (use relative_to for proper ancestry check)
    home = Path.home().resolve()
    try:
        resolved.relative_to(home)
    except ValueError:
        raise HTTPException(400, "Invalid project path: must be under home directory")
    return str(resolved)


# Singleton proxy
_proxy: SyncthingProxy | None = None
_singleton_lock = threading.Lock()


def get_proxy() -> SyncthingProxy:
    global _proxy
    with _singleton_lock:
        if _proxy is None:
            _proxy = SyncthingProxy()
        return _proxy


def reset_proxy() -> None:
    """Reset the proxy singleton (used by reset endpoint and tests)."""
    global _proxy
    _proxy = None


# Singleton watcher manager
_watcher: WatcherManager | None = None


def get_watcher() -> WatcherManager:
    global _watcher
    with _singleton_lock:
        if _watcher is None:
            _watcher = WatcherManager()
        return _watcher


def reset_watcher() -> None:
    """Reset the watcher singleton (used by tests)."""
    global _watcher
    _watcher = None


def _get_sync_conn() -> sqlite3.Connection:
    """Get writer connection for sync operations."""
    return get_writer_db()


# TTL cache for _load_identity
_identity_cache = None
_identity_cache_time: float = 0.0
_IDENTITY_TTL = 5  # seconds


def _invalidate_identity_cache():
    """Clear the identity cache (useful for tests)."""
    global _identity_cache, _identity_cache_time
    _identity_cache = None
    _identity_cache_time = 0.0


def _load_identity():
    """Load identity-only SyncConfig from JSON. Returns config or None (TTL-cached)."""
    global _identity_cache, _identity_cache_time
    from karma.config import SyncConfig

    now = time.monotonic()
    if _identity_cache is not None and (now - _identity_cache_time) < _IDENTITY_TTL:
        return _identity_cache

    try:
        result = SyncConfig.load()
    except RuntimeError:
        result = None

    # Only cache successful loads — don't cache None so "not initialized" is always fresh
    if result is not None:
        _identity_cache = result
        _identity_cache_time = now
    else:
        _identity_cache = None
        _identity_cache_time = 0.0
    return result


def _compute_proj_suffix(git_identity: Optional[str], path: Optional[str], encoded: str) -> str:
    """Compute the project suffix used in Syncthing folder IDs."""
    if git_identity:
        return git_identity.replace("/", "-")
    return Path(path).name if path else encoded


async def _trigger_remote_reindex_bg() -> None:
    """Trigger remote session reindex in background thread.

    Called after sync actions (folder/device acceptance, project sharing,
    member addition) so newly arrived remote sessions appear immediately
    in the dashboard instead of waiting for the 5-minute periodic cycle.
    """
    import asyncio

    from db.indexer import trigger_remote_reindex

    try:
        await asyncio.to_thread(trigger_remote_reindex)
    except Exception as e:
        logger.debug("Background remote reindex failed: %s", e)

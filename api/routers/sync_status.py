"""Backwards-compatibility shim for sync_status.py.

This module was split into 7 router files + 3 service modules.
Re-exports key symbols so existing code that imports from
``routers.sync_status`` continues to work.

New code should import from the specific router or service module.
"""

# Re-export from services for compatibility
from services.sync_identity import (  # noqa: F401
    get_proxy,
    reset_proxy,
    get_watcher,
    _get_sync_conn,
    _load_identity,
    _invalidate_identity_cache,
    _trigger_remote_reindex_bg,
    validate_project_name,
    validate_device_id,
    validate_user_id,
    validate_project_path,
    ALLOWED_PROJECT_NAME,
    ALLOWED_MEMBER_NAME,
    ALLOWED_DEVICE_ID,
    _VALID_EVENT_TYPES,
    _compute_proj_suffix,
)
from services.syncthing_proxy import run_sync, SyncthingNotRunning  # noqa: F401
from db.connection import get_writer_db  # noqa: F401

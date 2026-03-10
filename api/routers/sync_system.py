"""Sync system endpoints — init, status, reset, detect."""

import logging
import shutil
import sqlite3
import subprocess
from pathlib import Path
from typing import Any, Optional

from fastapi import APIRouter, HTTPException

from db.sync_queries import list_teams
from schemas import InitRequest, ResetOptions
import services.sync_identity as _sid
from services.sync_identity import (
    reset_proxy,
    get_watcher,
    validate_user_id,
    ALLOWED_PROJECT_NAME,
)
from services.syncthing_proxy import SyncthingNotRunning, run_sync

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/sync", tags=["sync"])


@router.post("/init")
async def sync_init(req: InitRequest) -> Any:
    """Initialize Karma sync configuration."""
    validate_user_id(req.user_id)
    if req.backend != "syncthing":
        raise HTTPException(400, "Only 'syncthing' backend is supported")
    from karma.config import SyncConfig, SyncthingSettings

    device_id: Optional[str] = None

    if req.backend == "syncthing":
        proxy = _sid.get_proxy()
        try:
            info = await run_sync(proxy.detect)
        except SyncthingNotRunning:
            raise HTTPException(503, "Syncthing is not running")

        if not info.get("running"):
            raise HTTPException(503, "Syncthing is not running")

        from karma.syncthing import read_local_api_key

        api_key = await run_sync(read_local_api_key)
        device_id = info.get("device_id")

        syncthing_settings = SyncthingSettings(
            api_key=api_key,
            device_id=device_id,
        )
        config = SyncConfig(user_id=req.user_id, syncthing=syncthing_settings)
    else:
        config = SyncConfig(user_id=req.user_id)

    await run_sync(config.save)

    return {
        "ok": True,
        "user_id": config.user_id,
        "machine_id": config.machine_id,
        "device_id": device_id,
    }


@router.get("/status")
async def sync_status():
    """Get sync configuration and status."""
    config = await run_sync(_sid._load_identity)
    if config is None:
        return {"configured": False}

    conn = _sid._get_sync_conn()
    teams_list = list_teams(conn)
    teams = {}
    for t in teams_list:
        teams[t["name"]] = {
            "backend": t["backend"],
            "project_count": t["project_count"],
            "member_count": t["member_count"],
        }

    return {
        "configured": True,
        "user_id": config.user_id,
        "machine_id": config.machine_id,
        "device_id": config.syncthing.device_id if config.syncthing else None,
        "teams": teams,
    }


@router.post("/reset")
async def sync_reset(options: Optional[ResetOptions] = None) -> Any:
    """Full sync teardown: clean Syncthing config, kill daemon, delete files & tables."""
    from karma.config import SYNC_CONFIG_PATH, KARMA_BASE

    if options is None:
        options = ResetOptions()

    steps: dict[str, Any] = {}

    # 1. Stop watcher if running
    watcher = get_watcher()
    if watcher.is_running:
        await run_sync(watcher.stop)
        steps["watcher_stopped"] = True

    # 2. Clean Syncthing config (remove karma folders & team devices) then shut it down
    try:
        proxy = _sid.get_proxy()
        # Remove all karma-* shared folders
        try:
            result = await run_sync(proxy.remove_karma_folders)
            steps["syncthing_folders_removed"] = result.get("removed", [])
        except Exception as e:
            steps["syncthing_folders_removed"] = f"error: {e}"

        # Remove all non-self devices (team members)
        try:
            result = await run_sync(proxy.remove_all_non_self_devices)
            steps["syncthing_devices_removed"] = result.get("removed", [])
        except Exception as e:
            steps["syncthing_devices_removed"] = f"error: {e}"

        # Shut down the Syncthing daemon
        try:
            result = await run_sync(proxy.shutdown)
            steps["syncthing_shutdown"] = result.get("ok", False)
        except Exception as e:
            steps["syncthing_shutdown"] = f"error: {e}"
    except Exception:
        steps["syncthing_cleanup"] = "skipped (not running)"

    # 3. Delete remote session files
    remote_dir = KARMA_BASE / "remote-sessions"
    if remote_dir.exists():
        shutil.rmtree(remote_dir, ignore_errors=True)
        steps["remote_sessions_deleted"] = True
    else:
        steps["remote_sessions_deleted"] = False

    # 4. Delete sync config file + stale sync.db
    if SYNC_CONFIG_PATH.exists():
        SYNC_CONFIG_PATH.unlink()
        steps["config_deleted"] = True
    else:
        steps["config_deleted"] = False

    stale_sync_db = KARMA_BASE / "sync.db"
    if stale_sync_db.exists():
        stale_sync_db.unlink(missing_ok=True)
        steps["stale_sync_db_deleted"] = True

    # 5. Clear all sync tables + orphan remote sessions
    conn = _sid._get_sync_conn()
    tables_cleared = []
    for table in ["sync_events", "sync_team_projects", "sync_members", "sync_teams"]:
        try:
            conn.execute(f"DELETE FROM {table}")  # noqa: S608 — table names are hardcoded
            tables_cleared.append(table)
        except sqlite3.OperationalError:
            pass  # table doesn't exist yet

    # Clean up remote session rows — the files on disk were already deleted
    # in step 3, so these would be orphans after reset.
    try:
        cursor = conn.execute("DELETE FROM sessions WHERE source = 'remote'")
        remote_deleted = cursor.rowcount
        steps["remote_sessions_db_deleted"] = remote_deleted
    except sqlite3.OperationalError:
        steps["remote_sessions_db_deleted"] = 0

    conn.commit()
    steps["tables_cleared"] = tables_cleared

    # 6. Stop brew service FIRST to deregister launchd plist (prevents respawn),
    #    then kill any remaining Syncthing processes.
    try:
        r = subprocess.run(
            ["brew", "services", "stop", "syncthing"],
            capture_output=True, text=True, timeout=15,
        )
        steps["brew_service_stopped"] = r.returncode == 0
    except Exception as e:
        logger.debug("brew services stop failed: %s", e)
        steps["brew_service_stopped"] = False

    try:
        subprocess.run(["pkill", "syncthing"], capture_output=True, timeout=5)
        steps["process_killed"] = True
    except Exception as e:
        logger.debug("pkill syncthing failed: %s", e)
        steps["process_killed"] = False

    # 7. Optionally full uninstall: uninstall binary, remove config dirs
    if options.uninstall_syncthing:
        # Uninstall via brew
        try:
            r = subprocess.run(
                ["brew", "uninstall", "syncthing"],
                capture_output=True, text=True, timeout=30,
            )
            steps["brew_uninstalled"] = r.returncode == 0
        except Exception as e:
            logger.debug("brew uninstall syncthing failed: %s", e)
            steps["brew_uninstalled"] = False

        # Remove Syncthing config directories
        st_config_dirs = [
            Path.home() / "Library" / "Application Support" / "Syncthing",
            Path.home() / ".local" / "share" / "syncthing",
            Path.home() / ".config" / "syncthing",
        ]
        removed_dirs = []
        for d in st_config_dirs:
            if d.exists():
                shutil.rmtree(d, ignore_errors=True)
                removed_dirs.append(str(d))
        steps["syncthing_config_removed"] = removed_dirs

    # 8. Reset proxy singleton and invalidate in-memory caches
    reset_proxy()

    try:
        from services.remote_sessions import invalidate_caches
        invalidate_caches()
        steps["caches_invalidated"] = True
    except Exception as e:
        logger.debug("Cache invalidation failed: %s", e)
        steps["caches_invalidated"] = False

    return {"ok": True, "steps": steps}


@router.get("/detect")
async def sync_detect() -> Any:
    """Detect whether Syncthing is installed and running."""
    proxy = _sid.get_proxy()
    try:
        return await run_sync(proxy.detect)
    except SyncthingNotRunning:
        raise HTTPException(status_code=503, detail="Syncthing is not running")

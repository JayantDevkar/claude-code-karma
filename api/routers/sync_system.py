"""Sync system endpoints — status, initialization, reconciliation, reset."""
from __future__ import annotations

import logging
import shutil
import sqlite3
import subprocess
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from routers.sync_deps import (
    get_conn,
    get_optional_config,
    make_reconciliation_service,
    make_repos,
    require_config,
    validate_name,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/sync", tags=["sync-system"])


# --- Request schemas -------------------------------------------------------

class InitRequest(BaseModel):
    user_id: str
    backend: str = "syncthing"


class ResetOptions(BaseModel):
    uninstall_syncthing: bool = False


# --- Dependencies ----------------------------------------------------------

async def get_recon_svc(config=Depends(require_config)):
    return make_reconciliation_service(config)


# --- Endpoints -------------------------------------------------------------

@router.get("/status")
async def sync_status(
    conn: sqlite3.Connection = Depends(get_conn),
    config=Depends(get_optional_config),
):
    """Sync configuration and team summary."""
    if config is None:
        return {"configured": False}

    repos = make_repos()
    teams = repos["teams"].list_all(conn)

    return {
        "configured": True,
        "user_id": config.user_id,
        "machine_id": config.machine_id,
        "member_tag": config.member_tag,
        "device_id": config.syncthing.device_id if config.syncthing else None,
        "teams": [
            {"name": t.name, "status": t.status.value, "leader_member_tag": t.leader_member_tag}
            for t in teams
        ],
    }


@router.post("/init")
async def sync_init(req: InitRequest):
    """Initialize Karma sync — detects Syncthing and saves config."""
    validate_name(req.user_id, "user_id")
    if req.backend != "syncthing":
        raise HTTPException(400, "Only 'syncthing' backend is supported")

    from karma.config import SyncConfig, SyncthingSettings
    from karma.syncthing import read_local_api_key
    from services.syncthing.client import SyncthingClient

    api_key = read_local_api_key()
    if not api_key:
        raise HTTPException(
            503, "Cannot read Syncthing API key. Is Syncthing installed?"
        )

    client = SyncthingClient(api_url="http://localhost:8384", api_key=api_key)
    try:
        status = await client.get_system_status()
    except Exception:
        raise HTTPException(503, "Syncthing is not running or unreachable")

    device_id = status.get("myID")
    syncthing_settings = SyncthingSettings(api_key=api_key, device_id=device_id)
    config = SyncConfig(user_id=req.user_id, syncthing=syncthing_settings)
    config.save()

    return {
        "ok": True,
        "user_id": config.user_id,
        "machine_id": config.machine_id,
        "member_tag": config.member_tag,
        "device_id": device_id,
    }


@router.post("/reconcile")
async def trigger_reconciliation(
    conn: sqlite3.Connection = Depends(get_conn),
    svc=Depends(get_recon_svc),
):
    """Trigger a manual 3-phase reconciliation cycle."""
    try:
        await svc.run_cycle(conn)
    except Exception as e:
        logger.warning("Manual reconciliation failed: %s", e)
        raise HTTPException(500, f"Reconciliation failed: {e}")
    return {"ok": True}


@router.get("/detect")
async def sync_detect():
    """Detect whether Syncthing is installed and running."""
    try:
        from karma.syncthing import read_local_api_key
        from services.syncthing.client import SyncthingClient

        api_key = read_local_api_key()
        if not api_key:
            return {"running": False, "reason": "no_api_key"}

        client = SyncthingClient(api_url="http://localhost:8384", api_key=api_key)
        status = await client.get_system_status()
        return {
            "running": True,
            "device_id": status.get("myID"),
            "version": status.get("version"),
        }
    except Exception:
        return {"running": False}


@router.post("/reset")
async def sync_reset(options: Optional[ResetOptions] = None):
    """Full sync teardown — clean Syncthing, delete files, clear DB."""
    from karma.config import SYNC_CONFIG_PATH, KARMA_BASE

    if options is None:
        options = ResetOptions()

    steps: dict[str, Any] = {}

    # 1. Clean Syncthing config (best-effort)
    try:
        from karma.syncthing import read_local_api_key
        from services.syncthing.client import SyncthingClient

        api_key = read_local_api_key()
        if api_key:
            client = SyncthingClient(
                api_url="http://localhost:8384", api_key=api_key
            )
            # Remove all karma-* folders
            try:
                folders = await client.get_config_folders()
                removed = []
                for f in folders:
                    if f.get("id", "").startswith("karma-"):
                        await client.delete_config_folder(f["id"])
                        removed.append(f["id"])
                steps["folders_removed"] = removed
            except Exception as e:
                steps["folders_removed"] = f"error: {e}"

            # Remove all non-self devices
            try:
                sys_status = await client.get_system_status()
                my_id = sys_status.get("myID", "")
                devices = await client.get_config_devices()
                removed_devs = []
                for d in devices:
                    if d.get("deviceID") != my_id:
                        await client.delete_config_device(d["deviceID"])
                        removed_devs.append(d["deviceID"])
                steps["devices_removed"] = removed_devs
            except Exception as e:
                steps["devices_removed"] = f"error: {e}"
    except Exception:
        steps["syncthing_cleanup"] = "skipped"

    # 2. Delete filesystem dirs
    for dir_name in ["remote-sessions", "handshakes", "metadata-folders"]:
        d = KARMA_BASE / dir_name
        if d.exists():
            shutil.rmtree(d, ignore_errors=True)
            steps[f"{dir_name.replace('-', '_')}_deleted"] = True

    # 3. Delete sync config
    if SYNC_CONFIG_PATH.exists():
        SYNC_CONFIG_PATH.unlink()
        steps["config_deleted"] = True

    # 4. Clear v4 sync tables
    conn = get_conn()
    tables_cleared = []
    for table in [
        "sync_subscriptions",
        "sync_projects",
        "sync_removed_members",
        "sync_events",
        "sync_members",
        "sync_teams",
    ]:
        try:
            conn.execute(f"DELETE FROM {table}")  # noqa: S608
            tables_cleared.append(table)
        except sqlite3.OperationalError:
            pass
    conn.commit()
    steps["tables_cleared"] = tables_cleared

    # 5. Stop Syncthing service (best-effort)
    try:
        subprocess.run(
            ["brew", "services", "stop", "syncthing"],
            capture_output=True,
            timeout=15,
        )
        steps["service_stopped"] = True
    except Exception:
        steps["service_stopped"] = False

    # 6. Optionally uninstall Syncthing
    if options.uninstall_syncthing:
        try:
            r = subprocess.run(
                ["brew", "uninstall", "syncthing"],
                capture_output=True,
                text=True,
                timeout=30,
            )
            steps["brew_uninstalled"] = r.returncode == 0
        except Exception:
            steps["brew_uninstalled"] = False

    return {"ok": True, "steps": steps}

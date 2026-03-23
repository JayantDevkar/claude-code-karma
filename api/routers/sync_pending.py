"""Sync Pending Devices + Folders router — v4, Syncthing cluster pending API."""
from __future__ import annotations

import logging
import re
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from routers.sync_deps import make_managers, require_config

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/sync", tags=["sync-pending"])


# --- Request schemas -------------------------------------------------------

class AcceptDeviceRequest(BaseModel):
    name: Optional[str] = None


class RejectFolderRequest(BaseModel):
    device_id: str


# --- Dependencies ----------------------------------------------------------

async def get_syncthing_client(config=Depends(require_config)):
    """Build a raw SyncthingClient from config."""
    from services.syncthing.client import SyncthingClient

    api_key = config.syncthing.api_key if config.syncthing else ""
    return SyncthingClient(api_url="http://localhost:8384", api_key=api_key)


async def get_folder_mgr(config=Depends(require_config)):
    """Return the FolderManager from make_managers."""
    _, folders, _ = make_managers(config)
    return folders


# --- Pending devices -------------------------------------------------------

@router.get("/pending-devices")
async def list_pending_devices(client=Depends(get_syncthing_client)):
    """List devices requesting to connect (Syncthing pending devices)."""
    try:
        raw = await client.get_pending_devices()
    except Exception as e:
        logger.warning("Failed to fetch pending devices: %s", e)
        return {"devices": []}

    devices = []
    for device_id, info in raw.items():
        devices.append({
            "device_id": device_id,
            "name": info.get("name", ""),
            "address": info.get("address", ""),
            "time": info.get("time", ""),
        })
    return {"devices": devices}


@router.post("/pending-devices/{device_id}/accept")
async def accept_pending_device(
    device_id: str,
    req: AcceptDeviceRequest,
    client=Depends(get_syncthing_client),
    config=Depends(require_config),
):
    """Accept a pending device and auto-accept any karma-meta--* folders from it."""
    device_config = {
        "deviceID": device_id,
        "name": req.name or "",
        "addresses": ["dynamic"],
        "autoAcceptFolders": False,
    }
    try:
        await client.put_config_device(device_config)
    except Exception as e:
        raise HTTPException(500, f"Failed to accept device: {e}")

    # Auto-accept karma-meta--* folders offered by the same device
    discovered_teams: list[str] = []
    try:
        from config import settings as app_settings
        karma_base = app_settings.karma_base
        raw = await client.get_pending_folders()

        _meta_re = re.compile(r"^karma-meta--(.+)$")

        for folder_id, folder_data in raw.items():
            m = _meta_re.match(folder_id)
            if not m:
                continue
            # Syncthing nests under "offeredBy": {device_id: {...}}
            offered_by = folder_data.get("offeredBy", folder_data)
            # Check if this folder is offered by the device we just accepted
            if device_id not in offered_by:
                continue

            team_name = m.group(1)

            try:
                from services.syncthing.folder_manager import build_folder_config

                devices = [{"deviceID": device_id, "encryptionPassword": ""}]
                local_id = config.syncthing.device_id if config.syncthing else None
                if local_id:
                    devices.append({"deviceID": local_id, "encryptionPassword": ""})

                folder_config = build_folder_config(
                    karma_base, folder_id, "sendreceive", devices,
                )
                await client.put_config_folder(folder_config)
                await client.dismiss_pending_folder(folder_id, device_id)
                discovered_teams.append(team_name)
            except Exception as folder_exc:
                logger.warning(
                    "Failed to auto-accept metadata folder %s: %s",
                    folder_id,
                    folder_exc,
                )
    except Exception as e:
        logger.warning("Failed to auto-accept metadata folders: %s", e)

    return {"ok": True, "device_id": device_id, "teams": discovered_teams}


@router.delete("/pending-devices/{device_id}")
async def dismiss_pending_device(
    device_id: str,
    client=Depends(get_syncthing_client),
):
    """Dismiss/reject a pending device."""
    try:
        await client.dismiss_pending_device(device_id)
    except Exception as e:
        raise HTTPException(500, f"Failed to dismiss device: {e}")
    return {"ok": True, "device_id": device_id}


# --- Pending folders -------------------------------------------------------

# Pattern: karma-out--{member_tag}--{suffix}
_KARMA_FOLDER_RE = re.compile(r"^karma-(out|meta)--(.+?)(?:--(.+))?$")


def _parse_folder_id(folder_id: str) -> dict:
    """Extract folder_type, member_tag, suffix from a karma folder ID."""
    m = _KARMA_FOLDER_RE.match(folder_id)
    if m:
        return {
            "folder_type": m.group(1),
            "from_member": m.group(2),
            "suffix": m.group(3),
        }
    return {"folder_type": "unknown", "from_member": None, "suffix": None}


@router.get("/pending")
async def list_pending_folders(client=Depends(get_syncthing_client)):
    """List folders offered by peers (Syncthing pending folders)."""
    try:
        raw = await client.get_pending_folders()
    except Exception as e:
        logger.warning("Failed to fetch pending folders: %s", e)
        return {"folders": []}

    folders = []
    for folder_id, folder_data in raw.items():
        parsed = _parse_folder_id(folder_id)
        # Syncthing nests under "offeredBy": {device_id: {time, label, ...}}
        device_map = folder_data.get("offeredBy", folder_data)
        for dev_id, info in device_map.items():
            folders.append({
                "folder_id": folder_id,
                "label": info.get("label", folder_id),
                "from_device": dev_id,
                "from_member": parsed["from_member"],
                "offered_at": info.get("time", ""),
                "folder_type": parsed["folder_type"],
            })
    return {"folders": folders}


@router.post("/pending/accept/{folder_id:path}")
async def accept_pending_folder(
    folder_id: str,
    config=Depends(require_config),
    client=Depends(get_syncthing_client),
    folder_mgr=Depends(get_folder_mgr),
):
    """Accept a pending folder by creating it in Syncthing config."""
    # Determine which device offered the folder
    try:
        raw = await client.get_pending_folders()
    except Exception as e:
        raise HTTPException(500, f"Failed to fetch pending folders: {e}")

    folder_data = raw.get(folder_id)
    if not folder_data:
        raise HTTPException(404, f"Pending folder '{folder_id}' not found")

    # Syncthing nests under "offeredBy": {device_id: {...}}
    offered_by = folder_data.get("offeredBy", folder_data)
    device_ids = list(offered_by.keys())
    if not device_ids:
        raise HTTPException(404, f"No offering device found for folder '{folder_id}'")

    # Parse folder_id to determine type and create appropriate config
    parsed = _parse_folder_id(folder_id)
    devices = [{"deviceID": did, "encryptionPassword": ""} for did in device_ids]

    from config import settings as app_settings
    from services.syncthing.folder_manager import build_folder_config, resolve_folder_type

    folder_config = build_folder_config(
        app_settings.karma_base, folder_id, resolve_folder_type(folder_id), devices,
    )
    try:
        await client.put_config_folder(folder_config)
    except Exception as e:
        raise HTTPException(500, f"Failed to accept folder: {e}")
    return {"ok": True, "folder_id": folder_id}


@router.post("/pending/reject/{folder_id:path}")
async def reject_pending_folder(
    folder_id: str,
    req: RejectFolderRequest,
    client=Depends(get_syncthing_client),
):
    """Reject/dismiss a pending folder."""
    try:
        await client.dismiss_pending_folder(folder_id, req.device_id)
    except Exception as e:
        raise HTTPException(500, f"Failed to reject folder: {e}")
    return {"ok": True, "folder_id": folder_id}

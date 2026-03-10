import logging
from typing import Any, Optional

from fastapi import APIRouter, HTTPException

from db.sync_queries import (
    get_team, get_known_devices, list_members,
    upsert_member, log_event,
)
from schemas import AcceptPendingDeviceRequest, AddDeviceRequest
from services.folder_id import is_karma_folder
import services.sync_identity as _sid
from services.sync_identity import (
    validate_device_id, _trigger_remote_reindex_bg,
    ALLOWED_PROJECT_NAME,
)
from services.sync_folders import (
    auto_share_folders, ensure_handshake_folder,
    extract_username_from_folder_ids,
)
from services.sync_reconciliation import (
    reconcile_introduced_devices,
    ensure_leader_introducers,
    auto_accept_pending_peers,
)
from services.syncthing_proxy import SyncthingNotRunning, run_sync

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/sync", tags=["sync"])


@router.get("/devices")
async def sync_devices() -> Any:
    """List all configured Syncthing devices."""
    proxy = _sid.get_proxy()
    try:
        devices = await run_sync(proxy.get_devices)
        return {"devices": devices}
    except SyncthingNotRunning:
        raise HTTPException(status_code=503, detail="Syncthing is not running")


@router.post("/devices")
async def sync_add_device(req: AddDeviceRequest) -> Any:
    """Add a new Syncthing device."""
    validate_device_id(req.device_id)
    proxy = _sid.get_proxy()
    try:
        return await run_sync(proxy.add_device, req.device_id, req.name)
    except SyncthingNotRunning:
        raise HTTPException(status_code=503, detail="Syncthing is not running")
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))


@router.delete("/devices/{device_id}")
async def sync_remove_device(device_id: str) -> Any:
    """Remove a paired Syncthing device."""
    validate_device_id(device_id)
    proxy = _sid.get_proxy()
    try:
        return await run_sync(proxy.remove_device, device_id)
    except SyncthingNotRunning:
        raise HTTPException(status_code=503, detail="Syncthing is not running")


@router.get("/pending-devices")
async def sync_pending_devices() -> Any:
    """List Syncthing devices trying to connect that aren't configured.

    Auto-accepts pending devices (handshake completion) but does NOT
    auto-accept pending folders — those require explicit user action.
    """
    conn = _sid._get_sync_conn()

    # Get proxy once — used by both Phase 0 and Phase 1
    try:
        proxy = _sid.get_proxy()
    except Exception:
        proxy = None

    # Phase 0: Ensure leader devices have introducer=True (auto-heals existing setups)
    if proxy:
        try:
            await ensure_leader_introducers(proxy, conn)
        except Exception:
            pass

    # Phase 0.5: Reconcile devices that Syncthing's introducer auto-added
    # but the karma DB doesn't know about (multi-device leader scenario).
    config = None
    reconciled = 0
    try:
        config = await run_sync(_sid._load_identity)
        if config and proxy:
            reconciled = await reconcile_introduced_devices(proxy, config, conn)
    except Exception as e:
        logger.debug("Reconcile introduced devices failed: %s", e)

    # Phase 1 only: auto-accept pending devices (handshake completion).
    # Folder acceptance is now explicit — handled by POST /pending/accept/{folder_id}.
    peer_accepted = 0
    remaining_pending = None
    try:
        if config is None:
            config = await run_sync(_sid._load_identity)
        if config and proxy:
            peer_accepted, remaining_pending = await auto_accept_pending_peers(proxy, config, conn)
    except Exception as e:
        logger.debug("Auto-accept pending peers failed: %s", e)

    auto_accepted = reconciled + peer_accepted

    # Use remaining from auto-accept if available, otherwise fetch fresh
    if remaining_pending is None:
        proxy = _sid.get_proxy()
        try:
            remaining_pending = await run_sync(proxy.get_pending_devices)
        except SyncthingNotRunning:
            return {"devices": [], "auto_accepted": auto_accepted}

    # Filter out devices we already know about (team members)
    known_device_ids = set(get_known_devices(conn).keys())

    result = []
    for device_id, info in remaining_pending.items():
        if device_id not in known_device_ids:
            result.append({
                "device_id": device_id,
                "name": info.get("name", ""),
                "address": info.get("address", ""),
                "time": info.get("time", ""),
            })

    return {"devices": result, "auto_accepted": auto_accepted}



@router.post("/pending-devices/{device_id}/accept")
async def sync_accept_pending_device(device_id: str, req: AcceptPendingDeviceRequest) -> Any:
    """Manually accept a pending device and add it as a team member.

    This handles the chicken-and-egg problem where auto-accept requires
    karma-* folders but Syncthing can't deliver folder offers from an
    unpaired device.  The user sees the pending request in the UI and
    clicks Accept, which:
      1. Pairs the device in Syncthing
      2. Adds the device as a team member (using member_name or hostname)
      3. Creates a handshake folder so the new member can discover us
      4. Shares existing project folders with the new member
    """
    validate_device_id(device_id)
    team_name = req.team_name
    if not ALLOWED_PROJECT_NAME.match(team_name):
        raise HTTPException(400, "Invalid team name")

    conn = _sid._get_sync_conn()
    team = get_team(conn, team_name)
    if team is None:
        raise HTTPException(404, f"Team '{team_name}' not found")

    proxy = _sid.get_proxy()

    # Verify this device is actually pending in Syncthing
    try:
        pending = await run_sync(proxy.get_pending_devices)
    except SyncthingNotRunning:
        raise HTTPException(503, "Syncthing is not running")

    if device_id not in pending:
        raise HTTPException(404, "Device is not in the pending list")

    device_info = pending[device_id]

    # Resolve member name: explicit request > folder ID extraction > hostname.
    # Never blindly use the Syncthing hostname (e.g. "Ayush-Mac-mini.local")
    # because it doesn't match the karma user_id used in folder IDs.
    member_name = req.member_name
    if not member_name:
        # Try to extract real karma username from pending/configured folders
        karma_folder_ids = []
        try:
            pending_folders = await run_sync(proxy.get_pending_folders)
            for folder_id, info in pending_folders.items():
                if not is_karma_folder(folder_id):
                    continue
                if device_id in info.get("offeredBy", {}):
                    karma_folder_ids.append(folder_id)
        except Exception:
            pass
        if not karma_folder_ids:
            try:
                configured_folders = await run_sync(proxy.get_configured_folders)
                for folder in configured_folders:
                    folder_id = folder.get("id", "")
                    if not is_karma_folder(folder_id):
                        continue
                    folder_device_ids = {
                        d.get("deviceID") for d in folder.get("devices", [])
                    }
                    if device_id in folder_device_ids:
                        karma_folder_ids.append(folder_id)
            except Exception:
                pass
        if karma_folder_ids:
            member_name = extract_username_from_folder_ids(
                karma_folder_ids, conn=conn,
            )
        if not member_name:
            member_name = device_info.get("name", "unknown")

    # 1. Accept device in Syncthing
    try:
        await run_sync(proxy.add_device, device_id, member_name)
    except Exception as e:
        raise HTTPException(500, f"Failed to pair device: {e}")

    # 2. Add as team member
    upsert_member(conn, team_name, member_name, device_id=device_id)
    log_event(conn, "pending_accepted", team_name=team_name, member_name=member_name)
    logger.info("Manually accepted pending device %s (%s) into team %s", member_name, device_id[:20], team_name)

    # 3. Create handshake folder so new member discovers us
    config = await run_sync(_sid._load_identity)
    if config:
        try:
            await ensure_handshake_folder(proxy, config, team_name, [device_id])
        except Exception as e:
            logger.warning("Failed to create handshake folder for accepted device: %s", e)

        # 4. Share existing project folders with the new member
        try:
            await auto_share_folders(proxy, config, conn, team_name, device_id)
        except Exception as e:
            logger.warning("Failed to auto-share folders with accepted device: %s", e)

    # Reindex remote sessions so any already-synced files appear immediately
    await _trigger_remote_reindex_bg()

    return {
        "ok": True,
        "device_id": device_id,
        "member_name": member_name,
        "team_name": team_name,
    }


@router.delete("/pending-devices/{device_id}")
async def sync_dismiss_pending_device(device_id: str) -> Any:
    """Dismiss a pending device request without accepting it.

    Tells Syncthing to stop showing this device as pending.
    The device can re-appear if it attempts to connect again.
    """
    validate_device_id(device_id)
    proxy = _sid.get_proxy()
    try:
        await run_sync(proxy.dismiss_pending_device, device_id)
    except SyncthingNotRunning:
        raise HTTPException(503, "Syncthing is not running")
    except Exception as e:
        raise HTTPException(500, f"Failed to dismiss device: {e}")
    return {"ok": True, "device_id": device_id}

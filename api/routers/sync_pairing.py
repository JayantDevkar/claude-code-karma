"""Sync Pairing + Devices router — pairing codes and device status."""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from routers.sync_deps import make_managers, require_config

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/sync", tags=["sync-pairing"])


# --- Schemas ---------------------------------------------------------------

class ValidateCodeRequest(BaseModel):
    code: str


# --- Dependencies ----------------------------------------------------------

def get_pairing_svc():
    from services.sync.pairing_service import PairingService

    return PairingService()


async def get_device_mgr(config=Depends(require_config)):
    devices, _, _ = make_managers(config)
    return devices


# --- Endpoints -------------------------------------------------------------

@router.get("/pairing/code")
async def generate_pairing_code(
    config=Depends(require_config),
    pairing=Depends(get_pairing_svc),
):
    """Generate a permanent pairing code for this device."""
    device_id = config.syncthing.device_id if config.syncthing else ""
    if not device_id:
        raise HTTPException(400, "No Syncthing device ID configured")
    code = pairing.generate_code(config.member_tag, device_id)
    return {"code": code, "member_tag": config.member_tag}


@router.post("/pairing/validate")
async def validate_pairing_code(
    req: ValidateCodeRequest,
    pairing=Depends(get_pairing_svc),
):
    """Validate and decode a pairing code (preview, does not add member)."""
    try:
        info = pairing.validate_code(req.code)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {"member_tag": info.member_tag, "device_id": info.device_id}


@router.get("/devices")
async def list_devices(
    config=Depends(require_config),
    devices=Depends(get_device_mgr),
):
    """List connected Syncthing devices."""
    try:
        connected = await devices.list_connected()
    except Exception:
        connected = []
    device_id = config.syncthing.device_id if config.syncthing else ""
    return {
        "my_device_id": device_id,
        "connected_devices": connected,
    }

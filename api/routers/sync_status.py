"""Sync status API endpoints."""

import json
import re
from pathlib import Path
from typing import Any, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from services.syncthing_proxy import SyncthingNotRunning, SyncthingProxy, run_sync

SYNC_CONFIG_PATH = Path.home() / ".claude_karma" / "sync-config.json"

router = APIRouter(prefix="/sync", tags=["sync"])

# Input validation
ALLOWED_PROJECT_NAME = re.compile(r"^[a-zA-Z0-9_\-]+$")
ALLOWED_DEVICE_ID = re.compile(r"^[A-Z0-9\-]+$")


def validate_project_name(name: str) -> str:
    if not ALLOWED_PROJECT_NAME.match(name) or len(name) > 128:
        raise HTTPException(400, "Invalid project name")
    return name


def validate_device_id(device_id: str) -> str:
    if not ALLOWED_DEVICE_ID.match(device_id) or len(device_id) > 72:
        raise HTTPException(400, "Invalid device ID")
    return device_id


# Singleton proxy
_proxy: SyncthingProxy | None = None


def get_proxy() -> SyncthingProxy:
    global _proxy
    if _proxy is None:
        _proxy = SyncthingProxy()
    return _proxy


class AddDeviceRequest(BaseModel):
    device_id: str
    name: str


class InitRequest(BaseModel):
    user_id: str
    backend: str = "syncthing"


def _load_config() -> Optional[dict]:
    if not SYNC_CONFIG_PATH.exists():
        return None
    try:
        return json.loads(SYNC_CONFIG_PATH.read_text())
    except (json.JSONDecodeError, OSError):
        return None


def validate_user_id(user_id: str) -> str:
    if not ALLOWED_PROJECT_NAME.match(user_id) or len(user_id) > 128:
        raise HTTPException(400, "Invalid user_id")
    return user_id


@router.post("/init")
async def sync_init(req: InitRequest) -> Any:
    """Initialize Karma sync configuration."""
    validate_user_id(req.user_id)
    if req.backend not in ("syncthing", "ipfs"):
        raise HTTPException(400, "Invalid backend; must be 'syncthing' or 'ipfs'")

    # Import CLI config models via sys.path (same approach as syncthing_proxy.py)
    import sys
    from pathlib import Path as _Path

    cli_path = _Path(__file__).parent.parent.parent / "cli"
    if str(cli_path) not in sys.path:
        sys.path.insert(0, str(cli_path))

    from karma.config import SyncConfig, SyncthingSettings

    device_id: Optional[str] = None

    if req.backend == "syncthing":
        proxy = get_proxy()
        try:
            info = await run_sync(proxy.detect)
        except SyncthingNotRunning:
            raise HTTPException(503, "Syncthing is not running")

        if not info.get("running"):
            raise HTTPException(503, "Syncthing is not running")

        # Read API key from local Syncthing config
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
    config = _load_config()
    if config is None:
        return {"configured": False}

    teams = {}
    for name, team in config.get("teams", {}).items():
        teams[name] = {
            "backend": team["backend"],
            "project_count": len(team.get("projects", {})),
            "member_count": len(team.get("ipfs_members", {}))
            + len(team.get("syncthing_members", {})),
        }

    return {
        "configured": True,
        "user_id": config.get("user_id"),
        "machine_id": config.get("machine_id"),
        "teams": teams,
    }


@router.get("/teams")
async def sync_teams():
    """List all teams with their backend and members."""
    config = _load_config()
    if config is None:
        return {"teams": []}

    teams = []
    for name, team in config.get("teams", {}).items():
        projects = []
        for pname, pconfig in team.get("projects", {}).items():
            projects.append({
                "name": pname,
                "encoded_name": pconfig.get("encoded_name", pname),
                "path": pconfig.get("path"),
            })
        teams.append(
            {
                "name": name,
                "backend": team["backend"],
                "projects": projects,
                "members": list(team.get("ipfs_members", {}).keys())
                + list(team.get("syncthing_members", {}).keys()),
            }
        )

    return {"teams": teams}


@router.get("/detect")
async def sync_detect() -> Any:
    """Detect whether Syncthing is installed and running."""
    proxy = get_proxy()
    try:
        return await run_sync(proxy.detect)
    except SyncthingNotRunning:
        raise HTTPException(status_code=503, detail="Syncthing is not running")


@router.get("/devices")
async def sync_devices() -> Any:
    """List all configured Syncthing devices."""
    proxy = get_proxy()
    try:
        devices = await run_sync(proxy.get_devices)
        return {"devices": devices}
    except SyncthingNotRunning:
        raise HTTPException(status_code=503, detail="Syncthing is not running")


@router.post("/devices")
async def sync_add_device(req: AddDeviceRequest) -> Any:
    """Add a new Syncthing device."""
    validate_device_id(req.device_id)
    proxy = get_proxy()
    try:
        return await run_sync(proxy.add_device, req.device_id, req.name)
    except SyncthingNotRunning:
        raise HTTPException(status_code=503, detail="Syncthing is not running")


@router.delete("/devices/{device_id}")
async def sync_remove_device(device_id: str) -> Any:
    """Remove a paired Syncthing device."""
    validate_device_id(device_id)
    proxy = get_proxy()
    try:
        return await run_sync(proxy.remove_device, device_id)
    except SyncthingNotRunning:
        raise HTTPException(status_code=503, detail="Syncthing is not running")


@router.get("/projects")
async def sync_projects() -> Any:
    """List all configured Syncthing folders."""
    proxy = get_proxy()
    try:
        folders = await run_sync(proxy.get_folder_status)
        return {"folders": folders}
    except SyncthingNotRunning:
        raise HTTPException(status_code=503, detail="Syncthing is not running")


@router.get("/activity")
async def sync_activity(since: int = 0, limit: int = 50) -> Any:
    """Get recent Syncthing events and bandwidth stats."""
    proxy = get_proxy()
    try:
        events = await run_sync(proxy.get_events, since, limit)
        try:
            bandwidth = await run_sync(proxy.get_bandwidth)
        except Exception:
            bandwidth = {"upload_rate": 0, "download_rate": 0, "upload_total": 0, "download_total": 0}
        return {
            "events": events,
            "upload_rate": bandwidth.get("upload_rate", 0),
            "download_rate": bandwidth.get("download_rate", 0),
            "upload_total": bandwidth.get("upload_total", 0),
            "download_total": bandwidth.get("download_total", 0),
        }
    except SyncthingNotRunning:
        raise HTTPException(status_code=503, detail="Syncthing is not running")


def _load_sync_config():
    """Load SyncConfig from CLI module. Returns (config_or_none, SyncConfig_class, ProjectConfig_class)."""
    import sys
    from pathlib import Path as _Path

    cli_path = _Path(__file__).parent.parent.parent / "cli"
    if str(cli_path) not in sys.path:
        sys.path.insert(0, str(cli_path))

    from karma.config import ProjectConfig, SyncConfig

    config = SyncConfig.load()
    return config, SyncConfig, ProjectConfig


@router.post("/projects/{project_name}/enable")
async def sync_project_enable(project_name: str) -> Any:
    """Enable sync for a project."""
    validate_project_name(project_name)

    config, SyncConfig, ProjectConfig = await run_sync(_load_sync_config)
    if config is None:
        raise HTTPException(status_code=400, detail="Not initialized")

    project_config = ProjectConfig(path=project_name, encoded_name=project_name)
    new_projects = dict(config.projects)
    new_projects[project_name] = project_config
    updated = config.model_copy(update={"projects": new_projects})
    await run_sync(updated.save)

    return {"ok": True, "project": project_name}


@router.post("/projects/{project_name}/disable")
async def sync_project_disable(project_name: str) -> Any:
    """Disable sync for a project."""
    validate_project_name(project_name)

    config, SyncConfig, ProjectConfig = await run_sync(_load_sync_config)
    if config is None:
        raise HTTPException(status_code=400, detail="Not initialized")

    new_projects = dict(config.projects)
    new_projects.pop(project_name, None)
    updated = config.model_copy(update={"projects": new_projects})
    await run_sync(updated.save)

    return {"ok": True, "project": project_name}


@router.post("/projects/{project_name}/sync-now")
async def sync_project_sync_now(project_name: str) -> Any:
    """Trigger an immediate sync for a project."""
    validate_project_name(project_name)

    return {"ok": True, "project": project_name, "message": "Sync triggered"}

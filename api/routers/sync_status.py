"""Sync status API endpoints."""

import re
import sys
from pathlib import Path
from typing import Any, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from services.syncthing_proxy import SyncthingNotRunning, SyncthingProxy, run_sync
from services.watcher_manager import WatcherManager

# Add CLI to path once for SyncConfig / syncthing imports
_CLI_PATH = Path(__file__).parent.parent.parent / "cli"
if str(_CLI_PATH) not in sys.path:
    sys.path.insert(0, str(_CLI_PATH))

router = APIRouter(prefix="/sync", tags=["sync"])

# Input validation
ALLOWED_PROJECT_NAME = re.compile(r"^[a-zA-Z0-9_\-]+$")
ALLOWED_DEVICE_ID = re.compile(r"^[A-Z0-9\-]+$")


def validate_project_name(name: str) -> str:
    if not ALLOWED_PROJECT_NAME.match(name) or len(name) > 512:
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


# Singleton watcher manager
_watcher: WatcherManager | None = None


def get_watcher() -> WatcherManager:
    global _watcher
    if _watcher is None:
        _watcher = WatcherManager()
    return _watcher


class AddDeviceRequest(BaseModel):
    device_id: str
    name: str


class InitRequest(BaseModel):
    user_id: str
    backend: str = "syncthing"


class CreateTeamRequest(BaseModel):
    name: str
    backend: str = "syncthing"


class AddMemberRequest(BaseModel):
    name: str
    device_id: str


class AddTeamProjectRequest(BaseModel):
    name: str
    path: str


def validate_user_id(user_id: str) -> str:
    if not ALLOWED_PROJECT_NAME.match(user_id) or len(user_id) > 128:
        raise HTTPException(400, "Invalid user_id")
    return user_id


def _load_sync_config():
    """Load SyncConfig from CLI module. Returns (config, SyncConfig, ProjectConfig) or (None, SyncConfig, ProjectConfig)."""
    from karma.config import ProjectConfig, SyncConfig

    try:
        config = SyncConfig.load()
    except RuntimeError:
        config = None
    return config, SyncConfig, ProjectConfig


@router.post("/init")
async def sync_init(req: InitRequest) -> Any:
    """Initialize Karma sync configuration."""
    validate_user_id(req.user_id)
    if req.backend not in ("syncthing", "ipfs"):
        raise HTTPException(400, "Invalid backend; must be 'syncthing' or 'ipfs'")

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
    config, _, _ = await run_sync(_load_sync_config)
    if config is None:
        return {"configured": False}

    data = config.model_dump()
    teams = {}
    for name, team in data.get("teams", {}).items():
        teams[name] = {
            "backend": team["backend"],
            "project_count": len(team.get("projects", {})),
            "member_count": len(team.get("ipfs_members", {}))
            + len(team.get("syncthing_members", {})),
        }

    return {
        "configured": True,
        "user_id": data.get("user_id"),
        "machine_id": data.get("machine_id"),
        "teams": teams,
    }


@router.get("/teams")
async def sync_teams():
    """List all teams with their backend and members."""
    config, _, _ = await run_sync(_load_sync_config)
    if config is None:
        return {"teams": []}

    data = config.model_dump()
    teams = []
    for name, team in data.get("teams", {}).items():
        projects = []
        for pname, pconfig in team.get("projects", {}).items():
            projects.append({
                "name": pname,
                "encoded_name": pconfig.get("encoded_name", pname),
                "path": pconfig.get("path"),
            })
        members = []
        for mname, mdata in team.get("syncthing_members", {}).items():
            members.append({
                "name": mname,
                "device_id": mdata.get("syncthing_device_id", ""),
                "connected": False,
                "in_bytes_total": 0,
                "out_bytes_total": 0,
            })
        for mname in team.get("ipfs_members", {}).keys():
            members.append({
                "name": mname,
                "device_id": "",
                "connected": False,
                "in_bytes_total": 0,
                "out_bytes_total": 0,
            })
        teams.append(
            {
                "name": name,
                "backend": team["backend"],
                "projects": projects,
                "members": members,
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
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))


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
        try:
            events = await run_sync(proxy.get_events, since, limit)
        except SyncthingNotRunning:
            raise
        except Exception:
            events = []
        try:
            bandwidth = await run_sync(proxy.get_bandwidth)
        except SyncthingNotRunning:
            raise
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
    """Trigger an immediate rescan for a project's Syncthing folder."""
    validate_project_name(project_name)
    proxy = get_proxy()
    try:
        # Find the Syncthing folder ID matching this project name
        # Match against folder ID, path, or label
        folders = await run_sync(proxy.get_folder_status)
        matched = [
            f for f in folders
            if project_name in f.get("id", "")
            or project_name in f.get("path", "")
            or project_name in f.get("label", "")
        ]
        if not matched:
            raise HTTPException(404, "No Syncthing folder found for this project")
        results = []
        for folder in matched:
            result = await run_sync(proxy.rescan_folder, folder["id"])
            results.append(result)
        return {"ok": True, "project": project_name, "scanned": [r["folder"] for r in results]}
    except SyncthingNotRunning:
        raise HTTPException(503, "Syncthing is not running")


@router.post("/rescan")
async def sync_rescan_all() -> Any:
    """Trigger an immediate rescan of all Syncthing folders."""
    proxy = get_proxy()
    try:
        return await run_sync(proxy.rescan_all)
    except SyncthingNotRunning:
        raise HTTPException(503, "Syncthing is not running")


# ─── Task 1: Team CRUD ───────────────────────────────────────────────


@router.post("/teams")
async def sync_create_team(req: CreateTeamRequest) -> Any:
    """Create a new sync group."""
    if not ALLOWED_PROJECT_NAME.match(req.name) or len(req.name) > 64:
        raise HTTPException(400, "Invalid team name")
    if req.backend not in ("syncthing", "ipfs"):
        raise HTTPException(400, "Invalid backend")

    config, SyncConfig, _ = await run_sync(_load_sync_config)
    if config is None:
        raise HTTPException(400, "Not initialized. Set up sync first.")

    if req.name in config.model_dump().get("teams", {}):
        raise HTTPException(409, f"Team '{req.name}' already exists")

    from karma.config import TeamConfig

    team_cfg = TeamConfig(backend=req.backend, projects={})
    teams = dict(config.teams)
    teams[req.name] = team_cfg
    updated = config.model_copy(update={"teams": teams})
    await run_sync(updated.save)

    return {"ok": True, "name": req.name, "backend": req.backend}


@router.delete("/teams/{team_name}")
async def sync_delete_team(team_name: str) -> Any:
    """Delete a sync group."""
    if not ALLOWED_PROJECT_NAME.match(team_name):
        raise HTTPException(400, "Invalid team name")

    config, _, _ = await run_sync(_load_sync_config)
    if config is None:
        raise HTTPException(400, "Not initialized")

    data = config.model_dump()
    if team_name not in data.get("teams", {}):
        raise HTTPException(404, f"Team '{team_name}' not found")

    teams = dict(config.teams)
    del teams[team_name]
    updated = config.model_copy(update={"teams": teams})
    await run_sync(updated.save)

    return {"ok": True, "name": team_name}


# ─── Task 2: Team member management ──────────────────────────────────


@router.post("/teams/{team_name}/members")
async def sync_add_member(team_name: str, req: AddMemberRequest) -> Any:
    """Add a member to a sync group."""
    if not ALLOWED_PROJECT_NAME.match(team_name):
        raise HTTPException(400, "Invalid team name")
    if not ALLOWED_PROJECT_NAME.match(req.name) or len(req.name) > 64:
        raise HTTPException(400, "Invalid member name")
    validate_device_id(req.device_id)

    config, _, _ = await run_sync(_load_sync_config)
    if config is None:
        raise HTTPException(400, "Not initialized")

    data = config.model_dump()
    if team_name not in data.get("teams", {}):
        raise HTTPException(404, f"Team '{team_name}' not found")

    from karma.config import TeamMemberSyncthing

    team_cfg = config.teams[team_name]

    syncthing_members = dict(team_cfg.syncthing_members)
    syncthing_members[req.name] = TeamMemberSyncthing(
        syncthing_device_id=req.device_id
    )
    teams = dict(config.teams)
    teams[team_name] = team_cfg.model_copy(
        update={"syncthing_members": syncthing_members}
    )
    updated = config.model_copy(update={"teams": teams})
    await run_sync(updated.save)

    # Pair device in Syncthing (best-effort — config is already saved)
    paired = False
    try:
        proxy = get_proxy()
        await run_sync(proxy.add_device, req.device_id, req.name)
        paired = True
    except Exception:
        pass

    return {
        "ok": True,
        "name": req.name,
        "device_id": req.device_id,
        "paired": paired,
    }


@router.delete("/teams/{team_name}/members/{member_name}")
async def sync_remove_member(team_name: str, member_name: str) -> Any:
    """Remove a member from a sync group."""
    if not ALLOWED_PROJECT_NAME.match(team_name):
        raise HTTPException(400, "Invalid team name")
    if not ALLOWED_PROJECT_NAME.match(member_name):
        raise HTTPException(400, "Invalid member name")

    config, _, _ = await run_sync(_load_sync_config)
    if config is None:
        raise HTTPException(400, "Not initialized")

    data = config.model_dump()
    if team_name not in data.get("teams", {}):
        raise HTTPException(404, f"Team '{team_name}' not found")

    team_cfg = config.teams[team_name]
    if member_name not in team_cfg.syncthing_members:
        raise HTTPException(404, f"Member '{member_name}' not found")

    device_id = team_cfg.syncthing_members[member_name].syncthing_device_id

    members = dict(team_cfg.syncthing_members)
    del members[member_name]
    teams = dict(config.teams)
    teams[team_name] = team_cfg.model_copy(update={"syncthing_members": members})
    updated = config.model_copy(update={"teams": teams})
    await run_sync(updated.save)

    try:
        proxy = get_proxy()
        await run_sync(proxy.remove_device, device_id)
    except Exception:
        pass  # Best-effort device removal from Syncthing

    return {"ok": True, "name": member_name}


# ─── Task 3: Team project management ─────────────────────────────────


@router.post("/teams/{team_name}/projects")
async def sync_add_team_project(team_name: str, req: AddTeamProjectRequest) -> Any:
    """Add a project to a sync group."""
    validate_project_name(req.name)
    if not ALLOWED_PROJECT_NAME.match(team_name):
        raise HTTPException(400, "Invalid team name")

    config, _, _ = await run_sync(_load_sync_config)
    if config is None:
        raise HTTPException(400, "Not initialized")
    if team_name not in config.teams:
        raise HTTPException(404, f"Team '{team_name}' not found")

    from karma.sync import encode_project_path
    from karma.config import ProjectConfig

    encoded = encode_project_path(req.path) if req.path else req.name
    project_config = ProjectConfig(path=req.path, encoded_name=encoded)

    team_cfg = config.teams[team_name]
    projects = dict(team_cfg.projects)
    projects[req.name] = project_config
    teams = dict(config.teams)
    teams[team_name] = team_cfg.model_copy(update={"projects": projects})
    updated = config.model_copy(update={"teams": teams})
    await run_sync(updated.save)

    return {
        "ok": True,
        "name": req.name,
        "encoded_name": encoded,
    }


@router.delete("/teams/{team_name}/projects/{project_name}")
async def sync_remove_team_project(team_name: str, project_name: str) -> Any:
    """Remove a project from a sync group."""
    validate_project_name(project_name)
    if not ALLOWED_PROJECT_NAME.match(team_name):
        raise HTTPException(400, "Invalid team name")

    config, _, _ = await run_sync(_load_sync_config)
    if config is None:
        raise HTTPException(400, "Not initialized")
    if team_name not in config.teams:
        raise HTTPException(404, f"Team '{team_name}' not found")

    team_cfg = config.teams[team_name]
    if project_name not in team_cfg.projects:
        raise HTTPException(404, f"Project '{project_name}' not found in team")

    projects = dict(team_cfg.projects)
    del projects[project_name]
    teams = dict(config.teams)
    teams[team_name] = team_cfg.model_copy(update={"projects": projects})
    updated = config.model_copy(update={"teams": teams})
    await run_sync(updated.save)

    return {"ok": True, "name": project_name}


# ─── Task 4: Watcher manager endpoints ───────────────────────────────


@router.get("/watch/status")
async def sync_watch_status() -> Any:
    """Get watcher status."""
    return get_watcher().status()


@router.post("/watch/start")
async def sync_watch_start(team_name: str | None = None) -> Any:
    """Start the session watcher for a team."""
    config, _, _ = await run_sync(_load_sync_config)
    if config is None:
        raise HTTPException(400, "Not initialized")

    data = config.model_dump()
    teams = data.get("teams", {})

    if team_name is None:
        syncthing_teams = [n for n, t in teams.items() if t.get("backend") == "syncthing"]
        if len(syncthing_teams) == 1:
            team_name = syncthing_teams[0]
        elif len(syncthing_teams) == 0:
            raise HTTPException(400, "No syncthing teams configured")
        else:
            raise HTTPException(
                400,
                f"Multiple teams found. Specify team_name: {syncthing_teams}",
            )

    if team_name not in teams:
        raise HTTPException(404, f"Team '{team_name}' not found")

    watcher = get_watcher()
    if watcher.is_running:
        raise HTTPException(409, "Watcher already running. Stop it first.")

    try:
        result = await run_sync(watcher.start, team_name, data)
        return result
    except Exception as e:
        raise HTTPException(500, f"Failed to start watcher: {e}")


@router.post("/watch/stop")
async def sync_watch_stop() -> Any:
    """Stop the session watcher."""
    watcher = get_watcher()
    if not watcher.is_running:
        return watcher.status()
    return await run_sync(watcher.stop)


# ─── Task 5: Pending folders ─────────────────────────────────────────


@router.get("/pending")
async def sync_pending() -> Any:
    """List pending folder offers from known team members."""
    config, _, _ = await run_sync(_load_sync_config)
    if config is None:
        return {"pending": []}

    known: dict[str, tuple[str, str]] = {}
    for team_name, team_cfg in config.teams.items():
        for member_name, member_cfg in team_cfg.syncthing_members.items():
            known[member_cfg.syncthing_device_id] = (member_name, team_name)

    if not known:
        return {"pending": []}

    proxy = get_proxy()
    try:
        pending = await run_sync(proxy.get_pending_folders_for_ui, known)
        return {"pending": pending}
    except SyncthingNotRunning:
        return {"pending": []}


@router.post("/pending/accept")
async def sync_accept_pending() -> Any:
    """Accept all pending folder offers from known team members."""
    config, _, _ = await run_sync(_load_sync_config)
    if config is None:
        raise HTTPException(400, "Not initialized")

    try:
        from karma.syncthing import SyncthingClient, read_local_api_key

        api_key = config.syncthing.api_key or await run_sync(read_local_api_key)
        st = SyncthingClient(api_key=api_key)
        if not st.is_running():
            raise HTTPException(503, "Syncthing is not running")

        from karma.main import _accept_pending_folders

        accepted = await run_sync(_accept_pending_folders, st, config)
        return {"ok": True, "accepted": accepted}
    except SyncthingNotRunning:
        raise HTTPException(503, "Syncthing is not running")
    except Exception as e:
        raise HTTPException(500, f"Failed to accept pending folders: {e}")


# ─── Task 6: Per-project sync status ─────────────────────────────────


@router.get("/teams/{team_name}/project-status")
async def sync_team_project_status(team_name: str) -> Any:
    """Get per-project sync status with local/packaged/received counts."""
    if not ALLOWED_PROJECT_NAME.match(team_name):
        raise HTTPException(400, "Invalid team name")

    config, _, _ = await run_sync(_load_sync_config)
    if config is None:
        raise HTTPException(400, "Not initialized")
    if team_name not in config.teams:
        raise HTTPException(404, f"Team '{team_name}' not found")

    from pathlib import Path as P
    from karma.config import KARMA_BASE
    from karma.worktree_discovery import find_worktree_dirs

    team_cfg = config.teams[team_name]
    projects_dir = P.home() / ".claude" / "projects"
    result = []

    for proj_name, proj in team_cfg.projects.items():
        encoded = proj.encoded_name
        claude_dir = projects_dir / encoded

        local_count = 0
        if claude_dir.is_dir():
            local_count = sum(
                1
                for f in claude_dir.glob("*.jsonl")
                if not f.name.startswith("agent-") and f.stat().st_size > 0
            )
        wt_dirs = find_worktree_dirs(encoded, projects_dir)
        for wd in wt_dirs:
            local_count += sum(
                1
                for f in wd.glob("*.jsonl")
                if not f.name.startswith("agent-") and f.stat().st_size > 0
            )

        outbox = KARMA_BASE / "remote-sessions" / config.user_id / encoded / "sessions"
        packaged_count = 0
        if outbox.is_dir():
            packaged_count = sum(
                1
                for f in outbox.glob("*.jsonl")
                if not f.name.startswith("agent-")
            )

        received_counts = {}
        for mname in team_cfg.syncthing_members:
            inbox = KARMA_BASE / "remote-sessions" / mname / encoded / "sessions"
            if inbox.is_dir():
                received_counts[mname] = sum(
                    1
                    for f in inbox.glob("*.jsonl")
                    if not f.name.startswith("agent-")
                )
            else:
                received_counts[mname] = 0

        result.append({
            "name": proj_name,
            "encoded_name": encoded,
            "path": proj.path,
            "local_count": local_count,
            "packaged_count": packaged_count,
            "received_counts": received_counts,
            "gap": max(0, local_count - packaged_count),
        })

    return {"projects": result}

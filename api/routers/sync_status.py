"""Sync status API endpoints — backed by SQLite."""

import logging
import re
import sqlite3
import sys
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from db.connection import get_writer_db, create_read_connection
from db.sync_queries import (
    create_team,
    delete_team,
    list_teams,
    get_team,
    add_member,
    remove_member,
    list_members,
    add_team_project,
    remove_team_project,
    list_team_projects,
    log_event,
    query_events,
    get_known_devices,
)
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


def validate_user_id(user_id: str) -> str:
    if not ALLOWED_PROJECT_NAME.match(user_id) or len(user_id) > 128:
        raise HTTPException(400, "Invalid user_id")
    return user_id


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


def _get_sync_conn() -> sqlite3.Connection:
    """Get writer connection for sync operations."""
    return get_writer_db()


def _load_identity():
    """Load identity-only SyncConfig from JSON. Returns config or None."""
    from karma.config import SyncConfig

    try:
        return SyncConfig.load()
    except RuntimeError:
        return None


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


class JoinTeamRequest(BaseModel):
    join_code: str


# ─── Init & Status ────────────────────────────────────────────────────


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
    config = await run_sync(_load_identity)
    if config is None:
        return {"configured": False}

    conn = _get_sync_conn()
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
async def sync_reset() -> Any:
    """Reset sync configuration: delete config file + clear sync tables."""
    from karma.config import SYNC_CONFIG_PATH

    # Stop watcher if running
    watcher = get_watcher()
    if watcher.is_running:
        await run_sync(watcher.stop)

    # Delete config file
    if SYNC_CONFIG_PATH.exists():
        SYNC_CONFIG_PATH.unlink()

    # Clear sync tables
    conn = _get_sync_conn()
    conn.execute("DELETE FROM sync_events")
    conn.execute("DELETE FROM sync_team_projects")
    conn.execute("DELETE FROM sync_members")
    conn.execute("DELETE FROM sync_teams")
    conn.commit()

    # Reset proxy so it re-detects on next call
    global _proxy
    _proxy = None

    return {"ok": True}


@router.get("/teams")
async def sync_teams_list():
    """List all teams with their backend, members, and projects."""
    conn = _get_sync_conn()
    teams_data = list_teams(conn)

    teams = []
    for t in teams_data:
        members_data = list_members(conn, t["name"])
        projects_data = list_team_projects(conn, t["name"])
        teams.append({
            "name": t["name"],
            "backend": t["backend"],
            "projects": [
                {
                    "name": p["project_encoded_name"],
                    "encoded_name": p["project_encoded_name"],
                    "path": p["path"],
                }
                for p in projects_data
            ],
            "members": [
                {
                    "name": m["name"],
                    "device_id": m["device_id"] or "",
                    "connected": False,
                    "in_bytes_total": 0,
                    "out_bytes_total": 0,
                }
                for m in members_data
            ],
        })

    return {"teams": teams}


# ─── Syncthing proxy endpoints (unchanged) ────────────────────────────


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


@router.post("/projects/{project_name}/sync-now")
async def sync_project_sync_now(project_name: str) -> Any:
    """Trigger an immediate rescan for a project's Syncthing folder."""
    validate_project_name(project_name)
    proxy = get_proxy()
    try:
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


# ─── Team CRUD ─────────────────────────────────────────────────────────


@router.post("/teams")
async def sync_create_team(req: CreateTeamRequest) -> Any:
    """Create a new sync group."""
    if not ALLOWED_PROJECT_NAME.match(req.name) or len(req.name) > 64:
        raise HTTPException(400, "Invalid team name")
    if req.backend not in ("syncthing", "ipfs"):
        raise HTTPException(400, "Invalid backend")

    config = await run_sync(_load_identity)
    if config is None:
        raise HTTPException(400, "Not initialized. Set up sync first.")

    conn = _get_sync_conn()
    if get_team(conn, req.name) is not None:
        raise HTTPException(409, f"Team '{req.name}' already exists")

    create_team(conn, req.name, req.backend)
    log_event(conn, "team_created", team_name=req.name)

    return {"ok": True, "name": req.name, "backend": req.backend}


@router.delete("/teams/{team_name}")
async def sync_delete_team(team_name: str) -> Any:
    """Delete a sync group."""
    if not ALLOWED_PROJECT_NAME.match(team_name):
        raise HTTPException(400, "Invalid team name")

    conn = _get_sync_conn()
    if get_team(conn, team_name) is None:
        raise HTTPException(404, f"Team '{team_name}' not found")

    log_event(conn, "team_deleted", team_name=team_name)
    delete_team(conn, team_name)

    return {"ok": True, "name": team_name}


# ─── Join Code ────────────────────────────────────────────────────────


@router.post("/teams/join")
async def sync_join_team(req: JoinTeamRequest) -> Any:
    """Join a team via a join code (team_name:user_id:device_id)."""
    parts = req.join_code.split(":", 2)
    if len(parts) != 3:
        raise HTTPException(400, "Invalid join code format. Expected team:user:device_id")
    team_name, leader_name, device_id = parts

    validate_user_id(team_name)
    validate_user_id(leader_name)
    validate_device_id(device_id)

    config = await run_sync(_load_identity)
    if config is None:
        raise HTTPException(400, "Not initialized. Run sync setup first.")

    conn = _get_sync_conn()

    # Create team locally if it doesn't exist
    if get_team(conn, team_name) is None:
        create_team(conn, team_name, "syncthing")
        log_event(conn, "team_created", team_name=team_name)

    # Add leader as member (idempotent)
    try:
        add_member(conn, team_name, leader_name, device_id=device_id)
        log_event(conn, "member_added", team_name=team_name, member_name=leader_name)
    except sqlite3.IntegrityError:
        pass  # already exists

    # Pair device in Syncthing (best-effort)
    paired = False
    try:
        proxy = get_proxy()
        await run_sync(proxy.add_device, device_id, leader_name)
        paired = True
    except Exception:
        pass

    # Auto-accept pending folders from the leader
    accepted = 0
    try:
        from karma.syncthing import SyncthingClient, read_local_api_key

        api_key = config.syncthing.api_key or await run_sync(read_local_api_key)
        st = SyncthingClient(api_key=api_key)
        if st.is_running():
            from karma.main import _accept_pending_folders

            accepted = await run_sync(_accept_pending_folders, st, config)
            if accepted:
                log_event(conn, "pending_accepted", detail={"count": accepted})
    except Exception:
        pass

    # Generate joiner's own code to share back
    own_device_id = config.syncthing.device_id if config.syncthing else None
    own_join_code = f"{team_name}:{config.user_id}:{own_device_id}" if own_device_id else None

    return {
        "ok": True,
        "team_name": team_name,
        "leader_name": leader_name,
        "paired": paired,
        "accepted_folders": accepted,
        "your_join_code": own_join_code,
    }


@router.get("/teams/{team_name}/join-code")
async def sync_team_join_code(team_name: str) -> Any:
    """Get the join code for a team."""
    if not ALLOWED_PROJECT_NAME.match(team_name):
        raise HTTPException(400, "Invalid team name")

    config = await run_sync(_load_identity)
    if config is None:
        raise HTTPException(400, "Not initialized")

    conn = _get_sync_conn()
    if get_team(conn, team_name) is None:
        raise HTTPException(404, f"Team '{team_name}' not found")

    device_id = config.syncthing.device_id if config.syncthing else None
    if not device_id:
        raise HTTPException(400, "No Syncthing device ID configured")

    join_code = f"{team_name}:{config.user_id}:{device_id}"
    return {"join_code": join_code, "team_name": team_name, "user_id": config.user_id}


@router.get("/pending-devices")
async def sync_pending_devices() -> Any:
    """List Syncthing devices trying to connect that aren't configured."""
    conn = _get_sync_conn()
    known = get_known_devices(conn)
    known_device_ids = set(known.keys())

    proxy = get_proxy()
    try:
        pending = await run_sync(proxy.get_pending_devices)
    except SyncthingNotRunning:
        return {"devices": []}

    result = []
    for device_id, info in pending.items():
        if device_id not in known_device_ids:
            result.append({
                "device_id": device_id,
                "name": info.get("name", ""),
                "address": info.get("address", ""),
                "time": info.get("time", ""),
            })

    return {"devices": result}


# ─── Team member management ───────────────────────────────────────────


@router.post("/teams/{team_name}/members")
async def sync_add_member(team_name: str, req: AddMemberRequest) -> Any:
    """Add a member to a sync group."""
    if not ALLOWED_PROJECT_NAME.match(team_name):
        raise HTTPException(400, "Invalid team name")
    if not ALLOWED_PROJECT_NAME.match(req.name) or len(req.name) > 64:
        raise HTTPException(400, "Invalid member name")
    validate_device_id(req.device_id)

    conn = _get_sync_conn()
    if get_team(conn, team_name) is None:
        raise HTTPException(404, f"Team '{team_name}' not found")

    add_member(conn, team_name, req.name, device_id=req.device_id)
    log_event(conn, "member_added", team_name=team_name, member_name=req.name)

    # Pair device in Syncthing (best-effort)
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

    conn = _get_sync_conn()
    if get_team(conn, team_name) is None:
        raise HTTPException(404, f"Team '{team_name}' not found")

    members = list_members(conn, team_name)
    member = next((m for m in members if m["name"] == member_name), None)
    if member is None:
        raise HTTPException(404, f"Member '{member_name}' not found")

    device_id = member["device_id"]
    remove_member(conn, team_name, member_name)
    log_event(conn, "member_removed", team_name=team_name, member_name=member_name)

    if device_id:
        try:
            proxy = get_proxy()
            await run_sync(proxy.remove_device, device_id)
        except Exception:
            pass

    return {"ok": True, "name": member_name}


# ─── Team project management ──────────────────────────────────────────


@router.post("/teams/{team_name}/projects")
async def sync_add_team_project(team_name: str, req: AddTeamProjectRequest) -> Any:
    """Add a project to a sync group."""
    validate_project_name(req.name)
    if not ALLOWED_PROJECT_NAME.match(team_name):
        raise HTTPException(400, "Invalid team name")

    conn = _get_sync_conn()
    if get_team(conn, team_name) is None:
        raise HTTPException(404, f"Team '{team_name}' not found")

    from karma.sync import encode_project_path

    encoded = encode_project_path(req.path) if req.path else req.name

    # Ensure project exists in projects table (for FK)
    conn.execute(
        "INSERT OR IGNORE INTO projects (encoded_name, project_path) VALUES (?, ?)",
        (encoded, req.path),
    )
    conn.commit()

    add_team_project(conn, team_name, encoded, req.path)
    log_event(conn, "project_added", team_name=team_name, project_encoded_name=encoded)

    # Create Syncthing shared folder so teammates see a pending offer
    syncthing_ok = False
    try:
        config = await run_sync(_load_identity)
        if config is not None:
            from pathlib import Path as P
            from karma.config import KARMA_BASE

            proj_short = P(req.path).name if req.path else encoded
            members = list_members(conn, team_name)

            # Outbox: send my sessions to teammates
            outbox_id = f"karma-out-{config.user_id}-{proj_short}"
            outbox_path = str(KARMA_BASE / "remote-sessions" / config.user_id / encoded)
            P(outbox_path).mkdir(parents=True, exist_ok=True)

            device_ids = []
            if config.syncthing.device_id:
                device_ids.append(config.syncthing.device_id)
            for m in members:
                if m["device_id"] and m["device_id"] not in device_ids:
                    device_ids.append(m["device_id"])

            proxy = get_proxy()
            proxy.add_folder(outbox_id, outbox_path, device_ids, folder_type="sendonly")
            syncthing_ok = True
    except Exception as e:
        logger.warning("Failed to create Syncthing folder for project %s: %s", encoded, e)

    return {
        "ok": True,
        "name": req.name,
        "encoded_name": encoded,
        "syncthing_folder_created": syncthing_ok,
    }


@router.delete("/teams/{team_name}/projects/{project_name}")
async def sync_remove_team_project(team_name: str, project_name: str) -> Any:
    """Remove a project from a sync group."""
    validate_project_name(project_name)
    if not ALLOWED_PROJECT_NAME.match(team_name):
        raise HTTPException(400, "Invalid team name")

    conn = _get_sync_conn()
    if get_team(conn, team_name) is None:
        raise HTTPException(404, f"Team '{team_name}' not found")

    projects = list_team_projects(conn, team_name)
    if not any(p["project_encoded_name"] == project_name for p in projects):
        raise HTTPException(404, f"Project '{project_name}' not found in team")

    remove_team_project(conn, team_name, project_name)
    log_event(conn, "project_removed", team_name=team_name, project_encoded_name=project_name)

    return {"ok": True, "name": project_name}


# ─── Watcher manager endpoints ────────────────────────────────────────


@router.get("/watch/status")
async def sync_watch_status() -> Any:
    """Get watcher status."""
    return get_watcher().status()


@router.post("/watch/start")
async def sync_watch_start(team_name: str | None = None) -> Any:
    """Start the session watcher for a team."""
    config = await run_sync(_load_identity)
    if config is None:
        raise HTTPException(400, "Not initialized")

    conn = _get_sync_conn()
    teams_data = list_teams(conn)

    if team_name is None:
        syncthing_teams = [t["name"] for t in teams_data if t["backend"] == "syncthing"]
        if len(syncthing_teams) == 1:
            team_name = syncthing_teams[0]
        elif len(syncthing_teams) == 0:
            raise HTTPException(400, "No syncthing teams configured")
        else:
            raise HTTPException(
                400,
                f"Multiple teams found. Specify team_name: {syncthing_teams}",
            )

    team = get_team(conn, team_name)
    if team is None:
        raise HTTPException(404, f"Team '{team_name}' not found")

    watcher = get_watcher()
    if watcher.is_running:
        raise HTTPException(409, "Watcher already running. Stop it first.")

    # Build config_data dict that WatcherManager expects
    projects = list_team_projects(conn, team_name)
    config_data = {
        "user_id": config.user_id,
        "machine_id": config.machine_id,
        "teams": {
            team_name: {
                "backend": team["backend"],
                "projects": {
                    p["project_encoded_name"]: {
                        "encoded_name": p["project_encoded_name"],
                        "path": p["path"] or "",
                    }
                    for p in projects
                },
            }
        },
    }

    try:
        result = await run_sync(watcher.start, team_name, config_data)
        log_event(conn, "watcher_started", team_name=team_name)
        return result
    except Exception as e:
        raise HTTPException(500, f"Failed to start watcher: {e}")


@router.post("/watch/stop")
async def sync_watch_stop() -> Any:
    """Stop the session watcher."""
    watcher = get_watcher()
    if not watcher.is_running:
        return watcher.status()
    team = watcher._team
    result = await run_sync(watcher.stop)
    if team:
        try:
            conn = _get_sync_conn()
            log_event(conn, "watcher_stopped", team_name=team)
        except Exception:
            pass
    return result


# ─── Pending folders ──────────────────────────────────────────────────


@router.get("/pending")
async def sync_pending() -> Any:
    """List pending folder offers from known team members."""
    conn = _get_sync_conn()
    known = get_known_devices(conn)

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
    config = await run_sync(_load_identity)
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
        if accepted:
            conn = _get_sync_conn()
            log_event(conn, "pending_accepted", detail={"count": accepted})
        return {"ok": True, "accepted": accepted}
    except SyncthingNotRunning:
        raise HTTPException(503, "Syncthing is not running")
    except Exception as e:
        raise HTTPException(500, f"Failed to accept pending folders: {e}")


# ─── Per-project sync status ──────────────────────────────────────────


@router.get("/teams/{team_name}/project-status")
async def sync_team_project_status(team_name: str) -> Any:
    """Get per-project sync status with local/packaged/received counts."""
    if not ALLOWED_PROJECT_NAME.match(team_name):
        raise HTTPException(400, "Invalid team name")

    config = await run_sync(_load_identity)
    if config is None:
        raise HTTPException(400, "Not initialized")

    conn = _get_sync_conn()
    team = get_team(conn, team_name)
    if team is None:
        raise HTTPException(404, f"Team '{team_name}' not found")

    from karma.config import KARMA_BASE
    from karma.worktree_discovery import find_worktree_dirs

    projects = list_team_projects(conn, team_name)
    members = list_members(conn, team_name)
    projects_dir = Path.home() / ".claude" / "projects"
    result = []

    for proj in projects:
        encoded = proj["project_encoded_name"]
        proj_path = proj["path"]
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
        for m in members:
            mname = m["name"]
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
            "name": encoded,
            "encoded_name": encoded,
            "path": proj_path,
            "local_count": local_count,
            "packaged_count": packaged_count,
            "received_counts": received_counts,
            "gap": max(0, local_count - packaged_count),
        })

    return {"projects": result}


# ─── Activity (sync events) ──────────────────────────────────────────


@router.get("/activity")
async def sync_activity(
    team_name: str | None = None,
    event_type: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> Any:
    """Get recent sync activity events and bandwidth stats."""
    conn = _get_sync_conn()
    events = query_events(
        conn, team_name=team_name, event_type=event_type,
        limit=limit, offset=offset,
    )

    # Best-effort bandwidth from Syncthing
    bandwidth = {"upload_rate": 0, "download_rate": 0, "upload_total": 0, "download_total": 0}
    try:
        proxy = get_proxy()
        bandwidth = await run_sync(proxy.get_bandwidth)
    except Exception:
        pass

    return {
        "events": events,
        "upload_rate": bandwidth.get("upload_rate", 0),
        "download_rate": bandwidth.get("download_rate", 0),
        "upload_total": bandwidth.get("upload_total", 0),
        "download_total": bandwidth.get("download_total", 0),
    }

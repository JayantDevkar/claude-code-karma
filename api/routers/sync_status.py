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
    upsert_member,
    remove_member,
    list_members,
    add_team_project,
    remove_team_project,
    list_team_projects,
    upsert_team_project,
    log_event,
    query_events,
    get_known_devices,
    find_project_by_git_identity,
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
_VALID_EVENT_TYPES = frozenset({
    "team_created", "team_deleted",
    "member_added", "member_removed", "member_auto_accepted",
    "project_added", "project_removed",
    "folders_shared", "pending_accepted",
    "sync_now", "watcher_started", "watcher_stopped",
    "session_packaged", "session_received",
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
    if not ALLOWED_PROJECT_NAME.match(user_id) or len(user_id) > 128:
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
    home = Path.home()
    try:
        resolved.relative_to(home)
    except ValueError:
        raise HTTPException(400, "Invalid project path: must be under home directory")
    return str(resolved)


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


def _compute_proj_suffix(git_identity: Optional[str], path: Optional[str], encoded: str) -> str:
    """Compute the project suffix used in Syncthing folder IDs."""
    if git_identity:
        return git_identity.replace("/", "-")
    return Path(path).name if path else encoded


async def _ensure_outbox_folder(proxy, config, encoded: str, proj_suffix: str, device_ids: list[str]) -> None:
    """Create or update an outbox Syncthing folder for a project.

    Tries update_folder_devices first (idempotent), falls back to add_folder.
    """
    from karma.config import KARMA_BASE

    outbox_id = f"karma-out-{config.user_id}-{proj_suffix}"
    outbox_path = str(KARMA_BASE / "remote-sessions" / config.user_id / encoded)
    Path(outbox_path).mkdir(parents=True, exist_ok=True)

    try:
        await run_sync(proxy.update_folder_devices, outbox_id, device_ids)
    except ValueError:
        all_ids = list(device_ids)
        if config.syncthing.device_id and config.syncthing.device_id not in all_ids:
            all_ids.append(config.syncthing.device_id)
        await run_sync(proxy.add_folder, outbox_id, outbox_path, all_ids, "sendonly")


async def _ensure_inbox_folders(
    proxy, config, members: list[dict], encoded: str, proj_suffix: str,
    *, only_device_id: Optional[str] = None,
) -> dict:
    """Create receiveonly inbox folders for team members' outboxes.

    For each member (or a single member if only_device_id is set),
    creates a local receiveonly folder that receives their sessions.

    Args:
        proxy: SyncthingProxy instance
        config: SyncConfig with local identity
        members: Team members from list_members()
        encoded: Project encoded name (used in inbox path)
        proj_suffix: Project suffix for folder ID
        only_device_id: If set, only create inbox for this device
    """
    from karma.config import KARMA_BASE

    result = {"inboxes": 0, "errors": []}

    for m in members:
        if not m["device_id"]:
            continue
        # Skip self
        if config.syncthing.device_id and m["device_id"] == config.syncthing.device_id:
            continue
        # Filter to single device if requested
        if only_device_id and m["device_id"] != only_device_id:
            continue

        inbox_path = str(KARMA_BASE / "remote-sessions" / m["name"] / encoded)
        inbox_id = f"karma-out-{m['name']}-{proj_suffix}"
        inbox_devices = [m["device_id"]]
        if config.syncthing.device_id:
            inbox_devices.append(config.syncthing.device_id)
        try:
            Path(inbox_path).mkdir(parents=True, exist_ok=True)
            # Try update first (folder may already exist from another team sharing the same project)
            try:
                await run_sync(proxy.update_folder_devices, inbox_id, inbox_devices)
            except ValueError:
                # Folder doesn't exist yet — create it
                await run_sync(proxy.add_folder, inbox_id, inbox_path, inbox_devices, "receiveonly")
            result["inboxes"] += 1
        except Exception as e:
            result["errors"].append(f"inbox {m['name']}/{proj_suffix}: {e}")

    return result


def _parse_folder_id(folder_id: str):
    """Parse a karma folder ID into (member_name, suffix).

    Expected format: ``karma-out-{member_name}-{suffix}``
    Returns None if the folder ID does not match.
    """
    prefix = "karma-out-"
    if not folder_id.startswith(prefix):
        return None
    rest = folder_id[len(prefix):]
    parts = rest.split("-")
    if len(parts) < 2:
        return None
    for i in range(1, len(parts)):
        candidate_name = "-".join(parts[:i])
        candidate_suffix = "-".join(parts[i:])
        if candidate_name and candidate_suffix:
            return candidate_name, candidate_suffix
    return None


def _parse_handshake_folder(folder_id: str):
    """Parse a karma-join handshake folder ID into (username, team_name).

    Expected format: ``karma-join-{username}-{team_name}``
    Returns None if the folder ID does not match.
    """
    prefix = "karma-join-"
    if not folder_id.startswith(prefix):
        return None
    rest = folder_id[len(prefix):]
    parts = rest.split("-")
    if len(parts) < 2:
        return None
    # Same ambiguity as _parse_folder_id — try shortest username first
    for i in range(1, len(parts)):
        candidate_name = "-".join(parts[:i])
        candidate_team = "-".join(parts[i:])
        if candidate_name and candidate_team:
            return candidate_name, candidate_team
    return None


async def _ensure_handshake_folder(proxy, config, team_name: str, device_ids: list[str]) -> None:
    """Create a lightweight handshake folder to signal team membership.

    This folder is shared with the leader's device so they can auto-accept
    us even before any projects are added to the team.
    Format: karma-join-{user_id}-{team_name}
    """
    from karma.config import KARMA_BASE

    folder_id = f"karma-join-{config.user_id}-{team_name}"
    folder_path = str(KARMA_BASE / "handshakes" / team_name)
    Path(folder_path).mkdir(parents=True, exist_ok=True)

    try:
        await run_sync(proxy.update_folder_devices, folder_id, device_ids)
    except ValueError:
        all_ids = list(device_ids)
        if config.syncthing.device_id and config.syncthing.device_id not in all_ids:
            all_ids.append(config.syncthing.device_id)
        await run_sync(proxy.add_folder, folder_id, folder_path, all_ids, "sendonly")


def _find_team_for_folder(conn, folder_ids: list[str]) -> Optional[str]:
    """Find which team a set of karma folder IDs belong to.

    First checks for karma-join-* handshake folders (direct team name).
    Then falls back to matching karma-out-* suffixes against team projects.
    """
    # Fast path: handshake folders contain the team name directly
    for folder_id in folder_ids:
        parsed = _parse_handshake_folder(folder_id)
        if parsed:
            _, team_name = parsed
            # Verify this team exists locally
            if get_team(conn, team_name):
                return team_name

    # Slow path: match karma-out-* folder suffixes against team project suffixes
    teams = list_teams(conn)
    team_projects = {t["name"]: list_team_projects(conn, t["name"]) for t in teams}

    for folder_id in folder_ids:
        parsed = _parse_folder_id(folder_id)
        if not parsed:
            continue
        _, suffix = parsed
        for team_name, projects in team_projects.items():
            for proj in projects:
                proj_suffix = _compute_proj_suffix(
                    proj.get("git_identity"), proj.get("path"), proj["project_encoded_name"]
                )
                if proj_suffix == suffix:
                    return team_name
    return None


async def _auto_accept_pending_peers(proxy, config, conn) -> tuple[int, dict]:
    """Auto-accept pending devices AND pending folders from known devices.

    Phase 1 — Device acceptance (two strategies):
    1. **Folder matching**: If the pending device offers karma-* folders,
       match them against team projects or handshake folders.
    2. **Join code trust**: If we have teams with join codes, any pending
       device must have our device_id (from the join code) to connect.

    Phase 2 — Folder acceptance (independent of Phase 1):
    Accepts pending folder offers from any already-known device. This
    handles folders that weren't accepted during device acceptance
    (e.g., device was accepted in a previous poll cycle but folder
    acceptance failed, or folders arrived after device was accepted).

    Returns:
        (accepted_count, remaining_pending_devices)
    """
    # ── Phase 1: Accept pending devices ──────────────────────────────
    try:
        pending_devices = await run_sync(proxy.get_pending_devices)
    except Exception:
        pending_devices = {}

    accepted = 0
    accepted_ids = set()

    if pending_devices:
        try:
            pending_folders = await run_sync(proxy.get_pending_folders)
        except Exception:
            pending_folders = {}

        # Pre-compute: teams with join codes (for fallback strategy)
        all_teams = list_teams(conn)
        teams_with_codes = [t for t in all_teams if t.get("join_code")]

        for device_id in list(pending_devices.keys()):
            device_info = pending_devices.get(device_id, {})
            device_name = device_info.get("name", "")

            # Strategy 1: Match via karma folder offers
            karma_folders = []
            for folder_id, info in pending_folders.items():
                if not folder_id.startswith("karma-"):
                    continue
                if device_id in info.get("offeredBy", {}):
                    karma_folders.append(folder_id)

            username = None
            team_name = None

            if karma_folders:
                # Extract username from folder IDs
                for folder_id in karma_folders:
                    hs = _parse_handshake_folder(folder_id)
                    if hs:
                        username = hs[0]
                        break
                    parsed = _parse_folder_id(folder_id)
                    if parsed:
                        candidate_name, _ = parsed
                        if device_name and device_name == candidate_name:
                            username = candidate_name
                            break
                        if username is None:
                            username = candidate_name

                team_name = _find_team_for_folder(conn, karma_folders)

            # Strategy 2: Fallback — if we have teams, accept the pending device.
            # Trust signal: they must have our device_id (from join code) to connect.
            if not team_name and teams_with_codes:
                team_name = teams_with_codes[0]["name"]
                if not username:
                    if device_name:
                        username = device_name.split(".")[0].lower().replace(" ", "-")
                    else:
                        username = f"peer-{device_id[:7].lower()}"
                logger.info(
                    "Auto-accept (join-code trust): pending device %s → team %s as %s",
                    device_id[:20], team_name, username,
                )

            if not team_name:
                continue

            # Auto-accept device in Syncthing
            try:
                await run_sync(proxy.add_device, device_id, username)
            except Exception as e:
                logger.warning("Auto-accept: failed to add device %s: %s", device_id[:20], e)
                continue

            # Add as team member in DB
            upsert_member(conn, team_name, username, device_id=device_id)
            log_event(conn, "member_auto_accepted", team_name=team_name, member_name=username)
            logger.info("Auto-accepted peer %s (%s) into team %s", username, device_id[:20], team_name)

            # Auto-share folders back (my outbox → new member, includes ALL member device_ids)
            try:
                await _auto_share_folders(proxy, config, conn, team_name, device_id)
            except Exception as e:
                logger.warning("Auto-accept: failed to share folders back to %s: %s", username, e)

            accepted_ids.add(device_id)
            accepted += 1

    # ── Phase 2: Accept pending folders from known devices ───────────
    # Runs independently — handles folders orphaned from previous device
    # acceptance cycles or folders that arrived after device was accepted.
    try:
        from karma.syncthing import SyncthingClient, read_local_api_key
        from karma.main import _accept_pending_folders

        api_key = config.syncthing.api_key or await run_sync(read_local_api_key)
        st = SyncthingClient(api_key=api_key)
        if st.is_running():
            folders_accepted = await run_sync(_accept_pending_folders, st, config, conn)
            if folders_accepted:
                accepted += folders_accepted
                log_event(conn, "pending_accepted", detail={"count": folders_accepted})
                logger.info("Auto-accepted %d pending folders from known devices", folders_accepted)
    except Exception as e:
        logger.warning("Phase 2 auto-accept pending folders failed: %s", e)

    # Return remaining pending devices (minus the ones we accepted)
    remaining = {did: info for did, info in pending_devices.items() if did not in accepted_ids}
    return accepted, remaining


async def _auto_share_folders(proxy, config, conn, team_name, new_device_id) -> dict:
    """Auto-create Syncthing shared folders for all projects in a team.

    For each project:
    1. Outbox (sendonly): my sessions → teammates
    2. Inbox (receiveonly): new member's sessions → my machine
    Uses git_identity in folder ID when available.
    """
    projects = list_team_projects(conn, team_name)
    members = list_members(conn, team_name)

    result = {"outboxes": 0, "inboxes": 0, "errors": []}

    for proj in projects:
        encoded = proj["project_encoded_name"]
        proj_suffix = _compute_proj_suffix(proj.get("git_identity"), proj.get("path"), encoded)

        # Collect all device IDs for this team (deduped)
        all_device_ids = [new_device_id]
        for m in members:
            if m["device_id"] and m["device_id"] not in all_device_ids:
                all_device_ids.append(m["device_id"])

        # 1. My outbox: send my sessions to teammates
        try:
            await _ensure_outbox_folder(proxy, config, encoded, proj_suffix, all_device_ids)
            result["outboxes"] += 1
        except Exception as e:
            result["errors"].append(f"outbox {proj_suffix}: {e}")

        # 2. Inbox for the new member (their outbox is our receiveonly inbox)
        inbox_result = await _ensure_inbox_folders(
            proxy, config, members, encoded, proj_suffix,
            only_device_id=new_device_id,
        )
        result["inboxes"] += inbox_result["inboxes"]
        result["errors"].extend(inbox_result["errors"])

    return result


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
    team_name: str | None = None


# ─── Init & Status ────────────────────────────────────────────────────


@router.post("/init")
async def sync_init(req: InitRequest) -> Any:
    """Initialize Karma sync configuration."""
    validate_user_id(req.user_id)
    if req.backend != "syncthing":
        raise HTTPException(400, "Only 'syncthing' backend is supported")
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


class ResetOptions(BaseModel):
    """Options for sync reset."""
    uninstall_syncthing: bool = False  # Remove Syncthing config directory


@router.post("/reset")
async def sync_reset(options: Optional[ResetOptions] = None) -> Any:
    """Full sync teardown: clean Syncthing config, kill daemon, delete files & tables."""
    import shutil
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
        proxy = get_proxy()
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

    # 4. Delete sync config file
    if SYNC_CONFIG_PATH.exists():
        SYNC_CONFIG_PATH.unlink()
        steps["config_deleted"] = True
    else:
        steps["config_deleted"] = False

    # 5. Clear all sync tables + orphan remote sessions
    conn = _get_sync_conn()
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

    # 6. Kill any remaining Syncthing processes
    import subprocess
    try:
        subprocess.run(["pkill", "-f", "syncthing"], capture_output=True, timeout=5)
        steps["process_killed"] = True
    except Exception:
        steps["process_killed"] = False

    # 7. Optionally full uninstall: stop brew service, uninstall binary, remove config dirs
    if options.uninstall_syncthing:
        # Stop brew service
        try:
            r = subprocess.run(
                ["brew", "services", "stop", "syncthing"],
                capture_output=True, text=True, timeout=15,
            )
            steps["brew_service_stopped"] = r.returncode == 0
        except Exception:
            steps["brew_service_stopped"] = False

        # Uninstall via brew
        try:
            r = subprocess.run(
                ["brew", "uninstall", "syncthing"],
                capture_output=True, text=True, timeout=30,
            )
            steps["brew_uninstalled"] = r.returncode == 0
        except Exception:
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

    # 8. Reset proxy singleton
    global _proxy
    _proxy = None

    return {"ok": True, "steps": steps}


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
    if not ALLOWED_PROJECT_NAME.match(req.name) or len(req.name) < 2 or len(req.name) > 64:
        raise HTTPException(400, "Invalid team name: must be 2-64 characters, letters/numbers/dashes/underscores only")

    if req.backend != "syncthing":
        raise HTTPException(400, "Only 'syncthing' backend is supported")

    config = await run_sync(_load_identity)
    if config is None:
        raise HTTPException(400, "Not initialized. Set up sync first.")

    conn = _get_sync_conn()
    if get_team(conn, req.name) is not None:
        raise HTTPException(409, f"Team '{req.name}' already exists")

    own_device_id = config.syncthing.device_id if config.syncthing else None
    join_code = f"{req.name}:{config.user_id}:{own_device_id}" if own_device_id else None

    create_team(conn, req.name, req.backend, join_code=join_code)

    # Add creator as a member so they appear in the member list and their
    # device_id is included when sharing folders (mirrors join flow)
    if own_device_id:
        upsert_member(conn, req.name, config.user_id, device_id=own_device_id)

    log_event(conn, "team_created", team_name=req.name)

    return {"ok": True, "name": req.name, "backend": req.backend, "join_code": join_code}


async def _cleanup_syncthing_for_team(proxy, config, conn, team_name: str) -> dict:
    """Clean up all Syncthing folders and devices for a team (reverse of join).

    Removes:
    - My outbox folders for this team's projects
    - Inbox folders (other members' outboxes) for this team's projects
    - Handshake folders for this team
    - Team member devices (if not used by other teams)
    """
    members = list_members(conn, team_name)
    projects = list_team_projects(conn, team_name)
    result = {"folders_removed": 0, "devices_removed": 0}

    # Compute project suffixes for this team
    proj_suffixes = set()
    for proj in projects:
        suffix = _compute_proj_suffix(
            proj.get("git_identity"), proj.get("path"), proj["project_encoded_name"]
        )
        proj_suffixes.add(suffix)

    # Collect member names for matching inbox folders
    member_names = {m["name"] for m in members}
    if config and config.user_id:
        member_names.add(config.user_id)

    # Scan all Syncthing folders and remove matching karma folders
    try:
        folders = await run_sync(proxy.get_folder_status)
        for folder in folders:
            folder_id = folder.get("id", "")

            # Check karma-out-* folders (outbox + inbox)
            if folder_id.startswith("karma-out-"):
                parsed = _parse_folder_id(folder_id)
                if parsed and parsed[1] in proj_suffixes and parsed[0] in member_names:
                    try:
                        await run_sync(proxy.remove_folder, folder_id)
                        result["folders_removed"] += 1
                    except Exception as e:
                        logger.warning("Failed to remove folder %s: %s", folder_id, e)

            # Check karma-join-* folders (handshake)
            elif folder_id.startswith("karma-join-"):
                parsed = _parse_handshake_folder(folder_id)
                if parsed and parsed[1] == team_name:
                    try:
                        await run_sync(proxy.remove_folder, folder_id)
                        result["folders_removed"] += 1
                    except Exception as e:
                        logger.warning("Failed to remove handshake folder %s: %s", folder_id, e)
    except Exception as e:
        logger.warning("Failed to scan Syncthing folders for cleanup: %s", e)

    # Remove team member devices (if not used by other teams)
    for m in members:
        device_id = m["device_id"]
        if config and config.syncthing.device_id and device_id == config.syncthing.device_id:
            continue  # Don't remove self
        other_count = conn.execute(
            "SELECT COUNT(*) FROM sync_members WHERE device_id = ? AND team_name != ?",
            (device_id, team_name),
        ).fetchone()[0]
        if other_count == 0:
            try:
                await run_sync(proxy.remove_device, device_id)
                result["devices_removed"] += 1
            except Exception as e:
                logger.warning("Failed to remove device %s: %s", device_id[:20], e)

    return result


async def _cleanup_syncthing_for_member(
    proxy, config, conn, team_name: str, member_device_id: str, member_name: str,
) -> dict:
    """Clean up Syncthing state when removing a member (reverse of add-member).

    Removes:
    - The member's inbox folders from my machine
    - The member's device_id from my outbox folder sharing lists
    - The member's device (if not used by other teams)
    """
    projects = list_team_projects(conn, team_name)
    result = {"folders_removed": 0, "devices_updated": 0}

    proj_suffixes = set()
    for proj in projects:
        suffix = _compute_proj_suffix(
            proj.get("git_identity"), proj.get("path"), proj["project_encoded_name"]
        )
        proj_suffixes.add(suffix)

    try:
        folders = await run_sync(proxy.get_folder_status)
        for folder in folders:
            folder_id = folder.get("id", "")
            if not folder_id.startswith("karma-out-"):
                continue
            parsed = _parse_folder_id(folder_id)
            if not parsed or parsed[1] not in proj_suffixes:
                continue

            username, suffix = parsed

            if config and username == config.user_id:
                # My outbox — remove the kicked member's device from sharing list
                try:
                    res = await run_sync(
                        proxy.remove_device_from_folder, folder_id, member_device_id,
                    )
                    if res.get("removed"):
                        result["devices_updated"] += 1
                except Exception as e:
                    logger.warning("Failed to remove device from folder %s: %s", folder_id, e)
            elif username == member_name:
                # The kicked member's inbox on my machine — remove entirely
                try:
                    await run_sync(proxy.remove_folder, folder_id)
                    result["folders_removed"] += 1
                except Exception as e:
                    logger.warning("Failed to remove inbox folder %s: %s", folder_id, e)
    except Exception as e:
        logger.warning("Failed to scan Syncthing folders for member cleanup: %s", e)

    # Remove handshake folder if exists
    handshake_id = f"karma-join-{member_name}-{team_name}"
    try:
        await run_sync(proxy.remove_folder, handshake_id)
    except Exception:
        pass  # No-op if doesn't exist

    # Remove device (if not used by other teams)
    other_count = conn.execute(
        "SELECT COUNT(*) FROM sync_members WHERE device_id = ? AND team_name != ?",
        (member_device_id, team_name),
    ).fetchone()[0]
    if other_count == 0:
        try:
            await run_sync(proxy.remove_device, member_device_id)
        except Exception as e:
            logger.warning("Failed to remove device %s: %s", member_device_id[:20], e)

    return result


@router.delete("/teams/{team_name}")
async def sync_delete_team(team_name: str) -> Any:
    """Leave/delete a sync team — cleans up Syncthing folders and devices."""
    if not ALLOWED_PROJECT_NAME.match(team_name):
        raise HTTPException(400, "Invalid team name")

    conn = _get_sync_conn()
    if get_team(conn, team_name) is None:
        raise HTTPException(404, f"Team '{team_name}' not found")

    # Clean up Syncthing state before deleting DB records (need member/project data)
    cleanup = {"folders_removed": 0, "devices_removed": 0}
    try:
        config = _load_identity()
        if config:
            proxy = get_proxy()
            cleanup = await _cleanup_syncthing_for_team(proxy, config, conn, team_name)
    except Exception as e:
        logger.warning("Syncthing cleanup for team %s failed: %s", team_name, e)

    log_event(conn, "team_left", team_name=team_name, detail=cleanup)
    delete_team(conn, team_name)

    return {"ok": True, "name": team_name, **cleanup}


# ─── Join Code ────────────────────────────────────────────────────────


@router.post("/teams/join")
async def sync_join_team(req: JoinTeamRequest) -> Any:
    """Join a team via a join code (user_id:device_id or team_name:user_id:device_id)."""
    parts = req.join_code.split(":", 2)
    if len(parts) == 2:
        # New format: user_id:device_id (team inferred from request context or must exist)
        leader_name, device_id = parts
        team_name = req.team_name or None
        if not team_name:
            raise HTTPException(400, "Join code has no team. Provide team_name or use team:user:device_id format.")
    elif len(parts) == 3:
        team_name, leader_name, device_id = parts
    else:
        raise HTTPException(400, "Invalid join code format. Expected user:device_id or team:user:device_id")

    validate_user_id(team_name)
    validate_user_id(leader_name)
    validate_device_id(device_id)

    # Enforce same team name constraints as explicit create endpoint
    if len(team_name) < 2 or len(team_name) > 64:
        raise HTTPException(400, "Invalid team name in join code: must be 2-64 characters")

    config = await run_sync(_load_identity)
    if config is None:
        raise HTTPException(400, "Not initialized. Run sync setup first.")

    own_device_id = config.syncthing.device_id if config.syncthing else None
    conn = _get_sync_conn()

    # Auto-create team if it doesn't exist locally (join codes are Syncthing-only)
    # Store the same join code so all members share a single fixed code
    team_created = False
    if get_team(conn, team_name) is None:
        create_team(conn, team_name, backend="syncthing", join_code=req.join_code.strip())
        log_event(conn, "team_created", team_name=team_name)
        # Add self as a member so the joiner appears in the team's member list
        upsert_member(conn, team_name, config.user_id, device_id=own_device_id)
        team_created = True

    # Add or update leader as member (idempotent, updates device_id on rejoin)
    upsert_member(conn, team_name, leader_name, device_id=device_id)
    log_event(conn, "member_added", team_name=team_name, member_name=leader_name)

    # Pair device in Syncthing (best-effort)
    paired = False
    try:
        proxy = get_proxy()
        await run_sync(proxy.add_device, device_id, leader_name)
        paired = True
    except Exception:
        pass

    # Create handshake folder so the leader can auto-accept us (works even without projects)
    if paired:
        try:
            await _ensure_handshake_folder(proxy, config, team_name, [device_id])
        except Exception as e:
            logger.warning("Failed to create handshake folder: %s", e)

    # Auto-create shared folders for joiner's projects in this team
    folders_created = None
    if paired:
        try:
            folders_created = await _auto_share_folders(proxy, config, conn, team_name, device_id)
        except Exception as e:
            logger.warning("Auto-share folders failed during join: %s", e)

        if folders_created and (folders_created["outboxes"] or folders_created["inboxes"]):
            try:
                log_event(conn, "folders_shared", team_name=team_name, member_name=leader_name,
                          detail={"outboxes": folders_created["outboxes"], "inboxes": folders_created["inboxes"]})
            except Exception as e:
                logger.warning("Failed to log folders_shared event: %s", e)

    # Auto-add local projects matching team's shared projects (bidirectional sharing)
    auto_added_projects = 0
    if paired:
        try:
            team_projects = list_team_projects(conn, team_name)
            for tp in team_projects:
                git_id = tp.get("git_identity")
                if not git_id:
                    continue
                local = find_project_by_git_identity(conn, git_id)
                if local and local["encoded_name"] != tp["project_encoded_name"]:
                    encoded = local["encoded_name"]
                    upsert_team_project(conn, team_name, encoded, local.get("project_path"), git_identity=git_id)
                    proj_suffix = _compute_proj_suffix(git_id, local.get("project_path"), encoded)
                    members = list_members(conn, team_name)
                    member_device_ids = [m["device_id"] for m in members if m["device_id"]]
                    await _ensure_outbox_folder(proxy, config, encoded, proj_suffix, member_device_ids)
                    auto_added_projects += 1
        except Exception as e:
            logger.warning("Auto-add matching projects failed: %s", e)

    # Auto-accept pending folders from the leader
    accepted = 0
    try:
        from karma.syncthing import SyncthingClient, read_local_api_key

        api_key = config.syncthing.api_key or await run_sync(read_local_api_key)
        st = SyncthingClient(api_key=api_key)
        if st.is_running():
            from karma.main import _accept_pending_folders

            accepted = await run_sync(_accept_pending_folders, st, config, conn)
            if accepted:
                log_event(conn, "pending_accepted", detail={"count": accepted})
    except Exception:
        pass

    return {
        "ok": True,
        "team_name": team_name,
        "team_created": team_created,
        "leader_name": leader_name,
        "paired": paired,
        "folders_created": folders_created,
        "accepted_folders": accepted,
        "auto_added_projects": auto_added_projects,
    }


@router.get("/teams/{team_name}/join-code")
async def sync_team_join_code(team_name: str) -> Any:
    """Get the join code for a team.

    Returns the fixed join code stored at team creation time. All members
    share the same code so any member can invite new people.
    """
    if not ALLOWED_PROJECT_NAME.match(team_name):
        raise HTTPException(400, "Invalid team name")

    config = await run_sync(_load_identity)
    if config is None:
        raise HTTPException(400, "Not initialized")

    conn = _get_sync_conn()
    team = get_team(conn, team_name)
    if team is None:
        raise HTTPException(404, f"Team '{team_name}' not found")

    # Return stored join code if available, otherwise generate one (backwards compat)
    join_code = team.get("join_code")
    if not join_code:
        device_id = config.syncthing.device_id if config.syncthing else None
        if not device_id:
            raise HTTPException(400, "No Syncthing device ID configured")
        join_code = f"{team_name}:{config.user_id}:{device_id}"

    return {"join_code": join_code, "team_name": team_name, "user_id": config.user_id}


@router.get("/pending-devices")
async def sync_pending_devices() -> Any:
    """List Syncthing devices trying to connect that aren't configured.

    Before returning, auto-accepts any pending devices that have karma
    folder offers matching a team project (seamless join handshake).
    """
    conn = _get_sync_conn()

    # Auto-accept pending devices that match karma folder offers (best-effort).
    # Returns remaining pending devices so we don't need to re-fetch.
    auto_accepted = 0
    remaining_pending = None
    try:
        config = await run_sync(_load_identity)
        if config:
            proxy = get_proxy()
            auto_accepted, remaining_pending = await _auto_accept_pending_peers(proxy, config, conn)
    except Exception:
        pass

    # Use remaining from auto-accept if available, otherwise fetch fresh
    if remaining_pending is None:
        proxy = get_proxy()
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
    folders_created = None
    try:
        proxy = get_proxy()
        await run_sync(proxy.add_device, req.device_id, req.name)
        paired = True

        # Auto-create shared folders for all projects in this team
        config = await run_sync(_load_identity)
        if config is not None:
            folders_created = await _auto_share_folders(proxy, config, conn, team_name, req.device_id)
    except Exception as e:
        logger.warning("Syncthing pairing/folder setup failed for %s: %s", req.name, e)

    if folders_created and (folders_created["outboxes"] or folders_created["inboxes"]):
        try:
            log_event(conn, "folders_shared", team_name=team_name, member_name=req.name,
                      detail={"outboxes": folders_created["outboxes"], "inboxes": folders_created["inboxes"]})
        except Exception as e:
            logger.warning("Failed to log folders_shared event: %s", e)

    return {
        "ok": True,
        "name": req.name,
        "device_id": req.device_id,
        "paired": paired,
        "folders_created": folders_created,
    }


@router.delete("/teams/{team_name}/members/{member_name}")
async def sync_remove_member(team_name: str, member_name: str) -> Any:
    """Remove a member — cleans up their Syncthing folders and device."""
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

    # Clean up Syncthing state before removing DB record
    cleanup = {"folders_removed": 0, "devices_updated": 0}
    try:
        config = _load_identity()
        if config:
            proxy = get_proxy()
            cleanup = await _cleanup_syncthing_for_member(
                proxy, config, conn, team_name, device_id, member_name,
            )
    except Exception as e:
        logger.warning("Syncthing cleanup for member %s failed: %s", member_name, e)

    remove_member(conn, team_name, device_id)
    log_event(conn, "member_removed", team_name=team_name, member_name=member_name, detail=cleanup)

    return {"ok": True, "name": member_name, **cleanup}


# ─── Team project management ──────────────────────────────────────────


@router.post("/teams/{team_name}/projects")
async def sync_add_team_project(team_name: str, req: AddTeamProjectRequest) -> Any:
    """Add a project to a sync group."""
    validate_project_name(req.name)
    if not ALLOWED_PROJECT_NAME.match(team_name):
        raise HTTPException(400, "Invalid team name")
    validated_path = validate_project_path(req.path)

    conn = _get_sync_conn()
    if get_team(conn, team_name) is None:
        raise HTTPException(404, f"Team '{team_name}' not found")

    from karma.sync import encode_project_path, detect_git_identity

    encoded = encode_project_path(validated_path) if validated_path else req.name
    git_identity = detect_git_identity(validated_path) if validated_path else None

    # Ensure project exists in projects table (for FK), include git_identity
    conn.execute(
        "INSERT OR IGNORE INTO projects (encoded_name, project_path, git_identity) VALUES (?, ?, ?)",
        (encoded, validated_path, git_identity),
    )
    if git_identity:
        conn.execute(
            "UPDATE projects SET git_identity = ? WHERE encoded_name = ? AND git_identity IS NULL",
            (git_identity, encoded),
        )
    conn.commit()

    add_team_project(conn, team_name, encoded, validated_path, git_identity=git_identity)
    log_event(conn, "project_added", team_name=team_name, project_encoded_name=encoded)

    # Create Syncthing folders: outbox (my sessions → teammates) + inboxes (their sessions → me)
    syncthing_ok = False
    folders_created = {"outboxes": 0, "inboxes": 0, "errors": []}
    try:
        config = await run_sync(_load_identity)
        if config is not None:
            proj_suffix = _compute_proj_suffix(git_identity, validated_path, encoded)
            members = list_members(conn, team_name)
            device_ids = [m["device_id"] for m in members if m["device_id"]]

            proxy = get_proxy()
            await _ensure_outbox_folder(proxy, config, encoded, proj_suffix, device_ids)
            folders_created["outboxes"] = 1

            # Create inbox folders for each existing member's outbox
            inbox_result = await _ensure_inbox_folders(
                proxy, config, members, encoded, proj_suffix,
            )
            folders_created["inboxes"] = inbox_result["inboxes"]
            folders_created["errors"] = inbox_result["errors"]

            syncthing_ok = True
    except Exception as e:
        logger.warning("Failed to create Syncthing folder for project %s: %s", encoded, e)

    return {
        "ok": True,
        "name": req.name,
        "encoded_name": encoded,
        "git_identity": git_identity,
        "syncthing_folder_created": syncthing_ok,
        "folders_created": folders_created,
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

    # Clean up Syncthing folders (outbox + inboxes) before removing DB row
    folders_removed = 0
    try:
        proj = next(p for p in projects if p["project_encoded_name"] == project_name)
        git_identity = proj.get("git_identity")
        proj_suffix = _compute_proj_suffix(git_identity, proj.get("path"), project_name)
        config = await run_sync(_load_identity)
        if config is not None:
            proxy = get_proxy()
            # Remove outbox folder
            outbox_id = f"karma-out-{config.user_id}-{proj_suffix}"
            try:
                await run_sync(proxy.remove_folder, outbox_id)
                folders_removed += 1
            except Exception as e:
                logger.debug("Failed to remove outbox folder %s: %s", outbox_id, e)
            # Remove inbox folders for each member
            members = list_members(conn, team_name)
            for m in members:
                if m["device_id"] == config.syncthing.device_id:
                    continue
                inbox_id = f"karma-out-{m['name']}-{proj_suffix}"
                try:
                    await run_sync(proxy.remove_folder, inbox_id)
                    folders_removed += 1
                except Exception as e:
                    logger.debug("Failed to remove inbox folder %s: %s", inbox_id, e)
    except Exception as e:
        logger.warning("Syncthing cleanup for project %s failed: %s", project_name, e)

    remove_team_project(conn, team_name, project_name)
    log_event(conn, "project_removed", team_name=team_name, project_encoded_name=project_name)

    return {"ok": True, "name": project_name, "folders_removed": folders_removed}


# ─── On-demand sync ────────────────────────────────────────────────────


@router.post("/teams/{team_name}/sync-now")
async def sync_team_sync_now(team_name: str) -> Any:
    """Trigger an immediate session package for all projects in a team."""
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
    from karma.packager import SessionPackager
    from karma.worktree_discovery import find_all_worktree_dirs

    projects = list_team_projects(conn, team_name)
    projects_dir = Path.home() / ".claude" / "projects"

    packaged_count = 0
    errors = []

    for proj in projects:
        encoded = proj["project_encoded_name"]
        proj_path = proj.get("path") or ""
        claude_dir = projects_dir / encoded

        if not claude_dir.is_dir():
            continue

        outbox = KARMA_BASE / "remote-sessions" / config.user_id / encoded
        outbox.mkdir(parents=True, exist_ok=True)

        try:
            wt_dirs = find_all_worktree_dirs(encoded, proj_path, projects_dir)
            packager = SessionPackager(
                project_dir=claude_dir,
                user_id=config.user_id,
                machine_id=config.machine_id,
                project_path=proj_path,
                extra_dirs=wt_dirs,
                team_name=team_name,
            )
            manifest = await run_sync(packager.package, outbox)
            packaged_count += manifest.session_count
        except Exception as e:
            logger.warning("sync-now: failed to package %s: %s", encoded, e)
            errors.append(f"{encoded}: {e}")

    log_event(
        conn, "sync_now", team_name=team_name,
        detail={"packaged_count": packaged_count, "errors": errors},
    )

    return {
        "ok": True,
        "team_name": team_name,
        "packaged_count": packaged_count,
        "project_count": len(projects),
        "errors": errors,
    }


# ─── Watcher manager endpoints ────────────────────────────────────────


@router.get("/watch/status")
async def sync_watch_status() -> Any:
    """Get watcher status."""
    return get_watcher().status()


@router.post("/watch/start")
async def sync_watch_start(team_name: str | None = None) -> Any:
    """Start the session watcher for a team (or all teams if none specified)."""
    config = await run_sync(_load_identity)
    if config is None:
        raise HTTPException(400, "Not initialized")

    conn = _get_sync_conn()
    teams_data = list_teams(conn)

    watcher = get_watcher()
    if watcher.is_running:
        raise HTTPException(409, "Watcher already running. Stop it first.")

    syncthing_teams = [t for t in teams_data if t["backend"] == "syncthing"]
    if not syncthing_teams:
        raise HTTPException(400, "No syncthing teams configured")

    if team_name is not None:
        # Single-team mode: validate the specified team
        team = get_team(conn, team_name)
        if team is None:
            raise HTTPException(404, f"Team '{team_name}' not found")
        target_teams = [team]
    else:
        # Multi-team mode: aggregate all syncthing teams
        target_teams = syncthing_teams

    # Build config_data dict with all target teams' projects (deduped by encoded_name)
    teams_config = {}
    seen_projects = set()
    for t in target_teams:
        t_name = t["name"]
        projects = list_team_projects(conn, t_name)
        team_projects = {}
        for p in projects:
            enc = p["project_encoded_name"]
            if enc not in seen_projects:
                team_projects[enc] = {
                    "encoded_name": enc,
                    "path": p["path"] or "",
                }
                seen_projects.add(enc)
        teams_config[t_name] = {
            "backend": t["backend"],
            "projects": team_projects,
        }

    config_data = {
        "user_id": config.user_id,
        "machine_id": config.machine_id,
        "teams": teams_config,
    }

    try:
        result = await run_sync(watcher.start_all, config_data)
        for t in target_teams:
            log_event(conn, "watcher_started", team_name=t["name"])
        return result
    except Exception as e:
        logger.exception("Failed to start watcher: %s", e)
        raise HTTPException(500, "Failed to start watcher")


@router.post("/watch/stop")
async def sync_watch_stop() -> Any:
    """Stop the session watcher."""
    watcher = get_watcher()
    if not watcher.is_running:
        return watcher.status()
    teams = list(watcher.status().get("teams", []))
    result = await run_sync(watcher.stop)
    if teams:
        try:
            conn = _get_sync_conn()
            for team in teams:
                log_event(conn, "watcher_stopped", team_name=team)
        except Exception:
            pass
    return result


# ─── Pending folders ──────────────────────────────────────────────────


@router.get("/pending")
async def sync_pending() -> Any:
    """List pending folder offers from known team members.

    Enriches each entry with ``label`` (human-readable project name) and
    ``folder_type`` (handshake | sessions | unknown) so the frontend can
    display meaningful info instead of raw folder IDs.
    """
    conn = _get_sync_conn()
    known = get_known_devices(conn)

    if not known:
        return {"pending": []}

    proxy = get_proxy()
    try:
        pending = await run_sync(proxy.get_pending_folders_for_ui, known)
    except SyncthingNotRunning:
        return {"pending": []}

    # Pre-fetch team projects for label enrichment (avoids N+1)
    team_names = {item["from_team"] for item in pending if item.get("from_team")}
    team_projects_map: dict[str, list] = {}
    for tn in team_names:
        try:
            team_projects_map[tn] = list_team_projects(conn, tn)
        except Exception:
            team_projects_map[tn] = []

    for item in pending:
        folder_id = item["folder_id"]

        if folder_id.startswith("karma-join-"):
            item["label"] = "Team handshake"
            item["folder_type"] = "handshake"
        elif folder_id.startswith("karma-out-"):
            item["folder_type"] = "sessions"
            parsed = _parse_folder_id(folder_id)
            if parsed:
                _, suffix = parsed
                # Try to find a matching project for a friendly label
                projects = team_projects_map.get(item.get("from_team", ""), [])
                project_label = None
                for proj in projects:
                    proj_suffix = _compute_proj_suffix(
                        proj.get("git_identity"), proj.get("path"), proj["project_encoded_name"]
                    )
                    if proj_suffix == suffix:
                        git_id = proj.get("git_identity")
                        # "jayantdevkar/claude-code-karma" → "claude-code-karma"
                        project_label = git_id.split("/")[-1] if git_id else proj["project_encoded_name"]
                        break
                item["label"] = project_label or suffix
            else:
                item["label"] = folder_id
        else:
            item["label"] = folder_id
            item["folder_type"] = "unknown"

    return {"pending": pending}


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

        conn = _get_sync_conn()
        accepted = await run_sync(_accept_pending_folders, st, config, conn)
        if accepted:
            log_event(conn, "pending_accepted", detail={"count": accepted})
        return {"ok": True, "accepted": accepted}
    except SyncthingNotRunning:
        raise HTTPException(503, "Syncthing is not running")
    except Exception as e:
        logger.exception("Failed to accept pending folders: %s", e)
        raise HTTPException(500, "Failed to accept pending folders")


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
    from karma.worktree_discovery import find_all_worktree_dirs

    projects = list_team_projects(conn, team_name)
    members = list_members(conn, team_name)
    projects_dir = Path.home() / ".claude" / "projects"
    result = []

    for proj in projects:
        encoded = proj["project_encoded_name"]
        proj_path = proj.get("path") or ""
        claude_dir = projects_dir / encoded

        local_count = 0
        if claude_dir.is_dir():
            local_count = sum(
                1
                for f in claude_dir.glob("*.jsonl")
                if not f.name.startswith("agent-") and f.stat().st_size > 0
            )
        wt_dirs = find_all_worktree_dirs(encoded, proj_path, projects_dir)
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
    # Cap limit and offset to prevent abuse
    limit = max(1, min(limit, 200))
    offset = max(0, min(offset, 10000))

    # Validate team_name if provided
    if team_name and not ALLOWED_PROJECT_NAME.match(team_name):
        team_name = None

    # Allowlist of valid event types — ignore invalid ones
    if event_type and event_type not in _VALID_EVENT_TYPES:
        event_type = None

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

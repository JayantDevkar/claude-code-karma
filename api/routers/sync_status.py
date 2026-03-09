"""Sync status API endpoints — backed by SQLite."""

import logging
import re
import sqlite3
import sys
import threading
import time
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
    find_project_by_git_suffix,
    update_team_session_limit,
)
from schemas import (
    AcceptPendingDeviceRequest,
    AddDeviceRequest,
    AddMemberRequest,
    AddTeamProjectRequest,
    CreateTeamRequest,
    InitRequest,
    JoinTeamRequest,
    ResetOptions,
    UpdateTeamSettingsRequest,
)
from services.syncthing_proxy import SyncthingNotRunning, SyncthingProxy, run_sync
from services.watcher_manager import WatcherManager

# Add CLI to path once for SyncConfig / syncthing imports
_CLI_PATH = Path(__file__).parent.parent.parent / "cli"
if str(_CLI_PATH) not in sys.path:
    sys.path.insert(0, str(_CLI_PATH))

router = APIRouter(prefix="/sync", tags=["sync"])


async def _trigger_remote_reindex_bg() -> None:
    """Trigger remote session reindex in background thread.

    Called after sync actions (folder/device acceptance, project sharing,
    member addition) so newly arrived remote sessions appear immediately
    in the dashboard instead of waiting for the 5-minute periodic cycle.
    """
    import asyncio

    from db.indexer import trigger_remote_reindex

    try:
        await asyncio.to_thread(trigger_remote_reindex)
    except Exception as e:
        logger.debug("Background remote reindex failed: %s", e)


# Input validation
ALLOWED_PROJECT_NAME = re.compile(r"^[a-zA-Z0-9_\-]+$")
ALLOWED_MEMBER_NAME = re.compile(r"^[a-zA-Z0-9_\-\.]+$")  # hostnames have dots
ALLOWED_DEVICE_ID = re.compile(r"^[A-Z0-9\-]+$")
_VALID_EVENT_TYPES = frozenset({
    "team_created", "team_deleted", "team_left",
    "member_added", "member_removed", "member_auto_accepted",
    "member_joined", "project_shared",
    "project_added", "project_removed",
    "folders_shared", "pending_accepted",
    "sync_now", "watcher_started", "watcher_stopped",
    "session_packaged", "session_received",
    "file_rejected", "sync_paused",
    "settings_changed",
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
    if not ALLOWED_MEMBER_NAME.match(user_id) or len(user_id) > 128:
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
    home = Path.home().resolve()
    try:
        resolved.relative_to(home)
    except ValueError:
        raise HTTPException(400, "Invalid project path: must be under home directory")
    return str(resolved)


# Singleton proxy
_proxy: SyncthingProxy | None = None
_singleton_lock = threading.Lock()


def get_proxy() -> SyncthingProxy:
    global _proxy
    with _singleton_lock:
        if _proxy is None:
            _proxy = SyncthingProxy()
        return _proxy


# Singleton watcher manager
_watcher: WatcherManager | None = None


def get_watcher() -> WatcherManager:
    global _watcher
    with _singleton_lock:
        if _watcher is None:
            _watcher = WatcherManager()
        return _watcher


def _get_sync_conn() -> sqlite3.Connection:
    """Get writer connection for sync operations."""
    return get_writer_db()


# TTL cache for _load_identity
_identity_cache = None
_identity_cache_time: float = 0.0
_IDENTITY_TTL = 5  # seconds


def _invalidate_identity_cache():
    """Clear the identity cache (useful for tests)."""
    global _identity_cache, _identity_cache_time
    _identity_cache = None
    _identity_cache_time = 0.0


def _load_identity():
    """Load identity-only SyncConfig from JSON. Returns config or None (TTL-cached)."""
    global _identity_cache, _identity_cache_time
    from karma.config import SyncConfig

    now = time.monotonic()
    if _identity_cache is not None and (now - _identity_cache_time) < _IDENTITY_TTL:
        return _identity_cache

    try:
        result = SyncConfig.load()
    except RuntimeError:
        result = None

    # Only cache successful loads — don't cache None so "not initialized" is always fresh
    if result is not None:
        _identity_cache = result
        _identity_cache_time = now
    else:
        _identity_cache = None
        _identity_cache_time = 0.0
    return result


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


def _friendly_project_label(conn, folder_id: str, parsed_suffix: str) -> str:
    """Extract a human-readable project label from a folder ID.

    The folder ID is ``karma-out-{user_id}-{git_org}-{repo}``. Since user_id
    can contain hyphens, we can't reliably split it. Instead we match known
    git identities against the folder ID tail.

    Tries these strategies in order:
    1. Match git_identity from projects DB against the folder ID (most reliable)
    2. Match encoded_name from projects DB against the folder ID
    3. Fallback: last component of the suffix

    Example: folder_id "karma-out-my-mac-mini-jayantdevkar-claude-code-karma"
             git_identity "jayantdevkar/claude-code-karma"
             → label "claude-code-karma"
    """
    rest = folder_id[len("karma-out-"):] if folder_id.startswith("karma-out-") else parsed_suffix

    # Strategy 1: Find a git_identity whose normalized form appears in the folder ID
    try:
        rows = conn.execute(
            "SELECT git_identity FROM projects WHERE git_identity IS NOT NULL"
        ).fetchall()
        for row in rows:
            git_id = row[0] if isinstance(row, (tuple, list)) else row["git_identity"]
            if not git_id:
                continue
            normalized = git_id.replace("/", "-")
            if rest.endswith(normalized):
                return git_id.split("/")[-1]  # "claude-code-karma"
    except Exception as e:
        logger.debug("Folder label strategy 1 (git_identity) failed: %s", e)

    # Strategy 2: Find an encoded_name that the folder ID ends with
    try:
        rows = conn.execute("SELECT encoded_name FROM projects").fetchall()
        for row in rows:
            enc = row[0] if isinstance(row, (tuple, list)) else row["encoded_name"]
            if rest.endswith(enc):
                return enc
    except Exception as e:
        logger.debug("Folder label strategy 2 (encoded_name) failed: %s", e)

    # Strategy 3: Fallback — return the suffix as-is
    return parsed_suffix


def _parse_folder_id_with_hints(folder_id: str, known_user_ids: set[str]):
    """Parse a karma folder ID using known user IDs for accurate splitting.

    The ambiguity in ``karma-out-{user}-{suffix}`` is that both user and
    suffix can contain hyphens. By checking against known user IDs, we can
    split correctly.

    Falls back to _parse_folder_id() if no known user matches.
    """
    prefix = "karma-out-"
    if not folder_id.startswith(prefix):
        return None
    rest = folder_id[len(prefix):]

    # Try known user IDs (longest first to match most specific)
    for uid in sorted(known_user_ids, key=len, reverse=True):
        if rest.startswith(uid + "-"):
            suffix = rest[len(uid) + 1:]
            if suffix:
                return uid, suffix

    # Fallback to greedy parse
    return _parse_folder_id(folder_id)


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
    """Auto-accept pending devices that offer karma-* folders.

    Only accepts devices when we can verify their identity via folder
    matching — the device must offer a karma-join-* handshake folder or
    karma-out-* session folder that matches a known team.

    This ensures usernames are always correct (extracted from the real
    karma user_id in the folder ID, never derived from hostnames).

    Returns:
        (accepted_count, remaining_pending_devices)
    """
    try:
        pending_devices = await run_sync(proxy.get_pending_devices)
    except Exception as e:
        logger.debug("Failed to fetch pending devices: %s", e)
        pending_devices = {}

    accepted = 0
    accepted_ids = set()

    if pending_devices:
        try:
            pending_folders = await run_sync(proxy.get_pending_folders)
        except Exception as e:
            logger.debug("Failed to fetch pending folders: %s", e)
            pending_folders = {}

        for device_id in list(pending_devices.keys()):
            device_info = pending_devices.get(device_id, {})
            device_name = device_info.get("name", "")

            # Collect karma-* folders offered by this device
            karma_folders = []
            for folder_id, info in pending_folders.items():
                if not folder_id.startswith("karma-"):
                    continue
                if device_id in info.get("offeredBy", {}):
                    karma_folders.append(folder_id)

            if not karma_folders:
                # No karma folders offered — cannot verify identity.
                # Device stays pending until handshake folder arrives.
                continue

            # Extract username from folder IDs (prefer handshake folders)
            username = None
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

            if not team_name or not username:
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

    # 6. Stop brew service FIRST to deregister launchd plist (prevents respawn),
    #    then kill any remaining Syncthing processes.
    import subprocess
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
    global _proxy
    _proxy = None

    try:
        from services.remote_sessions import invalidate_caches
        invalidate_caches()
        steps["caches_invalidated"] = True
    except Exception as e:
        logger.debug("Cache invalidation failed: %s", e)
        steps["caches_invalidated"] = False

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
    except Exception as e:
        logger.debug("Remove handshake folder %s no-op: %s", handshake_id, e)

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
        config = await run_sync(_load_identity)
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
    except Exception as e:
        logger.warning("Failed to pair device %s in Syncthing: %s", device_id, e)

    # Create handshake folder so the leader can auto-accept us (works even without projects)
    if paired:
        try:
            await _ensure_handshake_folder(proxy, config, team_name, [device_id])
        except Exception as e:
            logger.warning("Failed to create handshake folder: %s", e)

    # Find local projects matching team's shared projects (suggestions, NOT auto-shared)
    matching_projects = []
    try:
        team_projects = list_team_projects(conn, team_name)
        for tp in team_projects:
            git_id = tp.get("git_identity")
            if not git_id:
                continue
            local = find_project_by_git_identity(conn, git_id)
            if local:
                from db.sync_queries import count_sessions_for_project
                session_count = count_sessions_for_project(conn, local["encoded_name"])
                matching_projects.append({
                    "encoded_name": local["encoded_name"],
                    "path": local.get("project_path", ""),
                    "git_identity": git_id,
                    "session_count": session_count,
                })
    except Exception as e:
        logger.warning("Failed to find matching projects: %s", e)

    log_event(conn, "member_joined", team_name=team_name,
              member_name=config.user_id, detail={"via": "join_code", "leader": leader_name})

    return {
        "ok": True,
        "team_name": team_name,
        "team_created": team_created,
        "leader_name": leader_name,
        "paired": paired,
        "matching_projects": matching_projects,
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

    Auto-accepts pending devices (handshake completion) but does NOT
    auto-accept pending folders — those require explicit user action.
    """
    conn = _get_sync_conn()

    # Phase 1 only: auto-accept pending devices (handshake completion).
    # Folder acceptance is now explicit — handled by POST /pending/accept/{folder_id}.
    auto_accepted = 0
    remaining_pending = None
    try:
        config = await run_sync(_load_identity)
        if config:
            proxy = get_proxy()
            auto_accepted, remaining_pending = await _auto_accept_pending_peers(proxy, config, conn)
    except Exception as e:
        logger.debug("Auto-accept pending peers failed: %s", e)

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

    conn = _get_sync_conn()
    team = get_team(conn, team_name)
    if team is None:
        raise HTTPException(404, f"Team '{team_name}' not found")

    proxy = get_proxy()

    # Verify this device is actually pending in Syncthing
    try:
        pending = await run_sync(proxy.get_pending_devices)
    except SyncthingNotRunning:
        raise HTTPException(503, "Syncthing is not running")

    if device_id not in pending:
        raise HTTPException(404, "Device is not in the pending list")

    device_info = pending[device_id]
    member_name = req.member_name or device_info.get("name", "unknown")

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
    config = await run_sync(_load_identity)
    if config:
        try:
            await _ensure_handshake_folder(proxy, config, team_name, [device_id])
        except Exception as e:
            logger.warning("Failed to create handshake folder for accepted device: %s", e)

        # 4. Share existing project folders with the new member
        try:
            await _auto_share_folders(proxy, config, conn, team_name, device_id)
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
    proxy = get_proxy()
    try:
        await run_sync(proxy.dismiss_pending_device, device_id)
    except SyncthingNotRunning:
        raise HTTPException(503, "Syncthing is not running")
    except Exception as e:
        raise HTTPException(500, f"Failed to dismiss device: {e}")
    return {"ok": True, "device_id": device_id}


# ─── Team member management ───────────────────────────────────────────


@router.post("/teams/{team_name}/members")
async def sync_add_member(team_name: str, req: AddMemberRequest) -> Any:
    """Add a member to a sync group."""
    if not ALLOWED_PROJECT_NAME.match(team_name):
        raise HTTPException(400, "Invalid team name")
    if not ALLOWED_MEMBER_NAME.match(req.name) or len(req.name) > 64:
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

    # Reindex remote sessions so any already-synced files appear immediately
    await _trigger_remote_reindex_bg()

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
    if not ALLOWED_MEMBER_NAME.match(member_name):
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
        config = await run_sync(_load_identity)
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

    # Count sessions for activity detail
    from db.sync_queries import count_sessions_for_project
    session_count = count_sessions_for_project(conn, encoded)

    config = await run_sync(_load_identity)
    member_name = config.user_id if config else None
    log_event(conn, "project_shared", team_name=team_name, member_name=member_name,
              project_encoded_name=encoded, detail={"session_count": session_count})

    # Create Syncthing folders: outbox (my sessions → teammates) + inboxes (their sessions → me)
    syncthing_ok = False
    folders_created = {"outboxes": 0, "inboxes": 0, "errors": []}
    try:
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

    # Reindex remote sessions so any already-synced files appear immediately
    await _trigger_remote_reindex_bg()

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
            # Try to resolve suffix-based record to the correct local project
            local = find_project_by_git_suffix(conn, encoded)
            if local:
                resolved_encoded = local["encoded_name"]
                resolved_path = local.get("project_path") or ""
                resolved_dir = projects_dir / resolved_encoded
                if resolved_dir.is_dir():
                    old_suffix = encoded
                    # Fix the DB record
                    upsert_team_project(
                        conn, team_name, resolved_encoded, resolved_path,
                        git_identity=local.get("git_identity"),
                    )
                    try:
                        remove_team_project(conn, team_name, old_suffix)
                    except Exception as e:
                        logger.debug("Failed to remove stale team project entry %s: %s", old_suffix, e)
                    encoded = resolved_encoded
                    proj_path = resolved_path
                    claude_dir = resolved_dir
                    logger.info("sync-now: resolved '%s' -> '%s'", proj["project_encoded_name"], encoded)

                    # Fix Syncthing outbox folder: it may still point to the
                    # old suffix-based dir. Remove it and recreate with the
                    # correct encoded path via _ensure_outbox_folder.
                    try:
                        proxy = get_proxy()
                        git_id = local.get("git_identity")
                        proj_suffix = _compute_proj_suffix(git_id, resolved_path, resolved_encoded)
                        outbox_id = f"karma-out-{config.user_id}-{proj_suffix}"
                        # Remove the potentially-wrong folder so _ensure_outbox_folder
                        # recreates it with the correct path
                        try:
                            await run_sync(proxy.remove_folder, outbox_id)
                        except Exception as e:
                            logger.debug("Remove old outbox folder %s no-op: %s", outbox_id, e)
                        members = list_members(conn, team_name)
                        all_device_ids = [
                            m["device_id"] for m in members
                            if m["device_id"] and m["device_id"] != (config.syncthing.device_id if config.syncthing else None)
                        ]
                        await _ensure_outbox_folder(proxy, config, resolved_encoded, proj_suffix, all_device_ids)
                        logger.info("sync-now: recreated outbox folder '%s' with correct path", outbox_id)
                    except Exception as e:
                        logger.warning("sync-now: could not fix outbox folder path: %s", e)
                else:
                    continue
            else:
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
async def sync_watch_start(team_name: Optional[str] = None) -> Any:
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
        except Exception as e:
            logger.debug("Failed to log watcher_stopped events: %s", e)
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

    # Load identity to filter out own outbox folders
    config = await run_sync(_load_identity)
    own_user_id = config.user_id if config else None
    own_machine_id = config.machine_id if config else None

    # Build set of names that identify THIS machine (user_id, machine_id, etc.)
    # The remote leader may have used any of these when creating our outbox folder.
    own_names = set()
    if own_user_id:
        own_names.add(own_user_id)
    if own_machine_id:
        own_names.add(own_machine_id)

    # Collect all known user_ids for smarter folder ID parsing
    all_user_ids = set()
    if own_user_id:
        all_user_ids.add(own_user_id)
    if own_machine_id:
        all_user_ids.add(own_machine_id)
    for device_id, (member_name, _team) in known.items():
        all_user_ids.add(member_name)
    # Also add member names from DB
    for tn in {item.get("from_team") for item in pending if item.get("from_team")}:
        for m in list_members(conn, tn):
            all_user_ids.add(m["name"])

    def _is_own_outbox(folder_id: str) -> bool:
        """Check if folder is our own outbox (leader may have used user_id OR machine_id)."""
        for name in own_names:
            if folder_id.startswith(f"karma-out-{name}-"):
                return True
        return False

    # Separate own outbox folders from other people's outboxes.
    # Own outbox = leader created a receiveonly folder for us, we accept as sendonly.
    # Other outbox = leader's sendonly outbox, we accept as receiveonly.
    filtered = []
    own_outbox_pending = []
    for item in pending:
        folder_id = item["folder_id"]
        # Skip handshake folders — handled automatically
        if folder_id.startswith("karma-join-"):
            continue
        if _is_own_outbox(folder_id):
            own_outbox_pending.append(item)
        else:
            filtered.append(item)
    pending = own_outbox_pending + filtered

    # Pre-fetch team projects for label enrichment (avoids N+1)
    team_names = {item["from_team"] for item in pending if item.get("from_team")}
    team_projects_map: dict[str, list] = {}
    for tn in team_names:
        try:
            team_projects_map[tn] = list_team_projects(conn, tn)
        except Exception as e:
            logger.debug("Failed to fetch team projects for %s: %s", tn, e)
            team_projects_map[tn] = []

    for item in pending:
        folder_id = item["folder_id"]
        member = item.get("from_member", "unknown")

        if folder_id.startswith("karma-out-"):
            is_own = _is_own_outbox(folder_id)
            item["folder_type"] = "outbox" if is_own else "sessions"
            parsed = _parse_folder_id_with_hints(folder_id, all_user_ids)
            if parsed:
                owner, suffix = parsed
                # Try to find a matching project for a friendly label
                projects = team_projects_map.get(item.get("from_team", ""), [])
                project_label = None
                for proj in projects:
                    proj_suffix = _compute_proj_suffix(
                        proj.get("git_identity"), proj.get("path"), proj["project_encoded_name"]
                    )
                    if proj_suffix == suffix:
                        git_id = proj.get("git_identity")
                        project_label = git_id.split("/")[-1] if git_id else proj["project_encoded_name"]
                        break
                # Fallback: try to extract a readable project name from the suffix.
                # Suffix is typically "{github-org}-{repo-name}" e.g. "jayantdevkar-claude-code-karma".
                # Try git_identity lookup in DB, or split on the first dash as org/repo.
                if not project_label:
                    project_label = _friendly_project_label(conn, folder_id, suffix)
                label = project_label
                item["label"] = label
                if is_own:
                    item["description"] = f"Send your sessions for {label}"
                else:
                    item["description"] = f"Receive sessions from {member} for {label}"
            else:
                item["label"] = folder_id
                if is_own:
                    item["description"] = "Send your sessions"
                else:
                    item["description"] = f"Receive sessions from {member}"
        else:
            item["label"] = folder_id
            item["folder_type"] = "unknown"
            item["description"] = folder_id

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
            log_event(conn, "pending_accepted", member_name=config.user_id,
                      detail={"count": accepted, "phase": "manual"})

        # Reindex remote sessions so any already-synced files appear immediately
        await _trigger_remote_reindex_bg()

        return {"ok": True, "accepted": accepted}
    except SyncthingNotRunning:
        raise HTTPException(503, "Syncthing is not running")
    except Exception as e:
        logger.exception("Failed to accept pending folders: %s", e)
        raise HTTPException(500, "Failed to accept pending folders")


@router.post("/pending/accept/{folder_id:path}")
async def sync_accept_single_folder(folder_id: str) -> Any:
    """Accept a single pending folder offer.

    Only accepts karma-out-* folders from known team members.
    This is the explicit per-folder acceptance that replaces auto-accept.
    """
    if not folder_id.startswith("karma-"):
        raise HTTPException(400, "Invalid folder ID: must start with 'karma-'")

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
        accepted = await run_sync(
            _accept_pending_folders, st, config, conn, only_folder_id=folder_id,
        )
        if accepted:
            log_event(conn, "pending_accepted", member_name=config.user_id,
                      detail={"folder_id": folder_id, "phase": "individual"})

        # Reindex remote sessions so any already-synced files appear immediately
        await _trigger_remote_reindex_bg()

        return {"ok": True, "accepted": accepted, "folder_id": folder_id}
    except SyncthingNotRunning:
        raise HTTPException(503, "Syncthing is not running")
    except Exception as e:
        logger.exception("Failed to accept folder %s: %s", folder_id, e)
        raise HTTPException(500, f"Failed to accept folder: {e}")


@router.post("/pending/reject/{folder_id:path}")
async def sync_reject_single_folder(folder_id: str) -> Any:
    """Reject (dismiss) a single pending folder offer.

    Removes the pending folder offer from Syncthing so it no longer appears.
    Only dismisses karma-* folders from known team members.
    """
    if not folder_id.startswith("karma-"):
        raise HTTPException(400, "Invalid folder ID: must start with 'karma-'")

    config = await run_sync(_load_identity)
    if config is None:
        raise HTTPException(400, "Not initialized")

    try:
        from karma.syncthing import SyncthingClient, read_local_api_key

        api_key = config.syncthing.api_key or await run_sync(read_local_api_key)
        st = SyncthingClient(api_key=api_key)
        if not st.is_running():
            raise HTTPException(503, "Syncthing is not running")

        pending = st.get_pending_folders()
        folder_info = pending.get(folder_id)
        if not folder_info:
            raise HTTPException(404, f"Folder '{folder_id}' not found in pending offers")

        dismissed = 0
        for device_id in folder_info.get("offeredBy", {}):
            try:
                st.dismiss_pending_folder(folder_id, device_id)
                dismissed += 1
            except Exception as e:
                logger.debug("Failed to dismiss pending folder %s for device %s: %s", folder_id, device_id, e)

        conn = _get_sync_conn()
        log_event(conn, "pending_rejected", member_name=config.user_id,
                  detail={"folder_id": folder_id, "dismissed": dismissed})

        return {"ok": True, "folder_id": folder_id, "dismissed": dismissed}
    except SyncthingNotRunning:
        raise HTTPException(503, "Syncthing is not running")
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Failed to reject folder %s: %s", folder_id, e)
        raise HTTPException(500, f"Failed to reject folder: {e}")


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
            # Skip own outbox — only count genuinely received sessions
            if mname == config.user_id:
                continue
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
    team_name: Optional[str] = None,
    event_type: Optional[str] = None,
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
    except Exception as e:
        logger.debug("Failed to fetch bandwidth stats: %s", e)

    return {
        "events": events,
        "upload_rate": bandwidth.get("upload_rate", 0),
        "download_rate": bandwidth.get("download_rate", 0),
        "upload_total": bandwidth.get("upload_total", 0),
        "download_total": bandwidth.get("download_total", 0),
    }


@router.get("/teams/{team_name}/activity")
async def sync_team_activity(
    team_name: str,
    event_type: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
) -> Any:
    """Team-scoped activity feed for the team detail page."""
    if not ALLOWED_PROJECT_NAME.match(team_name):
        raise HTTPException(400, "Invalid team name")

    limit = max(1, min(limit, 200))
    offset = max(0, min(offset, 10000))

    if event_type and event_type not in _VALID_EVENT_TYPES:
        event_type = None

    conn = _get_sync_conn()
    if not conn.execute("SELECT 1 FROM sync_teams WHERE name = ?", (team_name,)).fetchone():
        raise HTTPException(404, f"Team '{team_name}' not found")

    events = query_events(
        conn, team_name=team_name, event_type=event_type,
        limit=limit, offset=offset,
    )
    return {"events": events}


_VALID_SESSION_LIMITS = frozenset({"all", "recent_100", "recent_10"})


@router.patch("/teams/{team_name}/settings")
async def sync_update_team_settings(team_name: str, req: UpdateTeamSettingsRequest) -> Any:
    """Update team sync settings (session limit)."""
    if not ALLOWED_PROJECT_NAME.match(team_name):
        raise HTTPException(400, "Invalid team name")

    if req.sync_session_limit not in _VALID_SESSION_LIMITS:
        raise HTTPException(400, f"Invalid session limit. Must be one of: {', '.join(sorted(_VALID_SESSION_LIMITS))}")

    conn = _get_sync_conn()
    team = get_team(conn, team_name)
    if team is None:
        raise HTTPException(404, f"Team '{team_name}' not found")

    old_limit = team.get("sync_session_limit", "all")
    update_team_session_limit(conn, team_name, req.sync_session_limit)

    config = await run_sync(_load_identity)
    member_name = config.user_id if config else None
    log_event(conn, "settings_changed", team_name=team_name, member_name=member_name,
              detail={"sync_session_limit": req.sync_session_limit, "previous": old_limit})

    return {
        "ok": True,
        "team_name": team_name,
        "sync_session_limit": req.sync_session_limit,
    }

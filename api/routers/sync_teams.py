"""Team management endpoints extracted from sync_status.py."""

import logging
from typing import Any, Optional

from fastapi import APIRouter, HTTPException

from db.sync_queries import (
    create_team, delete_team, list_teams, get_team,
    list_members, list_team_projects,
    upsert_member, log_event, clear_member_removal,
    find_project_by_git_identity, count_sessions_for_project,
    update_team_session_limit,
    get_effective_setting, set_setting,
    VALID_SYNC_DIRECTIONS, VALID_SETTING_KEYS,
    VALID_SESSION_LIMITS,
)
from services.folder_id import parse_member_tag
from schemas import CreateTeamRequest, JoinTeamRequest, UpdateTeamSettingsRequest
import services.sync_identity as _sid
from services.sync_identity import (
    validate_user_id, validate_device_id,
    ALLOWED_PROJECT_NAME, _compute_proj_suffix,
)
from services.sync_folders import ensure_handshake_folder, ensure_metadata_folder, cleanup_syncthing_for_team
from services.syncthing_proxy import run_sync

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/sync", tags=["sync"])


def _get_device_status_map() -> dict[str, dict]:
    """Fetch Syncthing device connection status, keyed by device_id.

    Returns {device_id: {"connected": bool, "in_bytes_total": int, "out_bytes_total": int}}.
    Falls back to empty dict if Syncthing is unreachable.
    """
    try:
        proxy = _sid.get_proxy()
        devices = proxy.get_devices()
        return {d["device_id"]: d for d in devices}
    except Exception:
        return {}


def _enrich_member(member: dict, device_status: dict[str, dict]) -> dict:
    """Build a member response dict with live connection data from Syncthing."""
    device_id = member.get("device_id") or ""
    device = device_status.get(device_id, {})
    return {
        "name": member["name"],
        "device_id": device_id,
        "connected": device.get("connected", False),
        "in_bytes_total": device.get("in_bytes_total", 0),
        "out_bytes_total": device.get("out_bytes_total", 0),
    }


@router.get("/teams")
async def sync_teams_list():
    """List all teams with their backend, members, and projects."""
    conn = _sid._get_sync_conn()
    teams_data = list_teams(conn)

    # Fetch live device connection status from Syncthing (best-effort)
    device_status = _get_device_status_map()

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
                _enrich_member(m, device_status)
                for m in members_data
            ],
        })

    return {"teams": teams}


@router.post("/teams")
async def sync_create_team(req: CreateTeamRequest) -> Any:
    """Create a new sync group."""
    if not ALLOWED_PROJECT_NAME.match(req.name) or len(req.name) < 2 or len(req.name) > 64:
        raise HTTPException(400, "Invalid team name: must be 2-64 characters, letters/numbers/dashes/underscores only")

    if req.backend != "syncthing":
        raise HTTPException(400, "Only 'syncthing' backend is supported")

    config = await run_sync(_sid._load_identity)
    if config is None:
        raise HTTPException(400, "Not initialized. Set up sync first.")

    conn = _sid._get_sync_conn()
    if get_team(conn, req.name) is not None:
        raise HTTPException(409, f"Team '{req.name}' already exists")

    own_device_id = config.syncthing.device_id if config.syncthing else None
    join_code = f"{req.name}:{config.user_id}:{own_device_id}" if own_device_id else None

    create_team(conn, req.name, req.backend, join_code=join_code)

    # Add creator as a member so they appear in the member list and their
    # device_id is included when sharing folders (mirrors join flow)
    if own_device_id:
        upsert_member(conn, req.name, config.user_id, device_id=own_device_id,
                      machine_id=config.machine_id, machine_tag=config.machine_tag,
                      member_tag=config.member_tag)

    log_event(conn, "team_created", team_name=req.name)

    # Create metadata folder (sendreceive, shared with future members)
    if own_device_id:
        try:
            proxy = _sid.get_proxy()
            await ensure_metadata_folder(proxy, config, req.name, [own_device_id], is_creator=True)
        except Exception as e:
            logger.warning("Failed to create metadata folder for team %s: %s", req.name, e)

    return {"ok": True, "name": req.name, "backend": req.backend, "join_code": join_code}


@router.get("/teams/{team_name}")
async def sync_get_team(team_name: str) -> Any:
    """Get a single team's details."""
    if not ALLOWED_PROJECT_NAME.match(team_name):
        raise HTTPException(400, "Invalid team name")

    conn = _sid._get_sync_conn()
    team = get_team(conn, team_name)
    if team is None:
        raise HTTPException(404, f"Team '{team_name}' not found")

    members_data = list_members(conn, team_name)
    projects_data = list_team_projects(conn, team_name)
    device_status = _get_device_status_map()

    return {
        "name": team["name"],
        "backend": team["backend"],
        "join_code": team.get("join_code"),
        "projects": [
            {
                "name": p["project_encoded_name"],
                "encoded_name": p["project_encoded_name"],
                "path": p["path"],
            }
            for p in projects_data
        ],
        "members": [
            _enrich_member(m, device_status)
            for m in members_data
        ],
    }


@router.delete("/teams/{team_name}")
async def sync_delete_team(team_name: str) -> Any:
    """Leave/delete a sync team — cleans up Syncthing folders and devices."""
    if not ALLOWED_PROJECT_NAME.match(team_name):
        raise HTTPException(400, "Invalid team name")

    conn = _sid._get_sync_conn()
    if get_team(conn, team_name) is None:
        raise HTTPException(404, f"Team '{team_name}' not found")

    # Clean up Syncthing state before deleting DB records (need member/project data)
    cleanup = {"folders_removed": 0, "devices_removed": 0}
    try:
        config = await run_sync(_sid._load_identity)
        if config:
            proxy = _sid.get_proxy()
            cleanup = await cleanup_syncthing_for_team(proxy, config, conn, team_name)
    except Exception as e:
        logger.warning("Syncthing cleanup for team %s failed: %s", team_name, e)

    log_event(conn, "team_left", team_name=team_name, detail=cleanup)
    delete_team(conn, team_name)

    return {"ok": True, "name": team_name, **cleanup}


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

    config = await run_sync(_sid._load_identity)
    if config is None:
        raise HTTPException(400, "Not initialized. Run sync setup first.")

    own_device_id = config.syncthing.device_id if config.syncthing else None
    conn = _sid._get_sync_conn()

    # Auto-create team if it doesn't exist locally (join codes are Syncthing-only)
    # Store the same join code so all members share a single fixed code
    team_created = False
    if get_team(conn, team_name) is None:
        create_team(conn, team_name, backend="syncthing", join_code=req.join_code.strip())
        log_event(conn, "team_created", team_name=team_name)
        # Add self as a member so the joiner appears in the team's member list
        upsert_member(conn, team_name, config.user_id, device_id=own_device_id,
                      machine_id=config.machine_id, machine_tag=config.machine_tag,
                      member_tag=config.member_tag)
        team_created = True

    # Clear any previous removal records — joining via code is an explicit action
    clear_member_removal(conn, team_name, device_id)
    if own_device_id:
        clear_member_removal(conn, team_name, own_device_id)
    # Add or update leader as member (idempotent, updates device_id on rejoin)
    leader_user_id, leader_machine_tag = parse_member_tag(leader_name)
    upsert_member(conn, team_name, leader_user_id, device_id=device_id,
                  machine_tag=leader_machine_tag,
                  member_tag=leader_name if leader_machine_tag else None)
    log_event(conn, "member_added", team_name=team_name, member_name=leader_name)

    # Pair device in Syncthing (best-effort)
    paired = False
    try:
        proxy = _sid.get_proxy()
        await run_sync(proxy.add_device, device_id, leader_name, introducer=True)
        paired = True
    except Exception as e:
        logger.warning("Failed to pair device %s in Syncthing: %s", device_id, e)

    # Create handshake folder so the leader can auto-accept us (works even without projects)
    if paired:
        try:
            await ensure_handshake_folder(proxy, config, team_name, [device_id])
        except Exception as e:
            logger.warning("Failed to create handshake folder: %s", e)

    # Create/join metadata folder
    if paired:
        try:
            await ensure_metadata_folder(proxy, config, team_name, [device_id])
        except Exception as e:
            logger.warning("Failed to create metadata folder: %s", e)

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

    # Update own metadata state after joining
    try:
        from services.sync_metadata_writer import update_own_metadata
        update_own_metadata(config, conn, team_name)
    except Exception as e:
        logger.debug("Failed to update own metadata after join: %s", e)

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


@router.post("/teams/{team_name}/invite")
async def sync_generate_invite(team_name: str) -> Any:
    """Generate an invite code for this team using the current device as entry point.

    Any team member can generate an invite — the joiner connects to the inviter
    first, then the Syncthing mesh propagates all other devices.
    """
    if not ALLOWED_PROJECT_NAME.match(team_name):
        raise HTTPException(400, "Invalid team name")

    conn = _sid._get_sync_conn()
    team = get_team(conn, team_name)
    if team is None:
        raise HTTPException(404, f"Team '{team_name}' not found")

    config = await run_sync(_sid._load_identity)
    if config is None:
        raise HTTPException(400, "Not initialized")

    if not config.syncthing or not config.syncthing.device_id:
        raise HTTPException(400, "Syncthing not configured")

    # Verify caller is a member of this team
    members = list_members(conn, team_name)
    is_member = any(
        m["device_id"] == config.syncthing.device_id for m in members
    )
    if not is_member:
        raise HTTPException(403, "You are not a member of this team")

    invite_code = f"{team_name}:{config.member_tag}:{config.syncthing.device_id}"

    return {
        "invite_code": invite_code,
        "team_name": team_name,
        "inviter": config.member_tag,
    }


@router.get("/teams/{team_name}/join-code")
async def sync_team_join_code(team_name: str) -> Any:
    """Get the join code for a team.

    Returns the fixed join code stored at team creation time. All members
    share the same code so any member can invite new people.
    """
    if not ALLOWED_PROJECT_NAME.match(team_name):
        raise HTTPException(400, "Invalid team name")

    config = await run_sync(_sid._load_identity)
    if config is None:
        raise HTTPException(400, "Not initialized")

    conn = _sid._get_sync_conn()
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


@router.get("/teams/{team_name}/settings")
async def sync_get_team_settings(team_name: str) -> Any:
    """Get team sync settings with resolved effective values."""
    if not ALLOWED_PROJECT_NAME.match(team_name):
        raise HTTPException(400, "Invalid team name")

    conn = _sid._get_sync_conn()
    team = get_team(conn, team_name)
    if team is None:
        raise HTTPException(404, f"Team '{team_name}' not found")

    settings = {}
    for key in VALID_SETTING_KEYS:
        value, source = get_effective_setting(conn, key, team_name=team_name)
        settings[key] = {"value": value, "source": source}

    # Include sync_session_limit from the sync_teams table
    settings["sync_session_limit"] = {
        "value": team.get("sync_session_limit", "all"),
        "source": "team",
    }

    return {"team_name": team_name, "settings": settings}


@router.patch("/teams/{team_name}/settings")
async def sync_update_team_settings(team_name: str, req: UpdateTeamSettingsRequest) -> Any:
    """Update team sync settings."""
    if not ALLOWED_PROJECT_NAME.match(team_name):
        raise HTTPException(400, "Invalid team name")

    conn = _sid._get_sync_conn()
    team = get_team(conn, team_name)
    if team is None:
        raise HTTPException(404, f"Team '{team_name}' not found")

    config = await run_sync(_sid._load_identity)
    member_name = config.user_id if config else None
    changes = {}

    # Handle sync_session_limit (stays in sync_teams table for backward compat)
    if req.sync_session_limit is not None:
        if req.sync_session_limit not in VALID_SESSION_LIMITS:
            raise HTTPException(400, f"Invalid session limit. Must be one of: {', '.join(sorted(VALID_SESSION_LIMITS))}")
        old_limit = team.get("sync_session_limit", "all")
        update_team_session_limit(conn, team_name, req.sync_session_limit)
        changes["sync_session_limit"] = {"old": old_limit, "new": req.sync_session_limit}

    # Handle auto_accept_members
    if req.auto_accept_members is not None:
        if req.auto_accept_members not in ("true", "false"):
            raise HTTPException(400, "auto_accept_members must be 'true' or 'false'")
        scope = f"team:{team_name}"
        old = set_setting(conn, scope, "auto_accept_members", req.auto_accept_members)
        changes["auto_accept_members"] = {"old": old or "true", "new": req.auto_accept_members}

    # Handle sync_direction
    if req.sync_direction is not None:
        if req.sync_direction not in VALID_SYNC_DIRECTIONS:
            raise HTTPException(400, f"Invalid sync_direction. Must be one of: {', '.join(sorted(VALID_SYNC_DIRECTIONS))}")
        scope = f"team:{team_name}"
        old = set_setting(conn, scope, "sync_direction", req.sync_direction)
        changes["sync_direction"] = {"old": old or "both", "new": req.sync_direction}

    if not changes:
        raise HTTPException(400, "No settings provided to update")

    log_event(conn, "settings_changed", team_name=team_name, member_name=member_name,
              detail=changes)

    # Update own metadata state (settings changed)
    try:
        from services.sync_metadata_writer import update_own_metadata
        update_own_metadata(config, conn, team_name)
    except Exception as e:
        logger.debug("Failed to update own metadata after settings change: %s", e)

    return {"ok": True, "team_name": team_name, "changes": changes}

"""Sync Teams + Members router — v4, thin delegation to TeamService."""
from __future__ import annotations

import logging
import sqlite3
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from domain.team import AuthorizationError, InvalidTransitionError
from domain.events import SyncEvent, SyncEventType
from routers.sync_deps import (
    get_conn,
    make_repos,
    make_team_service,
    require_config,
    validate_name,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/sync", tags=["sync-teams"])


# --- Request schemas -------------------------------------------------------

class CreateTeamRequest(BaseModel):
    name: str


class AddMemberRequest(BaseModel):
    pairing_code: str


# --- Dependencies (overridable in tests) -----------------------------------

async def get_team_svc(config=Depends(require_config)):
    return make_team_service(config)


def get_pairing_svc():
    from services.sync.pairing_service import PairingService

    return PairingService()


# --- Team endpoints --------------------------------------------------------

@router.post("/teams", status_code=201)
async def create_team(
    req: CreateTeamRequest,
    conn: sqlite3.Connection = Depends(get_conn),
    config=Depends(require_config),
    svc=Depends(get_team_svc),
):
    """Create a new team. Caller becomes the leader."""
    validate_name(req.name, "team name")
    device_id = config.syncthing.device_id if config.syncthing else ""
    try:
        team = await svc.create_team(
            conn,
            name=req.name,
            leader_member_tag=config.member_tag,
            leader_device_id=device_id,
        )
    except ValueError as e:
        raise HTTPException(400, str(e))
    return _team_dict(team)


@router.get("/teams")
async def list_teams(conn: sqlite3.Connection = Depends(get_conn)):
    """List all teams."""
    repos = make_repos()
    teams = repos["teams"].list_all(conn)
    return {"teams": [_team_dict(t) for t in teams]}


@router.get("/teams/{name}")
async def get_team(name: str, conn: sqlite3.Connection = Depends(get_conn)):
    """Team detail with members, projects, and subscriptions."""
    repos = make_repos()
    team = repos["teams"].get(conn, name)
    if team is None:
        raise HTTPException(404, f"Team '{name}' not found")
    members = repos["members"].list_for_team(conn, name)
    projects = repos["projects"].list_for_team(conn, name)
    subs_list = []
    for m in members:
        subs_list.extend(repos["subs"].list_for_member(conn, m.member_tag))
    return {
        **_team_dict(team),
        "members": [_member_dict(m) for m in members],
        "projects": [
            {
                "git_identity": p.git_identity,
                "encoded_name": p.encoded_name,
                "folder_suffix": p.folder_suffix,
                "status": p.status.value,
            }
            for p in projects
        ],
        "subscriptions": [
            {
                "member_tag": s.member_tag,
                "team_name": s.team_name,
                "project_git_identity": s.project_git_identity,
                "status": s.status.value,
                "direction": s.direction.value,
            }
            for s in subs_list
        ],
    }


@router.delete("/teams/{name}")
async def dissolve_team(
    name: str,
    conn: sqlite3.Connection = Depends(get_conn),
    config=Depends(require_config),
    svc=Depends(get_team_svc),
):
    """Dissolve a team. Leader only."""
    device_id = config.syncthing.device_id if config.syncthing else ""
    try:
        team = await svc.dissolve_team(conn, team_name=name, by_device=device_id)
    except AuthorizationError:
        raise HTTPException(403, "Only the team leader can dissolve the team")
    except InvalidTransitionError as e:
        raise HTTPException(409, str(e))
    except ValueError as e:
        raise HTTPException(404, str(e))
    return {"ok": True, "name": team.name, "status": team.status.value}


@router.post("/teams/{name}/leave")
async def leave_team(
    name: str,
    conn: sqlite3.Connection = Depends(get_conn),
    config=Depends(require_config),
    svc=Depends(get_team_svc),
):
    """Leave a team. Non-leaders use this to self-remove.

    Runs the same cleanup as auto-leave in reconciliation:
    removes folders, unpairs devices not shared with other teams, deletes team locally.
    """
    member_tag = config.member_tag if config else ""
    repos = make_repos()
    team = repos["teams"].get(conn, name)
    if team is None:
        raise HTTPException(404, f"Team '{name}' not found")

    if team.leader_member_tag == member_tag:
        raise HTTPException(400, "Team leaders must dissolve the team, not leave it")

    # Run the same cleanup as reconciliation auto-leave
    from services.syncthing.client import SyncthingClient
    from services.syncthing.device_manager import DeviceManager
    from services.syncthing.folder_manager import FolderManager
    from services.sync.metadata_service import MetadataService
    from config import settings as app_settings

    api_key = config.syncthing.api_key if config.syncthing else ""
    client = SyncthingClient(api_url="http://localhost:8384", api_key=api_key)
    devices = DeviceManager(client)
    folders = FolderManager(client, karma_base=app_settings.karma_base)

    projects = repos["projects"].list_for_team(conn, name)
    members = repos["members"].list_for_team(conn, name)
    suffixes = [p.folder_suffix for p in projects]
    tags = [m.member_tag for m in members]

    await folders.cleanup_team_folders(suffixes, tags, name)

    # Unpair devices not shared with other teams
    for member in members:
        if member.member_tag == member_tag:
            continue
        others = repos["members"].get_by_device(conn, member.device_id)
        if len([o for o in others if o.team_name != name]) == 0:
            await devices.unpair(member.device_id)

    repos["teams"].delete(conn, name)
    repos["events"].log(conn, SyncEvent(
        event_type=SyncEventType.member_auto_left,
        team_name=name,
        member_tag=member_tag,
    ))
    return {"ok": True, "name": name}


# --- Member endpoints ------------------------------------------------------

@router.post("/teams/{name}/members", status_code=201)
async def add_member(
    name: str,
    req: AddMemberRequest,
    conn: sqlite3.Connection = Depends(get_conn),
    config=Depends(require_config),
    svc=Depends(get_team_svc),
    pairing=Depends(get_pairing_svc),
):
    """Add member via pairing code. Leader only."""
    try:
        info = pairing.validate_code(req.pairing_code)
    except ValueError as e:
        raise HTTPException(400, f"Invalid pairing code: {e}")
    device_id = config.syncthing.device_id if config.syncthing else ""
    try:
        member = await svc.add_member(
            conn,
            team_name=name,
            by_device=device_id,
            new_member_tag=info.member_tag,
            new_device_id=info.device_id,
        )
    except AuthorizationError:
        raise HTTPException(403, "Only the team leader can add members")
    except InvalidTransitionError as e:
        raise HTTPException(409, str(e))
    except ValueError as e:
        raise HTTPException(404, str(e))
    return _member_dict(member)


@router.delete("/teams/{name}/members/{tag}")
async def remove_member(
    name: str,
    tag: str,
    conn: sqlite3.Connection = Depends(get_conn),
    config=Depends(require_config),
    svc=Depends(get_team_svc),
):
    """Remove a member. Leader only."""
    device_id = config.syncthing.device_id if config.syncthing else ""
    try:
        member = await svc.remove_member(
            conn, team_name=name, by_device=device_id, member_tag=tag,
        )
    except AuthorizationError:
        raise HTTPException(403, "Only the team leader can remove members")
    except InvalidTransitionError as e:
        raise HTTPException(409, str(e))
    except ValueError as e:
        raise HTTPException(404, str(e))
    return _member_dict(member)


@router.get("/teams/{name}/members")
async def list_members(name: str, conn: sqlite3.Connection = Depends(get_conn)):
    """List team members."""
    repos = make_repos()
    team = repos["teams"].get(conn, name)
    if team is None:
        raise HTTPException(404, f"Team '{name}' not found")
    members = repos["members"].list_for_team(conn, name)
    return {"members": [_member_dict(m) for m in members]}


# --- Join code endpoint ----------------------------------------------------

@router.get("/teams/{name}/join-code")
async def get_join_code(
    name: str,
    conn: sqlite3.Connection = Depends(get_conn),
    config=Depends(require_config),
    pairing=Depends(get_pairing_svc),
):
    """Generate a join code for this team's device."""
    repos = make_repos()
    team = repos["teams"].get(conn, name)
    if team is None:
        raise HTTPException(404, f"Team '{name}' not found")
    device_id = config.syncthing.device_id if config.syncthing else ""
    if not device_id:
        raise HTTPException(400, "No Syncthing device ID configured")
    code = pairing.generate_code(config.member_tag, device_id)
    return {"code": code, "member_tag": config.member_tag, "device_id": device_id}


# --- Activity endpoint -----------------------------------------------------

@router.get("/teams/{name}/activity")
async def get_team_activity(
    name: str,
    limit: int = Query(default=20, ge=1, le=200),
    conn: sqlite3.Connection = Depends(get_conn),
):
    """Return recent activity events for a team."""
    repos = make_repos()
    team = repos["teams"].get(conn, name)
    if team is None:
        raise HTTPException(404, f"Team '{name}' not found")
    events = repos["events"].query(conn, team=name, limit=limit)
    return {
        "events": [
            {
                "event_type": e.event_type.value,
                "team_name": e.team_name,
                "member_tag": e.member_tag,
                "detail": e.detail,
                "created_at": e.created_at.isoformat(),
            }
            for e in events
        ]
    }


# --- Project status endpoint -----------------------------------------------

@router.get("/teams/{name}/project-status")
async def get_project_status(
    name: str,
    conn: sqlite3.Connection = Depends(get_conn),
):
    """Per-project subscription counts for a team."""
    repos = make_repos()
    team = repos["teams"].get(conn, name)
    if team is None:
        raise HTTPException(404, f"Team '{name}' not found")
    projects = repos["projects"].list_for_team(conn, name)
    result = []
    for p in projects:
        subs = repos["subs"].list_for_project(conn, name, p.git_identity)
        counts = {"offered": 0, "accepted": 0, "paused": 0, "declined": 0}
        for s in subs:
            if s.status.value in counts:
                counts[s.status.value] += 1
        result.append({
            "git_identity": p.git_identity,
            "folder_suffix": p.folder_suffix,
            "status": p.status.value,
            "subscription_counts": counts,
        })
    return {"projects": result}


# --- Session stats endpoint ------------------------------------------------

@router.get("/teams/{name}/session-stats")
async def get_session_stats(
    name: str,
    days: int = Query(default=30, ge=1, le=365),
    conn: sqlite3.Connection = Depends(get_conn),
):
    """Per-member stats for a team: status and subscription count."""
    repos = make_repos()
    team = repos["teams"].get(conn, name)
    if team is None:
        raise HTTPException(404, f"Team '{name}' not found")
    members = repos["members"].list_for_team(conn, name)
    result = []
    for m in members:
        subs = repos["subs"].list_for_member(conn, m.member_tag)
        # Filter to this team's subscriptions
        team_subs = [s for s in subs if s.team_name == name]
        result.append({
            "member_tag": m.member_tag,
            "user_id": m.user_id,
            "status": m.status.value,
            "subscription_count": len(team_subs),
        })
    return {"members": result}


# --- Helpers ---------------------------------------------------------------

def _team_dict(team) -> dict:
    return {
        "name": team.name,
        "leader_member_tag": team.leader_member_tag,
        "status": team.status.value,
        "created_at": team.created_at.isoformat(),
    }


def _member_dict(member) -> dict:
    return {
        "member_tag": member.member_tag,
        "device_id": member.device_id,
        "user_id": member.user_id,
        "machine_tag": member.machine_tag,
        "status": member.status.value,
    }

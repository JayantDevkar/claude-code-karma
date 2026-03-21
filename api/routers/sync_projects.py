"""Sync Projects + Subscriptions router — v4, delegates to ProjectService."""
from __future__ import annotations

import logging
import sqlite3
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from domain.subscription import SyncDirection
from domain.team import AuthorizationError, InvalidTransitionError
from domain.project import SharedProjectStatus
from routers.sync_deps import (
    get_conn,
    get_read_conn,
    make_project_service,
    make_repos,
    require_config,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/sync", tags=["sync-projects"])


# --- Request schemas -------------------------------------------------------

class ShareProjectRequest(BaseModel):
    git_identity: str
    encoded_name: Optional[str] = None


class AcceptRequest(BaseModel):
    direction: str = "both"


class DirectionRequest(BaseModel):
    direction: str


# --- Dependencies ----------------------------------------------------------

async def get_project_svc(config=Depends(require_config)):
    return make_project_service(config)


# --- Project endpoints -----------------------------------------------------

@router.post("/teams/{name}/projects", status_code=201)
async def share_project(
    name: str,
    req: ShareProjectRequest,
    conn: sqlite3.Connection = Depends(get_conn),
    config=Depends(require_config),
    svc=Depends(get_project_svc),
):
    """Share a project with the team. Leader only."""
    device_id = config.syncthing.device_id if config.syncthing else ""
    try:
        project = await svc.share_project(
            conn,
            team_name=name,
            by_device=device_id,
            git_identity=req.git_identity,
            encoded_name=req.encoded_name,
        )
    except AuthorizationError:
        raise HTTPException(403, "Only the team leader can share projects")
    except ValueError as e:
        raise HTTPException(400, str(e))
    return _project_dict(project)


@router.delete("/teams/{name}/projects/{git_identity:path}")
async def remove_project(
    name: str,
    git_identity: str,
    conn: sqlite3.Connection = Depends(get_conn),
    config=Depends(require_config),
    svc=Depends(get_project_svc),
):
    """Remove a project from the team. Leader only."""
    device_id = config.syncthing.device_id if config.syncthing else ""
    try:
        project = await svc.remove_project(
            conn, team_name=name, by_device=device_id, git_identity=git_identity,
        )
    except AuthorizationError:
        raise HTTPException(403, "Only the team leader can remove projects")
    except InvalidTransitionError as e:
        raise HTTPException(409, str(e))
    except ValueError as e:
        raise HTTPException(404, str(e))
    return {"ok": True, **_project_dict(project)}


@router.get("/teams/{name}/projects")
async def list_projects(name: str, conn: sqlite3.Connection = Depends(get_read_conn)):
    """List projects shared in the team."""
    repos = make_repos()
    team = repos["teams"].get(conn, name)
    if team is None:
        raise HTTPException(404, f"Team '{name}' not found")
    projects = repos["projects"].list_for_team(conn, name)
    return {"projects": [_project_dict(p) for p in projects]}


# --- Subscription endpoints ------------------------------------------------

@router.post("/subscriptions/{team}/{git_identity:path}/accept")
async def accept_subscription(
    team: str,
    git_identity: str,
    req: AcceptRequest,
    conn: sqlite3.Connection = Depends(get_conn),
    config=Depends(require_config),
    svc=Depends(get_project_svc),
):
    """Accept a subscription with the given sync direction."""
    direction = _parse_direction(req.direction)
    try:
        sub = await svc.accept_subscription(
            conn,
            member_tag=config.member_tag,
            team_name=team,
            git_identity=git_identity,
            direction=direction,
        )
    except InvalidTransitionError as e:
        raise HTTPException(409, str(e))
    except ValueError as e:
        raise HTTPException(404, str(e))
    return _sub_dict(sub)


@router.post("/subscriptions/{team}/{git_identity:path}/pause")
async def pause_subscription(
    team: str,
    git_identity: str,
    conn: sqlite3.Connection = Depends(get_conn),
    config=Depends(require_config),
    svc=Depends(get_project_svc),
):
    """Pause an accepted subscription."""
    try:
        sub = await svc.pause_subscription(
            conn,
            member_tag=config.member_tag,
            team_name=team,
            git_identity=git_identity,
        )
    except InvalidTransitionError as e:
        raise HTTPException(409, str(e))
    except ValueError as e:
        raise HTTPException(404, str(e))
    return _sub_dict(sub)


@router.post("/subscriptions/{team}/{git_identity:path}/resume")
async def resume_subscription(
    team: str,
    git_identity: str,
    conn: sqlite3.Connection = Depends(get_conn),
    config=Depends(require_config),
    svc=Depends(get_project_svc),
):
    """Resume a paused subscription."""
    try:
        sub = await svc.resume_subscription(
            conn,
            member_tag=config.member_tag,
            team_name=team,
            git_identity=git_identity,
        )
    except InvalidTransitionError as e:
        raise HTTPException(409, str(e))
    except ValueError as e:
        raise HTTPException(404, str(e))
    return _sub_dict(sub)


@router.post("/subscriptions/{team}/{git_identity:path}/decline")
async def decline_subscription(
    team: str,
    git_identity: str,
    conn: sqlite3.Connection = Depends(get_conn),
    config=Depends(require_config),
    svc=Depends(get_project_svc),
):
    """Decline a subscription."""
    try:
        sub = await svc.decline_subscription(
            conn,
            member_tag=config.member_tag,
            team_name=team,
            git_identity=git_identity,
        )
    except InvalidTransitionError as e:
        raise HTTPException(409, str(e))
    except ValueError as e:
        raise HTTPException(404, str(e))
    return _sub_dict(sub)


@router.post("/subscriptions/{team}/{git_identity:path}/reopen")
async def reopen_subscription(
    team: str,
    git_identity: str,
    conn: sqlite3.Connection = Depends(get_conn),
    config=Depends(require_config),
    svc=Depends(get_project_svc),
):
    """Reopen a declined subscription, returning it to OFFERED status."""
    try:
        sub = await svc.reopen_subscription(
            conn,
            member_tag=config.member_tag,
            team_name=team,
            git_identity=git_identity,
        )
    except InvalidTransitionError as e:
        raise HTTPException(409, str(e))
    except ValueError as e:
        raise HTTPException(404, str(e))
    return _sub_dict(sub)


@router.patch("/subscriptions/{team}/{git_identity:path}/direction")
async def change_direction(
    team: str,
    git_identity: str,
    req: DirectionRequest,
    conn: sqlite3.Connection = Depends(get_conn),
    config=Depends(require_config),
    svc=Depends(get_project_svc),
):
    """Change sync direction of an accepted subscription."""
    direction = _parse_direction(req.direction)
    try:
        sub = await svc.change_direction(
            conn,
            member_tag=config.member_tag,
            team_name=team,
            git_identity=git_identity,
            direction=direction,
        )
    except InvalidTransitionError as e:
        raise HTTPException(409, str(e))
    except ValueError as e:
        raise HTTPException(404, str(e))
    return _sub_dict(sub)


@router.get("/subscriptions")
async def list_subscriptions(
    conn: sqlite3.Connection = Depends(get_read_conn),
    config=Depends(require_config),
):
    """List all subscriptions for the current member."""
    repos = make_repos()
    subs = repos["subs"].list_for_member(conn, config.member_tag)
    return {"subscriptions": [_sub_dict(s) for s in subs]}


# --- Helpers ---------------------------------------------------------------

def _parse_direction(value: str) -> SyncDirection:
    try:
        return SyncDirection(value)
    except ValueError:
        raise HTTPException(400, f"Invalid direction '{value}'. Use: send, receive, both")


def _project_dict(p) -> dict:
    return {
        "git_identity": p.git_identity,
        "folder_suffix": p.folder_suffix,
        "encoded_name": p.encoded_name,
        "status": p.status.value,
    }


def _sub_dict(s) -> dict:
    return {
        "member_tag": s.member_tag,
        "team_name": s.team_name,
        "project_git_identity": s.project_git_identity,
        "status": s.status.value,
        "direction": s.direction.value,
    }

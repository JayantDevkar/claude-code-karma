"""Sync Teams + Members router — v4, thin delegation to TeamService."""
from __future__ import annotations

import logging
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from domain.team import AuthorizationError, InvalidTransitionError
from routers.sync_deps import (
    get_conn,
    get_optional_config,
    get_read_conn,
    make_managers,
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
async def list_teams(
    conn: sqlite3.Connection = Depends(get_read_conn),
    include_dissolved: bool = Query(False, description="Include dissolved teams"),
):
    """List all teams with member/project counts."""
    repos = make_repos()
    teams = repos["teams"].list_all(conn) if include_dissolved else repos["teams"].list_active(conn)
    result = []
    for t in teams:
        members = repos["members"].list_for_team(conn, t.name)
        projects = repos["projects"].list_for_team(conn, t.name)
        result.append({
            **_team_dict(t),
            "member_count": len(members),
            "project_count": len(projects),
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
        })
    return {"teams": result}


@router.get("/teams/{name}")
async def get_team(name: str, conn: sqlite3.Connection = Depends(get_read_conn)):
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
    """Leave a team. Non-leaders use this to self-remove."""
    member_tag = config.member_tag if config else ""
    try:
        await svc.leave_team(conn, team_name=name, member_tag=member_tag)
    except ValueError as e:
        raise HTTPException(400, str(e))
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

    # Check if the removed member's device is connected — if not,
    # the removal signal can't propagate via Syncthing metadata sync.
    delivery_pending = True
    try:
        devices, _, _ = make_managers(config)
        connected = await devices.is_connected(member.device_id)
        delivery_pending = not connected
    except Exception:
        pass  # Assume pending if we can't check

    result = _member_dict(member)
    result["delivery_pending"] = delivery_pending
    return result


@router.get("/teams/{name}/members")
async def list_members(
    name: str,
    conn: sqlite3.Connection = Depends(get_read_conn),
    config=Depends(get_optional_config),
):
    """List team members with delivery status for removed members."""
    repos = make_repos()
    team = repos["teams"].get(conn, name)
    if team is None:
        raise HTTPException(404, f"Team '{name}' not found")
    members = repos["members"].list_for_team(conn, name)

    # Check connectivity for removed members to surface delivery_pending
    connections: dict | None = None
    removed = [m for m in members if m.status.value == "removed"]
    if removed and config and config.syncthing:
        try:
            devices, _, _ = make_managers(config)
            connections = await devices._client.get_connections()
        except Exception:
            pass

    result = []
    for m in members:
        d = _member_dict(m)
        if m.status.value == "removed":
            connected = False
            if connections and m.device_id in connections:
                connected = connections[m.device_id].get("connected", False)
            d["delivery_pending"] = not connected
        result.append(d)

    return {"members": result}


# --- Join code endpoint ----------------------------------------------------

@router.get("/teams/{name}/join-code")
async def get_join_code(
    name: str,
    conn: sqlite3.Connection = Depends(get_read_conn),
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
    conn: sqlite3.Connection = Depends(get_read_conn),
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
    conn: sqlite3.Connection = Depends(get_read_conn),
    config=Depends(get_optional_config),
):
    """Per-project sync status: subscriptions, session counts, sync gap."""
    repos = make_repos()
    team = repos["teams"].get(conn, name)
    if team is None:
        raise HTTPException(404, f"Team '{name}' not found")
    projects = repos["projects"].list_for_team(conn, name)

    # Resolve local encoded_name and display_name for each project
    encoded_map, name_map = _resolve_project_names(conn, projects)
    relevant_encoded = {v for v in encoded_map.values() if v is not None}

    # Batch query: local session counts
    local_counts: dict[str, int] = {}
    if relevant_encoded:
        placeholders = ",".join("?" * len(relevant_encoded))
        rows = conn.execute(
            f"SELECT project_encoded_name, COUNT(*) FROM sessions "
            f"WHERE (source IS NULL OR source != 'remote') "
            f"AND project_encoded_name IN ({placeholders}) "
            f"GROUP BY project_encoded_name",
            list(relevant_encoded),
        ).fetchall()
        local_counts = {r[0]: r[1] for r in rows}

    # Batch query: received session counts per project + remote member
    received_by_encoded: dict[str, dict[str, int]] = {}
    if relevant_encoded:
        placeholders = ",".join("?" * len(relevant_encoded))
        rows = conn.execute(
            f"SELECT project_encoded_name, remote_user_id, COUNT(*) FROM sessions "
            f"WHERE source = 'remote' AND remote_user_id IS NOT NULL "
            f"AND project_encoded_name IN ({placeholders}) "
            f"GROUP BY project_encoded_name, remote_user_id",
            list(relevant_encoded),
        ).fetchall()
        for enc, uid, cnt in rows:
            received_by_encoded.setdefault(enc, {})[uid] = cnt

    # Local member_tag for outbox counting
    member_tag = config.member_tag if config else None

    # Get active session counts to exclude from gap
    active_counts = _get_active_counts()

    result = []
    for p in projects:
        subs = repos["subs"].list_for_project(conn, name, p.git_identity)
        sub_counts = {"offered": 0, "accepted": 0, "paused": 0, "declined": 0}
        for s in subs:
            if s.status.value in sub_counts:
                sub_counts[s.status.value] += 1

        encoded = encoded_map.get(p.git_identity)
        display = name_map.get(p.git_identity)
        local_count = local_counts.get(encoded, 0) if encoded else 0
        received = received_by_encoded.get(encoded, {}) if encoded else {}
        packaged_count = (
            _count_packaged(member_tag, p.folder_suffix) if member_tag else 0
        )
        active_count = active_counts.get(encoded, 0) if encoded else 0

        result.append({
            "git_identity": p.git_identity,
            "folder_suffix": p.folder_suffix,
            "status": p.status.value,
            "encoded_name": encoded,
            "name": display,
            "subscription_counts": sub_counts,
            "local_count": local_count,
            "packaged_count": packaged_count,
            "active_count": active_count,
            "received_counts": received,
            "gap": max(0, local_count - packaged_count - active_count) if member_tag else None,
        })
    return {"projects": result}


# --- Session stats endpoint ------------------------------------------------

@router.get("/teams/{name}/session-stats")
async def get_session_stats(
    name: str,
    days: int = Query(default=30, ge=1, le=365),
    conn: sqlite3.Connection = Depends(get_read_conn),
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


def _resolve_project_names(
    conn: sqlite3.Connection, projects,
) -> tuple[dict[str, str | None], dict[str, str | None]]:
    """Resolve local encoded_name and display_name for sync projects.

    Uses git_identity substring matching (same pattern as indexer.py).
    Returns (encoded_by_git, name_by_git).
    """
    local_rows = conn.execute(
        "SELECT encoded_name, git_identity, display_name FROM projects "
        "WHERE git_identity IS NOT NULL"
    ).fetchall()

    encoded_by_git: dict[str, str | None] = {}
    name_by_git: dict[str, str | None] = {}

    for p in projects:
        sync_git = (p.git_identity or "").rstrip("/").lower()
        if sync_git.endswith(".git"):
            sync_git = sync_git[:-4]

        matched_enc = None
        matched_name = None
        for enc, local_git, display_name in local_rows:
            lg = (local_git or "").rstrip("/").lower()
            if lg.endswith(".git"):
                lg = lg[:-4]
            if lg and (
                lg in sync_git or sync_git in lg
                or lg.endswith(sync_git) or sync_git.endswith(lg)
            ):
                matched_enc = enc
                matched_name = display_name
                break

        encoded_by_git[p.git_identity] = matched_enc
        name_by_git[p.git_identity] = matched_name

    return encoded_by_git, name_by_git


def _count_packaged(member_tag: str, folder_suffix: str) -> int:
    """Count *.jsonl files in the local Syncthing outbox for a project."""
    from config import settings as app_settings
    from services.syncthing.folder_manager import build_outbox_folder_id

    folder_id = build_outbox_folder_id(member_tag, folder_suffix)
    sessions_dir = app_settings.karma_base / folder_id / "sessions"
    if not sessions_dir.is_dir():
        return 0
    return sum(1 for _ in sessions_dir.glob("*.jsonl"))


def _get_active_counts(live_sessions_dir: Path | None = None) -> dict[str, int]:
    """Count active (non-ended, non-stale) sessions per project encoded_name.

    Reads ~/.claude_karma/live-sessions/*.json. Returns {encoded_name: count}.
    Uses worktree-to-parent resolution so worktree sessions roll up to
    the real project.
    """
    from services.sync.session_packager import STALE_LIVE_SESSION_SECONDS

    if live_sessions_dir is None:
        from config import settings as app_settings
        live_sessions_dir = app_settings.karma_base / "live-sessions"

    if not live_sessions_dir.is_dir():
        return {}

    import json as _json
    now = datetime.now(timezone.utc)
    counts: dict[str, int] = {}

    for json_file in live_sessions_dir.glob("*.json"):
        try:
            data = _json.loads(json_file.read_text(encoding="utf-8"))
            if data.get("state") == "ENDED":
                continue

            # Check staleness
            updated_str = data.get("updated_at")
            if updated_str:
                updated = datetime.fromisoformat(updated_str.replace("Z", "+00:00"))
                if updated.tzinfo is None:
                    updated = updated.replace(tzinfo=timezone.utc)
                if (now - updated).total_seconds() > STALE_LIVE_SESSION_SECONDS:
                    continue

            # Extract encoded_name from transcript_path
            tp = data.get("transcript_path", "")
            if "/projects/" not in tp:
                continue
            parts = tp.split("/projects/", 1)[1].split("/")
            if not parts:
                continue
            enc = parts[0]

            # Worktree resolution: if encoded name is a worktree path, resolve
            # to real project via git_root if available
            git_root = data.get("git_root")
            if git_root and (".claude-worktrees" in enc or "-worktrees-" in enc):
                enc = "-" + git_root.lstrip("/").replace("/", "-")

            counts[enc] = counts.get(enc, 0) + 1
        except (ValueError, OSError):
            continue
    return counts


# --- Member settings endpoint ------------------------------------------------

@router.get("/teams/{name}/members/{device_id}/settings")
async def get_member_settings(
    name: str,
    device_id: str,
    conn: sqlite3.Connection = Depends(get_read_conn),
):
    """Get sync direction settings for a member in a team."""
    repos = make_repos()
    team = repos["teams"].get(conn, name)
    if team is None:
        raise HTTPException(404, f"Team '{name}' not found")

    # Find member by device_id in this team
    members = repos["members"].get_by_device(conn, device_id)
    member = next((m for m in members if m.team_name == name), None)
    if member is None:
        raise HTTPException(404, f"No member with device '{device_id}' in team '{name}'")

    # Get accepted subscriptions for this member in this team
    subs = repos["subs"].list_for_member(conn, member.member_tag)
    team_subs = [s for s in subs if s.team_name == name and s.status.value == "accepted"]

    # Determine effective direction from subscriptions
    # Map API values to frontend format: send→send_only, receive→receive_only
    api_to_frontend = {"send": "send_only", "receive": "receive_only", "both": "both"}

    if team_subs:
        directions = {s.direction.value for s in team_subs}
        if len(directions) == 1:
            raw = directions.pop()
            direction_value = api_to_frontend.get(raw, raw)
        else:
            direction_value = "mixed"
        # Source: "default" if direction is "both" (the default), "member" otherwise
        source = "default" if direction_value == "both" else "member"
    else:
        direction_value = "both"
        source = "default"

    return {
        "settings": {
            "sync_direction": {
                "value": direction_value,
                "source": source,
            }
        }
    }


@router.patch("/teams/{name}/members/{device_id}/settings")
async def update_member_settings(
    name: str,
    device_id: str,
    body: dict,
    conn: sqlite3.Connection = Depends(get_conn),
):
    """Update sync direction for a member in a team."""
    repos = make_repos()
    team = repos["teams"].get(conn, name)
    if team is None:
        raise HTTPException(404, f"Team '{name}' not found")

    members = repos["members"].get_by_device(conn, device_id)
    member = next((m for m in members if m.team_name == name), None)
    if member is None:
        raise HTTPException(404, f"No member with device '{device_id}' in team '{name}'")

    new_direction = body.get("sync_direction")

    # Accept frontend aliases: send_only→send, receive_only→receive, none→both
    # null means "reset to default (both)"
    from domain.subscription import SyncDirection
    if new_direction is None:
        new_direction = "both"
    direction_aliases = {"send_only": "send", "receive_only": "receive", "none": "both"}
    normalized = direction_aliases.get(new_direction, new_direction)
    try:
        direction_enum = SyncDirection(normalized)
    except ValueError:
        raise HTTPException(400, f"Invalid direction: {new_direction}. Use: both, send, receive")

    # Update all accepted subscriptions for this member in this team
    subs = repos["subs"].list_for_member(conn, member.member_tag)
    team_subs = [s for s in subs if s.team_name == name and s.status.value == "accepted"]

    for sub in team_subs:
        updated = sub.change_direction(direction_enum)
        repos["subs"].save(conn, updated)

    source = "default" if normalized == "both" else "member"
    # Return frontend-compatible value
    api_to_frontend = {"send": "send_only", "receive": "receive_only", "both": "both"}
    return {
        "settings": {
            "sync_direction": {
                "value": api_to_frontend.get(normalized, new_direction),
                "source": source,
            }
        }
    }

"""Sync Members router — cross-team member listing and member profiles."""
from __future__ import annotations

import asyncio
import logging
import re
import sqlite3
from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from db.queries import (
    query_last_packaged_timestamp,
    query_member_daily_sync_stats,
    query_member_last_active,
    query_member_local_session_count,
    query_member_received_count,
    query_member_remote_sessions_count,
    query_member_sent_count,
    query_member_session_count,
    query_member_subscription_count,
    query_member_total_sessions,
    query_resolve_project,
)
from routers.sync_deps import get_optional_config, get_read_conn, make_repos

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/sync", tags=["sync-members"])

DEVICE_ID_RE = re.compile(r"^[A-Z2-7]{7}(-[A-Z2-7]{7}){7}$")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_connections(config: Any) -> dict:
    """Fetch Syncthing connections once.  Returns {} on any error."""
    if config is None or not getattr(config, "syncthing", None):
        return {}
    try:
        import httpx
        api_key = config.syncthing.api_key or ""
        resp = httpx.get(
            "http://localhost:8384/rest/system/connections",
            headers={"X-API-Key": api_key},
            timeout=5.0,
        )
        resp.raise_for_status()
        return resp.json().get("connections", {})
    except Exception:
        return {}


def _event_dict(e, idx: int = 0) -> dict:
    return {
        "id": idx,
        "event_type": e.event_type.value,
        "team_name": e.team_name,
        "member_tag": e.member_tag,
        "detail": e.detail,
        "created_at": e.created_at.isoformat(),
    }


# ---------------------------------------------------------------------------
# GET /sync/members — cross-team member list
# ---------------------------------------------------------------------------

@router.get("/members")
async def list_members(
    conn: sqlite3.Connection = Depends(get_read_conn),
    config=Depends(get_optional_config),
):
    """List all members across all teams, deduplicated by device_id."""
    repos = make_repos()
    teams = repos["teams"].list_all(conn)

    # Aggregate members across teams, dedup by member_tag (device_id may be empty)
    my_device_id = (
        config.syncthing.device_id
        if config and getattr(config, "syncthing", None)
        else None
    )
    my_member_tag = config.member_tag if config else None

    members_by_tag: dict[str, dict] = {}
    for t in teams:
        for m in repos["members"].list_for_team(conn, t.name):
            tag = m.member_tag
            if tag in members_by_tag:
                entry = members_by_tag[tag]
                if t.name not in entry["teams"]:
                    entry["teams"].append(t.name)
                if m.added_at < entry["_added_at"]:
                    entry["_added_at"] = m.added_at
                # Prefer non-empty device_id
                if not entry["device_id"] and m.device_id:
                    entry["device_id"] = m.device_id
                # Fallback to config device_id for self
                if not entry["device_id"] and tag == my_member_tag and my_device_id:
                    entry["device_id"] = my_device_id
            else:
                members_by_tag[tag] = {
                    "name": m.user_id,
                    "device_id": m.device_id or my_device_id if tag == my_member_tag else m.device_id,
                    "teams": [t.name],
                    "_added_at": m.added_at,
                    "_member_tag": tag,
                    "_machine_tag": m.machine_tag,
                }

    # Fetch connection status once
    connections = await asyncio.to_thread(_get_connections, config)

    result = []
    for entry in members_by_tag.values():
        tag = entry["_member_tag"]
        did = entry["device_id"]
        is_you = tag == my_member_tag
        connected = is_you or bool(connections.get(did, {}).get("connected", False))
        result.append({
            "name": entry["name"],
            "device_id": did or "",
            "member_tag": tag,
            "machine_tag": entry.get("_machine_tag", ""),
            "connected": connected,
            "is_you": is_you,
            "team_count": len(entry["teams"]),
            "teams": entry["teams"],
            "added_at": entry["_added_at"].isoformat(),
        })

    result.sort(key=lambda x: (not x["is_you"], x["name"].lower()))
    return {"members": result, "total": len(result)}


# ---------------------------------------------------------------------------
# GET /sync/members/{identifier} — full member profile
# ---------------------------------------------------------------------------

@router.get("/members/{identifier}")
async def get_member_profile(
    identifier: str,
    conn: sqlite3.Connection = Depends(get_read_conn),
    config=Depends(get_optional_config),
):
    """Full member profile. Accepts member_tag or device_id (auto-detected)."""
    if not identifier or not identifier.strip():
        raise HTTPException(400, "identifier must not be empty")
    repos = make_repos()

    # Detect format: Syncthing device_id vs member_tag
    if DEVICE_ID_RE.match(identifier):
        memberships = repos["members"].get_by_device(conn, identifier)
    else:
        memberships = repos["members"].get_all_by_member_tag(conn, identifier)

    # Fallback for self: config device_id or member_tag
    if not memberships and config:
        my_did = (
            config.syncthing.device_id
            if getattr(config, "syncthing", None)
            else None
        )
        if config.member_tag:
            if identifier == my_did or identifier == config.member_tag:
                teams = repos["teams"].list_all(conn)
                for t in teams:
                    m = repos["members"].get(conn, t.name, config.member_tag)
                    if m:
                        memberships.append(m)

    if not memberships:
        raise HTTPException(404, f"Member '{identifier}' not found")

    member_tag = memberships[0].member_tag
    user_id = memberships[0].user_id
    device_id = memberships[0].device_id or ""

    # Syncthing connection info (single HTTP call)
    my_device_id = (
        config.syncthing.device_id
        if config and getattr(config, "syncthing", None)
        else None
    )
    my_member_tag = config.member_tag if config else None
    connections = await asyncio.to_thread(_get_connections, config)
    conn_entry = connections.get(device_id, {}) if device_id else {}
    is_you = member_tag == my_member_tag if my_member_tag else False
    connected = is_you or bool(conn_entry.get("connected", False))
    in_bytes = conn_entry.get("inBytesTotal", 0)
    out_bytes = conn_entry.get("outBytesTotal", 0)

    # Build teams list with projects and online counts
    teams_data = []
    all_project_encoded = set()
    for m in memberships:
        team_members = repos["members"].list_for_team(conn, m.team_name)
        team_projects = repos["projects"].list_for_team(conn, m.team_name)

        # Count online members using already-fetched connections
        online_count = 0
        for tm in team_members:
            if tm.member_tag == my_member_tag:
                online_count += 1  # self is always online
            elif tm.device_id and connections.get(tm.device_id, {}).get("connected", False):
                online_count += 1

        # Build project list with session counts
        proj_list = []
        for p in team_projects:
            if p.status.value != "shared":
                continue
            enc, display = query_resolve_project(conn, p.git_identity)
            display = display or p.git_identity
            sess_count = 0
            if enc:
                all_project_encoded.add(enc)
                sess_count = query_member_session_count(conn, enc)
            proj_list.append({
                "encoded_name": enc or p.git_identity,
                "name": display,
                "session_count": sess_count,
            })

        teams_data.append({
            "name": m.team_name,
            "member_count": len(team_members),
            "project_count": len([p for p in team_projects if p.status.value == "shared"]),
            "online_count": online_count,
            "projects": proj_list,
        })

    # Stats: sessions sent/received, total projects, last active
    sent_count = 0
    received_count = 0
    total_sessions = 0

    sent_count = query_member_sent_count(conn, member_tag)

    # Fallback: if no packaged events logged yet, count outbox files on disk
    if sent_count == 0 and is_you:
        from config import settings as app_settings
        from services.syncthing.folder_manager import build_outbox_folder_id
        for m in memberships:
            for p in repos["projects"].list_for_team(conn, m.team_name):
                if p.status.value != "shared":
                    continue
                folder_id = build_outbox_folder_id(member_tag, p.folder_suffix)
                sessions_dir = app_settings.karma_base / folder_id / "sessions"
                if sessions_dir.is_dir():
                    sent_count += sum(1 for _ in sessions_dir.glob("*.jsonl"))

    received_count = query_member_received_count(conn, member_tag)

    # Fallback: if no received events but we have remote sessions in DB
    if received_count == 0 and not is_you:
        if all_project_encoded:
            received_count = query_member_remote_sessions_count(
                conn, member_tag, list(all_project_encoded)
            )

    if all_project_encoded:
        total_sessions = query_member_total_sessions(
            conn, list(all_project_encoded)
        )

    # Total distinct projects across subscriptions
    total_projects = query_member_subscription_count(conn, member_tag)

    last_active = query_member_last_active(conn, member_tag)

    stats = {
        "total_sessions": total_sessions,
        "sessions_sent": sent_count,
        "sessions_received": received_count,
        "total_projects": total_projects,
        "last_active": last_active,
    }

    # Session stats: daily sent/received aggregation
    session_stats_rows = query_member_daily_sync_stats(conn, member_tag)

    daily: dict[str, dict] = {}
    for date_str, etype, cnt in session_stats_rows:
        if date_str not in daily:
            daily[date_str] = {"date": date_str, "member_name": user_id, "out": 0, "packaged": 0, "received": 0}
        if etype == "session_packaged":
            daily[date_str]["packaged"] = cnt
            daily[date_str]["out"] = cnt
        elif etype == "session_received":
            daily[date_str]["received"] = cnt

    session_stats = list(daily.values())

    # Incoming stats: daily received
    incoming_stats = [
        {"date": d["date"], "incoming": d["received"]}
        for d in daily.values()
        if d["received"] > 0
    ]

    # --- New fields: sync health ---
    from routers.sync_teams import _get_active_counts, _count_packaged

    unsynced_count = None
    last_packaged_at = None
    project_sync = None
    sync_direction_val = None

    if is_you:
        active_counts = _get_active_counts()
        project_sync_list = []
        total_gap = 0
        for m_item in memberships:
            team_projects = repos["projects"].list_for_team(conn, m_item.team_name)
            for p in team_projects:
                if p.status.value != "shared":
                    continue
                enc, display = query_resolve_project(conn, p.git_identity)
                local_count = 0
                if enc:
                    local_count = query_member_local_session_count(conn, enc)
                packaged_count = _count_packaged(member_tag, p.folder_suffix)
                active_count = active_counts.get(enc, 0) if enc else 0
                gap = max(0, local_count - packaged_count - active_count)
                total_gap += gap
                project_sync_list.append({
                    "team_name": m_item.team_name,
                    "git_identity": p.git_identity,
                    "encoded_name": enc,
                    "name": display or p.git_identity,
                    "local_count": local_count,
                    "packaged_count": packaged_count,
                    "active_count": active_count,
                    "gap": gap,
                })
        unsynced_count = total_gap
        project_sync = project_sync_list

        last_packaged_at = query_last_packaged_timestamp(conn)

    # sync_direction: aggregate from accepted subscriptions
    subs = repos["subs"].list_for_member(conn, member_tag)
    accepted_dirs = {s.direction.value for s in subs if s.status.value == "accepted"}
    if len(accepted_dirs) == 0:
        sync_direction_val = None
    elif len(accepted_dirs) == 1:
        sync_direction_val = next(iter(accepted_dirs))
    else:
        sync_direction_val = "mixed"

    # Activity feed
    events = repos["events"].query(conn, member_tag=member_tag, limit=50)
    activity = [_event_dict(e, idx=i) for i, e in enumerate(events)]

    return {
        "user_id": user_id,
        "device_id": device_id,
        "member_tag": member_tag,
        "machine_tag": memberships[0].machine_tag,
        "connected": connected,
        "is_you": is_you,
        "in_bytes_total": in_bytes,
        "out_bytes_total": out_bytes,
        "teams": teams_data,
        "stats": stats,
        "session_stats": session_stats,
        "incoming_stats": incoming_stats,
        "activity": activity,
        "unsynced_count": unsynced_count,
        "last_packaged_at": last_packaged_at,
        "sync_direction": sync_direction_val,
        "project_sync": project_sync,
    }



# _resolve_project has been moved to db.queries.query_resolve_project

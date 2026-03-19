"""Sync Members router — cross-team member listing and member profiles."""
from __future__ import annotations

import logging
import sqlite3

from fastapi import APIRouter, Depends, HTTPException

from routers.sync_deps import get_conn, get_optional_config, make_repos

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/sync", tags=["sync-members"])


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
    conn: sqlite3.Connection = Depends(get_conn),
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
                }

    # Fetch connection status once
    connections = _get_connections(config)

    result = []
    for entry in members_by_tag.values():
        tag = entry["_member_tag"]
        did = entry["device_id"]
        is_you = tag == my_member_tag
        connected = is_you or bool(connections.get(did, {}).get("connected", False))
        result.append({
            "name": entry["name"],
            "device_id": did or "",
            "connected": connected,
            "is_you": is_you,
            "team_count": len(entry["teams"]),
            "teams": entry["teams"],
            "added_at": entry["_added_at"].isoformat(),
        })

    result.sort(key=lambda x: (not x["is_you"], x["name"].lower()))
    return {"members": result, "total": len(result)}


# ---------------------------------------------------------------------------
# GET /sync/members/{device_id} — full member profile
# ---------------------------------------------------------------------------

@router.get("/members/{device_id}")
async def get_member_profile(
    device_id: str,
    conn: sqlite3.Connection = Depends(get_conn),
    config=Depends(get_optional_config),
):
    """Full member profile: teams, stats, session history, activity."""
    if not device_id or not device_id.strip():
        raise HTTPException(400, "device_id must not be empty")
    repos = make_repos()
    memberships = repos["members"].get_by_device(conn, device_id)
    if not memberships:
        raise HTTPException(404, f"Member with device '{device_id}' not found")

    member_tag = memberships[0].member_tag
    user_id = memberships[0].user_id

    # Syncthing connection info (single HTTP call)
    my_device_id = (
        config.syncthing.device_id
        if config and getattr(config, "syncthing", None)
        else None
    )
    my_member_tag = config.member_tag if config else None
    connections = _get_connections(config)
    conn_entry = connections.get(device_id, {})
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
            enc, display = _resolve_project(conn, p.git_identity)
            display = display or p.git_identity
            sess_count = 0
            if enc:
                all_project_encoded.add(enc)
                row = conn.execute(
                    "SELECT COUNT(*) FROM sessions WHERE project_encoded_name = ?",
                    (enc,),
                ).fetchone()
                if row:
                    sess_count = row[0]
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

    sent_row = conn.execute(
        "SELECT COUNT(*) FROM sync_events WHERE event_type = 'session_packaged' AND member_tag = ?",
        (member_tag,),
    ).fetchone()
    if sent_row:
        sent_count = sent_row[0]

    recv_row = conn.execute(
        "SELECT COUNT(*) FROM sync_events WHERE event_type = 'session_received' AND member_tag = ?",
        (member_tag,),
    ).fetchone()
    if recv_row:
        received_count = recv_row[0]

    if all_project_encoded:
        placeholders = ",".join("?" * len(all_project_encoded))
        total_row = conn.execute(
            f"SELECT COUNT(*) FROM sessions WHERE project_encoded_name IN ({placeholders})",
            list(all_project_encoded),
        ).fetchone()
        if total_row:
            total_sessions = total_row[0]

    # Total distinct projects across subscriptions
    sub_rows = conn.execute(
        "SELECT COUNT(DISTINCT project_git_identity) FROM sync_subscriptions WHERE member_tag = ?",
        (member_tag,),
    ).fetchone()
    total_projects = sub_rows[0] if sub_rows else 0

    last_active_row = conn.execute(
        "SELECT MAX(created_at) FROM sync_events WHERE member_tag = ?",
        (member_tag,),
    ).fetchone()
    last_active = last_active_row[0] if last_active_row and last_active_row[0] else None

    stats = {
        "total_sessions": total_sessions,
        "sessions_sent": sent_count,
        "sessions_received": received_count,
        "total_projects": total_projects,
        "last_active": last_active,
    }

    # Session stats: daily sent/received aggregation
    session_stats_rows = conn.execute(
        "SELECT date(created_at) as d, event_type, COUNT(*) "
        "FROM sync_events "
        "WHERE member_tag = ? AND event_type IN ('session_packaged', 'session_received') "
        "GROUP BY d, event_type ORDER BY d",
        (member_tag,),
    ).fetchall()

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

    # Activity feed
    events = repos["events"].query(conn, member_tag=member_tag, limit=50)
    activity = [_event_dict(e, idx=i) for i, e in enumerate(events)]

    return {
        "user_id": user_id,
        "device_id": device_id,
        "connected": connected,
        "is_you": is_you,
        "in_bytes_total": in_bytes,
        "out_bytes_total": out_bytes,
        "teams": teams_data,
        "stats": stats,
        "session_stats": session_stats,
        "incoming_stats": incoming_stats,
        "activity": activity,
    }


# ---------------------------------------------------------------------------
# Git identity resolution (mirrors indexer.py pattern)
# ---------------------------------------------------------------------------

def _resolve_project(conn: sqlite3.Connection, git_identity: str) -> tuple[str | None, str | None]:
    """Resolve a sync project's git_identity to (encoded_name, display_name)."""
    norm = (git_identity or "").rstrip("/").lower()
    if norm.endswith(".git"):
        norm = norm[:-4]
    if not norm:
        return None, None
    rows = conn.execute(
        "SELECT encoded_name, git_identity, display_name FROM projects "
        "WHERE git_identity IS NOT NULL"
    ).fetchall()
    for enc, local_git, display in rows:
        lg = (local_git or "").rstrip("/").lower()
        if lg.endswith(".git"):
            lg = lg[:-4]
        if lg and (lg in norm or norm in lg or lg.endswith(norm) or norm.endswith(lg)):
            return enc, display
    return None, None

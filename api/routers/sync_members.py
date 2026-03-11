"""Member management endpoints extracted from sync_status.py."""

import logging
from typing import Any, Optional

from fastapi import APIRouter, HTTPException

from db.sync_queries import (
    get_team, add_member, remove_member, upsert_member,
    get_member_by_device_id, list_members, list_team_projects,
    log_event, query_events, query_session_stats_by_member,
    cleanup_data_for_member, clear_member_removal,
    get_effective_setting, get_setting, set_setting, delete_setting,
    VALID_SYNC_DIRECTIONS, VALID_SETTING_KEYS,
)
from schemas import AddMemberRequest, UpdateMemberSettingsRequest
import services.sync_identity as _sid
from services.sync_identity import (
    validate_device_id, _trigger_remote_reindex_bg,
    validate_event_type_filter, cap_pagination,
    ALLOWED_PROJECT_NAME, ALLOWED_MEMBER_NAME, ALLOWED_DEVICE_ID,
    _VALID_EVENT_TYPES,
)
from services.sync_folders import auto_share_folders, cleanup_syncthing_for_member
from services.syncthing_proxy import run_sync

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/sync", tags=["sync"])


@router.post("/teams/{team_name}/members")
async def sync_add_member(team_name: str, req: AddMemberRequest) -> Any:
    """Add a member to a sync group."""
    if not ALLOWED_PROJECT_NAME.match(team_name):
        raise HTTPException(400, "Invalid team name")
    if not ALLOWED_MEMBER_NAME.match(req.name) or len(req.name) > 64:
        raise HTTPException(400, "Invalid member name")
    validate_device_id(req.device_id)

    conn = _sid._get_sync_conn()
    if get_team(conn, team_name) is None:
        raise HTTPException(404, f"Team '{team_name}' not found")

    # Clear any previous removal record — this is an explicit re-addition
    clear_member_removal(conn, team_name, req.device_id)
    add_member(conn, team_name, req.name, device_id=req.device_id)
    log_event(conn, "member_added", team_name=team_name, member_name=req.name)

    # Pair device in Syncthing (best-effort)
    paired = False
    folders_created = None
    try:
        proxy = _sid.get_proxy()
        await run_sync(proxy.add_device, req.device_id, req.name)
        paired = True

        # Auto-create shared folders for all projects in this team
        config = await run_sync(_sid._load_identity)
        if config is not None:
            folders_created = await auto_share_folders(proxy, config, conn, team_name, req.device_id)
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
async def sync_remove_member(
    team_name: str, member_name: str, keep_data: bool = False,
) -> Any:
    """Remove a member — cleans up their Syncthing folders, device, and session data."""
    if not ALLOWED_PROJECT_NAME.match(team_name):
        raise HTTPException(400, "Invalid team name")
    if not ALLOWED_MEMBER_NAME.match(member_name):
        raise HTTPException(400, "Invalid member name")

    conn = _sid._get_sync_conn()
    if get_team(conn, team_name) is None:
        raise HTTPException(404, f"Team '{team_name}' not found")

    members = list_members(conn, team_name)
    member = next((m for m in members if m["name"] == member_name), None)
    if member is None:
        raise HTTPException(404, f"Member '{member_name}' not found")

    device_id = member["device_id"]
    member_tag = member.get("member_tag") or member_name

    # Write removal signal to metadata folder (creator-only enforcement)
    try:
        from karma.config import KARMA_BASE as _kb
        from services.sync_metadata import write_removal_signal, validate_removal_authority

        meta_dir = _kb / "metadata-folders" / team_name
        if meta_dir.exists():
            config = await run_sync(_sid._load_identity)
            if config and not validate_removal_authority(meta_dir, config.member_tag, conn=conn, team_name=team_name):
                raise HTTPException(
                    403,
                    "Only the team creator can remove members. "
                    "You can control your own sync direction instead.",
                )
            if config:
                write_removal_signal(
                    meta_dir,
                    removed_member_tag=member_tag,
                    removed_device_id=device_id,
                    removed_by=config.member_tag,
                )
    except HTTPException:
        raise
    except Exception as e:
        logger.warning("Failed to write removal signal: %s", e)

    # Clean up Syncthing state before removing DB record
    cleanup = {"folders_removed": 0, "devices_updated": 0}
    try:
        config = await run_sync(_sid._load_identity)
        if config:
            proxy = _sid.get_proxy()
            cleanup = await cleanup_syncthing_for_member(
                proxy, config, conn, team_name, device_id, member_name,
            )
    except Exception as e:
        logger.warning("Syncthing cleanup for member %s failed: %s", member_name, e)

    # Clean up filesystem and DB session data (scoped to team projects)
    data_cleanup = {"dirs_removed": 0, "sessions_deleted": 0}
    if not keep_data:
        try:
            from karma.config import KARMA_BASE

            data_cleanup = await run_sync(
                cleanup_data_for_member, conn, team_name, member_name, KARMA_BASE,
            )
        except Exception as e:
            logger.warning("Data cleanup for member %s failed: %s", member_name, e)

        try:
            from services.remote_sessions import invalidate_caches
            invalidate_caches()
        except Exception as e:
            logger.debug("Cache invalidation failed: %s", e)

    remove_member(conn, team_name, device_id)
    log_event(conn, "member_removed", team_name=team_name, member_name=member_name,
              detail={**cleanup, **data_cleanup})

    return {"ok": True, "name": member_name, **cleanup, **data_cleanup}


@router.get("/members")
async def sync_list_members() -> Any:
    """List all unique members across all teams."""
    conn = _sid._get_sync_conn()
    rows = conn.execute(
        """SELECT m.name, m.device_id, m.member_tag, MIN(m.added_at) as first_added,
                  GROUP_CONCAT(m.team_name) as team_names
           FROM sync_members m
           GROUP BY m.device_id
           ORDER BY m.name""",
    ).fetchall()

    # Get local device_id for "is_you" tagging
    own_device_id: str | None = None
    config = await run_sync(_sid._load_identity)
    if config and config.syncthing:
        own_device_id = config.syncthing.device_id

    # Get device connection info (graceful fallback)
    connected_device_ids: set[str] = set()
    try:
        proxy = _sid.get_proxy()
        devices = await run_sync(proxy.get_devices)
        connected_device_ids = {
            dev["device_id"] for dev in devices if dev.get("connected")
        }
    except Exception:
        pass

    members = []
    for row in rows:
        teams = row["team_names"].split(",") if row["team_names"] else []
        member_tag = row["member_tag"] if "member_tag" in row.keys() else None
        members.append({
            "name": row["name"],
            "device_id": row["device_id"],
            "member_tag": member_tag,
            "connected": row["device_id"] in connected_device_ids,
            "is_you": row["device_id"] == own_device_id,
            "team_count": len(teams),
            "teams": teams,
            "added_at": row["first_added"],
        })

    return {"members": members, "total": len(members)}


def _resolve_member(conn, identifier: str):
    """Resolve identifier (name or device_id) to member rows. Raises 404 if not found."""
    if not (ALLOWED_MEMBER_NAME.match(identifier) or ALLOWED_DEVICE_ID.match(identifier)) or len(identifier) > 128:
        raise HTTPException(400, "Invalid member identifier")
    rows = conn.execute(
        "SELECT team_name, name, device_id, member_tag, machine_tag, added_at FROM sync_members WHERE name = ? ORDER BY added_at",
        (identifier,),
    ).fetchall()
    if not rows:
        rows = conn.execute(
            "SELECT team_name, name, device_id, member_tag, machine_tag, added_at FROM sync_members WHERE device_id = ? ORDER BY added_at",
            (identifier,),
        ).fetchall()
    if not rows:
        raise HTTPException(404, f"Member '{identifier}' not found")
    return rows


@router.get("/members/{identifier}")
async def sync_member_profile(identifier: str) -> Any:
    """Aggregated member profile across all teams. Accepts member name or device_id."""
    conn = _sid._get_sync_conn()
    rows = _resolve_member(conn, identifier)
    member_name = rows[0]["name"]

    member_rows = [dict(r) for r in rows]
    # Use the first device_id found (a member typically has one device)
    device_id = member_rows[0]["device_id"]
    team_names = [r["team_name"] for r in member_rows]

    # Get local device_id for "is_you" tagging
    own_device_id: str | None = None
    config = await run_sync(_sid._load_identity)
    if config and config.syncthing:
        own_device_id = config.syncthing.device_id

    # Get device connection info from Syncthing (graceful fallback)
    connected = False
    in_bytes_total = 0
    out_bytes_total = 0
    devices: list[dict] = []
    try:
        proxy = _sid.get_proxy()
        devices = await run_sync(proxy.get_devices)
        for dev in devices:
            if dev.get("device_id") == device_id:
                connected = dev.get("connected", False)
                in_bytes_total = dev.get("in_bytes_total", 0)
                out_bytes_total = dev.get("out_bytes_total", 0)
                break
    except Exception:
        pass  # Syncthing not running — use defaults

    # Build a device-connected lookup from already-fetched devices
    connected_device_ids: set[str] = {
        dev["device_id"] for dev in devices if dev.get("connected")
    }

    # Batch: fetch all per-project session counts for this member in one query
    # instead of N separate COUNT(*) queries (N = total projects across teams).
    #
    # Event semantics (all logged on the LOCAL machine):
    #   session_packaged  member_name=local_user  → local user sent sessions
    #   session_received  member_name=sender_id   → we received sessions FROM sender
    #
    # So for a given member_name:
    #   session_packaged → sessions they packaged/sent   (only present if they're the local user)
    #   session_received → sessions we received FROM them (i.e. they sent TO us)
    # Both represent "sent by this member" from different perspectives.
    team_placeholders = ",".join("?" for _ in team_names)
    session_count_rows = conn.execute(
        f"""SELECT team_name, project_encoded_name,
                   COUNT(DISTINCT CASE WHEN event_type = 'session_packaged' THEN session_uuid END) AS packaged,
                   COUNT(DISTINCT CASE WHEN event_type = 'session_received' THEN session_uuid END) AS received_from
            FROM sync_events
            WHERE member_name = ?
              AND team_name IN ({team_placeholders})
              AND event_type IN ('session_packaged', 'session_received')
            GROUP BY team_name, project_encoded_name""",
        (member_name, *team_names),
    ).fetchall()

    # Build lookup: (team_name, project_encoded_name) → {sent, received, total}
    # Both event types represent sessions this member sent (packaged locally
    # or received from them remotely). They are mutually exclusive: local user
    # has session_packaged events, remote members have session_received events.
    session_counts: dict[tuple[str, str], dict] = {}
    for r in session_count_rows:
        sent = r["packaged"] + r["received_from"]
        session_counts[(r["team_name"], r["project_encoded_name"])] = {
            "sent": sent,
            "received": 0,  # We don't track when others receive our sessions
            "total": sent,
        }

    # Build per-team info and aggregate stats
    teams = []
    total_sent = 0
    total_received = 0
    project_set: set[str] = set()

    for team_name in team_names:
        members = list_members(conn, team_name)
        projects = list_team_projects(conn, team_name)

        online_count = sum(
            1 for m in members if m["device_id"] in connected_device_ids
        )

        team_projects = []
        for p in projects:
            encoded = p["project_encoded_name"]
            project_set.add(encoded)
            counts = session_counts.get((team_name, encoded), {"sent": 0, "received": 0, "total": 0})
            total_sent += counts["sent"]
            total_received += counts["received"]
            team_projects.append({
                "encoded_name": encoded,
                "name": p.get("path", "").split("/")[-1] if p.get("path") else encoded,
                "session_count": counts["total"],
            })

        teams.append({
            "name": team_name,
            "member_count": len(members),
            "project_count": len(projects),
            "online_count": online_count,
            "projects": team_projects,
        })

    # Last active: most recent event by this member
    last_row = conn.execute(
        "SELECT created_at FROM sync_events WHERE member_name = ? ORDER BY created_at DESC LIMIT 1",
        (member_name,),
    ).fetchone()
    last_active = last_row[0] if last_row else None

    # Session stats — this member's outgoing (what they contributed)
    all_session_stats = []
    for team_name in team_names:
        all_session_stats.extend(
            query_session_stats_by_member(conn, team_name, 30, member_name=member_name)
        )

    # Compute received counts — sessions this member receives
    is_you = device_id == own_device_id
    local_user = config.user_id if config else None
    received_by_date: dict[str, int] = {}

    if local_user and team_names:
        if is_you:
            # What you received from others: session_received events by other members
            recv_rows = conn.execute(
                """SELECT DATE(created_at, 'localtime') AS date, COUNT(DISTINCT session_uuid) AS cnt
                   FROM sync_events
                   WHERE team_name IN ({})
                     AND member_name != ?
                     AND member_name IS NOT NULL
                     AND event_type = 'session_received'
                     AND created_at >= datetime('now', 'localtime', '-30 days')
                   GROUP BY date
                   ORDER BY date""".format(",".join("?" for _ in team_names)),
                (*team_names, member_name),
            ).fetchall()
        else:
            # What this remote member receives from you: session_packaged by local user
            recv_rows = conn.execute(
                """SELECT DATE(created_at, 'localtime') AS date, COUNT(DISTINCT session_uuid) AS cnt
                   FROM sync_events
                   WHERE team_name IN ({})
                     AND member_name = ?
                     AND event_type = 'session_packaged'
                     AND created_at >= datetime('now', 'localtime', '-30 days')
                   GROUP BY date
                   ORDER BY date""".format(",".join("?" for _ in team_names)),
                (*team_names, local_user),
            ).fetchall()
        received_by_date = {r[0]: r[1] for r in recv_rows}

    # Merge received counts into session_stats
    for stat in all_session_stats:
        stat["received"] = received_by_date.pop(stat["date"], 0)
    # Add dates that only have received data (no sent)
    for date, count in sorted(received_by_date.items()):
        all_session_stats.append({
            "date": date, "member_name": member_name,
            "out": 0, "packaged": 0, "received": count,
        })

    total_received = sum(stat["received"] for stat in all_session_stats)

    # Incoming stats — sessions from OTHER members per day (what this member receives)
    incoming_rows = conn.execute(
        """SELECT DATE(created_at, 'localtime') AS date, COUNT(DISTINCT session_uuid) AS incoming
           FROM sync_events
           WHERE team_name IN ({})
             AND member_name != ?
             AND member_name IS NOT NULL
             AND event_type IN ('session_packaged', 'session_received')
             AND created_at >= datetime('now', 'localtime', '-30 days')
           GROUP BY date
           ORDER BY date""".format(",".join("?" for _ in team_names)),
        (*team_names, member_name),
    ).fetchall()
    incoming_stats = [{"date": r[0], "incoming": r[1]} for r in incoming_rows]

    # Recent activity events
    activity_rows = query_events(conn, member_name=member_name, limit=50)

    return {
        "user_id": member_name,
        "device_id": device_id,
        "connected": connected,
        "is_you": is_you,
        "in_bytes_total": in_bytes_total,
        "out_bytes_total": out_bytes_total,
        "teams": teams,
        "stats": {
            "total_sessions": total_sent + total_received,
            "sessions_sent": total_sent,
            "sessions_received": total_received,
            "total_projects": len(project_set),
            "last_active": last_active,
        },
        "session_stats": all_session_stats,
        "incoming_stats": incoming_stats,
        "activity": activity_rows,
    }


@router.get("/members/{identifier}/activity")
async def sync_member_activity(
    identifier: str,
    event_type: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
) -> Any:
    """Activity feed for a single member across all teams. Accepts member name or device_id."""
    limit, offset = cap_pagination(limit, offset)
    event_type = validate_event_type_filter(event_type)

    conn = _sid._get_sync_conn()
    rows = _resolve_member(conn, identifier)
    member_name = rows[0]["name"]

    events = query_events(
        conn, event_type=event_type, member_name=member_name, limit=limit, offset=offset
    )
    return {"events": events}


@router.get("/teams/{team_name}/members/{device_id}/settings")
async def sync_get_member_settings(team_name: str, device_id: str) -> Any:
    """Get member sync settings with resolved effective values."""
    if not ALLOWED_PROJECT_NAME.match(team_name):
        raise HTTPException(400, "Invalid team name")
    device_id = validate_device_id(device_id)

    conn = _sid._get_sync_conn()
    team = get_team(conn, team_name)
    if team is None:
        raise HTTPException(404, f"Team '{team_name}' not found")

    # Direct lookup by device_id scoped to this team
    member = get_member_by_device_id(conn, device_id, team_name=team_name)
    if member is None:
        raise HTTPException(404, f"Member with device '{device_id}' not found in team '{team_name}'")

    settings = {}
    for key in VALID_SETTING_KEYS:
        value, source = get_effective_setting(conn, key, team_name=team_name, device_id=device_id)
        settings[key] = {"value": value, "source": source}

    return {
        "team_name": team_name,
        "device_id": device_id,
        "member_name": member["name"],
        "settings": settings,
    }


@router.patch("/teams/{team_name}/members/{device_id}/settings")
async def sync_update_member_settings(
    team_name: str, device_id: str, req: UpdateMemberSettingsRequest
) -> Any:
    """Update member sync settings (per-team overrides)."""
    if not ALLOWED_PROJECT_NAME.match(team_name):
        raise HTTPException(400, "Invalid team name")
    device_id = validate_device_id(device_id)

    conn = _sid._get_sync_conn()
    team = get_team(conn, team_name)
    if team is None:
        raise HTTPException(404, f"Team '{team_name}' not found")

    member = get_member_by_device_id(conn, device_id, team_name=team_name)
    if member is None:
        raise HTTPException(404, f"Member with device '{device_id}' not found in team '{team_name}'")

    config = await run_sync(_sid._load_identity)
    actor_name = config.user_id if config else None
    scope = f"member:{team_name}:{device_id}"
    changes = {}

    if req.sync_direction is not None:
        if req.sync_direction not in VALID_SYNC_DIRECTIONS:
            raise HTTPException(
                400,
                f"Invalid sync_direction. Must be one of: {', '.join(sorted(VALID_SYNC_DIRECTIONS))}",
            )
        old = set_setting(conn, scope, "sync_direction", req.sync_direction)
        changes["sync_direction"] = {"old": old or "both", "new": req.sync_direction}
    elif "sync_direction" in (req.model_fields_set or set()):
        # Explicitly sent null — clear the override
        old_val = get_setting(conn, scope, "sync_direction")
        delete_setting(conn, scope, "sync_direction")
        value, source = get_effective_setting(conn, "sync_direction", team_name=team_name, device_id=device_id)
        changes["sync_direction"] = {"old": old_val, "new": value, "source": source, "cleared": True}

    if not changes:
        raise HTTPException(400, "No settings provided to update")

    log_event(
        conn,
        "settings_changed",
        team_name=team_name,
        member_name=actor_name,
        detail={"target_member": member["name"], "target_device": device_id, **changes},
    )

    # Update own metadata state (settings changed)
    try:
        from services.sync_metadata_writer import update_own_metadata
        if config is not None:
            update_own_metadata(config, conn, team_name)
    except Exception as e:
        logger.debug("Failed to update own metadata after member settings change: %s", e)

    return {"ok": True, "team_name": team_name, "device_id": device_id, "changes": changes}

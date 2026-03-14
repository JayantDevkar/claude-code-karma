"""Sync runtime operation endpoints (extracted from sync_status.py)."""

import logging
from pathlib import Path
from typing import Any, Optional

from fastapi import APIRouter, HTTPException

from db.sync_queries import (
    get_team, list_teams, list_members, list_team_projects,
    upsert_team_project, remove_team_project,
    find_project_by_git_suffix,
    log_event, log_session_packaged_events,
    query_events, query_session_stats_by_member,
)
from services.folder_id import build_outbox_id
import services.sync_identity as _sid
from services.sync_identity import (
    validate_project_name, _trigger_remote_reindex_bg,
    validate_event_type_filter, cap_pagination,
    ALLOWED_PROJECT_NAME, ALLOWED_MEMBER_NAME,
    _VALID_EVENT_TYPES, _compute_proj_suffix,
)
from services.sync_folders import ensure_outbox_folder
from services.syncthing_proxy import SyncthingNotRunning, run_sync

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/sync", tags=["sync"])


# ─── Rescan ──────────────────────────────────────────────────────────


@router.post("/rescan")
async def sync_rescan_all() -> Any:
    """Trigger an immediate rescan of all Syncthing folders."""
    proxy = _sid.get_proxy()
    try:
        return await run_sync(proxy.rescan_all)
    except SyncthingNotRunning:
        raise HTTPException(503, "Syncthing is not running")


# ─── Sync now ────────────────────────────────────────────────────────


async def _do_sync_now(config, conn, team_name: str) -> dict:
    """Core sync-now logic: package unsynced sessions for all projects in a team.

    SessionPackager only packages sessions not already in the outbox,
    so calling this repeatedly is safe and avoids duplicate data.
    """
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

                    # Fix Syncthing outbox folder path
                    try:
                        proxy = _sid.get_proxy()
                        git_id = local.get("git_identity")
                        proj_suffix = _compute_proj_suffix(git_id, resolved_path, resolved_encoded)
                        outbox_id = build_outbox_id(config.member_tag, proj_suffix)
                        try:
                            await run_sync(proxy.remove_folder, outbox_id)
                        except Exception as e:
                            logger.debug("Remove old outbox folder %s no-op: %s", outbox_id, e)
                        members = list_members(conn, team_name)
                        all_device_ids = [
                            m["device_id"] for m in members
                            if m["device_id"] and m["device_id"] != (config.syncthing.device_id if config.syncthing else None)
                        ]
                        await ensure_outbox_folder(proxy, config, resolved_encoded, proj_suffix, all_device_ids)
                    except Exception as e:
                        logger.warning("sync-now: could not fix outbox folder path: %s", e)
                else:
                    continue
            else:
                continue

        outbox = KARMA_BASE / "remote-sessions" / config.member_tag / encoded
        outbox.mkdir(parents=True, exist_ok=True)

        try:
            wt_dirs = find_all_worktree_dirs(encoded, proj_path, projects_dir)
            packager = SessionPackager(
                project_dir=claude_dir,
                user_id=config.user_id,
                machine_id=config.machine_id,
                device_id=config.syncthing.device_id if config.syncthing else None,
                project_path=proj_path,
                extra_dirs=wt_dirs,
                team_name=team_name,
                member_tag=config.member_tag,
            )
            manifest = await run_sync(packager.package, outbox)
            packaged_count += manifest.session_count
            log_session_packaged_events(
                conn, team_name, encoded, config.user_id, manifest.sessions
            )
        except Exception as e:
            logger.warning("sync-now: failed to package %s: %s", encoded, e)
            errors.append(f"{encoded}: {e}")

    log_event(
        conn, "sync_now", team_name=team_name,
        detail={"packaged_count": packaged_count, "errors": errors},
    )

    return {
        "packaged_count": packaged_count,
        "project_count": len(projects),
        "errors": errors,
    }


@router.post("/teams/{team_name}/sync-now")
async def sync_team_sync_now(team_name: str) -> Any:
    """Trigger an immediate session package for all projects in a team."""
    if not ALLOWED_PROJECT_NAME.match(team_name):
        raise HTTPException(400, "Invalid team name")

    config = await run_sync(_sid._load_identity)
    if config is None:
        raise HTTPException(400, "Not initialized")

    conn = _sid._get_sync_conn()
    team = get_team(conn, team_name)
    if team is None:
        raise HTTPException(404, f"Team '{team_name}' not found")

    result = await _do_sync_now(config, conn, team_name)
    return {"ok": True, "team_name": team_name, **result}


# ─── Global sync-now ─────────────────────────────────────────────────


@router.post("/sync-now")
async def sync_all_teams_now() -> Any:
    """Trigger an immediate session package for ALL teams (only unsynced sessions)."""
    config = await run_sync(_sid._load_identity)
    if config is None:
        raise HTTPException(400, "Not initialized")

    conn = _sid._get_sync_conn()
    teams_data = list_teams(conn)
    syncthing_teams = [t for t in teams_data if t["backend"] == "syncthing"]

    if not syncthing_teams:
        raise HTTPException(400, "No syncthing teams configured")

    total_packaged = 0
    total_projects = 0
    all_errors = []
    team_results = []

    for t in syncthing_teams:
        result = await _do_sync_now(config, conn, t["name"])
        total_packaged += result["packaged_count"]
        total_projects += result["project_count"]
        all_errors.extend(result["errors"])
        team_results.append({
            "team_name": t["name"],
            "packaged_count": result["packaged_count"],
            "project_count": result["project_count"],
        })

    return {
        "ok": True,
        "total_packaged": total_packaged,
        "total_projects": total_projects,
        "teams": team_results,
        "errors": all_errors,
    }


# ─── Activity & stats ────────────────────────────────────────────────


@router.get("/activity")
async def sync_activity(
    team_name: Optional[str] = None,
    event_type: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
) -> Any:
    """Get recent sync activity events and bandwidth stats."""
    limit, offset = cap_pagination(limit, offset)

    # Validate team_name if provided
    if team_name and not ALLOWED_PROJECT_NAME.match(team_name):
        team_name = None

    event_type = validate_event_type_filter(event_type)

    conn = _sid._get_sync_conn()
    events = query_events(
        conn, team_name=team_name, event_type=event_type,
        limit=limit, offset=offset,
    )

    # Best-effort bandwidth from Syncthing
    bandwidth = {"upload_rate": 0, "download_rate": 0, "upload_total": 0, "download_total": 0}
    try:
        proxy = _sid.get_proxy()
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
    member_name: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
) -> Any:
    """Team-scoped activity feed for the team detail page."""
    if not ALLOWED_PROJECT_NAME.match(team_name):
        raise HTTPException(400, "Invalid team name")

    limit, offset = cap_pagination(limit, offset)
    event_type = validate_event_type_filter(event_type)

    # Validate member_name
    if member_name and not ALLOWED_MEMBER_NAME.match(member_name):
        member_name = None

    conn = _sid._get_sync_conn()
    if not conn.execute("SELECT 1 FROM sync_teams WHERE name = ?", (team_name,)).fetchone():
        raise HTTPException(404, f"Team '{team_name}' not found")

    events = query_events(
        conn, team_name=team_name, event_type=event_type,
        member_name=member_name, limit=limit, offset=offset,
    )
    return {"events": events}


@router.get("/teams/{team_name}/session-stats")
async def sync_team_session_stats(
    team_name: str,
    days: int = 30,
) -> Any:
    """Session activity stats per member per day for charts."""
    if not ALLOWED_PROJECT_NAME.match(team_name):
        raise HTTPException(400, "Invalid team name")

    days = max(1, min(days, 365))

    conn = _sid._get_sync_conn()
    if not conn.execute("SELECT 1 FROM sync_teams WHERE name = ?", (team_name,)).fetchone():
        raise HTTPException(404, f"Team '{team_name}' not found")

    stats = query_session_stats_by_member(conn, team_name, days)
    return {"stats": stats, "days": days}

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
    get_watcher, validate_project_name, _trigger_remote_reindex_bg,
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
                    # correct encoded path via ensure_outbox_folder.
                    try:
                        proxy = _sid.get_proxy()
                        git_id = local.get("git_identity")
                        proj_suffix = _compute_proj_suffix(git_id, resolved_path, resolved_encoded)
                        outbox_id = build_outbox_id(config.user_id, proj_suffix)
                        # Remove the potentially-wrong folder so ensure_outbox_folder
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
                        await ensure_outbox_folder(proxy, config, resolved_encoded, proj_suffix, all_device_ids)
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
                device_id=config.syncthing.device_id if config.syncthing else None,
                project_path=proj_path,
                extra_dirs=wt_dirs,
                team_name=team_name,
            )
            manifest = await run_sync(packager.package, outbox)
            packaged_count += manifest.session_count
            # Log session_packaged per unique session (dedup)
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
    config = await run_sync(_sid._load_identity)
    if config is None:
        raise HTTPException(400, "Not initialized")

    conn = _sid._get_sync_conn()
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
        "device_id": config.syncthing.device_id if config.syncthing else None,
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
            conn = _sid._get_sync_conn()
            for team in teams:
                log_event(conn, "watcher_stopped", team_name=team)
        except Exception as e:
            logger.debug("Failed to log watcher_stopped events: %s", e)
    return result


# ─── Activity & stats ────────────────────────────────────────────────


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

    # Support comma-separated event types — validate each part
    if event_type:
        parts = [t.strip() for t in event_type.split(",") if t.strip()]
        valid_parts = [t for t in parts if t in _VALID_EVENT_TYPES]
        event_type = ",".join(valid_parts) if valid_parts else None

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

    limit = max(1, min(limit, 200))
    offset = max(0, min(offset, 10000))

    # Support comma-separated event types — validate each part
    if event_type:
        parts = [t.strip() for t in event_type.split(",") if t.strip()]
        valid_parts = [t for t in parts if t in _VALID_EVENT_TYPES]
        event_type = ",".join(valid_parts) if valid_parts else None

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

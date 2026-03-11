"""Sync project management endpoints — extracted from sync_status.py."""

import logging
from pathlib import Path
from typing import Any, Optional

from fastapi import APIRouter, HTTPException

from db.sync_queries import (
    get_team,
    list_members,
    list_team_projects,
    add_team_project,
    remove_team_project,
    log_event,
    count_sessions_for_project,
)
from schemas import AddTeamProjectRequest
from services.folder_id import (
    build_outbox_id,
    is_outbox_folder,
    parse_outbox_id,
)
import services.sync_identity as _sid
from services.sync_identity import (
    validate_project_name,
    validate_project_path,
    _trigger_remote_reindex_bg,
    ALLOWED_PROJECT_NAME,
    _compute_proj_suffix,
)
from services.sync_folders import ensure_outbox_folder, ensure_inbox_folders
from services.syncthing_proxy import SyncthingNotRunning, run_sync

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/sync", tags=["sync"])


@router.get("/projects")
async def sync_projects() -> Any:
    """List all configured Syncthing folders."""
    proxy = _sid.get_proxy()
    try:
        folders = await run_sync(proxy.get_folder_status)
        return {"folders": folders}
    except SyncthingNotRunning:
        raise HTTPException(status_code=503, detail="Syncthing is not running")


@router.post("/projects/{project_name}/sync-now")
async def sync_project_sync_now(project_name: str) -> Any:
    """Trigger an immediate rescan for a project's Syncthing folder."""
    validate_project_name(project_name)
    proxy = _sid.get_proxy()
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


@router.post("/teams/{team_name}/projects")
async def sync_add_team_project(team_name: str, req: AddTeamProjectRequest) -> Any:
    """Add a project to a sync group."""
    validate_project_name(req.name)
    if not ALLOWED_PROJECT_NAME.match(team_name):
        raise HTTPException(400, "Invalid team name")
    validated_path = validate_project_path(req.path)

    conn = _sid._get_sync_conn()
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
    session_count = count_sessions_for_project(conn, encoded)

    config = await run_sync(_sid._load_identity)
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

            proxy = _sid.get_proxy()
            await ensure_outbox_folder(proxy, config, encoded, proj_suffix, device_ids)
            folders_created["outboxes"] = 1

            # Create inbox folders for each existing member's outbox
            inbox_result = await ensure_inbox_folders(
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

    conn = _sid._get_sync_conn()
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
        config = await run_sync(_sid._load_identity)
        if config is not None:
            proxy = _sid.get_proxy()
            # Remove outbox folder
            outbox_id = build_outbox_id(config.user_id, proj_suffix)
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
                inbox_id = build_outbox_id(m['name'], proj_suffix)
                try:
                    await run_sync(proxy.remove_folder, inbox_id)
                    folders_removed += 1
                except Exception as e:
                    logger.debug("Failed to remove inbox folder %s: %s", inbox_id, e)
    except Exception as e:
        logger.warning("Syncthing cleanup for project %s failed: %s", project_name, e)

    # Clean up remote session data (filesystem + DB)
    try:
        from db.sync_queries import cleanup_data_for_project
        stats = cleanup_data_for_project(conn, team_name, project_name)
        if stats["sessions_deleted"] or stats["dirs_deleted"]:
            logger.info(
                "Cleaned up %d sessions and %d dirs for %s/%s",
                stats["sessions_deleted"], stats["dirs_deleted"],
                team_name, project_name,
            )
    except Exception as e:
        logger.warning("Failed to clean up project data: %s", e)

    remove_team_project(conn, team_name, project_name)
    log_event(conn, "project_removed", team_name=team_name, project_encoded_name=project_name)

    return {"ok": True, "name": project_name, "folders_removed": folders_removed}


@router.get("/teams/{team_name}/project-status")
async def sync_team_project_status(team_name: str) -> Any:
    """Get per-project sync status with local/packaged/received counts."""
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
        remote_base = KARMA_BASE / "remote-sessions"
        if remote_base.is_dir():
            for user_dir in remote_base.iterdir():
                if not user_dir.is_dir():
                    continue
                dir_name = user_dir.name
                # Skip own outbox (check both dir name and resolved user_id)
                if dir_name == config.user_id:
                    continue
                from services.remote_sessions import _resolve_user_id
                resolved = _resolve_user_id(user_dir, conn=conn)
                if resolved == config.user_id:
                    continue
                inbox = user_dir / encoded / "sessions"
                if inbox.is_dir():
                    count = sum(
                        1
                        for f in inbox.glob("*.jsonl")
                        if not f.name.startswith("agent-")
                    )
                    if count > 0:
                        received_counts[resolved] = count

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

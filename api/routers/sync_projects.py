"""Sync project management endpoints — extracted from sync_status.py."""

import logging
from pathlib import Path
from typing import Any, Optional

from fastapi import APIRouter, HTTPException

from db.sync_queries import (
    get_team,
    list_members,
    list_team_projects,
    list_all_team_projects,
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


def _compute_project_stats(
    encoded: str,
    proj_path: str,
    config: Any,
    projects_dir: Path,
    conn: Any,
) -> dict:
    """Compute local/packaged/received counts for a single project."""
    from karma.config import KARMA_BASE
    from karma.worktree_discovery import find_all_worktree_dirs

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

    outbox = KARMA_BASE / "remote-sessions" / config.member_tag / encoded / "sessions"
    packaged_count = 0
    if outbox.is_dir():
        packaged_count = sum(
            1
            for f in outbox.glob("*.jsonl")
            if not f.name.startswith("agent-")
        )

    received_counts: dict[str, int] = {}
    remote_base = KARMA_BASE / "remote-sessions"
    if remote_base.is_dir():
        for user_dir in remote_base.iterdir():
            if not user_dir.is_dir():
                continue
            dir_name = user_dir.name
            if dir_name == config.user_id or dir_name == config.member_tag:
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

    return {
        "name": encoded,
        "encoded_name": encoded,
        "path": proj_path,
        "local_count": local_count,
        "packaged_count": packaged_count,
        "received_counts": received_counts,
        "gap": max(0, local_count - packaged_count),
    }


@router.get("/project-status")
async def sync_all_project_status() -> Any:
    """Get per-project sync status across ALL teams (deduplicated)."""
    config = await run_sync(_sid._load_identity)
    if config is None:
        raise HTTPException(400, "Not initialized")

    conn = _sid._get_sync_conn()
    all_projects = list_all_team_projects(conn)
    projects_dir = Path.home() / ".claude" / "projects"

    # Deduplicate by encoded_name, collect team names
    seen: dict[str, dict] = {}
    for proj in all_projects:
        encoded = proj["project_encoded_name"]
        if encoded not in seen:
            seen[encoded] = {
                "encoded": encoded,
                "path": proj.get("path") or "",
                "teams": [proj["team_name"]],
            }
        else:
            if proj["team_name"] not in seen[encoded]["teams"]:
                seen[encoded]["teams"].append(proj["team_name"])

    result = []
    for info in seen.values():
        stats = _compute_project_stats(
            info["encoded"], info["path"], config, projects_dir, conn
        )
        stats["teams"] = info["teams"]
        result.append(stats)

    return {"projects": result}


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

    # Update own metadata state (subscriptions changed)
    try:
        from services.sync_metadata_writer import update_own_metadata
        if config is not None:
            update_own_metadata(config, conn, team_name)
    except Exception as e:
        logger.debug("Failed to update own metadata: %s", e)

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

    # Clean up Syncthing folders: device subtraction (v3, fixes BP-3/BP-4)
    # Instead of deleting folders, recompute device lists WITHOUT this team.
    # Folders are only deleted when no other team claims them.
    folders_removed = 0
    folders_updated = 0
    try:
        proj = next(p for p in projects if p["project_encoded_name"] == project_name)
        git_identity = proj.get("git_identity")
        proj_suffix = _compute_proj_suffix(git_identity, proj.get("path"), project_name)
        config = await run_sync(_sid._load_identity)
        if config is not None:
            proxy = _sid.get_proxy()
            from db.sync_queries import compute_union_devices_excluding_team

            # Get all configured folders matching this project suffix
            all_folders = await run_sync(proxy.get_configured_folders)
            for folder in all_folders:
                folder_id = folder.get("id", "")
                parsed = parse_outbox_id(folder_id)
                if not parsed or parsed[1] != proj_suffix:
                    continue

                owner_member_tag = parsed[0]
                # Compute desired devices WITHOUT this team
                desired = compute_union_devices_excluding_team(
                    conn, proj_suffix, team_name, owner_member_tag
                )
                self_device_id = config.syncthing.device_id
                if self_device_id:
                    desired.add(self_device_id)

                if len(desired) <= 1 and self_device_id and desired <= {self_device_id}:
                    # No other team claims this folder — delete it
                    try:
                        await run_sync(proxy.remove_folder, folder_id)
                        folders_removed += 1
                    except Exception as e:
                        logger.debug("Failed to remove folder %s: %s", folder_id, e)
                else:
                    # Other teams still need it — update device list
                    try:
                        res = await run_sync(proxy.set_folder_devices, folder_id, list(desired))
                        if res.get("removed"):
                            folders_updated += 1
                    except Exception as e:
                        logger.debug("Failed to update folder %s: %s", folder_id, e)
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

    # Update own metadata state (subscriptions changed)
    try:
        from services.sync_metadata_writer import update_own_metadata
        config = await run_sync(_sid._load_identity)
        if config is not None:
            update_own_metadata(config, conn, team_name)
    except Exception as e:
        logger.debug("Failed to update own metadata: %s", e)

    return {"ok": True, "name": project_name, "folders_removed": folders_removed, "folders_updated": folders_updated}


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

    projects = list_team_projects(conn, team_name)
    projects_dir = Path.home() / ".claude" / "projects"
    result = []

    for proj in projects:
        encoded = proj["project_encoded_name"]
        proj_path = proj.get("path") or ""
        stats = _compute_project_stats(encoded, proj_path, config, projects_dir, conn)
        result.append(stats)

    return {"projects": result}

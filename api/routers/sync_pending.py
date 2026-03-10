import logging
from typing import Any, Optional

from fastapi import APIRouter, HTTPException

from db.sync_queries import (
    get_known_devices, list_team_projects,
    log_event,
)
from services.folder_id import (
    is_handshake_folder, is_karma_folder, is_outbox_folder,
    parse_handshake_id, parse_outbox_id,
)
import services.sync_identity as _sid
from services.sync_identity import (
    _trigger_remote_reindex_bg, _compute_proj_suffix,
)
from services.sync_folders import friendly_project_label
from services.sync_reconciliation import reconcile_introduced_devices
from services.syncthing_proxy import SyncthingNotRunning, run_sync

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/sync", tags=["sync"])


@router.get("/pending")
async def sync_pending() -> Any:
    """List pending folder offers from known team members.

    Enriches each entry with ``label`` (human-readable project name) and
    ``folder_type`` (handshake | sessions | unknown) so the frontend can
    display meaningful info instead of raw folder IDs.
    """
    conn = _sid._get_sync_conn()

    # Load identity early — needed for reconciliation and own-outbox filtering
    config = await run_sync(_sid._load_identity)

    try:
        proxy = _sid.get_proxy()
    except Exception:
        return {"pending": []}

    # Reconcile introduced devices before checking known_devices, so that
    # devices propagated by the Syncthing introducer (multi-device leader)
    # are added to the DB and their pending folders become visible.
    try:
        if config:
            await reconcile_introduced_devices(proxy, config, conn)
    except Exception as e:
        logger.debug("Reconcile in sync_pending failed: %s", e)

    known = get_known_devices(conn)

    if not known:
        return {"pending": []}

    try:
        pending = await run_sync(proxy.get_pending_folders_for_ui, known)
    except SyncthingNotRunning:
        return {"pending": []}
    own_user_id = config.user_id if config else None
    own_machine_id = config.machine_id if config else None

    # Build set of names that identify THIS machine (user_id, machine_id, etc.)
    # The remote leader may have used any of these when creating our outbox folder.
    own_names = set()
    if own_user_id:
        own_names.add(own_user_id)
    if own_machine_id:
        own_names.add(own_machine_id)

    def _is_own_outbox(folder_id: str) -> bool:
        """Check if folder is our own outbox (leader may have used user_id OR machine_id)."""
        parsed = parse_outbox_id(folder_id)
        return parsed is not None and parsed[0] in own_names

    # Separate own outbox folders from other people's outboxes.
    # Own outbox = leader created a receiveonly folder for us, we accept as sendonly.
    # Other outbox = leader's sendonly outbox, we accept as receiveonly.
    filtered = []
    own_outbox_pending = []
    for item in pending:
        folder_id = item["folder_id"]
        # Skip handshake folders — handled automatically
        if is_handshake_folder(folder_id):
            continue
        if _is_own_outbox(folder_id):
            own_outbox_pending.append(item)
        else:
            filtered.append(item)
    pending = own_outbox_pending + filtered

    # Pre-fetch team projects for label enrichment (avoids N+1)
    team_names = {item["from_team"] for item in pending if item.get("from_team")}
    team_projects_map: dict[str, list] = {}
    for tn in team_names:
        try:
            team_projects_map[tn] = list_team_projects(conn, tn)
        except Exception as e:
            logger.debug("Failed to fetch team projects for %s: %s", tn, e)
            team_projects_map[tn] = []

    for item in pending:
        folder_id = item["folder_id"]
        member = item.get("from_member", "unknown")

        if is_outbox_folder(folder_id):
            is_own = _is_own_outbox(folder_id)
            item["folder_type"] = "outbox" if is_own else "sessions"
            parsed = parse_outbox_id(folder_id)
            if parsed:
                owner, suffix = parsed
                # Try to find a matching project for a friendly label
                projects = team_projects_map.get(item.get("from_team", ""), [])
                project_label = None
                for proj in projects:
                    proj_suffix = _compute_proj_suffix(
                        proj.get("git_identity"), proj.get("path"), proj["project_encoded_name"]
                    )
                    if proj_suffix == suffix:
                        git_id = proj.get("git_identity")
                        project_label = git_id.split("/")[-1] if git_id else proj["project_encoded_name"]
                        break
                # Fallback: try to extract a readable project name from the suffix.
                # Suffix is typically "{github-org}-{repo-name}" e.g. "jayantdevkar-claude-code-karma".
                # Try git_identity lookup in DB, or split on the first dash as org/repo.
                if not project_label:
                    project_label = friendly_project_label(conn, folder_id, suffix)
                label = project_label
                item["label"] = label
                if is_own:
                    item["description"] = f"Send your sessions for {label}"
                else:
                    item["description"] = f"Receive sessions from {member} for {label}"
            else:
                item["label"] = folder_id
                if is_own:
                    item["description"] = "Send your sessions"
                else:
                    item["description"] = f"Receive sessions from {member}"
        else:
            item["label"] = folder_id
            item["folder_type"] = "unknown"
            item["description"] = folder_id

    return {"pending": pending}


@router.post("/pending/accept")
async def sync_accept_pending() -> Any:
    """Accept all pending folder offers from known team members."""
    config = await run_sync(_sid._load_identity)
    if config is None:
        raise HTTPException(400, "Not initialized")

    try:
        proxy = _sid.get_proxy()
        conn = _sid._get_sync_conn()
        accepted = await run_sync(proxy.accept_pending_folders, config, conn)
        if accepted:
            log_event(conn, "pending_accepted", member_name=config.user_id,
                      detail={"count": accepted, "phase": "manual"})

        # Reindex remote sessions so any already-synced files appear immediately
        await _trigger_remote_reindex_bg()

        return {"ok": True, "accepted": accepted}
    except SyncthingNotRunning:
        raise HTTPException(503, "Syncthing is not running")
    except Exception as e:
        logger.exception("Failed to accept pending folders: %s", e)
        raise HTTPException(500, "Failed to accept pending folders")


@router.post("/pending/accept/{folder_id:path}")
async def sync_accept_single_folder(folder_id: str) -> Any:
    """Accept a single pending folder offer.

    Only accepts karma-out-* folders from known team members.
    This is the explicit per-folder acceptance that replaces auto-accept.
    """
    if not is_karma_folder(folder_id):
        raise HTTPException(400, "Invalid folder ID: must start with 'karma-'")

    config = await run_sync(_sid._load_identity)
    if config is None:
        raise HTTPException(400, "Not initialized")

    try:
        proxy = _sid.get_proxy()
        conn = _sid._get_sync_conn()
        accepted = await run_sync(
            proxy.accept_pending_folders, config, conn, only_folder_id=folder_id,
        )
        if accepted:
            log_event(conn, "pending_accepted", member_name=config.user_id,
                      detail={"folder_id": folder_id, "phase": "individual"})

        # Reindex remote sessions so any already-synced files appear immediately
        await _trigger_remote_reindex_bg()

        return {"ok": True, "accepted": accepted, "folder_id": folder_id}
    except SyncthingNotRunning:
        raise HTTPException(503, "Syncthing is not running")
    except Exception as e:
        logger.exception("Failed to accept folder %s: %s", folder_id, e)
        raise HTTPException(500, f"Failed to accept folder: {e}")


@router.post("/pending/reject/{folder_id:path}")
async def sync_reject_single_folder(folder_id: str) -> Any:
    """Reject (dismiss) a single pending folder offer.

    Removes the pending folder offer from Syncthing so it no longer appears.
    Only dismisses karma-* folders from known team members.
    """
    if not is_karma_folder(folder_id):
        raise HTTPException(400, "Invalid folder ID: must start with 'karma-'")

    config = await run_sync(_sid._load_identity)
    if config is None:
        raise HTTPException(400, "Not initialized")

    try:
        proxy = _sid.get_proxy()
        result = await run_sync(proxy.reject_pending_folder, folder_id)

        conn = _sid._get_sync_conn()
        log_event(conn, "pending_rejected", member_name=config.user_id,
                  detail={"folder_id": folder_id, "dismissed": result["dismissed"]})

        return result
    except SyncthingNotRunning:
        raise HTTPException(503, "Syncthing is not running")
    except ValueError as e:
        raise HTTPException(404, str(e))
    except Exception as e:
        logger.exception("Failed to reject folder %s: %s", folder_id, e)
        raise HTTPException(500, f"Failed to reject folder: {e}")

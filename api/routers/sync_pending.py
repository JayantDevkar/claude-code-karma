import logging
from typing import Any, Optional

from fastapi import APIRouter, HTTPException

from db.sync_queries import (
    get_known_devices, is_folder_rejected, list_team_projects,
    log_event, reject_folder, unreject_folder,
)
from services.folder_id import (
    is_handshake_folder, is_karma_folder, is_outbox_folder,
    parse_handshake_id, parse_member_tag, parse_outbox_id,
)
import services.sync_identity as _sid
from services.sync_identity import (
    _trigger_remote_reindex_bg, _compute_proj_suffix,
)
from services.sync_folders import friendly_project_label
from services.sync_reconciliation import (
    mesh_pair_from_metadata,
    reconcile_pending_handshakes,
)
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

    # Discover projects from peer metadata — ensures sync_team_projects is
    # populated before the from_team correction loop below.  Without this,
    # joiners see wrong team attribution until the 60s timer fires.
    # Lightweight: only file reads + DB writes, no Syncthing API calls.
    try:
        if config:
            from karma.config import KARMA_BASE
            from db.sync_queries import list_teams
            from services.sync_metadata import read_all_member_states
            from services.sync_metadata_reconciler import _reconcile_projects_from_metadata

            for team in list_teams(conn):
                meta_dir = KARMA_BASE / "metadata-folders" / team["name"]
                if meta_dir.exists():
                    states = read_all_member_states(meta_dir)
                    _reconcile_projects_from_metadata(conn, team["name"], states, config.member_tag)
    except Exception as e:
        logger.debug("Project reconciliation from metadata failed: %s", e)

    # Discover and pair with peers via metadata folders (v3 explicit mesh).
    # Must run before get_pending_folders_for_ui so newly paired devices'
    # pending folders become visible.
    try:
        if config:
            await mesh_pair_from_metadata(proxy, config, conn)
    except Exception as e:
        logger.debug("Mesh pair from metadata in sync_pending failed: %s", e)

    # Process pending handshake folders from already-paired devices
    # (new team membership signals). Must run before get_pending_folders_for_ui
    # so processed handshakes are dismissed and don't appear in the list.
    try:
        if config:
            await reconcile_pending_handshakes(proxy, config, conn)
    except Exception as e:
        logger.debug("Reconcile pending handshakes failed: %s", e)

    known = get_known_devices(conn)

    if not known:
        return {"pending": []}

    try:
        pending = await run_sync(proxy.get_pending_folders_for_ui, known)
    except SyncthingNotRunning:
        return {"pending": []}

    # Filter out folders that are already configured in Syncthing.
    # When a folder is shared with remote devices, those devices may
    # "offer" it back as pending — skip these since they're already set up.
    try:
        configured_folders = await run_sync(proxy.get_configured_folders)
        configured_ids = {f.get("id") for f in configured_folders}
        pending = [item for item in pending if item["folder_id"] not in configured_ids]
    except Exception as e:
        logger.debug("Failed to filter configured folders from pending: %s", e)

    own_user_id = config.user_id if config else None
    own_machine_id = config.machine_id if config else None
    own_member_tag = config.member_tag if config else None

    # Build set of names that identify THIS machine (user_id, machine_id, member_tag, etc.)
    # The remote leader may have used any of these when creating our outbox folder.
    own_names = set()
    if own_user_id:
        own_names.add(own_user_id)
    if own_machine_id:
        own_names.add(own_machine_id)
    if own_member_tag:
        own_names.add(own_member_tag)

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

    # Filter out persistently rejected folders (BP-14: team-scoped)
    pending = [
        item for item in pending
        if not is_folder_rejected(conn, item["folder_id"], team_name=item.get("from_team"))
    ]

    # Pre-fetch projects only for teams referenced by pending items' devices.
    # A multi-team device may have from_team set to any of its teams, so we
    # load projects for ALL teams the device belongs to (via known devices map).
    relevant_teams: set[str] = set()
    for item in pending:
        device_id = item.get("from_device")
        if device_id and device_id in known:
            for _, team in known[device_id]:
                relevant_teams.add(team)
        from_team = item.get("from_team")
        if from_team:
            relevant_teams.add(from_team)

    team_projects_map: dict[str, list] = {}
    for tn in relevant_teams:
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
                # Try to find a matching project across ALL teams.
                # This handles multi-team devices where from_team may
                # not be the team that owns this particular project.
                project_label = None
                for tn, projects in team_projects_map.items():
                    for proj in projects:
                        proj_suffix = _compute_proj_suffix(
                            proj.get("git_identity"), proj.get("path"), proj["project_encoded_name"]
                        )
                        if proj_suffix == suffix:
                            git_id = proj.get("git_identity")
                            project_label = git_id.split("/")[-1] if git_id else proj["project_encoded_name"]
                            # Correct from_team to the actual team that owns this project
                            item["from_team"] = tn
                            break
                    if project_label:
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
                    # Show "user (machine)" if member_tag present
                    user_id, machine_tag = parse_member_tag(member)
                    display_name = f"{user_id} ({machine_tag})" if machine_tag else member
                    item["description"] = f"Receive sessions from {display_name} for {label}"
            else:
                item["label"] = folder_id
                if is_own:
                    item["description"] = "Send your sessions"
                else:
                    user_id, machine_tag = parse_member_tag(member)
                    display_name = f"{user_id} ({machine_tag})" if machine_tag else member
                    item["description"] = f"Receive sessions from {display_name}"
        else:
            item["label"] = folder_id
            item["folder_type"] = "unknown"
            item["description"] = folder_id

    # Deduplicate pending by project suffix — multiple devices offering
    # the same project appear as a single entry with device_count.
    # This prevents confusing UX where the same project appears N times
    # (once per device) when a user has multiple machines.
    grouped: dict[tuple[str, str], dict] = {}  # (suffix, folder_type) → merged item
    ungroupable = []
    for item in pending:
        folder_id = item["folder_id"]
        if is_outbox_folder(folder_id):
            parsed = parse_outbox_id(folder_id)
            if parsed:
                _, suffix = parsed
                key = (suffix, item.get("folder_type", "unknown"))
                if key not in grouped:
                    item["folder_ids"] = [folder_id]
                    item["device_count"] = 1
                    item["devices"] = [{
                        "device_id": item.get("from_device"),
                        "member": item.get("from_member"),
                        "folder_id": folder_id,
                    }]
                    grouped[key] = item
                else:
                    existing = grouped[key]
                    existing["folder_ids"].append(folder_id)
                    existing["device_count"] += 1
                    existing["devices"].append({
                        "device_id": item.get("from_device"),
                        "member": item.get("from_member"),
                        "folder_id": folder_id,
                    })
                continue
        ungroupable.append(item)

    pending = list(grouped.values()) + ungroupable

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

        # Resolve team for this folder (needed for team-scoped unrejection)
        team = None
        try:
            from services.sync_folders import find_team_for_folder
            team = find_team_for_folder(conn, [folder_id])
        except Exception as e:
            logger.debug("Failed to find team for folder %s: %s", folder_id, e)

        # Remove any prior rejection so re-acceptance works (team-scoped)
        unreject_folder(conn, folder_id, team_name=team)

        # Update metadata subscriptions to restore opt-in
        if team:
            try:
                from services.sync_metadata_writer import update_own_metadata
                update_own_metadata(config, conn, team)
            except Exception as e:
                logger.debug("Failed to update metadata after accept: %s", e)

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
        raise HTTPException(500, "Failed to accept folder")


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

        # Persist rejection so the folder is never re-offered
        from services.sync_folders import find_team_for_folder
        team = find_team_for_folder(conn, [folder_id])
        reject_folder(conn, folder_id, team_name=team)

        # Update metadata subscriptions to signal opt-out to other members
        if team:
            try:
                from services.sync_metadata_writer import update_own_metadata
                update_own_metadata(config, conn, team)
            except Exception as e:
                logger.debug("Failed to update metadata after rejection: %s", e)

        log_event(conn, "pending_rejected", member_name=config.user_id,
                  detail={"folder_id": folder_id, "dismissed": result["dismissed"]})

        return result
    except SyncthingNotRunning:
        raise HTTPException(503, "Syncthing is not running")
    except ValueError as e:
        raise HTTPException(404, str(e))
    except Exception as e:
        logger.exception("Failed to reject folder %s: %s", folder_id, e)
        raise HTTPException(500, "Failed to reject folder")

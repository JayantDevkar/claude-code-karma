"""Reconcile local DB state with team metadata folder contents."""

import logging

from db.sync_queries import (
    list_members, list_teams, upsert_member, log_event,
)
from services.sync_metadata import (
    read_all_member_states, read_removal_signals, is_removed,
)

logger = logging.getLogger(__name__)


def reconcile_metadata_folder(config, conn, team_name: str) -> dict:
    """Read the team metadata folder and reconcile with local DB.

    1. Read all member state files -> add missing members to DB
    2. Read removal signals -> if WE are removed, flag for auto-leave
    3. Update identity columns for existing members
    4. Auto-share project folders with newly discovered members

    Returns dict with counts: members_added, members_updated, self_removed,
    and new_device_ids (for callers that need to trigger folder sharing).
    """
    from karma.config import KARMA_BASE

    meta_dir = KARMA_BASE / "metadata-folders" / team_name
    if not meta_dir.exists():
        return {"members_added": 0, "members_updated": 0, "self_removed": False,
                "new_device_ids": []}

    stats = {"members_added": 0, "members_updated": 0, "self_removed": False,
             "new_device_ids": []}

    # Check if WE are removed
    if is_removed(meta_dir, config.member_tag):
        logger.warning("This device has been removed from team %s", team_name)
        stats["self_removed"] = True
        return stats

    # Read all member states and reconcile with DB
    member_states = read_all_member_states(meta_dir)
    existing_members = list_members(conn, team_name)
    existing_tags = {m.get("member_tag") for m in existing_members if m.get("member_tag")}
    existing_devices = {m["device_id"] for m in existing_members}

    # Check removal signals (skip removed members)
    removal_signals = read_removal_signals(meta_dir)
    removed_tags = {r["member_tag"] for r in removal_signals}

    from services.folder_id import parse_member_tag

    for state in member_states:
        mtag = state.get("member_tag", "")
        device_id = state.get("device_id", "")
        user_id = state.get("user_id", "")

        if not mtag or not device_id:
            continue

        # Skip removed members
        if mtag in removed_tags:
            continue

        # Skip self
        if mtag == config.member_tag:
            continue

        if mtag not in existing_tags and device_id not in existing_devices:
            # New member discovered via metadata
            _, machine_tag = parse_member_tag(mtag)
            upsert_member(
                conn, team_name, user_id, device_id=device_id,
                machine_id=state.get("machine_id"),
                machine_tag=machine_tag,
                member_tag=mtag,
            )
            log_event(
                conn, "member_added", team_name=team_name,
                member_name=user_id,
                detail={"source": "metadata_folder", "member_tag": mtag},
            )
            stats["members_added"] += 1
            stats["new_device_ids"].append(device_id)
        elif device_id in existing_devices:
            # Existing member — update identity columns if missing
            _, machine_tag = parse_member_tag(mtag)
            upsert_member(
                conn, team_name, user_id, device_id=device_id,
                machine_id=state.get("machine_id"),
                machine_tag=machine_tag,
                member_tag=mtag,
            )
            stats["members_updated"] += 1

    # Discover projects from peer metadata — joiners learn about the
    # team's project list before accepting any folders.  This fixes
    # broken project links and wrong from_team attribution in pending UI.
    _reconcile_projects_from_metadata(conn, team_name, member_states, config.member_tag)

    # Auto-share project folders with newly discovered members
    if stats["new_device_ids"]:
        _auto_share_with_new_members(config, conn, team_name, stats["new_device_ids"])

    return stats


def _reconcile_projects_from_metadata(
    conn, team_name: str, member_states: list[dict], own_member_tag: str,
) -> int:
    """Discover team projects from peer metadata and populate sync_team_projects.

    Each member publishes their known project list in their metadata state
    file.  We union all peers' project lists and upsert any projects missing
    from our local ``sync_team_projects`` table.  This allows joiners to
    learn about a team's projects before accepting any folders, fixing:
    - Broken project links on the team page
    - Wrong ``from_team`` attribution in the pending UI
    - Missing project labels for incoming session offers
    """
    from db.sync_queries import list_team_projects, upsert_team_project

    existing = {p["project_encoded_name"] for p in list_team_projects(conn, team_name)}
    added = 0

    for state in member_states:
        mtag = state.get("member_tag", "")
        if mtag == own_member_tag:
            continue

        for proj in state.get("projects", []):
            encoded = proj.get("encoded_name", "")
            if not encoded or encoded in existing:
                continue

            upsert_team_project(
                conn, team_name, encoded,
                git_identity=proj.get("git_identity") or None,
                folder_suffix=proj.get("folder_suffix") or None,
            )
            existing.add(encoded)
            added += 1
            logger.info(
                "Discovered project %s in team %s from peer %s",
                encoded, team_name, mtag,
            )

    return added


def _auto_share_with_new_members(config, conn, team_name: str, device_ids: list[str]) -> None:
    """Trigger auto_share_folders for newly discovered members.

    Called from the synchronous reconcile_metadata_folder, so we need to
    handle the async auto_share_folders via asyncio.
    """
    import asyncio
    from services.sync_folders import auto_share_folders
    from services.sync_identity import get_proxy

    try:
        proxy = get_proxy()
    except Exception as e:
        logger.warning("Metadata reconciler: cannot get proxy for auto-share: %s", e)
        return

    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    for device_id in device_ids:
        try:
            if loop and loop.is_running():
                # SAFETY: conn belongs to the caller's thread.  We block on
                # future.result() so the coroutine has exclusive access while
                # we wait.  On timeout we cancel the future to prevent the
                # coroutine from touching conn after we return.
                future = asyncio.run_coroutine_threadsafe(
                    auto_share_folders(proxy, config, conn, team_name, device_id), loop
                )
                try:
                    result = future.result(timeout=30)
                except TimeoutError:
                    future.cancel()
                    logger.warning("auto_share_folders timed out for %s", device_id[:20])
                    continue
            else:
                new_loop = asyncio.new_event_loop()
                try:
                    result = new_loop.run_until_complete(
                        auto_share_folders(proxy, config, conn, team_name, device_id)
                    )
                finally:
                    new_loop.close()
            logger.info(
                "Metadata reconciler: shared folders with %s — outboxes=%d, inboxes=%d",
                device_id[:20], result.get("outboxes", 0), result.get("inboxes", 0),
            )
        except Exception as e:
            logger.warning(
                "Metadata reconciler: failed to share folders with %s: %s",
                device_id[:20], e,
            )


def reconcile_all_teams_metadata(config, conn, *, auto_leave: bool = False) -> dict:
    """Run metadata reconciliation for all teams.

    When auto_leave=True, teams where we've been removed are automatically
    cleaned up (Syncthing folders removed, team deleted from local DB).
    """
    # EC-2: Detect device ID changes before reconciliation
    try:
        from services.sync_reconciliation import detect_device_id_change
        detect_device_id_change(conn, config)
    except Exception as e:
        logger.debug("EC-2 device ID change check failed: %s", e)

    total = {"teams": 0, "members_added": 0, "self_removed_teams": []}
    for team in list_teams(conn):
        result = reconcile_metadata_folder(config, conn, team["name"])
        total["teams"] += 1
        total["members_added"] += result["members_added"]
        if result["self_removed"]:
            total["self_removed_teams"].append(team["name"])
            if auto_leave:
                _auto_leave_team(config, conn, team["name"])
    return total


def _auto_leave_team(config, conn, team_name: str) -> None:
    """Auto-leave a team after detecting removal via metadata folder.

    Cleans up Syncthing folders/devices and deletes the team from local DB.
    Called from sync context (watcher thread), so uses asyncio for async calls.

    Uses pending_leave marker for crash recovery (RC-2): if the process
    crashes during cleanup, the marker survives and cleanup is resumed
    on next startup.
    """
    from db.sync_queries import delete_team, set_pending_leave

    # Mark pending_leave for crash recovery (RC-2)
    try:
        set_pending_leave(conn, team_name)
    except Exception as e:
        logger.warning("Failed to set pending_leave for %s: %s", team_name, e)

    syncthing_cleaned = False
    try:
        import asyncio
        from services.sync_folders import cleanup_syncthing_for_team
        from services.sync_identity import get_proxy

        proxy = get_proxy()
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop and loop.is_running():
            # Inside an async context — use run_coroutine_threadsafe
            future = asyncio.run_coroutine_threadsafe(
                cleanup_syncthing_for_team(proxy, config, conn, team_name), loop
            )
            future.result(timeout=30)
        else:
            # Sync context (watcher thread) — create a new event loop
            loop = asyncio.new_event_loop()
            try:
                loop.run_until_complete(
                    cleanup_syncthing_for_team(proxy, config, conn, team_name)
                )
            finally:
                loop.close()
        syncthing_cleaned = True
    except Exception as e:
        logger.warning("Failed to clean up Syncthing for auto-leave team %s: %s", team_name, e)

    try:
        log_event(conn, "team_left", team_name=team_name,
                  detail={"reason": "removed_via_metadata", "syncthing_cleaned": syncthing_cleaned})
        delete_team(conn, team_name)  # This removes the row, clearing pending_leave
        logger.info("Auto-left team %s (removed via metadata, syncthing_cleaned=%s)", team_name, syncthing_cleaned)
    except Exception as e:
        logger.warning("Failed to delete team %s during auto-leave: %s", team_name, e)

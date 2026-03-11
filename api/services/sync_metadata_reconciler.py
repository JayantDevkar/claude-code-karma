"""Reconcile local DB state with team metadata folder contents."""

import logging
from pathlib import Path

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

    Returns dict with counts: members_added, members_updated, self_removed.
    """
    from karma.config import KARMA_BASE

    meta_dir = KARMA_BASE / "metadata-folders" / team_name
    if not meta_dir.exists():
        return {"members_added": 0, "members_updated": 0, "self_removed": False}

    stats = {"members_added": 0, "members_updated": 0, "self_removed": False}

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
            from services.folder_id import parse_member_tag
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
        elif device_id in existing_devices:
            # Existing member — update identity columns if missing
            from services.folder_id import parse_member_tag
            _, machine_tag = parse_member_tag(mtag)
            upsert_member(
                conn, team_name, user_id, device_id=device_id,
                machine_id=state.get("machine_id"),
                machine_tag=machine_tag,
                member_tag=mtag,
            )
            stats["members_updated"] += 1

    return stats


def reconcile_all_teams_metadata(config, conn, *, auto_leave: bool = False) -> dict:
    """Run metadata reconciliation for all teams.

    When auto_leave=True, teams where we've been removed are automatically
    cleaned up (Syncthing folders removed, team deleted from local DB).
    """
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
    """
    from db.sync_queries import delete_team

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
            # We're inside an async context — create a task
            # This shouldn't normally happen from the watcher thread
            logger.warning("auto_leave_team called from async context for %s", team_name)
        else:
            # Sync context (watcher thread) — create a new event loop
            loop = asyncio.new_event_loop()
            try:
                loop.run_until_complete(
                    cleanup_syncthing_for_team(proxy, config, conn, team_name)
                )
            finally:
                loop.close()
    except Exception as e:
        logger.warning("Failed to clean up Syncthing for auto-leave team %s: %s", team_name, e)

    try:
        log_event(conn, "team_left", team_name=team_name,
                  detail={"reason": "removed_via_metadata"})
        delete_team(conn, team_name)
        logger.info("Auto-left team %s (removed via metadata)", team_name)
    except Exception as e:
        logger.warning("Failed to delete team %s during auto-leave: %s", team_name, e)

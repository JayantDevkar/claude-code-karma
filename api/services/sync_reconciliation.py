"""Sync device reconciliation helpers.

Handles explicit mesh pairing via metadata folders, pending handshake
reconciliation, and auto-acceptance of pending peers.
"""

import logging
from typing import Optional

from db.sync_queries import (
    create_team,
    get_team,
    list_members,
    list_teams,
    log_event,
    upsert_member,
    was_member_removed,
)
from services.folder_id import (
    is_karma_folder,
    parse_handshake_id,
    parse_member_tag,
)
from services.sync_folders import (
    extract_username_from_folder_ids,
    find_team_for_folder,
    resolve_member_tag_from_metadata,
)
from services.sync_policy import should_auto_accept_device
from services.syncthing_proxy import run_sync

logger = logging.getLogger(__name__)


def detect_device_id_change(conn, config) -> int:
    """EC-2: Detect if our Syncthing device_id changed (e.g., reinstall).

    Compares config.syncthing.device_id against sync_members rows for our
    member_tag. If any row has a stale device_id, updates it and logs a warning.

    Returns count of rows updated.
    """
    device_id = config.syncthing.device_id if config.syncthing else None
    member_tag = config.member_tag
    if not device_id or not member_tag:
        return 0

    rows = conn.execute(
        "SELECT team_name, device_id FROM sync_members WHERE member_tag = ? AND device_id != ?",
        (member_tag, device_id),
    ).fetchall()

    if not rows:
        return 0

    logger.warning(
        "EC-2 device ID change detected for %s: updating %d stale rows (old IDs: %s)",
        member_tag, len(rows), ", ".join(r["device_id"][:20] for r in rows),
    )

    conn.execute(
        "UPDATE sync_members SET device_id = ? WHERE member_tag = ? AND device_id != ?",
        (device_id, member_tag, device_id),
    )
    conn.commit()

    from db.sync_queries import log_event
    log_event(conn, "device_id_changed", member_name=member_tag,
              detail={"new_device_id": device_id[:20], "stale_count": len(rows)})

    return len(rows)


def _has_member_tag_collision(conn, team_name: str, member_tag: str, device_id: str) -> bool:
    """BP-9: Detect member_tag collision — same tag, different device.

    Returns True if a member with the same member_tag but a DIFFERENT
    device_id already exists in the team. This indicates a spoofing
    attempt or accidental collision.
    """
    if not member_tag:
        return False
    row = conn.execute(
        "SELECT device_id FROM sync_members WHERE team_name = ? AND member_tag = ? AND device_id != ?",
        (team_name, member_tag, device_id),
    ).fetchone()
    if row:
        logger.critical(
            "BP-9 member_tag collision: tag=%s team=%s existing_device=%s new_device=%s",
            member_tag, team_name, row["device_id"][:20], device_id[:20],
        )
        return True
    return False


async def disable_all_introducers(proxy) -> int:
    """Disable introducer flag on all configured devices (v3 migration).

    v3 replaces Syncthing's introducer mechanism with explicit mesh pairing
    via metadata folders. This function is called once during migration to
    disable all existing introducer flags.

    Returns count of devices updated.
    """
    try:
        configured_devices = await run_sync(proxy.get_devices)
    except Exception as e:
        logger.debug("disable_all_introducers: failed to get devices: %s", e)
        return 0

    disabled = 0
    for device in configured_devices:
        if device.get("is_self"):
            continue
        device_id = device.get("device_id", "")
        if not device_id:
            continue
        # Check if introducer flag is set
        if not device.get("introducer", False):
            continue
        try:
            changed = await run_sync(proxy.set_device_introducer, device_id, False)
            if changed:
                logger.info("Disabled introducer flag on device %s", device_id[:20])
                disabled += 1
        except Exception as e:
            logger.warning("Failed to disable introducer on %s: %s", device_id[:20], e)

    return disabled


async def mesh_pair_from_metadata(proxy, config, conn) -> int:
    """Discover and pair with team peers via metadata folders (v3 explicit mesh).

    Replaces the v2 introducer-based device discovery. For each team:
    1. Read the metadata folder for member states
    2. Read removal signals
    3. For each member not yet configured in Syncthing:
       - Skip if removed, skip if self
       - Pair with their device (no introducer flag)
       - Upsert in DB
    4. Recompute device lists for the team's project folders

    Returns count of new devices paired.
    """
    from services.sync_folders import compute_and_apply_device_lists

    own_device_id = config.syncthing.device_id if config.syncthing else None
    if not own_device_id:
        return 0

    try:
        from karma.config import KARMA_BASE
        from services.sync_metadata import read_all_member_states, read_removal_signals
    except ImportError:
        logger.debug("mesh_pair: karma.config not available")
        return 0

    # Get currently configured device IDs (to skip already-paired)
    try:
        configured_devices = await run_sync(proxy.get_devices)
    except Exception as e:
        logger.debug("mesh_pair: failed to get configured devices: %s", e)
        return 0

    configured_ids = {
        d["device_id"] for d in configured_devices
        if d.get("device_id")
    }

    paired = 0
    teams_to_recompute = set()

    for team in list_teams(conn):
        team_name = team["name"]
        meta_dir = KARMA_BASE / "metadata-folders" / team_name
        if not meta_dir.exists():
            continue

        member_states = read_all_member_states(meta_dir)
        removal_signals = read_removal_signals(meta_dir)
        removed_tags = {r.get("member_tag") for r in removal_signals if r.get("member_tag")}

        for state in member_states:
            member_tag = state.get("member_tag", "")
            device_id = state.get("device_id", "")

            if not member_tag or not device_id:
                continue

            # Skip self
            if member_tag == config.member_tag:
                continue
            if device_id == own_device_id:
                continue

            # Skip removed members
            if member_tag in removed_tags:
                continue

            # Skip if already configured
            if device_id in configured_ids:
                # Still upsert in DB to ensure consistency
                user_id, machine_tag_part = parse_member_tag(member_tag)
                upsert_member(
                    conn, team_name, user_id, device_id=device_id,
                    machine_tag=machine_tag_part,
                    member_tag=member_tag if machine_tag_part else None,
                )
                continue

            # Skip if previously removed from this team
            if was_member_removed(conn, team_name, device_id):
                logger.debug(
                    "mesh_pair: skipping %s for team %s (previously removed)",
                    device_id[:20], team_name,
                )
                continue

            # Pair with new device (NO introducer — explicit mesh)
            try:
                await run_sync(proxy.add_device, device_id, member_tag)
                configured_ids.add(device_id)  # Update local cache
            except Exception as e:
                logger.warning(
                    "mesh_pair: failed to add device %s: %s", device_id[:20], e,
                )
                continue

            # Upsert member in DB
            user_id, machine_tag_part = parse_member_tag(member_tag)
            upsert_member(
                conn, team_name, user_id, device_id=device_id,
                machine_tag=machine_tag_part,
                member_tag=member_tag if machine_tag_part else None,
            )
            log_event(
                conn, "member_auto_accepted", team_name=team_name,
                member_name=member_tag,
                detail={"strategy": "mesh_pair_from_metadata"},
            )
            logger.info(
                "Mesh paired with %s (%s) in team %s",
                member_tag, device_id[:20], team_name,
            )

            paired += 1
            teams_to_recompute.add(team_name)

    # Recompute device lists for affected teams
    for team_name in teams_to_recompute:
        try:
            await compute_and_apply_device_lists(proxy, config, conn, team_name)
        except Exception as e:
            logger.warning("mesh_pair: recompute failed for team %s: %s", team_name, e)

    return paired


async def reconcile_pending_handshakes(proxy, config, conn) -> int:
    """Process pending handshake folders from already-paired devices.

    Closes the gap where an already-paired device offers a karma-join--{user}--{team}
    folder for a NEW team. Neither reconcile_introduced_devices (skips known devices)
    nor auto_accept_pending_peers (skips configured devices) handles this case.

    For each pending handshake folder from a configured (paired) device:
    1. Parse (username, team_name) from the folder ID
    2. Skip if device is already a member of that team (idempotent)
    3. Create team locally if it doesn't exist (like join code flow)
    4. Add device as team member
    5. Auto-share project folders back
    6. Dismiss the handshake folder (signal consumed)

    Handshake folders are team membership signals, not session data, so they
    are always processed regardless of auto_accept_members policy. The policy
    gates unknown device acceptance, not team signals from trusted devices.

    Returns count of new team memberships created.
    """
    own_device_id = config.syncthing.device_id if config.syncthing else None

    try:
        pending_folders = await run_sync(proxy.get_pending_folders)
    except Exception:
        return 0

    if not pending_folders:
        return 0

    # Build set of configured (already-paired) device IDs
    try:
        configured_devices = await run_sync(proxy.get_devices)
    except Exception:
        return 0
    configured_ids = {
        d["device_id"] for d in configured_devices
        if not d.get("is_self")
    }

    reconciled = 0

    for folder_id, info in pending_folders.items():
        parsed = parse_handshake_id(folder_id)
        if not parsed:
            continue

        username, team_name = parsed

        for device_id in info.get("offeredBy", {}):
            # Skip self
            if own_device_id and device_id == own_device_id:
                continue

            # Only process from already-configured (paired) devices.
            # Pending (unpaired) devices are handled by auto_accept_pending_peers.
            if device_id not in configured_ids:
                continue

            # Check if this device was intentionally removed from this team.
            # Stale handshake folders can be re-offered after removal —
            # don't undo an explicit user action.
            if was_member_removed(conn, team_name, device_id):
                logger.debug(
                    "Handshake reconciliation: skipping %s for team %s "
                    "(previously removed)", device_id[:20], team_name,
                )
                try:
                    await run_sync(
                        proxy.dismiss_pending_folder_offer, folder_id, device_id,
                    )
                except Exception:
                    pass
                continue

            # Check if device is already a member of THIS team
            members = list_members(conn, team_name)
            already_member = any(
                m["device_id"] == device_id for m in members
            )

            if already_member:
                # Already in the team — just dismiss the handshake signal
                try:
                    await run_sync(
                        proxy.dismiss_pending_folder_offer, folder_id, device_id,
                    )
                except Exception:
                    pass
                continue

            # RC-1: Skip if team has pending_leave (cleanup in progress).
            # A stale handshake must not re-create a team being left.
            existing_team = get_team(conn, team_name)
            if existing_team and existing_team.get("pending_leave"):
                logger.debug(
                    "Handshake reconciliation: skipping %s for team %s "
                    "(pending_leave in progress)", device_id[:20], team_name,
                )
                try:
                    await run_sync(
                        proxy.dismiss_pending_folder_offer, folder_id, device_id,
                    )
                except Exception:
                    pass
                continue

            # Ensure team exists locally (device may be signaling a team
            # we haven't joined yet — create it like the join code flow)
            if existing_team is None:
                create_team(conn, team_name, backend="syncthing")
                log_event(
                    conn, "team_created", team_name=team_name,
                    detail={"source": "handshake_reconciliation"},
                )
                # Add self as member so we appear in the team's member list
                upsert_member(
                    conn, team_name, config.user_id, device_id=own_device_id,
                    machine_id=config.machine_id, machine_tag=config.machine_tag,
                    member_tag=config.member_tag,
                )

            # Add the offering device as a team member
            # Parse member_tag from the username extracted from handshake folder
            user_id, machine_tag_part = parse_member_tag(username)
            effective_tag = username if machine_tag_part else None

            # BP-9: Collision detection — reject if tag already used by different device
            if effective_tag and _has_member_tag_collision(conn, team_name, effective_tag, device_id):
                try:
                    await run_sync(
                        proxy.dismiss_pending_folder_offer, folder_id, device_id,
                    )
                except Exception:
                    pass
                continue

            upsert_member(conn, team_name, user_id, device_id=device_id,
                          machine_tag=machine_tag_part, member_tag=effective_tag)
            log_event(
                conn, "member_auto_accepted", team_name=team_name,
                member_name=username,
                detail={"strategy": "handshake_reconciliation"},
            )
            logger.info(
                "Handshake reconciliation: added %s (%s) to team %s",
                username, device_id[:20], team_name,
            )

            # Auto-share project folders back to the new member
            try:
                from services.sync_folders import auto_share_folders
                await auto_share_folders(
                    proxy, config, conn, team_name, device_id,
                    metadata_only=True,
                )
            except Exception as e:
                logger.warning(
                    "Handshake reconciliation: failed to share folders "
                    "with %s: %s", username, e,
                )

            # Dismiss the handshake folder (signal consumed)
            try:
                await run_sync(
                    proxy.dismiss_pending_folder_offer, folder_id, device_id,
                )
            except Exception:
                pass

            reconciled += 1

    return reconciled


async def auto_accept_pending_peers(proxy, config, conn) -> tuple[int, dict]:
    """Auto-accept pending devices that offer karma-* folders.

    Only accepts devices when we can verify their identity via folder
    matching — the device must offer a karma-join-* handshake folder or
    karma-out-* session folder that matches a known team.

    Returns:
        (accepted_count, remaining_pending_devices)
    """
    try:
        pending_devices = await run_sync(proxy.get_pending_devices)
    except Exception as e:
        logger.debug("Failed to fetch pending devices: %s", e)
        pending_devices = {}

    accepted = 0
    accepted_ids = set()

    if pending_devices:
        try:
            pending_folders = await run_sync(proxy.get_pending_folders)
        except Exception as e:
            logger.debug("Failed to fetch pending folders: %s", e)
            pending_folders = {}

        # Fetch configured folders once (used as fallback when pending is empty)
        try:
            configured_folders = await run_sync(proxy.get_configured_folders)
        except Exception:
            configured_folders = []

        for device_id in list(pending_devices.keys()):
            device_info = pending_devices.get(device_id, {})
            device_name = device_info.get("name", "")

            # Collect karma-* folders offered by this device (pending)
            karma_folders = []
            for folder_id, info in pending_folders.items():
                if not is_karma_folder(folder_id):
                    continue
                if device_id in info.get("offeredBy", {}):
                    karma_folders.append(folder_id)

            # Also check already-configured folders
            if not karma_folders:
                for folder in configured_folders:
                    folder_id = folder.get("id", "")
                    if not is_karma_folder(folder_id):
                        continue
                    folder_device_ids = {
                        d.get("deviceID") for d in folder.get("devices", [])
                    }
                    if device_id in folder_device_ids:
                        karma_folders.append(folder_id)

            if not karma_folders:
                continue

            username = extract_username_from_folder_ids(karma_folders)
            team_name = find_team_for_folder(conn, karma_folders)

            if not team_name or not username:
                continue

            # Prefer member_tag from metadata folder (authoritative) over
            # folder-ID-derived name which may be a v1-style Syncthing name.
            resolved = resolve_member_tag_from_metadata(team_name, device_id)
            if resolved:
                username = resolved

            # Policy gate: check if auto-accept is enabled for this team.
            # Exception: handshake folders (karma-join--*) are join-code-authorized
            # signals and should always be processed, regardless of auto_accept_members
            # policy. The handshake folder proves the joiner had the join code.
            has_handshake = any(parse_handshake_id(fid) is not None for fid in karma_folders)
            if not has_handshake and not should_auto_accept_device(conn, team_name):
                logger.debug(
                    "Auto-accept disabled for team %s — skipping device %s",
                    team_name, device_id[:20],
                )
                continue

            # Auto-accept device in Syncthing (never as introducer)
            try:
                await run_sync(proxy.add_device, device_id, username)
            except Exception as e:
                logger.warning(
                    "Auto-accept: add_device failed for %s (may already exist via introducer): %s",
                    device_id[:20], e,
                )
                # Don't skip — device may already be configured via introducer.
                # Proceed with upsert_member and auto_share_folders.

            # Add as team member in DB
            user_id, machine_tag_part = parse_member_tag(username)
            effective_tag = username if machine_tag_part else None

            # BP-9: Collision detection — reject if tag already used by different device
            if effective_tag and _has_member_tag_collision(conn, team_name, effective_tag, device_id):
                continue

            upsert_member(conn, team_name, user_id, device_id=device_id,
                          machine_tag=machine_tag_part, member_tag=effective_tag)
            log_event(conn, "member_auto_accepted", team_name=team_name, member_name=username)
            logger.info("Auto-accepted peer %s (%s) into team %s", username, device_id[:20], team_name)

            # Auto-share folders back
            try:
                from services.sync_folders import auto_share_folders
                await auto_share_folders(
                    proxy, config, conn, team_name, device_id, metadata_only=True,
                )
            except Exception as e:
                logger.warning("Auto-accept: failed to share folders back to %s: %s", username, e)

            accepted_ids.add(device_id)
            accepted += 1

    # Return remaining pending devices (minus the ones we accepted)
    remaining = {did: info for did, info in pending_devices.items() if did not in accepted_ids}
    return accepted, remaining

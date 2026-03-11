"""Sync device reconciliation helpers.

Handles auto-acceptance of pending peers, reconciliation of introducer-propagated
devices, and leader introducer flag management.
"""

import logging
from typing import Optional

from db.sync_queries import (
    create_team,
    get_known_devices,
    get_team,
    list_members,
    list_teams,
    list_team_projects,
    log_event,
    upsert_member,
    was_member_removed,
)
from services.folder_id import (
    is_karma_folder,
    parse_handshake_id,
    parse_outbox_id,
)
from services.sync_folders import (
    auto_share_folders,
    extract_username_from_folder_ids,
    find_team_for_folder,
)
from services.sync_identity import _compute_proj_suffix
from services.sync_policy import should_auto_accept_device
from services.syncthing_proxy import run_sync

logger = logging.getLogger(__name__)


async def reconcile_introduced_devices(proxy, config, conn) -> int:
    """Reconcile Syncthing-configured devices with the karma DB.

    When the leader auto-accepts a new member on one device, Syncthing's
    introducer mechanism propagates the new device to the leader's other
    devices. Those devices add the member at the Syncthing level but the
    karma DB never learns about them.

    This function bridges the gap: for each configured device NOT in the
    karma DB, it checks configured karma-* folders shared with that device,
    extracts the username from the folder IDs, finds the team, and creates
    the member record.

    Returns count of members reconciled.
    """
    known_devices = get_known_devices(conn)
    own_device_id = config.syncthing.device_id if config.syncthing else None

    # Get all configured devices from Syncthing
    try:
        configured_devices = await run_sync(proxy.get_devices)
    except Exception as e:
        logger.debug("Reconcile: failed to get configured devices: %s", e)
        return 0

    # Get all configured folders from Syncthing
    try:
        configured_folders = await run_sync(proxy.get_configured_folders)
    except Exception:
        configured_folders = []

    reconciled = 0

    # Build a map of project suffixes → team name
    project_suffix_map: dict[str, str] = {}
    for team in list_teams(conn):
        for proj in list_team_projects(conn, team["name"]):
            ps = _compute_proj_suffix(
                proj.get("git_identity"), proj.get("path"),
                proj["project_encoded_name"],
            )
            project_suffix_map[ps] = team["name"]

    for device in configured_devices:
        device_id = device.get("device_id", "")
        if not device_id:
            continue
        # Skip self
        if device.get("is_self") or (own_device_id and device_id == own_device_id):
            continue
        # Skip already known devices
        if device_id in known_devices:
            continue

        # Syncthing device name — set when the device was first added
        # (via add_device(device_id, username)).  This is the most reliable
        # source of identity for introduced devices because folder IDs
        # identify the folder OWNER, not every device that shares it.
        syncthing_device_name = device.get("name", "")

        # Find receiveonly karma-* folders that include this device.
        karma_folder_ids = []
        for folder in configured_folders:
            folder_id = folder.get("id", "")
            if not is_karma_folder(folder_id):
                continue
            if folder.get("type") != "receiveonly":
                continue
            folder_device_ids = {d.get("deviceID") for d in folder.get("devices", [])}
            if device_id in folder_device_ids:
                karma_folder_ids.append(folder_id)

        if not karma_folder_ids:
            continue

        # Collect ALL (username, team_name) pairs from this device's folders.
        # A device may be in multiple teams — don't stop at the first match.
        memberships: list[tuple[str, str]] = []
        seen_teams: set[str] = set()

        for folder_id in karma_folder_ids:
            hs = parse_handshake_id(folder_id)
            if hs:
                # Handshake folders (karma-join--{user}--{team}) are created
                # BY the device owner, so uname genuinely identifies this
                # device — unlike outbox folders where the name identifies
                # the folder owner, not every device sharing it.
                uname, tname = hs
                if tname not in seen_teams:
                    memberships.append((uname, tname))
                    seen_teams.add(tname)
                continue
            parsed = parse_outbox_id(folder_id)
            if parsed:
                candidate_name, candidate_suffix = parsed
                if candidate_suffix in project_suffix_map:
                    tname = project_suffix_map[candidate_suffix]
                    if tname not in seen_teams:
                        # For receiveonly (inbox) folders, candidate_name is
                        # the folder OWNER whose sessions we receive — NOT the
                        # introduced device.  Use the Syncthing device name
                        # which was set when the device was originally added.
                        name = syncthing_device_name or candidate_name
                        memberships.append((name, tname))
                        seen_teams.add(tname)

        for username, team_name in memberships:
            if was_member_removed(conn, team_name, device_id):
                logger.debug(
                    "Reconcile introduced: skipping %s for team %s (previously removed)",
                    device_id[:20], team_name,
                )
                continue
            upsert_member(conn, team_name, username, device_id=device_id)
            log_event(
                conn, "member_auto_accepted", team_name=team_name,
                member_name=username,
                detail={"strategy": "reconciliation", "source": "introduced_device"},
            )
            # Auto-share project folders back to the introduced device
            try:
                await auto_share_folders(proxy, config, conn, team_name, device_id)
            except Exception as e:
                logger.warning(
                    "Reconcile introduced: failed to share folders with %s: %s",
                    device_id[:20], e,
                )
            logger.info(
                "Reconciled introduced device %s as %s in team %s",
                device_id[:20], username, team_name,
            )
            reconciled += 1

    return reconciled


async def ensure_leader_introducers(proxy, conn, *, own_device_id: str | None = None) -> int:
    """Ensure leader devices are marked as introducers in Syncthing.

    Parses each team's join code to find the leader device_id and sets the
    introducer flag if it is missing. Skips own device_id to avoid wasteful
    API calls.

    Returns count of devices updated.
    """
    updated = 0
    for team in list_teams(conn):
        join_code = team.get("join_code")
        if not join_code:
            continue
        parts = join_code.split(":", 2)
        if len(parts) == 3:
            _, _, leader_device_id = parts
        elif len(parts) == 2:
            _, leader_device_id = parts
        else:
            continue
        # Skip self — can't set introducer on own device
        if own_device_id and leader_device_id == own_device_id:
            continue
        try:
            changed = await run_sync(proxy.set_device_introducer, leader_device_id, True)
            if changed:
                logger.info("Auto-set introducer=True for leader device %s", leader_device_id[:20])
                updated += 1
        except Exception:
            pass
    return updated


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

            # Ensure team exists locally (device may be signaling a team
            # we haven't joined yet — create it like the join code flow)
            team = get_team(conn, team_name)
            if team is None:
                create_team(conn, team_name, backend="syncthing")
                log_event(
                    conn, "team_created", team_name=team_name,
                    detail={"source": "handshake_reconciliation"},
                )
                # Add self as member so we appear in the team's member list
                upsert_member(
                    conn, team_name, config.user_id, device_id=own_device_id,
                )

            # Add the offering device as a team member
            upsert_member(conn, team_name, username, device_id=device_id)
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
                await auto_share_folders(
                    proxy, config, conn, team_name, device_id,
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

            # Policy gate: check if auto-accept is enabled for this team
            if not should_auto_accept_device(conn, team_name):
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
            upsert_member(conn, team_name, username, device_id=device_id)
            log_event(conn, "member_auto_accepted", team_name=team_name, member_name=username)
            logger.info("Auto-accepted peer %s (%s) into team %s", username, device_id[:20], team_name)

            # Auto-share folders back
            try:
                await auto_share_folders(proxy, config, conn, team_name, device_id)
            except Exception as e:
                logger.warning("Auto-accept: failed to share folders back to %s: %s", username, e)

            accepted_ids.add(device_id)
            accepted += 1

    # Return remaining pending devices (minus the ones we accepted)
    remaining = {did: info for did, info in pending_devices.items() if did not in accepted_ids}
    return accepted, remaining

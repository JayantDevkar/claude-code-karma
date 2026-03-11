"""Sync folder management helpers.

Handles Syncthing folder creation, cleanup, and lookup for outbox/inbox/handshake
folders. Used by sync router modules.
"""

import logging
from pathlib import Path
from typing import Optional

from db.sync_queries import (
    get_team,
    list_members,
    list_team_projects,
)
from services.folder_id import (
    build_handshake_id,
    build_outbox_id,
    is_handshake_folder,
    is_karma_folder,
    is_outbox_folder,
    parse_handshake_id,
    parse_outbox_id,
    OUTBOX_PREFIX,
)
from services.sync_identity import _compute_proj_suffix
from services.sync_metadata import build_metadata_folder_id, is_metadata_folder, write_team_info, write_member_state
from services.syncthing_proxy import run_sync

logger = logging.getLogger(__name__)


async def ensure_metadata_folder(
    proxy, config, team_name: str, device_ids: list[str],
    *, is_creator: bool = False,
) -> None:
    """Create or update the team metadata folder (sendreceive, shared by all members).

    Also writes the local member's state file and team.json (if creator).
    """
    from karma.config import KARMA_BASE

    folder_id = build_metadata_folder_id(team_name)
    meta_path = KARMA_BASE / "metadata-folders" / team_name
    meta_path.mkdir(parents=True, exist_ok=True)

    try:
        await run_sync(proxy.update_folder_devices, folder_id, device_ids)
    except ValueError:
        all_ids = list(device_ids)
        if config.syncthing.device_id and config.syncthing.device_id not in all_ids:
            all_ids.append(config.syncthing.device_id)
        await run_sync(proxy.add_folder, folder_id, str(meta_path), all_ids, "sendreceive")

    # Write team.json if we're the creator
    if is_creator:
        write_team_info(meta_path, team_name=team_name, created_by=config.member_tag)

    # Write own member state
    write_member_state(
        meta_path,
        member_tag=config.member_tag,
        user_id=config.user_id,
        machine_id=config.machine_id,
        device_id=config.syncthing.device_id or "",
    )


async def ensure_outbox_folder(proxy, config, encoded: str, proj_suffix: str, device_ids: list[str]) -> None:
    """Create or update an outbox Syncthing folder for a project.

    Tries update_folder_devices first (idempotent), falls back to add_folder.
    """
    from karma.config import KARMA_BASE

    outbox_id = build_outbox_id(config.member_tag, proj_suffix)
    outbox_path = str(KARMA_BASE / "remote-sessions" / config.member_tag / encoded)
    Path(outbox_path).mkdir(parents=True, exist_ok=True)

    try:
        await run_sync(proxy.update_folder_devices, outbox_id, device_ids)
    except ValueError:
        all_ids = list(device_ids)
        if config.syncthing.device_id and config.syncthing.device_id not in all_ids:
            all_ids.append(config.syncthing.device_id)
        await run_sync(proxy.add_folder, outbox_id, outbox_path, all_ids, "sendonly")


async def ensure_inbox_folders(
    proxy, config, members: list[dict], encoded: str, proj_suffix: str,
    *, only_device_id: Optional[str] = None,
    member_subscriptions: Optional[dict[str, dict]] = None,
) -> dict:
    """Create receiveonly inbox folders for team members' outboxes.

    For each member (or a single member if only_device_id is set),
    creates a local receiveonly folder that receives their sessions.
    """
    from karma.config import KARMA_BASE

    result = {"inboxes": 0, "errors": []}

    for m in members:
        if not m["device_id"]:
            continue
        # Skip self
        if config.syncthing.device_id and m["device_id"] == config.syncthing.device_id:
            continue
        # Filter to single device if requested
        if only_device_id and m["device_id"] != only_device_id:
            continue

        # Check subscription opt-out from metadata
        if member_subscriptions:
            device_subs = member_subscriptions.get(m["device_id"], {})
            if device_subs.get(encoded) is False or device_subs.get(proj_suffix) is False:
                member_tag = m.get("member_tag") or m["name"]
                logger.info("Skipping inbox for %s — unsubscribed from %s", member_tag, encoded)
                continue

        member_tag = m.get("member_tag") or m["name"]  # fallback for legacy members
        inbox_path = str(KARMA_BASE / "remote-sessions" / member_tag / encoded)
        inbox_id = build_outbox_id(member_tag, proj_suffix)
        inbox_devices = [m["device_id"]]
        if config.syncthing.device_id:
            inbox_devices.append(config.syncthing.device_id)
        try:
            Path(inbox_path).mkdir(parents=True, exist_ok=True)
            # Try update first (folder may already exist from another team sharing the same project)
            try:
                await run_sync(proxy.update_folder_devices, inbox_id, inbox_devices)
            except ValueError:
                # Folder doesn't exist yet — create it
                await run_sync(proxy.add_folder, inbox_id, inbox_path, inbox_devices, "receiveonly")
            result["inboxes"] += 1
        except Exception as e:
            result["errors"].append(f"inbox {member_tag}/{proj_suffix}: {e}")

    return result


async def ensure_handshake_folder(proxy, config, team_name: str, device_ids: list[str]) -> None:
    """Create a lightweight handshake folder to signal team membership."""
    from karma.config import KARMA_BASE

    folder_id = build_handshake_id(config.member_tag, team_name)
    folder_path = str(KARMA_BASE / "handshakes" / team_name)
    Path(folder_path).mkdir(parents=True, exist_ok=True)

    try:
        await run_sync(proxy.update_folder_devices, folder_id, device_ids)
    except ValueError:
        all_ids = list(device_ids)
        if config.syncthing.device_id and config.syncthing.device_id not in all_ids:
            all_ids.append(config.syncthing.device_id)
        await run_sync(proxy.add_folder, folder_id, folder_path, all_ids, "sendonly")


def friendly_project_label(conn, folder_id: str, parsed_suffix: str) -> str:
    """Extract a human-readable project label from a folder ID.

    Tries these strategies in order:
    1. Match git_identity from projects DB against the folder ID (most reliable)
    2. Match encoded_name from projects DB against the folder ID
    3. Fallback: last component of the suffix
    """
    rest = folder_id[len(OUTBOX_PREFIX):] if is_outbox_folder(folder_id) else parsed_suffix

    # Strategy 1: Find a git_identity whose normalized form appears in the folder ID
    try:
        rows = conn.execute(
            "SELECT git_identity FROM projects WHERE git_identity IS NOT NULL"
        ).fetchall()
        for row in rows:
            git_id = row[0] if isinstance(row, (tuple, list)) else row["git_identity"]
            if not git_id:
                continue
            normalized = git_id.replace("/", "-")
            if rest.endswith(normalized):
                return git_id.split("/")[-1]
    except Exception as e:
        logger.debug("Folder label strategy 1 (git_identity) failed: %s", e)

    # Strategy 2: Find an encoded_name that the folder ID ends with
    try:
        rows = conn.execute("SELECT encoded_name FROM projects").fetchall()
        for row in rows:
            enc = row[0] if isinstance(row, (tuple, list)) else row["encoded_name"]
            if rest.endswith(enc):
                return enc
    except Exception as e:
        logger.debug("Folder label strategy 2 (encoded_name) failed: %s", e)

    # Strategy 3: Fallback — return the suffix as-is
    return parsed_suffix


def find_team_for_folder(conn, folder_ids: list[str]) -> Optional[str]:
    """Find which team a set of karma folder IDs belong to.

    First checks for karma-join-* handshake folders (direct team name).
    Then falls back to matching karma-out-* suffixes against team projects.
    """
    # Fast path: handshake folders contain the team name directly
    for folder_id in folder_ids:
        parsed = parse_handshake_id(folder_id)
        if parsed:
            _, team_name = parsed
            if get_team(conn, team_name):
                return team_name

    # Slow path: match karma-out-* folder suffixes against team project suffixes
    from db.sync_queries import list_teams
    teams = list_teams(conn)
    team_projects = {t["name"]: list_team_projects(conn, t["name"]) for t in teams}

    for folder_id in folder_ids:
        parsed = parse_outbox_id(folder_id)
        if not parsed:
            continue
        _, suffix = parsed
        for team_name, projects in team_projects.items():
            for proj in projects:
                proj_suffix = _compute_proj_suffix(
                    proj.get("git_identity"), proj.get("path"), proj["project_encoded_name"]
                )
                if proj_suffix == suffix:
                    return team_name
    return None


def extract_username_from_folder_ids(folder_ids: list[str]) -> Optional[str]:
    """Extract a karma username from a list of folder IDs.

    Prefers handshake folders which encode the real karma user_id directly.
    Falls back to outbox folder parsing.
    """
    candidates: list[str] = []
    for folder_id in folder_ids:
        hs = parse_handshake_id(folder_id)
        if hs:
            return hs[0]
        parsed = parse_outbox_id(folder_id)
        if parsed:
            candidate_name, _ = parsed
            candidates.append(candidate_name)
    if not candidates:
        return None
    return candidates[0]


async def auto_share_folders(proxy, config, conn, team_name, new_device_id) -> dict:
    """Auto-create Syncthing shared folders for all projects in a team.

    For each project:
    1. Outbox (sendonly): my sessions → teammates
    2. Inbox (receiveonly): new member's sessions → my machine
    """
    projects = list_team_projects(conn, team_name)
    members = list_members(conn, team_name)

    result = {"outboxes": 0, "inboxes": 0, "errors": []}

    # Read member subscriptions from metadata folder
    member_subscriptions: dict[str, dict] = {}
    try:
        from karma.config import KARMA_BASE
        from services.sync_metadata import read_all_member_states
        meta_dir = KARMA_BASE / "metadata-folders" / team_name
        if meta_dir.exists():
            for state in read_all_member_states(meta_dir):
                device = state.get("device_id", "")
                subs = state.get("subscriptions", {})
                if device:
                    member_subscriptions[device] = subs
    except Exception as e:
        logger.debug("Failed to read member subscriptions: %s", e)

    # Add new device to metadata folder
    try:
        all_device_ids = [new_device_id]
        for m in members:
            if m["device_id"] and m["device_id"] not in all_device_ids:
                all_device_ids.append(m["device_id"])
        meta_folder_id = build_metadata_folder_id(team_name)
        await run_sync(proxy.update_folder_devices, meta_folder_id, all_device_ids)
    except Exception as e:
        logger.debug("Failed to update metadata folder devices: %s", e)

    for proj in projects:
        encoded = proj["project_encoded_name"]
        proj_suffix = _compute_proj_suffix(proj.get("git_identity"), proj.get("path"), encoded)

        # Collect all device IDs for this team (deduped)
        all_device_ids = [new_device_id]
        for m in members:
            if m["device_id"] and m["device_id"] not in all_device_ids:
                all_device_ids.append(m["device_id"])

        # 1. My outbox: send my sessions to teammates
        try:
            await ensure_outbox_folder(proxy, config, encoded, proj_suffix, all_device_ids)
            result["outboxes"] += 1
        except Exception as e:
            result["errors"].append(f"outbox {proj_suffix}: {e}")

        # 2. Inbox for the new member (their outbox is our receiveonly inbox)
        inbox_result = await ensure_inbox_folders(
            proxy, config, members, encoded, proj_suffix,
            only_device_id=new_device_id,
            member_subscriptions=member_subscriptions,
        )
        result["inboxes"] += inbox_result["inboxes"]
        result["errors"].extend(inbox_result["errors"])

    return result


async def cleanup_syncthing_for_team(proxy, config, conn, team_name: str) -> dict:
    """Clean up all Syncthing folders and devices for a team (reverse of join).

    Removes:
    - My outbox folders for this team's projects
    - Inbox folders (other members' outboxes) for this team's projects
    - Handshake folders for this team
    - Team member devices (if not used by other teams)
    """
    members = list_members(conn, team_name)
    projects = list_team_projects(conn, team_name)
    result = {"folders_removed": 0, "devices_removed": 0}

    proj_suffixes = set()
    for proj in projects:
        suffix = _compute_proj_suffix(
            proj.get("git_identity"), proj.get("path"), proj["project_encoded_name"]
        )
        proj_suffixes.add(suffix)

    member_tags = {m.get("member_tag") or m["name"] for m in members}
    if config and hasattr(config, 'member_tag'):
        member_tags.add(config.member_tag)

    try:
        folders = await run_sync(proxy.get_configured_folders)
        for folder in folders:
            folder_id = folder.get("id", "")
            if is_outbox_folder(folder_id):
                parsed = parse_outbox_id(folder_id)
                if parsed and parsed[1] in proj_suffixes and parsed[0] in member_tags:
                    try:
                        await run_sync(proxy.remove_folder, folder_id)
                        result["folders_removed"] += 1
                    except Exception as e:
                        logger.warning("Failed to remove folder %s: %s", folder_id, e)
            elif is_handshake_folder(folder_id):
                parsed = parse_handshake_id(folder_id)
                if parsed and parsed[1] == team_name:
                    try:
                        await run_sync(proxy.remove_folder, folder_id)
                        result["folders_removed"] += 1
                    except Exception as e:
                        logger.warning("Failed to remove handshake folder %s: %s", folder_id, e)
            elif is_metadata_folder(folder_id):
                from services.sync_metadata import parse_metadata_folder_id
                parsed_team = parse_metadata_folder_id(folder_id)
                if parsed_team == team_name:
                    try:
                        await run_sync(proxy.remove_folder, folder_id)
                        result["folders_removed"] += 1
                    except Exception as e:
                        logger.warning("Failed to remove metadata folder %s: %s", folder_id, e)
    except Exception as e:
        logger.warning("Failed to scan Syncthing folders for cleanup: %s", e)

    for m in members:
        device_id = m["device_id"]
        if config and config.syncthing.device_id and device_id == config.syncthing.device_id:
            continue
        other_count = conn.execute(
            "SELECT COUNT(*) FROM sync_members WHERE device_id = ? AND team_name != ?",
            (device_id, team_name),
        ).fetchone()[0]
        if other_count == 0:
            try:
                await run_sync(proxy.remove_device, device_id)
                result["devices_removed"] += 1
            except Exception as e:
                logger.warning("Failed to remove device %s: %s", device_id[:20], e)

    return result


async def cleanup_syncthing_for_member(
    proxy, config, conn, team_name: str, member_device_id: str, member_name: str,
) -> dict:
    """Clean up Syncthing state when removing a member (reverse of add-member)."""
    projects = list_team_projects(conn, team_name)
    result = {"folders_removed": 0, "devices_updated": 0}

    proj_suffixes = set()
    for proj in projects:
        suffix = _compute_proj_suffix(
            proj.get("git_identity"), proj.get("path"), proj["project_encoded_name"]
        )
        proj_suffixes.add(suffix)

    try:
        folders = await run_sync(proxy.get_configured_folders)
        for folder in folders:
            folder_id = folder.get("id", "")
            if not is_outbox_folder(folder_id):
                continue
            parsed = parse_outbox_id(folder_id)
            if not parsed or parsed[1] not in proj_suffixes:
                continue
            username, suffix = parsed
            if config and (username == config.member_tag or username == config.user_id):
                try:
                    res = await run_sync(
                        proxy.remove_device_from_folder, folder_id, member_device_id,
                    )
                    if res.get("removed"):
                        result["devices_updated"] += 1
                except Exception as e:
                    logger.warning("Failed to remove device from folder %s: %s", folder_id, e)
            elif username == member_name:
                try:
                    await run_sync(proxy.remove_folder, folder_id)
                    result["folders_removed"] += 1
                except Exception as e:
                    logger.warning("Failed to remove inbox folder %s: %s", folder_id, e)
    except Exception as e:
        logger.warning("Failed to scan Syncthing folders for member cleanup: %s", e)

    handshake_id = build_handshake_id(member_name, team_name)
    try:
        await run_sync(proxy.remove_folder, handshake_id)
    except Exception as e:
        logger.debug("Remove handshake folder %s no-op: %s", handshake_id, e)

    other_count = conn.execute(
        "SELECT COUNT(*) FROM sync_members WHERE device_id = ? AND team_name != ?",
        (member_device_id, team_name),
    ).fetchone()[0]
    if other_count == 0:
        try:
            await run_sync(proxy.remove_device, member_device_id)
        except Exception as e:
            logger.warning("Failed to remove device %s: %s", member_device_id[:20], e)

    return result

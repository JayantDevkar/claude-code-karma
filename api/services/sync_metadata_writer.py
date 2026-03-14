"""Convenience wrapper to write own state to the metadata folder."""

import logging
from pathlib import Path

from services.sync_metadata import write_member_state

logger = logging.getLogger(__name__)


def update_own_metadata(config, conn, team_name: str) -> None:
    """Write/update this device's state in the team metadata folder.

    Reads current subscriptions, projects, and settings from DB, writes
    to the metadata folder so other members can see our state.

    The ``projects`` field publishes the team's project list so joiners
    can populate their local ``sync_team_projects`` before accepting
    folders — fixing broken project links and wrong ``from_team``
    attribution in the pending UI.
    """
    from karma.config import KARMA_BASE
    from db.sync_queries import list_team_projects, get_effective_setting

    meta_dir = KARMA_BASE / "metadata-folders" / team_name
    if not meta_dir.exists():
        logger.debug("Metadata dir not found for team %s", team_name)
        return

    # Build subscriptions from team projects (all subscribed by default)
    projects = list_team_projects(conn, team_name)
    subscriptions = {}
    for proj in projects:
        encoded = proj["project_encoded_name"]
        subscriptions[encoded] = True  # default opt-in

    # Build project list for metadata publication (so joiners can discover projects)
    # Pre-compute suffix per project (reused for both metadata and rejection check)
    from services.sync_identity import _compute_proj_suffix

    projects_meta = []
    suffix_by_encoded: dict[str, str] = {}
    for proj in projects:
        suffix = _compute_proj_suffix(
            proj.get("git_identity"), proj.get("path"), proj["project_encoded_name"]
        )
        suffix_by_encoded[proj["project_encoded_name"]] = suffix
        projects_meta.append({
            "encoded_name": proj["project_encoded_name"],
            "folder_suffix": suffix,
            "git_identity": proj.get("git_identity") or "",
            "project_name": proj.get("project_name") or "",
        })

    # Check rejected folders for opt-out
    try:
        rows = conn.execute(
            "SELECT folder_id FROM sync_rejected_folders WHERE team_name = ?",
            (team_name,),
        ).fetchall()
        if rows:
            from services.folder_id import parse_outbox_id

            rejected_suffixes = set()
            for row in rows:
                fid = row[0] if isinstance(row, tuple) else row["folder_id"]
                parsed = parse_outbox_id(fid)
                if parsed:
                    rejected_suffixes.add(parsed[1])

            for encoded, suffix in suffix_by_encoded.items():
                if suffix in rejected_suffixes:
                    subscriptions[encoded] = False
    except Exception as e:
        logger.debug("Failed to check rejected folders: %s", e)

    sync_direction, _ = get_effective_setting(conn, "sync_direction", team_name=team_name)
    # session_limit comes from sync_teams table, not from settings
    team_row = conn.execute(
        "SELECT sync_session_limit FROM sync_teams WHERE name = ?", (team_name,)
    ).fetchone()
    session_limit = (team_row[0] if team_row else "all") or "all"

    write_member_state(
        meta_dir,
        member_tag=config.member_tag,
        user_id=config.user_id,
        machine_id=config.machine_id,
        device_id=config.syncthing.device_id or "",
        subscriptions=subscriptions,
        projects=projects_meta,
        sync_direction=sync_direction,
        session_limit=session_limit,
    )

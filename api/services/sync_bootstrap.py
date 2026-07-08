"""Start (or restart) the sync worker stack from the current SyncConfig.

Called from two places:
  - API lifespan startup (config already on disk)
  - POST /sync/init (config was JUST written — without this, a freshly
    initialized machine had no reconciliation loop until the API was
    restarted, which is why first-time joiners never discovered teams)
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def start_sync_worker() -> bool:
    """Build config_data from the DB + SyncConfig and start the watcher stack.

    Idempotent: if the manager is already running it is left alone.
    Returns True when the worker is running after the call.
    """
    from models.sync_config import SyncConfig

    config = SyncConfig.load()
    if config is None or not config.member_tag:
        return False

    from services.watcher_singleton import get_watcher_manager

    manager = get_watcher_manager()
    if manager.is_running:
        return True

    from db.connection import get_writer_db
    from db.queries import resolve_encoded_name

    db = get_writer_db()
    teams_rows = db.execute(
        "SELECT name FROM sync_teams WHERE status = 'active'"
    ).fetchall()
    teams_dict: dict = {}
    for (tname,) in teams_rows:
        proj_rows = db.execute(
            "SELECT git_identity, encoded_name, folder_suffix "
            "FROM sync_projects WHERE team_name = ? AND status = 'shared'",
            (tname,),
        ).fetchall()
        projects_dict = {}
        for git_id, enc_name, _fsuffix in proj_rows:
            local_enc = resolve_encoded_name(db, git_id) or enc_name or git_id
            projects_dict[git_id] = {"encoded_name": local_enc, "path": ""}
        if projects_dict:
            teams_dict[tname] = {"projects": projects_dict}

    config_data = {
        "teams": teams_dict,
        "user_id": config.user_id,
        "machine_id": config.machine_id,
        "device_id": config.syncthing.device_id if config.syncthing else "",
        "member_tag": config.member_tag,
    }
    manager.start_all(config_data)
    logger.info(
        "Sync worker started: %d team(s), reconciliation + event listener",
        len(teams_dict),
    )
    return True

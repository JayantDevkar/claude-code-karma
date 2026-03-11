"""Team metadata folder helpers.

Each team has a ``karma-meta--{team}`` Syncthing folder (sendreceive) containing:
  members/{member_tag}.json  — each device writes its own state
  removals/{member_tag}.json — removal signals (creator-only authority)
  team.json                  — team-level info (name, creator)
"""

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

METADATA_PREFIX = "karma-meta--"


def build_metadata_folder_id(team_name: str) -> str:
    """Build ``karma-meta--{team_name}``."""
    if "--" in team_name:
        raise ValueError(f"team_name must not contain '--': {team_name!r}")
    return f"{METADATA_PREFIX}{team_name}"


def parse_metadata_folder_id(folder_id: str) -> Optional[str]:
    """Parse ``karma-meta--{team_name}`` into team_name. Returns None if not metadata."""
    if not folder_id.startswith(METADATA_PREFIX):
        return None
    return folder_id[len(METADATA_PREFIX):]


def is_metadata_folder(folder_id: str) -> bool:
    return folder_id.startswith(METADATA_PREFIX)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def write_member_state(
    meta_dir: Path,
    *,
    member_tag: str,
    user_id: str,
    machine_id: str = "",
    device_id: str = "",
    subscriptions: dict[str, bool] | None = None,
    sync_direction: str = "both",
    session_limit: str = "all",
) -> Path:
    """Write this device's state file to the metadata folder."""
    members_dir = meta_dir / "members"
    members_dir.mkdir(parents=True, exist_ok=True)

    state = {
        "member_tag": member_tag,
        "user_id": user_id,
        "machine_id": machine_id,
        "device_id": device_id,
        "subscriptions": subscriptions or {},
        "sync_direction": sync_direction,
        "session_limit": session_limit,
        "updated_at": _now_iso(),
    }

    path = members_dir / f"{member_tag}.json"
    path.write_text(json.dumps(state, indent=2))
    return path


def write_removal_signal(
    meta_dir: Path,
    *,
    removed_member_tag: str,
    removed_device_id: str,
    removed_by: str,
) -> Path:
    """Write a removal signal for a member."""
    removals_dir = meta_dir / "removals"
    removals_dir.mkdir(parents=True, exist_ok=True)

    signal = {
        "member_tag": removed_member_tag,
        "device_id": removed_device_id,
        "removed_by": removed_by,
        "removed_at": _now_iso(),
    }

    path = removals_dir / f"{removed_member_tag}.json"
    path.write_text(json.dumps(signal, indent=2))
    return path


def write_team_info(meta_dir: Path, *, team_name: str, created_by: str) -> Path:
    """Write team-level info (created once, rarely updated)."""
    info = {
        "name": team_name,
        "created_by": created_by,
        "created_at": _now_iso(),
    }

    path = meta_dir / "team.json"
    path.write_text(json.dumps(info, indent=2))
    return path


def read_all_member_states(meta_dir: Path) -> list[dict]:
    """Read all member state files from the metadata folder."""
    members_dir = meta_dir / "members"
    if not members_dir.exists():
        return []

    states = []
    for path in members_dir.glob("*.json"):
        try:
            states.append(json.loads(path.read_text()))
        except (json.JSONDecodeError, OSError) as e:
            logger.warning("Failed to read member state %s: %s", path, e)
    return states


def read_removal_signals(meta_dir: Path) -> list[dict]:
    """Read all removal signal files."""
    removals_dir = meta_dir / "removals"
    if not removals_dir.exists():
        return []

    signals = []
    for path in removals_dir.glob("*.json"):
        try:
            signals.append(json.loads(path.read_text()))
        except (json.JSONDecodeError, OSError) as e:
            logger.warning("Failed to read removal signal %s: %s", path, e)
    return signals


def read_team_info(meta_dir: Path) -> Optional[dict]:
    """Read team.json. Returns None if not found."""
    path = meta_dir / "team.json"
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        return None


def is_removed(meta_dir: Path, member_tag: str) -> bool:
    """Check if a member_tag has a removal signal."""
    path = meta_dir / "removals" / f"{member_tag}.json"
    return path.exists()


def validate_removal_authority(meta_dir: Path, remover_member_tag: str) -> bool:
    """Check if the remover is the team creator (creator-only removal)."""
    info = read_team_info(meta_dir)
    if info is None:
        return False
    return info.get("created_by") == remover_member_tag

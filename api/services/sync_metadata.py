"""Team metadata folder helpers.

Each team has a ``karma-meta--{team}`` Syncthing folder (sendreceive) containing:
  members/{member_tag}.json  — each device writes its own state
  removals/{member_tag}.json — removal signals (creator-only authority)
  team.json                  — team-level info (name, creator)
"""

import json
import logging
import os
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

METADATA_PREFIX = "karma-meta--"

# Only allow safe characters in member_tag filenames (no path traversal)
_SAFE_FILENAME = re.compile(r"^[a-zA-Z0-9_\-\.]+$")


def _safe_member_path(base_dir: Path, member_tag: str) -> Path:
    """Build a safe path for member_tag, rejecting traversal attempts."""
    if not _SAFE_FILENAME.match(member_tag) or ".." in member_tag:
        raise ValueError(f"Unsafe member_tag for filename: {member_tag!r}")
    return base_dir / f"{member_tag}.json"


def _atomic_write_json(path: Path, data: dict) -> None:
    """Write JSON atomically using tmp+rename (atomic on POSIX)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(data, f, indent=2)
        Path(tmp_path).rename(path)
    except BaseException:
        Path(tmp_path).unlink(missing_ok=True)
        raise


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

    path = _safe_member_path(members_dir, member_tag)
    _atomic_write_json(path, state)
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

    signal = {
        "member_tag": removed_member_tag,
        "device_id": removed_device_id,
        "removed_by": removed_by,
        "removed_at": _now_iso(),
    }

    path = _safe_member_path(removals_dir, removed_member_tag)
    _atomic_write_json(path, signal)
    return path


def write_team_info(meta_dir: Path, *, team_name: str, created_by: str) -> Path:
    """Write team-level info (created once, rarely updated)."""
    info = {
        "name": team_name,
        "created_by": created_by,
        "created_at": _now_iso(),
    }

    path = meta_dir / "team.json"
    _atomic_write_json(path, info)
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
    try:
        path = _safe_member_path(meta_dir / "removals", member_tag)
    except ValueError:
        logger.warning("Unsafe member_tag in is_removed check: %s", member_tag)
        return False
    return path.exists()


def validate_removal_authority(
    meta_dir: Path, remover_member_tag: str, *, conn=None, team_name: str = "",
) -> bool:
    """Check if the remover is the team creator (creator-only removal).

    Falls back to local DB when team.json hasn't synced yet (common P2P race).
    """
    info = read_team_info(meta_dir)
    if info is not None:
        return info.get("created_by") == remover_member_tag

    # team.json not yet synced — fall back to DB join_code (creator's info)
    if conn is not None and team_name:
        try:
            row = conn.execute(
                "SELECT join_code FROM sync_teams WHERE name = ?", (team_name,)
            ).fetchone()
            if row:
                join_code = row[0] if isinstance(row, tuple) else row["join_code"]
                if join_code:
                    # join_code format: team:user_id:device_id
                    parts = join_code.split(":", 2)
                    if len(parts) >= 2:
                        creator_user = parts[1] if len(parts) == 3 else parts[0]
                        # remover_member_tag is "user.machine" — check user part
                        remover_user = remover_member_tag.split(".", 1)[0]
                        return remover_user == creator_user
        except Exception as e:
            logger.debug("DB fallback for removal authority failed: %s", e)

    return False

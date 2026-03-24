"""Metadata folder read/write for P2P team state synchronization.

Each team has a metadata folder (karma-meta--{team}). Members write their
own state files. Leader writes team.json and removal signals.

Member state files use a unified schema — all fields coexist:
  {member_tag, device_id, user_id, machine_tag, status, projects, subscriptions, updated_at}
write_member_state() uses read-merge-write to preserve fields across callers.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from domain.member import Member
    from domain.team import Team


import re

_SAFE_PATH_COMPONENT = re.compile(r"^[a-zA-Z0-9._-]+$")


def _validate_path_component(value: str, label: str) -> None:
    """Reject values that could escape their intended directory."""
    if not value or ".." in value or not _SAFE_PATH_COMPONENT.match(value):
        raise ValueError(f"Unsafe {label}: {value!r}")


class MetadataService:
    def __init__(self, meta_base: Path):
        self.meta_base = meta_base

    def _team_dir(self, team_name: str) -> Path:
        _validate_path_component(team_name, "team_name")
        return self.meta_base / f"karma-meta--{team_name}"

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    def read_team_json(self, team_name: str) -> dict | None:
        """Read team.json from the metadata folder. Returns None if not found."""
        team_dir = self._team_dir(team_name)
        team_json_path = team_dir / "team.json"
        if not team_json_path.exists():
            return None
        try:
            return json.loads(team_json_path.read_text())
        except (json.JSONDecodeError, OSError):
            return None

    def read_team_metadata(self, team_name: str) -> dict[str, dict]:
        """Read all member states and removal signals from metadata folder.

        Returns dict keyed by member_tag. Special key '__removals' contains removal signals.
        """
        team_dir = self._team_dir(team_name)
        if not team_dir.exists():
            return {}

        result: dict[str, dict] = {}

        # Read member states
        members_dir = team_dir / "members"
        if members_dir.exists():
            for f in members_dir.glob("*.json"):
                try:
                    data = json.loads(f.read_text())
                    tag = data.get("member_tag", f.stem)
                    result[tag] = data
                except (json.JSONDecodeError, KeyError):
                    continue

        # Read removal signals
        removed_dir = team_dir / "removed"
        if removed_dir.exists():
            removals = {}
            for f in removed_dir.glob("*.json"):
                try:
                    data = json.loads(f.read_text())
                    tag = data.get("member_tag", f.stem)
                    removals[tag] = data
                except (json.JSONDecodeError, KeyError):
                    continue
            if removals:
                result["__removals"] = removals

        return result

    # ------------------------------------------------------------------
    # Write — team.json
    # ------------------------------------------------------------------

    def _write_team_json(self, team: "Team") -> None:
        """Write team.json only. Creates dirs if needed."""
        team_dir = self._team_dir(team.name)
        team_dir.mkdir(parents=True, exist_ok=True)
        (team_dir / "members").mkdir(exist_ok=True)
        (team_dir / "removed").mkdir(exist_ok=True)

        team_data = {
            "name": team.name,
            "team_id": team.team_id,
            "created_by": team.leader_member_tag,
            "leader_device_id": team.leader_device_id,
            "created_at": team.created_at.isoformat(),
        }
        (team_dir / "team.json").write_text(json.dumps(team_data, indent=2))

    def purge_stale_removals(self, team_name: str) -> None:
        """Delete all removal signal files from a team's metadata folder.

        Called during team creation to prevent stale signals from a previous
        team incarnation with the same name from triggering auto-leave.
        """
        _validate_path_component(team_name, "team_name")
        removed_dir = self._team_dir(team_name) / "removed"
        if not removed_dir.exists():
            return
        for f in removed_dir.glob("*.json"):
            try:
                f.unlink()
            except OSError:
                pass

    # ------------------------------------------------------------------
    # Write — unified member state (read-merge-write)
    # ------------------------------------------------------------------

    def write_member_state(self, team_name: str, member_tag: str, **fields) -> None:
        """Write or update a member's state file using read-merge-write.

        Reads the existing file (if any), merges in the provided fields,
        and writes back. Fields not provided are preserved from the existing
        file, eliminating the schema collision between basic info writes
        (device_id, status) and enriched writes (projects, subscriptions).

        Always sets updated_at to now.
        """
        _validate_path_component(member_tag, "member_tag")
        team_dir = self._team_dir(team_name)
        (team_dir / "members").mkdir(parents=True, exist_ok=True)

        member_file = team_dir / "members" / f"{member_tag}.json"

        # Read existing state
        existing: dict = {}
        if member_file.exists():
            try:
                existing = json.loads(member_file.read_text())
            except (json.JSONDecodeError, OSError):
                existing = {}

        # Merge: provided fields overwrite, unset fields preserved
        existing["member_tag"] = member_tag
        existing.update(fields)
        existing["updated_at"] = datetime.now(timezone.utc).isoformat()

        # Atomic write via temp file + os.replace (POSIX-atomic)
        tmp_file = member_file.with_suffix(".tmp")
        tmp_file.write_text(json.dumps(existing, indent=2))
        os.replace(tmp_file, member_file)

    # ------------------------------------------------------------------
    # Write — convenience: team.json + member basic info
    # ------------------------------------------------------------------

    def write_team_state(self, team: "Team", members: list["Member"]) -> None:
        """Write team.json + member state files (basic info, preserving enriched fields).

        Uses write_member_state() for each member, so existing projects/subscriptions
        fields are preserved via read-merge-write.
        """
        self._write_team_json(team)

        for member in members:
            self.write_member_state(
                team.name,
                member.member_tag,
                device_id=member.device_id,
                user_id=member.user_id,
                machine_tag=member.machine_tag,
                status=member.status.value,
            )

    # ------------------------------------------------------------------
    # Write — removal signals
    # ------------------------------------------------------------------

    def write_removal_signal(
        self, team_name: str, member_tag: str, *, removed_by: str, team_id: str = ""
    ) -> None:
        """Write removal signal to metadata folder.

        Includes ``team_id`` so the reconciler can ignore stale signals
        from a previous team incarnation with the same name.
        """
        _validate_path_component(member_tag, "member_tag")
        team_dir = self._team_dir(team_name)
        (team_dir / "removed").mkdir(parents=True, exist_ok=True)

        removal_data = {
            "member_tag": member_tag,
            "removed_by": removed_by,
            "removed_at": datetime.now(timezone.utc).isoformat(),
            "team_id": team_id,
        }
        removal_file = team_dir / "removed" / f"{member_tag}.json"
        removal_file.write_text(json.dumps(removal_data, indent=2))

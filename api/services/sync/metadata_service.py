"""Metadata folder read/write for P2P team state synchronization.

Each team has a metadata folder (karma-meta--{team}). Members write their
own state files. Leader writes team.json and removal signals.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from domain.member import Member
    from domain.project import SharedProject
    from domain.subscription import Subscription
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

    def write_team_state(self, team: "Team", members: list["Member"]) -> None:
        """Write team.json + member state files to metadata folder."""
        team_dir = self._team_dir(team.name)
        team_dir.mkdir(parents=True, exist_ok=True)
        (team_dir / "members").mkdir(exist_ok=True)
        (team_dir / "removed").mkdir(exist_ok=True)

        # Write team.json
        team_data = {
            "name": team.name,
            "created_by": team.leader_member_tag,
            "leader_device_id": team.leader_device_id,
            "created_at": team.created_at.isoformat(),
        }
        (team_dir / "team.json").write_text(json.dumps(team_data, indent=2))

        # Write member state files
        for member in members:
            _validate_path_component(member.member_tag, "member_tag")
            member_data = {
                "member_tag": member.member_tag,
                "device_id": member.device_id,
                "user_id": member.user_id,
                "machine_tag": member.machine_tag,
                "status": member.status.value,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
            member_file = team_dir / "members" / f"{member.member_tag}.json"
            member_file.write_text(json.dumps(member_data, indent=2))

    def write_own_state(
        self,
        team_name: str,
        member_tag: str,
        projects: list["SharedProject"],
        subscriptions: list["Subscription"],
    ) -> None:
        """Write own member state with projects and subscriptions."""
        team_dir = self._team_dir(team_name)
        (team_dir / "members").mkdir(parents=True, exist_ok=True)

        projects_data = [
            {
                "git_identity": p.git_identity,
                "folder_suffix": p.folder_suffix,
            }
            for p in projects
        ]
        subs_data = {
            s.project_git_identity: {
                "status": s.status.value,
                "direction": s.direction.value,
            }
            for s in subscriptions
        }
        state = {
            "member_tag": member_tag,
            "projects": projects_data,
            "subscriptions": subs_data,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        _validate_path_component(member_tag, "member_tag")
        state_file = team_dir / "members" / f"{member_tag}.json"
        state_file.write_text(json.dumps(state, indent=2))

    def write_removal_signal(
        self, team_name: str, member_tag: str, *, removed_by: str
    ) -> None:
        """Write removal signal to metadata folder."""
        _validate_path_component(member_tag, "member_tag")
        team_dir = self._team_dir(team_name)
        (team_dir / "removed").mkdir(parents=True, exist_ok=True)

        removal_data = {
            "member_tag": member_tag,
            "removed_by": removed_by,
            "removed_at": datetime.now(timezone.utc).isoformat(),
        }
        removal_file = team_dir / "removed" / f"{member_tag}.json"
        removal_file.write_text(json.dumps(removal_data, indent=2))

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

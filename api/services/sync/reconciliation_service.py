"""Reconciliation pipeline. Runs every 60s."""
from __future__ import annotations

import json
import logging
import re
import sqlite3
from typing import TYPE_CHECKING

from domain.member import Member, MemberStatus
from domain.project import SharedProjectStatus
from domain.subscription import Subscription, SubscriptionStatus, SyncDirection
from domain.team import Team
from domain.events import SyncEvent, SyncEventType

if TYPE_CHECKING:
    from repositories.team_repo import TeamRepository
    from repositories.member_repo import MemberRepository
    from repositories.project_repo import ProjectRepository
    from repositories.subscription_repo import SubscriptionRepository
    from repositories.event_repo import EventRepository
    from services.syncthing.device_manager import DeviceManager
    from services.syncthing.folder_manager import FolderManager
    from services.sync.metadata_service import MetadataService

logger = logging.getLogger(__name__)

_META_FOLDER_RE = re.compile(r"^karma-meta--(.+)$")


class ReconciliationService:
    """Orchestrates 4-phase reconciliation for all teams.

    Phase 0 (team discovery): Scan Syncthing config for karma-meta--*
        folders that have no local Team row. Bootstrap Team + self-Member
        from the metadata folder's team.json so joiners can participate
        in reconciliation immediately after accepting a device.

    Phase 1 (metadata): Read metadata folder. Detect removal signals
        (auto-leave if own tag removed). Discover new members. Detect
        removed projects (decline subs).

    Phase 2 (mesh pair): For each active member, ensure Syncthing device
        is paired. Skip self.

    Phase 3 (device lists): For each shared project, query accepted
        subscriptions with send|both direction. Compute desired device
        set. Apply declaratively via set_folder_devices.
    """

    def __init__(
        self,
        teams: "TeamRepository",
        members: "MemberRepository",
        projects: "ProjectRepository",
        subs: "SubscriptionRepository",
        events: "EventRepository",
        devices: "DeviceManager",
        folders: "FolderManager",
        metadata: "MetadataService",
        my_member_tag: str,
        my_device_id: str = "",
    ):
        self.teams = teams
        self.members = members
        self.projects = projects
        self.subs = subs
        self.events = events
        self.devices = devices
        self.folders = folders
        self.metadata = metadata
        self.my_member_tag = my_member_tag
        self.my_device_id = my_device_id

    async def run_cycle(self, conn: sqlite3.Connection) -> None:
        """Run full reconciliation for all teams."""
        # Phase 0: discover teams from Syncthing metadata folders
        try:
            await self.phase_team_discovery(conn)
        except Exception as exc:
            logger.warning("phase_team_discovery failed (non-fatal): %s", exc)

        for team in self.teams.list_all(conn):
            await self.phase_metadata(conn, team)
            await self.phase_mesh_pair(conn, team)
            await self.phase_device_lists(conn, team)

    async def phase_team_discovery(self, conn: sqlite3.Connection) -> None:
        """Phase 0: Discover teams from karma-meta--* folders in Syncthing config.

        When a joiner accepts a device, Syncthing may already have metadata
        folders configured but no local team record. This phase reads those
        folders, parses team.json, and bootstraps the local Team + Member rows
        so subsequent phases have something to iterate over.
        """
        try:
            configured_folders = await self.folders._client.get_config_folders()
        except Exception as exc:
            logger.debug("phase_team_discovery: cannot query folders: %s", exc)
            return

        for folder_cfg in configured_folders:
            folder_id = folder_cfg.get("id", "")
            m = _META_FOLDER_RE.match(folder_id)
            if not m:
                continue

            team_name = m.group(1)

            # Skip if team already exists locally
            existing = self.teams.get(conn, team_name)
            if existing is not None:
                continue

            # Read team.json from the metadata folder on disk
            try:
                team_dir = self.metadata._team_dir(team_name)
                team_json_path = team_dir / "team.json"
                if not team_json_path.exists():
                    logger.debug(
                        "phase_team_discovery: no team.json yet for %s", team_name
                    )
                    continue

                team_data = json.loads(team_json_path.read_text())
                leader_member_tag = team_data.get("created_by", "")
                leader_device_id = team_data.get("leader_device_id", "")

                if not leader_member_tag or not leader_device_id:
                    logger.warning(
                        "phase_team_discovery: incomplete team.json for %s", team_name
                    )
                    continue

                # Create team
                team = Team(
                    name=team_name,
                    leader_device_id=leader_device_id,
                    leader_member_tag=leader_member_tag,
                )
                self.teams.save(conn, team)

                # Create self as an ACTIVE member
                member = Member.from_member_tag(
                    member_tag=self.my_member_tag,
                    team_name=team_name,
                    device_id=self.my_device_id,
                    status=MemberStatus.ACTIVE,
                )
                self.members.save(conn, member)

                logger.info(
                    "phase_team_discovery: bootstrapped team '%s' (leader=%s)",
                    team_name,
                    leader_member_tag,
                )
            except Exception as exc:
                logger.warning(
                    "phase_team_discovery: failed to bootstrap team '%s': %s",
                    team_name,
                    exc,
                )

    async def phase_metadata(self, conn: sqlite3.Connection, team) -> None:
        """Phase 1: Read metadata, detect removals, discover members/projects."""
        states = self.metadata.read_team_metadata(team.name)
        if not states:
            return

        # Check removal signals — auto-leave if own tag is in removals
        removals = states.pop("__removals", {})
        if self.my_member_tag in removals:
            await self._auto_leave(conn, team)
            return

        # Discover new members from peer state files
        for tag, state in states.items():
            if tag == self.my_member_tag:
                continue
            existing = self.members.get(conn, team.name, tag)
            if existing is None:
                device_id = state.get("device_id")
                if device_id and not self.members.was_removed(conn, team.name, device_id):
                    new_member = Member.from_member_tag(
                        member_tag=tag,
                        team_name=team.name,
                        device_id=device_id,
                    )
                    # Register as ADDED then immediately activate (they've published state)
                    activated = new_member.activate()
                    self.members.save(conn, activated)
            elif existing.status == MemberStatus.ADDED:
                # Activate if we can see them in metadata (they've acknowledged)
                self.members.save(conn, existing.activate())

        # Discover/remove projects from leader's metadata state
        leader_state = states.get(team.leader_member_tag, {})
        leader_projects = {p["git_identity"] for p in leader_state.get("projects", [])}
        local_projects = self.projects.list_for_team(conn, team.name)

        for lp in local_projects:
            if lp.git_identity not in leader_projects and lp.status == SharedProjectStatus.SHARED:
                # Project removed by leader — decline all non-declined subs
                removed = lp.remove()
                self.projects.save(conn, removed)
                for sub in self.subs.list_for_project(conn, team.name, lp.git_identity):
                    if sub.status != SubscriptionStatus.DECLINED:
                        self.subs.save(conn, sub.decline())

    async def phase_mesh_pair(self, conn: sqlite3.Connection, team) -> None:
        """Phase 2: Pair with undiscovered active team members."""
        members = self.members.list_for_team(conn, team.name)
        for member in members:
            if member.is_active and member.member_tag != self.my_member_tag:
                await self.devices.ensure_paired(member.device_id)

    async def phase_device_lists(self, conn: sqlite3.Connection, team) -> None:
        """Phase 3: Declarative device list sync for all project folders."""
        from services.syncthing.folder_manager import build_outbox_folder_id

        projects = self.projects.list_for_team(conn, team.name)
        team_members = self.members.list_for_team(conn, team.name)

        for project in projects:
            if project.status.value != "shared":
                continue

            accepted = self.subs.list_accepted_for_suffix(conn, project.folder_suffix)

            # Compute desired device set: members with send|both direction
            desired: set[str] = set()
            for sub in accepted:
                if sub.direction in (SyncDirection.SEND, SyncDirection.BOTH):
                    member = self.members.get(conn, sub.team_name, sub.member_tag)
                    if member and member.is_active:
                        desired.add(member.device_id)

            # Apply declaratively to all outbox folders with this suffix
            for m in team_members:
                folder_id = build_outbox_folder_id(m.member_tag, project.folder_suffix)
                await self.folders.set_folder_devices(folder_id, desired)

    async def _auto_leave(self, conn: sqlite3.Connection, team) -> None:
        """Clean up everything for this team on the local machine."""
        projects = self.projects.list_for_team(conn, team.name)
        members = self.members.list_for_team(conn, team.name)
        suffixes = [p.folder_suffix for p in projects]
        tags = [m.member_tag for m in members]

        await self.folders.cleanup_team_folders(suffixes, tags, team.name)

        # Unpair devices not shared with other teams
        for member in members:
            if member.member_tag == self.my_member_tag:
                continue
            others = self.members.get_by_device(conn, member.device_id)
            if len([o for o in others if o.team_name != team.name]) == 0:
                await self.devices.unpair(member.device_id)

        self.teams.delete(conn, team.name)
        self.events.log(
            conn,
            SyncEvent(
                event_type=SyncEventType.member_auto_left,
                team_name=team.name,
                member_tag=self.my_member_tag,
            ),
        )

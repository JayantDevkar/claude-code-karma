"""TeamService — team lifecycle + member management orchestration."""
from __future__ import annotations

import logging
import sqlite3
from typing import TYPE_CHECKING

from domain.team import Team
from domain.member import Member, MemberStatus
from domain.subscription import Subscription
from domain.events import SyncEvent, SyncEventType
from services.syncthing.folder_manager import build_outbox_folder_id, build_metadata_folder_id

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from repositories.team_repo import TeamRepository
    from repositories.member_repo import MemberRepository
    from repositories.project_repo import ProjectRepository
    from repositories.subscription_repo import SubscriptionRepository
    from repositories.event_repo import EventRepository
    from services.syncthing.device_manager import DeviceManager
    from services.syncthing.folder_manager import FolderManager
    from services.sync.metadata_service import MetadataService


class TeamService:
    def __init__(
        self,
        teams: "TeamRepository",
        members: "MemberRepository",
        projects: "ProjectRepository",
        subs: "SubscriptionRepository",
        events: "EventRepository",
        devices: "DeviceManager",
        metadata: "MetadataService",
        folders: "FolderManager",
    ):
        self.teams = teams
        self.members = members
        self.projects = projects
        self.subs = subs
        self.events = events
        self.devices = devices
        self.metadata = metadata
        self.folders = folders

    async def create_team(
        self,
        conn: sqlite3.Connection,
        *,
        name: str,
        leader_member_tag: str,
        leader_device_id: str,
    ) -> Team:
        """Create a new team with the given leader as an immediately ACTIVE member."""
        team = Team(
            name=name,
            leader_device_id=leader_device_id,
            leader_member_tag=leader_member_tag,
        )
        leader = Member.from_member_tag(
            member_tag=leader_member_tag,
            team_name=name,
            device_id=leader_device_id,
            status=MemberStatus.ACTIVE,
        )
        self.teams.save(conn, team)
        self.members.save(conn, leader)
        self.metadata.write_team_state(team, [leader])
        self.events.log(conn, SyncEvent(
            event_type=SyncEventType.team_created,
            team_name=name,
        ))
        return team

    async def add_member(
        self,
        conn: sqlite3.Connection,
        *,
        team_name: str,
        by_device: str,
        new_member_tag: str,
        new_device_id: str,
    ) -> Member:
        """Add a new member to the team. Only the leader may add members.

        Creates OFFERED subscriptions for all currently shared projects.
        Pairs the new device via Syncthing.
        """
        team = self.teams.get(conn, team_name)
        if team is None:
            raise ValueError(f"Team '{team_name}' not found")

        member = Member.from_member_tag(
            member_tag=new_member_tag,
            team_name=team_name,
            device_id=new_device_id,
        )
        added = team.add_member(member, by_device=by_device)  # auth check
        self.members.save(conn, added)
        await self.devices.pair(new_device_id)

        # Immediately share metadata + project outbox folders with the new device
        # so the joiner sees pending folders without waiting for the 60s reconciliation timer.
        try:
            all_folders = await self.folders._client.get_config_folders()

            # Share metadata folder
            meta_folder_id = build_metadata_folder_id(team_name)
            meta_folder = next((f for f in all_folders if f["id"] == meta_folder_id), None)
            if meta_folder:
                existing_device_ids = {d["deviceID"] for d in meta_folder.get("devices", [])}
                existing_device_ids.add(new_device_id)
                await self.folders.set_folder_devices(meta_folder_id, existing_device_ids)

            # Share all project outbox folders
            shared_projects = self.projects.list_for_team(conn, team_name)
            for project in shared_projects:
                if project.status.value == "shared":
                    folder_id = build_outbox_folder_id(team.leader_member_tag, project.folder_suffix)
                    folder = next((f for f in all_folders if f["id"] == folder_id), None)
                    if folder:
                        existing = {d["deviceID"] for d in folder.get("devices", [])}
                        existing.add(new_device_id)
                        await self.folders.set_folder_devices(folder_id, existing)
        except Exception as e:
            logger.warning("Failed to share folders with new member %s: %s", new_member_tag, e)

        # Update metadata with all current members
        all_members = self.members.list_for_team(conn, team_name)
        self.metadata.write_team_state(team, all_members)

        # Create OFFERED subscriptions for all currently shared projects
        projects = self.projects.list_for_team(conn, team_name)
        for project in projects:
            if project.status.value == "shared":
                sub = Subscription(
                    member_tag=new_member_tag,
                    team_name=team_name,
                    project_git_identity=project.git_identity,
                )
                self.subs.save(conn, sub)

        self.events.log(conn, SyncEvent(
            event_type=SyncEventType.member_added,
            team_name=team_name,
            member_tag=new_member_tag,
            detail={"device_id": new_device_id, "added_by": team.leader_member_tag},
        ))
        return added

    async def remove_member(
        self,
        conn: sqlite3.Connection,
        *,
        team_name: str,
        by_device: str,
        member_tag: str,
    ) -> Member:
        """Remove a member from the team. Only the leader may remove members.

        Records the removal to prevent re-add from stale metadata.
        Writes a removal signal to the metadata folder.
        Unpairing happens only if the device is not in any other team.
        """
        team = self.teams.get(conn, team_name)
        if team is None:
            raise ValueError(f"Team '{team_name}' not found")

        member = self.members.get(conn, team_name, member_tag)
        if member is None:
            raise ValueError(f"Member '{member_tag}' not found in team '{team_name}'")

        removed = team.remove_member(member, by_device=by_device)  # auth check
        self.members.save(conn, removed)
        self.members.record_removal(conn, team_name, removed.device_id, member_tag=member_tag)

        # Write removal signal to metadata folder
        self.metadata.write_removal_signal(team_name, member_tag, removed_by=team.leader_member_tag)

        # Remove device from all team folder device lists
        projects = self.projects.list_for_team(conn, team_name)
        suffixes = [p.folder_suffix for p in projects if p.status.value == "shared"]
        all_members = self.members.list_for_team(conn, team_name)
        tags = [m.member_tag for m in all_members]
        await self.folders.remove_device_from_team_folders(suffixes, tags, removed.device_id)

        # Unpair only if device not in any other active team
        other_memberships = self.members.get_by_device(conn, removed.device_id)
        active_others = [
            m for m in other_memberships
            if m.team_name != team_name and m.is_active
        ]
        if not active_others:
            await self.devices.unpair(removed.device_id)

        self.events.log(conn, SyncEvent(
            event_type=SyncEventType.member_removed,
            team_name=team_name,
            member_tag=member_tag,
            detail={"device_id": removed.device_id, "removed_by": team.leader_member_tag},
        ))
        return removed

    async def dissolve_team(
        self,
        conn: sqlite3.Connection,
        *,
        team_name: str,
        by_device: str,
    ) -> Team:
        """Dissolve the team. Only the leader may dissolve.

        Cleans up all Syncthing folders, then deletes the team from DB
        (CASCADE handles members, projects, subscriptions).
        """
        team = self.teams.get(conn, team_name)
        if team is None:
            raise ValueError(f"Team '{team_name}' not found")

        dissolved = team.dissolve(by_device=by_device)  # auth check

        # Cleanup Syncthing folders for all projects + members
        projects = self.projects.list_for_team(conn, team_name)
        members = self.members.list_for_team(conn, team_name)
        suffixes = [p.folder_suffix for p in projects]
        tags = [m.member_tag for m in members]
        await self.folders.cleanup_team_folders(suffixes, tags, team_name)

        # Log event BEFORE delete so it survives even if an FK is later added
        self.events.log(conn, SyncEvent(
            event_type=SyncEventType.team_dissolved,
            team_name=team_name,
        ))

        # Delete team — CASCADE handles members, projects, subs
        self.teams.delete(conn, team_name)
        return dissolved

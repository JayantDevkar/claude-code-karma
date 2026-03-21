"""ProjectService — project sharing + subscription management orchestration."""
from __future__ import annotations

import logging
import sqlite3
from typing import TYPE_CHECKING

logger = logging.getLogger(__name__)

from domain.project import SharedProject, derive_folder_suffix
from domain.subscription import Subscription, SubscriptionStatus, SyncDirection
from domain.events import SyncEvent, SyncEventType
from domain.team import AuthorizationError

if TYPE_CHECKING:
    from repositories.project_repo import ProjectRepository
    from repositories.subscription_repo import SubscriptionRepository
    from repositories.member_repo import MemberRepository
    from repositories.team_repo import TeamRepository
    from repositories.event_repo import EventRepository
    from services.syncthing.folder_manager import FolderManager
    from services.sync.metadata_service import MetadataService


class ProjectService:
    def __init__(
        self,
        projects: "ProjectRepository",
        subs: "SubscriptionRepository",
        members: "MemberRepository",
        teams: "TeamRepository",
        folders: "FolderManager",
        metadata: "MetadataService",
        events: "EventRepository",
    ):
        self.projects = projects
        self.subs = subs
        self.members = members
        self.teams = teams
        self.folders = folders
        self.metadata = metadata
        self.events = events

    async def share_project(
        self,
        conn: sqlite3.Connection,
        *,
        team_name: str,
        by_device: str,
        git_identity: str,
        encoded_name: str | None = None,
    ) -> SharedProject:
        """Share a project with the team. Only the leader may share.

        Creates OFFERED subscriptions for each active non-leader member.
        If `encoded_name` is provided, creates the leader's outbox folder.
        """
        team = self.teams.get(conn, team_name)
        if not team or not team.is_leader(by_device):
            raise AuthorizationError("Only leader can share projects")
        if not git_identity:
            raise ValueError("git_identity is required (git-only projects)")

        project = SharedProject(
            team_name=team_name,
            git_identity=git_identity,
            encoded_name=encoded_name,
            folder_suffix=derive_folder_suffix(git_identity),
        )
        self.projects.save(conn, project)

        # Create ACCEPTED subscription for the leader (direction=BOTH) so they
        # participate in Phase 3 device lists and get inbox folders for members.
        leader_sub = Subscription(
            member_tag=team.leader_member_tag,
            team_name=team_name,
            project_git_identity=git_identity,
            status=SubscriptionStatus.ACCEPTED,
            direction=SyncDirection.BOTH,
        )
        self.subs.save(conn, leader_sub)

        # Create OFFERED subscription for each active non-leader member
        for member in self.members.list_for_team(conn, team_name):
            if member.is_active and not team.is_leader(member.device_id):
                sub = Subscription(
                    member_tag=member.member_tag,
                    team_name=team_name,
                    project_git_identity=git_identity,
                )
                self.subs.save(conn, sub)

        # Create leader's outbox if they have the repo locally
        if encoded_name:
            await self.folders.ensure_outbox_folder(
                team.leader_member_tag, project.folder_suffix,
            )

        # Publish leader's updated project list to metadata folder
        self._publish_member_metadata(conn, team_name, team.leader_member_tag)

        self.events.log(conn, SyncEvent(
            event_type=SyncEventType.project_shared,
            team_name=team_name,
            project_git_identity=git_identity,
        ))
        return project

    async def remove_project(
        self,
        conn: sqlite3.Connection,
        *,
        team_name: str,
        by_device: str,
        git_identity: str,
    ) -> SharedProject:
        """Remove a project from the team. Only the leader may remove.

        Declines all subscriptions and cleans up Syncthing folders.
        """
        team = self.teams.get(conn, team_name)
        if not team or not team.is_leader(by_device):
            raise AuthorizationError("Only leader can remove projects")

        project = self.projects.get(conn, team_name, git_identity)
        if not project:
            raise ValueError(f"Project '{git_identity}' not found in team '{team_name}'")

        removed = project.remove()
        self.projects.save(conn, removed)

        # Decline all subscriptions for this project
        for sub in self.subs.list_for_project(conn, team_name, git_identity):
            if sub.status.value != "declined":
                self.subs.save(conn, sub.decline())

        # Cleanup Syncthing folders for all members
        members = self.members.list_for_team(conn, team_name)
        tags = [m.member_tag for m in members]
        await self.folders.cleanup_project_folders(removed.folder_suffix, tags, conn=conn, team_name=team_name)

        # Publish leader's updated project list to metadata folder
        self._publish_member_metadata(conn, team_name, team.leader_member_tag)

        self.events.log(conn, SyncEvent(
            event_type=SyncEventType.project_removed,
            team_name=team_name,
            project_git_identity=git_identity,
        ))
        return removed

    async def accept_subscription(
        self,
        conn: sqlite3.Connection,
        *,
        member_tag: str,
        team_name: str,
        git_identity: str,
        direction: SyncDirection = SyncDirection.BOTH,
    ) -> Subscription:
        """Accept a subscription with the given sync direction.

        Applies the direction by creating outbox and/or inbox folders as needed.
        """
        sub = self.subs.get(conn, member_tag, team_name, git_identity)
        if sub is None:
            raise ValueError(
                f"Subscription not found for member '{member_tag}' "
                f"on project '{git_identity}' in team '{team_name}'"
            )

        # Auto-reopen declined subscriptions so the frontend can call
        # accept directly without needing to know the state machine.
        if sub.status == SubscriptionStatus.DECLINED:
            sub = sub.reopen()
            self.subs.save(conn, sub)

        accepted = sub.accept(direction)
        self.subs.save(conn, accepted)
        await self._apply_sync_direction(conn, accepted)

        self._publish_member_metadata(conn, team_name, member_tag)

        self.events.log(conn, SyncEvent(
            event_type=SyncEventType.subscription_accepted,
            team_name=team_name,
            member_tag=member_tag,
            project_git_identity=git_identity,
            detail={"direction": direction.value},
        ))
        return accepted

    async def pause_subscription(
        self,
        conn: sqlite3.Connection,
        *,
        member_tag: str,
        team_name: str,
        git_identity: str,
    ) -> Subscription:
        """Pause an accepted subscription."""
        sub = self.subs.get(conn, member_tag, team_name, git_identity)
        if sub is None:
            raise ValueError("Subscription not found")

        paused = sub.pause()
        self.subs.save(conn, paused)
        self._publish_member_metadata(conn, team_name, member_tag)

        self.events.log(conn, SyncEvent(
            event_type=SyncEventType.subscription_paused,
            team_name=team_name,
            member_tag=member_tag,
            project_git_identity=git_identity,
        ))
        return paused

    async def resume_subscription(
        self,
        conn: sqlite3.Connection,
        *,
        member_tag: str,
        team_name: str,
        git_identity: str,
    ) -> Subscription:
        """Resume a paused subscription, re-applying sync direction."""
        sub = self.subs.get(conn, member_tag, team_name, git_identity)
        if sub is None:
            raise ValueError("Subscription not found")

        resumed = sub.resume()
        self.subs.save(conn, resumed)
        await self._apply_sync_direction(conn, resumed)
        self._publish_member_metadata(conn, team_name, member_tag)

        self.events.log(conn, SyncEvent(
            event_type=SyncEventType.subscription_resumed,
            team_name=team_name,
            member_tag=member_tag,
            project_git_identity=git_identity,
        ))
        return resumed

    async def decline_subscription(
        self,
        conn: sqlite3.Connection,
        *,
        member_tag: str,
        team_name: str,
        git_identity: str,
    ) -> Subscription:
        """Decline a subscription."""
        sub = self.subs.get(conn, member_tag, team_name, git_identity)
        if sub is None:
            raise ValueError("Subscription not found")

        declined = sub.decline()
        self.subs.save(conn, declined)
        self._publish_member_metadata(conn, team_name, member_tag)

        self.events.log(conn, SyncEvent(
            event_type=SyncEventType.subscription_declined,
            team_name=team_name,
            member_tag=member_tag,
            project_git_identity=git_identity,
        ))
        return declined

    async def change_direction(
        self,
        conn: sqlite3.Connection,
        *,
        member_tag: str,
        team_name: str,
        git_identity: str,
        direction: SyncDirection,
    ) -> Subscription:
        """Change the sync direction of an accepted subscription.

        Removes outbox if switching away from send/both — but only if no
        other team's subscription for the same member+suffix still needs it.
        Creates outbox if switching to send/both from receive.
        """
        sub = self.subs.get(conn, member_tag, team_name, git_identity)
        if sub is None:
            raise ValueError("Subscription not found")

        old_direction = sub.direction
        changed = sub.change_direction(direction)
        self.subs.save(conn, changed)

        project = self.projects.get(conn, team_name, git_identity)

        # Remove outbox if no longer sending
        was_sending = old_direction in (SyncDirection.SEND, SyncDirection.BOTH)
        now_sending = direction in (SyncDirection.SEND, SyncDirection.BOTH)

        if project:
            if was_sending and not now_sending:
                # Check if another team's subscription still needs this outbox
                other_subs = self.subs.list_accepted_for_suffix(conn, project.folder_suffix)
                other_team_needs = any(
                    s.member_tag == member_tag
                    and s.team_name != team_name
                    and s.direction in (SyncDirection.SEND, SyncDirection.BOTH)
                    for s in other_subs
                )
                if not other_team_needs:
                    await self.folders.remove_outbox_folder(member_tag, project.folder_suffix)
            elif not was_sending and now_sending:
                await self.folders.ensure_outbox_folder(member_tag, project.folder_suffix)

        self._publish_member_metadata(conn, team_name, member_tag)

        self.events.log(conn, SyncEvent(
            event_type=SyncEventType.direction_changed,
            team_name=team_name,
            member_tag=member_tag,
            project_git_identity=git_identity,
            detail={"old_direction": old_direction.value, "new_direction": direction.value},
        ))
        return changed

    async def reopen_subscription(
        self,
        conn: sqlite3.Connection,
        *,
        member_tag: str,
        team_name: str,
        git_identity: str,
    ) -> Subscription:
        """Reopen a declined subscription, returning it to OFFERED status.

        The member can then accept it again with a new direction choice.
        """
        sub = self.subs.get(conn, member_tag, team_name, git_identity)
        if sub is None:
            raise ValueError("Subscription not found")

        reopened = sub.reopen()
        self.subs.save(conn, reopened)
        self._publish_member_metadata(conn, team_name, member_tag)

        self.events.log(conn, SyncEvent(
            event_type=SyncEventType.subscription_offered,
            team_name=team_name,
            member_tag=member_tag,
            project_git_identity=git_identity,
            detail={"reopened": True},
        ))
        return reopened

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _publish_member_metadata(
        self, conn: sqlite3.Connection, team_name: str, member_tag: str,
    ) -> None:
        """Publish a member's project list and subscriptions to the metadata folder.

        Queries current projects and subscriptions from DB, then writes them
        to the member's state file via read-merge-write (preserving basic fields).
        Best-effort: filesystem errors are logged but do not abort the caller.
        """
        try:
            projects = self.projects.list_for_team(conn, team_name)
            projects_data = [
                {
                    "git_identity": p.git_identity,
                    "folder_suffix": p.folder_suffix,
                    "encoded_name": p.encoded_name,
                }
                for p in projects
                if p.status.value == "shared"
            ]
            subs = self.subs.list_for_member(conn, member_tag)
            subs_data = {
                s.project_git_identity: {
                    "status": s.status.value,
                    "direction": s.direction.value,
                }
                for s in subs
                if s.team_name == team_name
            }
            self.metadata.write_member_state(
                team_name, member_tag,
                projects=projects_data,
                subscriptions=subs_data,
            )
        except Exception as e:
            logger.warning(
                "Failed to publish metadata for member '%s' in team '%s': %s",
                member_tag, team_name, e,
            )

    async def _apply_sync_direction(self, conn: sqlite3.Connection, sub: Subscription) -> None:
        """Create Syncthing folders based on subscription direction."""
        project = self.projects.get(conn, sub.team_name, sub.project_git_identity)
        if not project:
            return

        if sub.direction in (SyncDirection.SEND, SyncDirection.BOTH):
            await self.folders.ensure_outbox_folder(sub.member_tag, project.folder_suffix)

        if sub.direction in (SyncDirection.RECEIVE, SyncDirection.BOTH):
            # Create inbox folders for each active teammate (they are senders)
            members = self.members.list_for_team(conn, sub.team_name)
            for m in members:
                if m.member_tag != sub.member_tag and m.is_active:
                    await self.folders.ensure_inbox_folder(
                        m.member_tag, project.folder_suffix, m.device_id,
                    )

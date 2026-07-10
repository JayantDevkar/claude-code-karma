"""Tests for ProjectService — project sharing + subscription management."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import sqlite3
import pytest
from unittest.mock import MagicMock, AsyncMock

from db.schema import ensure_schema
from domain.team import AuthorizationError
from domain.member import MemberStatus
from domain.project import SharedProject, SharedProjectStatus, derive_folder_suffix
from domain.subscription import SubscriptionStatus, SyncDirection
from repositories.team_repo import TeamRepository
from repositories.member_repo import MemberRepository
from repositories.project_repo import ProjectRepository
from repositories.subscription_repo import SubscriptionRepository
from repositories.event_repo import EventRepository
from services.sync.project_service import ProjectService


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA foreign_keys=ON")
    ensure_schema(c)
    return c


@pytest.fixture
def mock_folders():
    m = MagicMock()
    m.ensure_outbox_folder = AsyncMock()
    m.ensure_inbox_folder = AsyncMock()
    m.remove_outbox_folder = AsyncMock()
    m.set_folder_devices = AsyncMock()
    m.remove_device_from_team_folders = AsyncMock()
    m.cleanup_team_folders = AsyncMock()
    m.cleanup_project_folders = AsyncMock()
    return m


@pytest.fixture
def mock_metadata(tmp_path):
    from services.sync.metadata_service import MetadataService
    return MetadataService(meta_base=tmp_path / "meta")


@pytest.fixture
def service(mock_folders, mock_metadata):
    return ProjectService(
        projects=ProjectRepository(),
        subs=SubscriptionRepository(),
        members=MemberRepository(),
        teams=TeamRepository(),
        folders=mock_folders,
        metadata=mock_metadata,
        events=EventRepository(),
    )


def _setup_team_with_member(conn, service):
    """Helper: create a team + add one member. Returns (team_repo, member_repo)."""
    from domain.team import Team
    from domain.member import Member

    teams = service.teams
    members = service.members

    team = Team(name="t", leader_device_id="DEV-L", leader_member_tag="j.m")
    teams.save(conn, team)

    leader = Member.from_member_tag(
        member_tag="j.m", team_name="t", device_id="DEV-L", status=MemberStatus.ACTIVE,
    )
    members.save(conn, leader)

    member = Member.from_member_tag(
        member_tag="a.l", team_name="t", device_id="DEV-A", status=MemberStatus.ACTIVE,
    )
    members.save(conn, member)
    return team


class TestShareProject:
    @pytest.mark.asyncio
    async def test_shares_project_and_creates_subscriptions(self, service, conn):
        _setup_team_with_member(conn, service)
        project = await service.share_project(
            conn, team_name="t", by_device="DEV-L",
            git_identity="owner/repo",
        )
        assert project.status == SharedProjectStatus.SHARED
        assert project.folder_suffix == "owner-repo"

        # Active non-leader member gets OFFERED subscription
        subs = service.subs.list_for_member(conn, "a.l")
        assert len(subs) == 1
        assert subs[0].status == SubscriptionStatus.OFFERED

    @pytest.mark.asyncio
    async def test_non_leader_cannot_share(self, service, conn):
        _setup_team_with_member(conn, service)
        with pytest.raises(AuthorizationError):
            await service.share_project(
                conn, team_name="t", by_device="DEV-OTHER",
                git_identity="owner/repo",
            )

    @pytest.mark.asyncio
    async def test_requires_git_identity(self, service, conn):
        _setup_team_with_member(conn, service)
        with pytest.raises(ValueError):
            await service.share_project(
                conn, team_name="t", by_device="DEV-L",
                git_identity="",
            )

    @pytest.mark.asyncio
    async def test_creates_outbox_when_encoded_name_provided(self, service, conn, mock_folders):
        _setup_team_with_member(conn, service)
        await service.share_project(
            conn, team_name="t", by_device="DEV-L",
            git_identity="owner/repo",
            encoded_name="-Users-j-repo",
        )
        mock_folders.ensure_outbox_folder.assert_called_once_with("j.m", "owner-repo")

    @pytest.mark.asyncio
    async def test_no_outbox_without_encoded_name(self, service, conn, mock_folders):
        _setup_team_with_member(conn, service)
        await service.share_project(
            conn, team_name="t", by_device="DEV-L",
            git_identity="owner/repo",
        )
        mock_folders.ensure_outbox_folder.assert_not_called()

    @pytest.mark.asyncio
    async def test_logs_project_shared_event(self, service, conn):
        _setup_team_with_member(conn, service)
        await service.share_project(
            conn, team_name="t", by_device="DEV-L",
            git_identity="owner/repo",
        )
        events = service.events.query(conn, team="t")
        assert any(e.event_type.value == "project_shared" for e in events)

    @pytest.mark.asyncio
    async def test_leader_gets_accepted_subscription(self, service, conn):
        """Leader gets an ACCEPTED/BOTH subscription for their own shared project."""
        _setup_team_with_member(conn, service)
        await service.share_project(
            conn, team_name="t", by_device="DEV-L",
            git_identity="owner/repo",
        )
        # Leader (j.m) should have an ACCEPTED subscription with direction=BOTH
        leader_subs = service.subs.list_for_member(conn, "j.m")
        assert len(leader_subs) == 1
        assert leader_subs[0].status.value == "accepted"
        assert leader_subs[0].direction.value == "both"


class TestAcceptSubscription:
    def _create_offered_sub(self, conn, service, git_identity="owner/repo"):
        from domain.subscription import Subscription
        # Save project FIRST (FK requires it before subscription)
        project = SharedProject(
            team_name="t", git_identity=git_identity,
            folder_suffix=derive_folder_suffix(git_identity),
        )
        service.projects.save(conn, project)
        sub = Subscription(
            member_tag="a.l", team_name="t",
            project_git_identity=git_identity,
            status=SubscriptionStatus.OFFERED,
        )
        service.subs.save(conn, sub)
        return sub

    def _setup_team_member(self, conn, service):
        from domain.team import Team
        from domain.member import Member
        team = Team(name="t", leader_device_id="DEV-L", leader_member_tag="j.m")
        service.teams.save(conn, team)
        leader = Member.from_member_tag(
            member_tag="j.m", team_name="t", device_id="DEV-L", status=MemberStatus.ACTIVE,
        )
        service.members.save(conn, leader)
        member = Member.from_member_tag(
            member_tag="a.l", team_name="t", device_id="DEV-A", status=MemberStatus.ACTIVE,
        )
        service.members.save(conn, member)

    @pytest.mark.asyncio
    async def test_accept_with_both_direction(self, service, conn, mock_folders):
        self._setup_team_member(conn, service)
        self._create_offered_sub(conn, service)
        accepted = await service.accept_subscription(
            conn, member_tag="a.l", team_name="t",
            git_identity="owner/repo", direction=SyncDirection.BOTH,
        )
        assert accepted.status == SubscriptionStatus.ACCEPTED
        assert accepted.direction == SyncDirection.BOTH
        # Both outbox + inbox created
        mock_folders.ensure_outbox_folder.assert_called_once_with("a.l", "owner-repo")
        mock_folders.ensure_inbox_folder.assert_called()

    @pytest.mark.asyncio
    async def test_accept_receive_only(self, service, conn, mock_folders):
        self._setup_team_member(conn, service)
        self._create_offered_sub(conn, service)
        accepted = await service.accept_subscription(
            conn, member_tag="a.l", team_name="t",
            git_identity="owner/repo", direction=SyncDirection.RECEIVE,
        )
        assert accepted.direction == SyncDirection.RECEIVE
        # No outbox created, only inbox
        mock_folders.ensure_outbox_folder.assert_not_called()
        mock_folders.ensure_inbox_folder.assert_called()

    @pytest.mark.asyncio
    async def test_accept_send_only(self, service, conn, mock_folders):
        self._setup_team_member(conn, service)
        self._create_offered_sub(conn, service)
        accepted = await service.accept_subscription(
            conn, member_tag="a.l", team_name="t",
            git_identity="owner/repo", direction=SyncDirection.SEND,
        )
        assert accepted.direction == SyncDirection.SEND
        # Outbox created, no inbox
        mock_folders.ensure_outbox_folder.assert_called_once_with("a.l", "owner-repo")
        mock_folders.ensure_inbox_folder.assert_not_called()

    @pytest.mark.asyncio
    async def test_logs_subscription_accepted_event(self, service, conn):
        self._setup_team_member(conn, service)
        self._create_offered_sub(conn, service)
        await service.accept_subscription(
            conn, member_tag="a.l", team_name="t",
            git_identity="owner/repo", direction=SyncDirection.BOTH,
        )
        events = service.events.query(conn, team="t")
        assert any(e.event_type.value == "subscription_accepted" for e in events)


class TestPauseResumeDecline:
    def _setup(self, conn, service):
        from domain.team import Team
        from domain.member import Member
        from domain.subscription import Subscription
        team = Team(name="t", leader_device_id="DEV-L", leader_member_tag="j.m")
        service.teams.save(conn, team)
        member = Member.from_member_tag(
            member_tag="a.l", team_name="t", device_id="DEV-A", status=MemberStatus.ACTIVE,
        )
        service.members.save(conn, member)
        project = SharedProject(team_name="t", git_identity="o/r", folder_suffix="o-r")
        service.projects.save(conn, project)
        # Start with accepted sub
        sub = Subscription(
            member_tag="a.l", team_name="t", project_git_identity="o/r",
            status=SubscriptionStatus.ACCEPTED,
        )
        service.subs.save(conn, sub)

    @pytest.mark.asyncio
    async def test_pause_subscription(self, service, conn):
        self._setup(conn, service)
        paused = await service.pause_subscription(
            conn, member_tag="a.l", team_name="t", git_identity="o/r",
        )
        assert paused.status == SubscriptionStatus.PAUSED
        saved = service.subs.get(conn, "a.l", "t", "o/r")
        assert saved.status == SubscriptionStatus.PAUSED

    @pytest.mark.asyncio
    async def test_resume_subscription(self, service, conn):
        self._setup(conn, service)
        await service.pause_subscription(
            conn, member_tag="a.l", team_name="t", git_identity="o/r",
        )
        resumed = await service.resume_subscription(
            conn, member_tag="a.l", team_name="t", git_identity="o/r",
        )
        assert resumed.status == SubscriptionStatus.ACCEPTED

    @pytest.mark.asyncio
    async def test_decline_subscription(self, service, conn):
        self._setup(conn, service)
        declined = await service.decline_subscription(
            conn, member_tag="a.l", team_name="t", git_identity="o/r",
        )
        assert declined.status == SubscriptionStatus.DECLINED
        saved = service.subs.get(conn, "a.l", "t", "o/r")
        assert saved.status == SubscriptionStatus.DECLINED

    @pytest.mark.asyncio
    async def test_logs_pause_event(self, service, conn):
        self._setup(conn, service)
        await service.pause_subscription(
            conn, member_tag="a.l", team_name="t", git_identity="o/r",
        )
        events = service.events.query(conn, team="t")
        assert any(e.event_type.value == "subscription_paused" for e in events)

    @pytest.mark.asyncio
    async def test_logs_resume_event(self, service, conn):
        self._setup(conn, service)
        await service.pause_subscription(
            conn, member_tag="a.l", team_name="t", git_identity="o/r",
        )
        await service.resume_subscription(
            conn, member_tag="a.l", team_name="t", git_identity="o/r",
        )
        events = service.events.query(conn, team="t")
        assert any(e.event_type.value == "subscription_resumed" for e in events)

    @pytest.mark.asyncio
    async def test_logs_decline_event(self, service, conn):
        self._setup(conn, service)
        await service.decline_subscription(
            conn, member_tag="a.l", team_name="t", git_identity="o/r",
        )
        events = service.events.query(conn, team="t")
        assert any(e.event_type.value == "subscription_declined" for e in events)


class TestChangeDirection:
    def _setup(self, conn, service):
        from domain.team import Team
        from domain.member import Member
        from domain.subscription import Subscription
        team = Team(name="t", leader_device_id="DEV-L", leader_member_tag="j.m")
        service.teams.save(conn, team)
        member = Member.from_member_tag(
            member_tag="a.l", team_name="t", device_id="DEV-A", status=MemberStatus.ACTIVE,
        )
        service.members.save(conn, member)
        project = SharedProject(team_name="t", git_identity="o/r", folder_suffix="o-r")
        service.projects.save(conn, project)
        sub = Subscription(
            member_tag="a.l", team_name="t", project_git_identity="o/r",
            status=SubscriptionStatus.ACCEPTED, direction=SyncDirection.BOTH,
        )
        service.subs.save(conn, sub)

    @pytest.mark.asyncio
    async def test_change_to_receive_removes_outbox(self, service, conn, mock_folders):
        self._setup(conn, service)
        changed = await service.change_direction(
            conn, member_tag="a.l", team_name="t",
            git_identity="o/r", direction=SyncDirection.RECEIVE,
        )
        assert changed.direction == SyncDirection.RECEIVE
        mock_folders.remove_outbox_folder.assert_called_once_with("a.l", "o-r")

    @pytest.mark.asyncio
    async def test_change_to_send_only(self, service, conn, mock_folders):
        from domain.subscription import Subscription
        from domain.team import Team
        from domain.member import Member
        # Create parent rows FIRST (FK requires team → member → project → subscription)
        team = Team(name="t", leader_device_id="DEV-L", leader_member_tag="j.m")
        service.teams.save(conn, team)
        member = Member.from_member_tag(
            member_tag="a.l", team_name="t", device_id="DEV-A", status=MemberStatus.ACTIVE,
        )
        service.members.save(conn, member)
        project = SharedProject(team_name="t", git_identity="o/r", folder_suffix="o-r")
        service.projects.save(conn, project)
        # Now save subscription (all FK parents exist)
        sub = Subscription(
            member_tag="a.l", team_name="t", project_git_identity="o/r",
            status=SubscriptionStatus.ACCEPTED, direction=SyncDirection.RECEIVE,
        )
        service.subs.save(conn, sub)

        changed = await service.change_direction(
            conn, member_tag="a.l", team_name="t",
            git_identity="o/r", direction=SyncDirection.SEND,
        )
        assert changed.direction == SyncDirection.SEND
        mock_folders.ensure_outbox_folder.assert_called_once_with("a.l", "o-r")
        mock_folders.remove_outbox_folder.assert_not_called()

    @pytest.mark.asyncio
    async def test_logs_direction_changed_event(self, service, conn):
        self._setup(conn, service)
        await service.change_direction(
            conn, member_tag="a.l", team_name="t",
            git_identity="o/r", direction=SyncDirection.RECEIVE,
        )
        events = service.events.query(conn, team="t")
        assert any(e.event_type.value == "direction_changed" for e in events)


class TestRemoveProject:
    def _setup(self, conn, service):
        from domain.team import Team
        from domain.member import Member
        from domain.subscription import Subscription
        team = Team(name="t", leader_device_id="DEV-L", leader_member_tag="j.m")
        service.teams.save(conn, team)
        leader = Member.from_member_tag(
            member_tag="j.m", team_name="t", device_id="DEV-L", status=MemberStatus.ACTIVE,
        )
        service.members.save(conn, leader)
        member = Member.from_member_tag(
            member_tag="a.l", team_name="t", device_id="DEV-A", status=MemberStatus.ACTIVE,
        )
        service.members.save(conn, member)
        project = SharedProject(team_name="t", git_identity="o/r", folder_suffix="o-r")
        service.projects.save(conn, project)
        sub = Subscription(
            member_tag="a.l", team_name="t", project_git_identity="o/r",
            status=SubscriptionStatus.ACCEPTED,
        )
        service.subs.save(conn, sub)

    @pytest.mark.asyncio
    async def test_removes_project_and_declines_all_subs(self, service, conn, mock_folders):
        self._setup(conn, service)
        removed = await service.remove_project(
            conn, team_name="t", by_device="DEV-L", git_identity="o/r",
        )
        assert removed.status == SharedProjectStatus.REMOVED
        # All subs declined
        subs = service.subs.list_for_project(conn, "t", "o/r")
        assert all(s.status == SubscriptionStatus.DECLINED for s in subs)
        mock_folders.cleanup_project_folders.assert_called_once()

    @pytest.mark.asyncio
    async def test_non_leader_cannot_remove_project(self, service, conn):
        self._setup(conn, service)
        with pytest.raises(AuthorizationError):
            await service.remove_project(
                conn, team_name="t", by_device="DEV-OTHER", git_identity="o/r",
            )

    @pytest.mark.asyncio
    async def test_logs_project_removed_event(self, service, conn):
        self._setup(conn, service)
        await service.remove_project(
            conn, team_name="t", by_device="DEV-L", git_identity="o/r",
        )
        events = service.events.query(conn, team="t")
        assert any(e.event_type.value == "project_removed" for e in events)

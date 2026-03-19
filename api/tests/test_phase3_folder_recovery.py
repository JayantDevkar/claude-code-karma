"""Tests for Phase 3 folder existence recovery.

When a folder is accidentally deleted (e.g., by a cross-team cleanup bug),
Phase 3 should re-create outbox folders for members with ACCEPTED send|both
subscriptions before attempting to set device lists.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import sqlite3
import pytest
from unittest.mock import MagicMock, AsyncMock

from db.schema import ensure_schema
from domain.team import Team
from domain.member import Member, MemberStatus
from domain.project import SharedProject, SharedProjectStatus, derive_folder_suffix
from domain.subscription import Subscription, SubscriptionStatus, SyncDirection
from repositories.team_repo import TeamRepository
from repositories.member_repo import MemberRepository
from repositories.project_repo import ProjectRepository
from repositories.subscription_repo import SubscriptionRepository
from repositories.event_repo import EventRepository
from services.sync.reconciliation_service import ReconciliationService


MY_TAG = "me.laptop"
MY_DEVICE = "DEV-ME"
PEER_TAG = "peer.desktop"
PEER_DEVICE = "DEV-PEER"
LEADER_TAG = "leader.server"
LEADER_DEVICE = "DEV-LEADER"
TEAM = "alpha"
GIT_ID = "owner/repo"
SUFFIX = derive_folder_suffix(GIT_ID)  # "owner-repo"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA foreign_keys=ON")
    ensure_schema(c)
    return c


@pytest.fixture
def mock_devices():
    m = MagicMock()
    m.ensure_paired = AsyncMock()
    m.unpair = AsyncMock()
    return m


@pytest.fixture
def mock_folders():
    m = MagicMock()
    m.set_folder_devices = AsyncMock()
    m.cleanup_team_folders = AsyncMock()
    m.ensure_outbox_folder = AsyncMock()
    m.get_configured_folders = AsyncMock(return_value=[])
    return m


@pytest.fixture
def mock_metadata():
    m = MagicMock()
    m.read_team_metadata = MagicMock(return_value={})
    return m


def make_service(mock_metadata, mock_devices, mock_folders, my_tag=MY_TAG):
    return ReconciliationService(
        teams=TeamRepository(),
        members=MemberRepository(),
        projects=ProjectRepository(),
        subs=SubscriptionRepository(),
        events=EventRepository(),
        devices=mock_devices,
        folders=mock_folders,
        metadata=mock_metadata,
        my_member_tag=my_tag,
    )


def seed_team(conn, name=TEAM, leader_tag=LEADER_TAG, leader_device=LEADER_DEVICE):
    team = Team(name=name, leader_device_id=leader_device, leader_member_tag=leader_tag)
    TeamRepository().save(conn, team)
    return team


def seed_member(conn, member_tag, team_name=TEAM, device_id=None, status=MemberStatus.ACTIVE):
    device_id = device_id or f"DEV-{member_tag}"
    m = Member.from_member_tag(
        member_tag=member_tag,
        team_name=team_name,
        device_id=device_id,
        status=MemberStatus.ADDED,
    )
    if status == MemberStatus.ACTIVE:
        m = m.activate()
    MemberRepository().save(conn, m)
    return m


def seed_project(conn, git_identity=GIT_ID, team_name=TEAM, status=SharedProjectStatus.SHARED):
    suffix = derive_folder_suffix(git_identity)
    p = SharedProject(
        team_name=team_name,
        git_identity=git_identity,
        folder_suffix=suffix,
        status=status,
    )
    ProjectRepository().save(conn, p)
    return p


def seed_subscription(conn, member_tag, git_identity=GIT_ID, team_name=TEAM,
                      status=SubscriptionStatus.ACCEPTED, direction=SyncDirection.BOTH):
    sub = Subscription(
        member_tag=member_tag,
        team_name=team_name,
        project_git_identity=git_identity,
        status=status,
        direction=direction,
    )
    SubscriptionRepository().save(conn, sub)
    return sub


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestPhase3FolderRecovery:
    """Phase 3 should ensure outbox folders exist before setting device lists."""

    @pytest.mark.asyncio
    async def test_ensure_outbox_called_for_accepted_both_sub(
        self, conn, mock_metadata, mock_devices, mock_folders
    ):
        """Active member with ACCEPTED/BOTH subscription triggers ensure_outbox_folder."""
        team = seed_team(conn)
        seed_member(conn, PEER_TAG, device_id=PEER_DEVICE)
        seed_project(conn)
        seed_subscription(conn, PEER_TAG, direction=SyncDirection.BOTH)

        service = make_service(mock_metadata, mock_devices, mock_folders)
        await service.phase_device_lists(conn, team)

        mock_folders.ensure_outbox_folder.assert_any_call(PEER_TAG, SUFFIX)

    @pytest.mark.asyncio
    async def test_ensure_outbox_called_for_accepted_send_sub(
        self, conn, mock_metadata, mock_devices, mock_folders
    ):
        """Active member with ACCEPTED/SEND subscription triggers ensure_outbox_folder."""
        team = seed_team(conn)
        seed_member(conn, PEER_TAG, device_id=PEER_DEVICE)
        seed_project(conn)
        seed_subscription(conn, PEER_TAG, direction=SyncDirection.SEND)

        service = make_service(mock_metadata, mock_devices, mock_folders)
        await service.phase_device_lists(conn, team)

        mock_folders.ensure_outbox_folder.assert_any_call(PEER_TAG, SUFFIX)

    @pytest.mark.asyncio
    async def test_ensure_outbox_not_called_for_receive_only(
        self, conn, mock_metadata, mock_devices, mock_folders
    ):
        """RECEIVE-only subscription does NOT trigger ensure_outbox_folder."""
        team = seed_team(conn)
        seed_member(conn, PEER_TAG, device_id=PEER_DEVICE)
        seed_project(conn)
        seed_subscription(conn, PEER_TAG, direction=SyncDirection.RECEIVE)

        service = make_service(mock_metadata, mock_devices, mock_folders)
        await service.phase_device_lists(conn, team)

        mock_folders.ensure_outbox_folder.assert_not_called()

    @pytest.mark.asyncio
    async def test_ensure_outbox_not_called_for_inactive_member(
        self, conn, mock_metadata, mock_devices, mock_folders
    ):
        """ADDED (not active) member does NOT trigger ensure_outbox_folder."""
        team = seed_team(conn)
        m = Member.from_member_tag(
            member_tag=PEER_TAG, team_name=TEAM, device_id=PEER_DEVICE,
            status=MemberStatus.ADDED,
        )
        MemberRepository().save(conn, m)
        seed_project(conn)
        seed_subscription(conn, PEER_TAG, direction=SyncDirection.BOTH)

        service = make_service(mock_metadata, mock_devices, mock_folders)
        await service.phase_device_lists(conn, team)

        mock_folders.ensure_outbox_folder.assert_not_called()

    @pytest.mark.asyncio
    async def test_ensure_outbox_skips_other_team_subs(
        self, conn, mock_metadata, mock_devices, mock_folders
    ):
        """Subscriptions from another team are NOT recovered in this team's phase."""
        team_a = seed_team(conn, name="team-a")
        team_b = seed_team(conn, name="team-b", leader_tag="lb.srv", leader_device="DEV-LB")

        # Member active in both teams
        seed_member(conn, PEER_TAG, team_name="team-a", device_id=PEER_DEVICE)
        seed_member(conn, PEER_TAG, team_name="team-b", device_id=PEER_DEVICE)

        # Same git identity shared in both teams (same folder_suffix)
        seed_project(conn, team_name="team-a")
        seed_project(conn, team_name="team-b")

        # ACCEPTED/BOTH in both teams
        seed_subscription(conn, PEER_TAG, team_name="team-a", direction=SyncDirection.BOTH)
        seed_subscription(conn, PEER_TAG, team_name="team-b", direction=SyncDirection.BOTH)

        service = make_service(mock_metadata, mock_devices, mock_folders)

        # Run phase_device_lists for team-a only
        await service.phase_device_lists(conn, team_a)

        # ensure_outbox_folder should be called only once — for team-a's sub
        # (list_accepted_for_suffix returns subs from BOTH teams via JOIN,
        # but the team_name filter ensures only team-a's sub triggers recovery)
        calls = mock_folders.ensure_outbox_folder.call_args_list
        assert len(calls) == 1
        assert calls[0].args == (PEER_TAG, SUFFIX)

    @pytest.mark.asyncio
    async def test_ensure_outbox_called_before_set_folder_devices(
        self, conn, mock_metadata, mock_devices, mock_folders
    ):
        """ensure_outbox_folder is called BEFORE set_folder_devices for the same project."""
        team = seed_team(conn)
        seed_member(conn, PEER_TAG, device_id=PEER_DEVICE)
        seed_project(conn)
        seed_subscription(conn, PEER_TAG, direction=SyncDirection.BOTH)

        # Track call order
        call_order = []
        original_ensure = mock_folders.ensure_outbox_folder
        original_set = mock_folders.set_folder_devices

        async def track_ensure(*args, **kwargs):
            call_order.append("ensure_outbox_folder")
            return await original_ensure(*args, **kwargs)

        async def track_set(*args, **kwargs):
            call_order.append("set_folder_devices")
            return await original_set(*args, **kwargs)

        mock_folders.ensure_outbox_folder = AsyncMock(side_effect=track_ensure)
        mock_folders.set_folder_devices = AsyncMock(side_effect=track_set)

        service = make_service(mock_metadata, mock_devices, mock_folders)
        await service.phase_device_lists(conn, team)

        # ensure must come before set
        ensure_idx = call_order.index("ensure_outbox_folder")
        set_idx = call_order.index("set_folder_devices")
        assert ensure_idx < set_idx, (
            f"ensure_outbox_folder (idx={ensure_idx}) must be called before "
            f"set_folder_devices (idx={set_idx}). Order: {call_order}"
        )

    @pytest.mark.asyncio
    async def test_ensure_outbox_not_called_for_removed_project(
        self, conn, mock_metadata, mock_devices, mock_folders
    ):
        """REMOVED projects are skipped entirely — no ensure_outbox_folder call."""
        team = seed_team(conn)
        seed_member(conn, PEER_TAG, device_id=PEER_DEVICE)
        seed_project(conn, status=SharedProjectStatus.REMOVED)
        seed_subscription(conn, PEER_TAG, direction=SyncDirection.BOTH)

        service = make_service(mock_metadata, mock_devices, mock_folders)
        await service.phase_device_lists(conn, team)

        mock_folders.ensure_outbox_folder.assert_not_called()

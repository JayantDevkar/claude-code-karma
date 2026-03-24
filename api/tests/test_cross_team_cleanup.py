"""Tests for cross-team safety in folder cleanup.

Verifies that leaving/dissolving a team or removing a project does NOT
destroy Syncthing folders that are still needed by another team sharing
the same project (same folder_suffix).
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
from services.syncthing.folder_manager import (
    FolderManager,
    build_metadata_folder_id,
    build_outbox_folder_id,
)
from services.syncthing.client import SyncthingClient


MEMBER_TAG = "alice.laptop"
DEVICE_ID = "DEV-ALICE"
TEAM1 = "team-one"
TEAM2 = "team-two"
GIT_IDENTITY = "owner/repo"
FOLDER_SUFFIX = derive_folder_suffix(GIT_IDENTITY)


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA foreign_keys=ON")
    ensure_schema(c)
    return c


@pytest.fixture
def mock_client():
    client = MagicMock(spec=SyncthingClient)
    client.get_config_folders = AsyncMock(return_value=[])
    client.put_config_folder = AsyncMock()
    client.delete_config_folder = AsyncMock()
    return client


@pytest.fixture
def manager(mock_client, tmp_path):
    base = tmp_path / ".claude_karma"
    base.mkdir()
    return FolderManager(client=mock_client, karma_base=base)


def seed_team(conn, name, leader_tag=MEMBER_TAG, leader_device=DEVICE_ID):
    team = Team(name=name, leader_device_id=leader_device, leader_member_tag=leader_tag)
    TeamRepository().save(conn, team)
    return team


def seed_member(conn, member_tag, team_name, device_id=DEVICE_ID):
    m = Member.from_member_tag(
        member_tag=member_tag,
        team_name=team_name,
        device_id=device_id,
        status=MemberStatus.ADDED,
    ).activate()
    MemberRepository().save(conn, m)
    return m


def seed_project(conn, team_name, git_identity=GIT_IDENTITY):
    suffix = derive_folder_suffix(git_identity)
    p = SharedProject(
        team_name=team_name,
        git_identity=git_identity,
        folder_suffix=suffix,
    )
    ProjectRepository().save(conn, p)
    return p


def seed_subscription(conn, member_tag, team_name, git_identity=GIT_IDENTITY,
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


class TestCleanupSkipsFolderNeededByOtherTeam:
    """M1 in T1+T2 both sharing P1. Leave T1 -> outbox NOT deleted."""

    @pytest.mark.asyncio
    async def test_cleanup_skips_folder_needed_by_other_team(self, conn, manager, mock_client):
        # Setup: alice is in team-one and team-two, both sharing the same project
        seed_team(conn, TEAM1)
        seed_team(conn, TEAM2)
        seed_member(conn, MEMBER_TAG, TEAM1)
        seed_member(conn, MEMBER_TAG, TEAM2)
        seed_project(conn, TEAM1)
        seed_project(conn, TEAM2)
        seed_subscription(conn, MEMBER_TAG, TEAM1)
        seed_subscription(conn, MEMBER_TAG, TEAM2)

        outbox_id = build_outbox_folder_id(MEMBER_TAG, FOLDER_SUFFIX)
        meta_id = build_metadata_folder_id(TEAM1)

        mock_client.get_config_folders.return_value = [
            {"id": outbox_id},
            {"id": meta_id},
        ]

        # Act: cleanup team-one folders WITH conn (cross-team check enabled)
        await manager.cleanup_team_folders(
            folder_suffixes=[FOLDER_SUFFIX],
            member_tags=[MEMBER_TAG],
            team_name=TEAM1,
            conn=conn,
        )

        # Assert: metadata folder deleted (team-scoped), outbox folder skipped
        deleted = [c[0][0] for c in mock_client.delete_config_folder.call_args_list]
        assert meta_id in deleted, "metadata folder should always be deleted (team-scoped)"
        assert outbox_id not in deleted, "outbox folder should be skipped (needed by team-two)"


class TestCleanupDeletesFolderWhenNoOtherTeam:
    """M1 only in T1. Leave T1 -> outbox IS deleted."""

    @pytest.mark.asyncio
    async def test_cleanup_deletes_folder_when_no_other_team(self, conn, manager, mock_client):
        # Setup: alice is only in team-one
        seed_team(conn, TEAM1)
        seed_member(conn, MEMBER_TAG, TEAM1)
        seed_project(conn, TEAM1)
        seed_subscription(conn, MEMBER_TAG, TEAM1)

        outbox_id = build_outbox_folder_id(MEMBER_TAG, FOLDER_SUFFIX)
        meta_id = build_metadata_folder_id(TEAM1)

        mock_client.get_config_folders.return_value = [
            {"id": outbox_id},
            {"id": meta_id},
        ]

        # Act: cleanup team-one folders WITH conn
        await manager.cleanup_team_folders(
            folder_suffixes=[FOLDER_SUFFIX],
            member_tags=[MEMBER_TAG],
            team_name=TEAM1,
            conn=conn,
        )

        # Assert: both metadata and outbox folders are deleted
        deleted = [c[0][0] for c in mock_client.delete_config_folder.call_args_list]
        assert meta_id in deleted
        assert outbox_id in deleted, "outbox folder should be deleted (no other team needs it)"


class TestCleanupProjectSkipsCrossTeamFolder:
    """Remove P1 from T1 while T2 still shares P1 -> outbox NOT deleted."""

    @pytest.mark.asyncio
    async def test_cleanup_project_skips_cross_team_folder(self, conn, manager, mock_client):
        # Setup: alice is in team-one and team-two, both sharing the same project
        seed_team(conn, TEAM1)
        seed_team(conn, TEAM2)
        seed_member(conn, MEMBER_TAG, TEAM1)
        seed_member(conn, MEMBER_TAG, TEAM2)
        seed_project(conn, TEAM1)
        seed_project(conn, TEAM2)
        seed_subscription(conn, MEMBER_TAG, TEAM1)
        seed_subscription(conn, MEMBER_TAG, TEAM2)

        outbox_id = build_outbox_folder_id(MEMBER_TAG, FOLDER_SUFFIX)

        mock_client.get_config_folders.return_value = [
            {"id": outbox_id},
        ]

        # Act: cleanup project folders for team-one WITH conn + team_name
        await manager.cleanup_project_folders(
            folder_suffix=FOLDER_SUFFIX,
            member_tags=[MEMBER_TAG],
            conn=conn,
            team_name=TEAM1,
        )

        # Assert: outbox folder should NOT be deleted (team-two still needs it)
        mock_client.delete_config_folder.assert_not_called()

    @pytest.mark.asyncio
    async def test_cleanup_project_deletes_when_no_cross_team(self, conn, manager, mock_client):
        """When only one team shares the project, folder IS deleted."""
        seed_team(conn, TEAM1)
        seed_member(conn, MEMBER_TAG, TEAM1)
        seed_project(conn, TEAM1)
        seed_subscription(conn, MEMBER_TAG, TEAM1)

        outbox_id = build_outbox_folder_id(MEMBER_TAG, FOLDER_SUFFIX)

        mock_client.get_config_folders.return_value = [
            {"id": outbox_id},
        ]

        await manager.cleanup_project_folders(
            folder_suffix=FOLDER_SUFFIX,
            member_tags=[MEMBER_TAG],
            conn=conn,
            team_name=TEAM1,
        )

        # Assert: folder IS deleted (no other team shares this project)
        mock_client.delete_config_folder.assert_called_once_with(outbox_id)

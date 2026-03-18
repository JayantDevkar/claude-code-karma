"""End-to-end smoke test: full sync v4 stack from router to domain model."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import sqlite3

import pytest
from unittest.mock import MagicMock, AsyncMock

from db.schema import ensure_schema

from domain.team import Team, TeamStatus
from domain.member import Member, MemberStatus
from domain.project import SharedProject, derive_folder_suffix
from domain.subscription import Subscription, SubscriptionStatus, SyncDirection
from domain.events import SyncEvent, SyncEventType
from repositories.team_repo import TeamRepository
from repositories.member_repo import MemberRepository
from repositories.project_repo import ProjectRepository
from repositories.subscription_repo import SubscriptionRepository
from repositories.event_repo import EventRepository
from services.sync.team_service import TeamService
from services.sync.project_service import ProjectService
from services.sync.pairing_service import PairingService
from services.sync.metadata_service import MetadataService
from services.sync.reconciliation_service import ReconciliationService


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA foreign_keys=ON")
    ensure_schema(c)
    return c


@pytest.fixture
def meta_base(tmp_path):
    return tmp_path / "meta"


@pytest.fixture
def stack(conn, meta_base):
    """Build full service stack with mocked Syncthing managers."""
    devices = MagicMock()
    devices.pair = AsyncMock()
    devices.unpair = AsyncMock()
    devices.ensure_paired = AsyncMock()

    folders = MagicMock()
    folders.ensure_outbox_folder = AsyncMock()
    folders.ensure_inbox_folder = AsyncMock()
    folders.set_folder_devices = AsyncMock()
    folders.remove_outbox_folder = AsyncMock()
    folders.remove_device_from_team_folders = AsyncMock()
    folders.cleanup_team_folders = AsyncMock()
    folders.cleanup_project_folders = AsyncMock()

    repos = {
        "teams": TeamRepository(),
        "members": MemberRepository(),
        "projects": ProjectRepository(),
        "subs": SubscriptionRepository(),
        "events": EventRepository(),
    }
    metadata = MetadataService(meta_base=meta_base)

    team_svc = TeamService(
        **repos, devices=devices, metadata=metadata, folders=folders,
    )
    project_svc = ProjectService(
        **repos,
        folders=folders,
        metadata=metadata,
    )
    recon_svc = ReconciliationService(
        **repos,
        devices=devices,
        folders=folders,
        metadata=metadata,
        my_member_tag="jayant.macbook",
    )
    pairing_svc = PairingService()

    return {
        "team_svc": team_svc,
        "project_svc": project_svc,
        "recon_svc": recon_svc,
        "pairing_svc": pairing_svc,
        "devices": devices,
        "folders": folders,
        **repos,
    }


class TestFullE2EFlow:
    """Tests the complete user journey from spec Flows 1-5."""

    async def test_complete_sync_lifecycle(self, conn, stack):
        team_svc = stack["team_svc"]
        project_svc = stack["project_svc"]
        pairing_svc = stack["pairing_svc"]

        # Flow 1: Leader creates team
        team = await team_svc.create_team(
            conn,
            name="karma",
            leader_member_tag="jayant.macbook",
            leader_device_id="DEV-L",
        )
        assert team.status == TeamStatus.ACTIVE

        # Leader shares project (git-only, with encoded_name)
        project = await project_svc.share_project(
            conn,
            team_name="karma",
            by_device="DEV-L",
            git_identity="jayantdevkar/claude-karma",
            encoded_name="-Users-jayant-GitHub-claude-karma",
        )
        assert project.git_identity == "jayantdevkar/claude-karma"
        assert project.folder_suffix == derive_folder_suffix("jayantdevkar/claude-karma")
        # Leader has local copy — outbox folder should be created
        stack["folders"].ensure_outbox_folder.assert_called_once()

        # Flow 2: Member generates pairing code, leader validates and adds member
        code = pairing_svc.generate_code("ayush.laptop", "DEV-A")
        info = pairing_svc.validate_code(code)
        assert info.member_tag == "ayush.laptop"
        assert info.device_id == "DEV-A"

        member = await team_svc.add_member(
            conn,
            team_name="karma",
            by_device="DEV-L",
            new_member_tag=info.member_tag,
            new_device_id=info.device_id,
        )
        assert member.status == MemberStatus.ADDED
        stack["devices"].pair.assert_called_once_with("DEV-A")

        # Verify subscription was auto-created as OFFERED
        subs = stack["subs"].list_for_member(conn, "ayush.laptop")
        assert len(subs) == 1
        assert subs[0].status == SubscriptionStatus.OFFERED
        assert subs[0].project_git_identity == "jayantdevkar/claude-karma"

        # Flow 3: Member accepts project with direction=BOTH
        stack["folders"].ensure_outbox_folder.reset_mock()
        stack["folders"].ensure_inbox_folder.reset_mock()

        accepted = await project_svc.accept_subscription(
            conn,
            member_tag="ayush.laptop",
            team_name="karma",
            git_identity="jayantdevkar/claude-karma",
            direction=SyncDirection.BOTH,
        )
        assert accepted.status == SubscriptionStatus.ACCEPTED
        assert accepted.direction == SyncDirection.BOTH
        # BOTH direction: outbox (send) + inbox (receive from each active teammate)
        stack["folders"].ensure_outbox_folder.assert_called()
        stack["folders"].ensure_inbox_folder.assert_called()

        # Flow 5: Member changes direction to RECEIVE only
        stack["folders"].remove_outbox_folder.reset_mock()

        changed = await project_svc.change_direction(
            conn,
            member_tag="ayush.laptop",
            team_name="karma",
            git_identity="jayantdevkar/claude-karma",
            direction=SyncDirection.RECEIVE,
        )
        assert changed.direction == SyncDirection.RECEIVE
        # Was sending (BOTH), now not sending — outbox should be removed
        stack["folders"].remove_outbox_folder.assert_called_once_with(
            "ayush.laptop", project.folder_suffix,
        )

        # Flow 4: Leader removes member
        removed = await team_svc.remove_member(
            conn,
            team_name="karma",
            by_device="DEV-L",
            member_tag="ayush.laptop",
        )
        assert removed.status == MemberStatus.REMOVED
        # Device not in other teams — should be unpaired
        stack["devices"].unpair.assert_called_once_with("DEV-A")

        # Verify removal signal written to metadata folder
        meta = metadata_service_from_stack(stack)
        team_meta = meta.read_team_metadata("karma")
        assert "__removals" in team_meta
        assert "ayush.laptop" in team_meta["__removals"]

        # Verify all expected events were logged
        events = stack["events"].query(conn, team="karma", limit=100)
        event_types = {e.event_type.value for e in events}
        assert "team_created" in event_types
        assert "project_shared" in event_types
        assert "member_added" in event_types
        assert "subscription_accepted" in event_types
        assert "direction_changed" in event_types
        assert "member_removed" in event_types

    async def test_pairing_code_roundtrip(self, stack):
        """Pairing code encodes and decodes member_tag + device_id losslessly."""
        pairing_svc = stack["pairing_svc"]
        code = pairing_svc.generate_code("alice.desktop", "DEV-XYZ")
        assert isinstance(code, str)
        assert len(code) > 0

        info = pairing_svc.validate_code(code)
        assert info.member_tag == "alice.desktop"
        assert info.device_id == "DEV-XYZ"

    async def test_team_create_logs_event(self, conn, stack):
        """Creating a team always logs team_created event."""
        await stack["team_svc"].create_team(
            conn,
            name="alpha",
            leader_member_tag="bob.server",
            leader_device_id="DEV-B",
        )
        events = stack["events"].query(conn, team="alpha")
        assert any(e.event_type == SyncEventType.team_created for e in events)

    async def test_share_project_without_local_repo_skips_outbox(self, conn, stack):
        """Sharing a project without encoded_name (git-only) skips outbox creation."""
        await stack["team_svc"].create_team(
            conn,
            name="beta",
            leader_member_tag="carol.laptop",
            leader_device_id="DEV-C",
        )
        stack["folders"].ensure_outbox_folder.reset_mock()

        project = await stack["project_svc"].share_project(
            conn,
            team_name="beta",
            by_device="DEV-C",
            git_identity="org/remote-only-repo",
            encoded_name=None,  # no local copy
        )
        assert project.git_identity == "org/remote-only-repo"
        # No local copy → no outbox folder
        stack["folders"].ensure_outbox_folder.assert_not_called()

    async def test_decline_subscription(self, conn, stack):
        """Member can decline an offered subscription."""
        # Setup
        await stack["team_svc"].create_team(
            conn,
            name="gamma",
            leader_member_tag="dave.mac",
            leader_device_id="DEV-D",
        )
        await stack["project_svc"].share_project(
            conn,
            team_name="gamma",
            by_device="DEV-D",
            git_identity="dave/project",
        )
        await stack["team_svc"].add_member(
            conn,
            team_name="gamma",
            by_device="DEV-D",
            new_member_tag="eve.laptop",
            new_device_id="DEV-E",
        )

        declined = await stack["project_svc"].decline_subscription(
            conn,
            member_tag="eve.laptop",
            team_name="gamma",
            git_identity="dave/project",
        )
        assert declined.status == SubscriptionStatus.DECLINED

        events = stack["events"].query(conn, team="gamma", limit=100)
        event_types = {e.event_type.value for e in events}
        assert "subscription_declined" in event_types


def metadata_service_from_stack(stack: dict) -> "MetadataService":
    """Extract MetadataService from the team_svc (shared reference)."""
    return stack["team_svc"].metadata

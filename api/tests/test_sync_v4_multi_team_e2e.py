"""Multi-team overlap E2E test — verifies cross-team safety.

Exercises the exact scenario from the v3 audit: two teams sharing the same
project with an overlapping member.  Validates that leave/dissolve/remove-project
operations on one team never corrupt the other team's data.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import sqlite3

import pytest
from unittest.mock import MagicMock, AsyncMock

from db.schema import ensure_schema

from domain.team import TeamStatus
from domain.member import MemberStatus
from domain.project import SharedProject, SharedProjectStatus, derive_folder_suffix
from domain.subscription import Subscription, SubscriptionStatus, SyncDirection
from domain.events import SyncEvent, SyncEventType
from repositories.team_repo import TeamRepository
from repositories.member_repo import MemberRepository
from repositories.project_repo import ProjectRepository
from repositories.subscription_repo import SubscriptionRepository
from repositories.event_repo import EventRepository
from services.sync.team_service import TeamService
from services.sync.project_service import ProjectService
from services.sync.reconciliation_service import ReconciliationService
from services.sync.metadata_service import MetadataService


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
    folders.ensure_metadata_folder = AsyncMock()
    folders.ensure_outbox_folder = AsyncMock()
    folders.ensure_inbox_folder = AsyncMock()
    folders.set_folder_devices = AsyncMock()
    folders.get_configured_folders = AsyncMock(return_value=[])
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
        **repos, folders=folders, metadata=metadata,
    )

    return {
        "team_svc": team_svc,
        "project_svc": project_svc,
        "devices": devices,
        "folders": folders,
        "metadata": metadata,
        **repos,
    }


# ---------------------------------------------------------------------------
# Helpers — build the two-team, overlapping-member scenario
# ---------------------------------------------------------------------------

async def _setup_two_teams_shared_project(conn, stack):
    """Create T1 (leader=L1) and T2 (leader=L2), both sharing 'owner/repo'.

    Alice is added to both teams and accepts the project in both (direction=BOTH).
    Returns dict with keys: t1, t2, p1, p2, alice_sub_t1, alice_sub_t2.
    """
    team_svc = stack["team_svc"]
    project_svc = stack["project_svc"]

    # --- Team 1 ---
    t1 = await team_svc.create_team(
        conn,
        name="team-1",
        leader_member_tag="leader1.desktop",
        leader_device_id="DEV-L1",
    )

    p1 = await project_svc.share_project(
        conn,
        team_name="team-1",
        by_device="DEV-L1",
        git_identity="owner/repo",
        encoded_name="-Users-owner-repo",
    )

    # --- Team 2 ---
    t2 = await team_svc.create_team(
        conn,
        name="team-2",
        leader_member_tag="leader2.laptop",
        leader_device_id="DEV-L2",
    )

    p2 = await project_svc.share_project(
        conn,
        team_name="team-2",
        by_device="DEV-L2",
        git_identity="owner/repo",
        encoded_name="-Users-owner-repo",
    )

    # --- Alice joins both teams ---
    await team_svc.add_member(
        conn,
        team_name="team-1",
        by_device="DEV-L1",
        new_member_tag="alice.laptop",
        new_device_id="DEV-ALICE",
    )

    await team_svc.add_member(
        conn,
        team_name="team-2",
        by_device="DEV-L2",
        new_member_tag="alice.laptop",
        new_device_id="DEV-ALICE",
    )

    # --- Activate Alice in both teams (simulates reconciliation Phase 1) ---
    members_repo = stack["members"]
    alice_t1 = members_repo.get(conn, "team-1", "alice.laptop")
    members_repo.save(conn, alice_t1.activate())
    alice_t2 = members_repo.get(conn, "team-2", "alice.laptop")
    members_repo.save(conn, alice_t2.activate())

    # --- Alice accepts project in both teams ---
    alice_sub_t1 = await project_svc.accept_subscription(
        conn,
        member_tag="alice.laptop",
        team_name="team-1",
        git_identity="owner/repo",
        direction=SyncDirection.BOTH,
    )

    alice_sub_t2 = await project_svc.accept_subscription(
        conn,
        member_tag="alice.laptop",
        team_name="team-2",
        git_identity="owner/repo",
        direction=SyncDirection.BOTH,
    )

    return {
        "t1": t1,
        "t2": t2,
        "p1": p1,
        "p2": p2,
        "alice_sub_t1": alice_sub_t1,
        "alice_sub_t2": alice_sub_t2,
    }


# ---------------------------------------------------------------------------
# Test class
# ---------------------------------------------------------------------------

class TestMultiTeamOverlapE2E:
    """Verifies cross-team safety when two teams share the same project
    with an overlapping member (Alice)."""

    async def test_leave_team1_preserves_team2_subscriptions(self, conn, stack):
        """Full lifecycle: Alice leaves Team 1, Team 2 subscription stays intact.

        Steps:
        1. Create Team 1 (leader: L1) and Team 2 (leader: L2)
        2. Both leaders share the same project (git_identity="owner/repo")
        3. Add Alice to both teams via pairing flow
        4. Alice accepts project in both teams (direction=BOTH)
        5. Verify Alice has 2 ACCEPTED subscriptions
        6. Alice leaves Team 1
        7. Verify: Alice's Team 2 subscription is still ACCEPTED with direction=both
        8. Verify: Team 1 data is deleted (team not found)
        9. Run Phase 3 reconciliation for Team 2 — verify it still works
        """
        ctx = await _setup_two_teams_shared_project(conn, stack)
        team_svc = stack["team_svc"]
        subs_repo = stack["subs"]

        # Step 5: Verify Alice has 2 ACCEPTED subscriptions
        alice_subs = subs_repo.list_for_member(conn, "alice.laptop")
        accepted = [s for s in alice_subs if s.status == SubscriptionStatus.ACCEPTED]
        assert len(accepted) == 2, (
            f"Expected 2 ACCEPTED subs for Alice, got {len(accepted)}: "
            f"{[(s.team_name, s.status.value) for s in alice_subs]}"
        )

        # Step 6: Alice leaves Team 1
        await team_svc.leave_team(
            conn,
            team_name="team-1",
            member_tag="alice.laptop",
        )

        # Step 7: Team 2 subscription must survive
        t2_sub = subs_repo.get(conn, "alice.laptop", "team-2", "owner/repo")
        assert t2_sub is not None, "Team 2 subscription must survive after leaving Team 1"
        assert t2_sub.status == SubscriptionStatus.ACCEPTED
        assert t2_sub.direction == SyncDirection.BOTH

        # Step 8: Team 1 is gone (deleted by leave_team)
        teams_repo = stack["teams"]
        t1_after = teams_repo.get(conn, "team-1")
        assert t1_after is None, "Team 1 should be deleted after Alice leaves"

        # Team 2 still exists and is ACTIVE
        t2_after = teams_repo.get(conn, "team-2")
        assert t2_after is not None
        assert t2_after.status == TeamStatus.ACTIVE

        # Step 9: Phase 3 reconciliation for Team 2 still works
        # Build a ReconciliationService as Alice's machine
        recon_svc = ReconciliationService(
            **{k: v for k, v in stack.items()
               if k in ("teams", "members", "projects", "subs", "events")},
            devices=stack["devices"],
            folders=stack["folders"],
            metadata=stack["metadata"],
            my_member_tag="alice.laptop",
            my_device_id="DEV-ALICE",
        )

        # Reset mocks so we can check Phase 3 calls
        stack["folders"].set_folder_devices.reset_mock()
        stack["folders"].ensure_outbox_folder.reset_mock()

        await recon_svc.phase_device_lists(conn, t2_after)

        # Phase 3 should have called set_folder_devices for Team 2's project
        assert stack["folders"].set_folder_devices.call_count > 0, (
            "Phase 3 must call set_folder_devices for Team 2 after Alice leaves Team 1"
        )

        # Verify the desired device set includes Alice and L2 (both have ACCEPTED+BOTH)
        # Since list_accepted_for_suffix returns all accepted subs for the suffix
        # across ALL teams, and Team 1 is deleted, only Team 2 subs remain.
        suffix = derive_folder_suffix("owner/repo")
        all_accepted = subs_repo.list_accepted_for_suffix(conn, suffix)
        accepted_tags = {s.member_tag for s in all_accepted}
        assert "alice.laptop" in accepted_tags, (
            "Alice must still appear in accepted subs for the project suffix"
        )
        assert "leader2.laptop" in accepted_tags, (
            "Leader 2 must still appear in accepted subs for the project suffix"
        )
        # Team 1's leader sub should be gone (CASCADE on team delete)
        assert all(s.team_name == "team-2" for s in all_accepted), (
            "All remaining accepted subs should belong to team-2"
        )

    async def test_dissolve_team_preserves_other_team(self, conn, stack):
        """Leader dissolves Team 1 — Team 2 and Alice's T2 subscription survive.

        Steps:
        1. Create T1 and T2 sharing same project, Alice in both (accepts both)
        2. L1 dissolves T1
        3. Verify: T2 and Alice's T2 subscription still intact
        """
        ctx = await _setup_two_teams_shared_project(conn, stack)
        team_svc = stack["team_svc"]
        teams_repo = stack["teams"]
        subs_repo = stack["subs"]
        projects_repo = stack["projects"]

        # Verify precondition: both teams exist
        assert teams_repo.get(conn, "team-1") is not None
        assert teams_repo.get(conn, "team-2") is not None

        # L1 dissolves Team 1
        dissolved = await team_svc.dissolve_team(
            conn,
            team_name="team-1",
            by_device="DEV-L1",
        )
        assert dissolved.status == TeamStatus.DISSOLVED

        # Team 1 is gone
        assert teams_repo.get(conn, "team-1") is None

        # Team 2 is alive and ACTIVE
        t2 = teams_repo.get(conn, "team-2")
        assert t2 is not None
        assert t2.status == TeamStatus.ACTIVE

        # Alice's Team 2 subscription survived
        t2_sub = subs_repo.get(conn, "alice.laptop", "team-2", "owner/repo")
        assert t2_sub is not None, "Alice's T2 subscription must survive T1 dissolution"
        assert t2_sub.status == SubscriptionStatus.ACCEPTED
        assert t2_sub.direction == SyncDirection.BOTH

        # Leader 2's subscription survived
        l2_sub = subs_repo.get(conn, "leader2.laptop", "team-2", "owner/repo")
        assert l2_sub is not None, "Leader 2's subscription must survive T1 dissolution"
        assert l2_sub.status == SubscriptionStatus.ACCEPTED

        # Team 2's project is still SHARED
        t2_proj = projects_repo.get(conn, "team-2", "owner/repo")
        assert t2_proj is not None
        assert t2_proj.status == SharedProjectStatus.SHARED

        # Team 1's project is gone (CASCADE)
        t1_proj = projects_repo.get(conn, "team-1", "owner/repo")
        assert t1_proj is None, "Team 1's project should be deleted by CASCADE"

        # Alice's Team 1 subscription is gone (CASCADE)
        t1_sub = subs_repo.get(conn, "alice.laptop", "team-1", "owner/repo")
        assert t1_sub is None, "Alice's T1 subscription should be deleted by CASCADE"

        # Team 1 members are gone (CASCADE)
        members_repo = stack["members"]
        t1_members = members_repo.list_for_team(conn, "team-1")
        assert len(t1_members) == 0, "Team 1 members should be deleted by CASCADE"

        # Team 2 members still intact
        t2_members = members_repo.list_for_team(conn, "team-2")
        t2_tags = {m.member_tag for m in t2_members}
        assert "leader2.laptop" in t2_tags
        assert "alice.laptop" in t2_tags

    async def test_remove_project_from_one_team_preserves_other(self, conn, stack):
        """L1 removes project from T1 — T2's project and Alice's T2 subscription survive.

        Steps:
        1. Create T1 and T2 sharing same project, Alice in both (accepts both)
        2. L1 removes project from T1
        3. Verify: T2's project still SHARED, Alice's T2 subscription still ACCEPTED
        """
        ctx = await _setup_two_teams_shared_project(conn, stack)
        project_svc = stack["project_svc"]
        subs_repo = stack["subs"]
        projects_repo = stack["projects"]

        # Precondition: both teams have the project as SHARED
        p1 = projects_repo.get(conn, "team-1", "owner/repo")
        p2 = projects_repo.get(conn, "team-2", "owner/repo")
        assert p1 is not None and p1.status == SharedProjectStatus.SHARED
        assert p2 is not None and p2.status == SharedProjectStatus.SHARED

        # L1 removes project from Team 1
        removed = await project_svc.remove_project(
            conn,
            team_name="team-1",
            by_device="DEV-L1",
            git_identity="owner/repo",
        )
        assert removed.status == SharedProjectStatus.REMOVED

        # Team 1's project is REMOVED
        t1_proj = projects_repo.get(conn, "team-1", "owner/repo")
        assert t1_proj is not None
        assert t1_proj.status == SharedProjectStatus.REMOVED

        # Team 2's project is still SHARED
        t2_proj = projects_repo.get(conn, "team-2", "owner/repo")
        assert t2_proj is not None, "T2 project must survive T1 project removal"
        assert t2_proj.status == SharedProjectStatus.SHARED

        # Alice's Team 2 subscription still ACCEPTED
        t2_sub = subs_repo.get(conn, "alice.laptop", "team-2", "owner/repo")
        assert t2_sub is not None, "Alice's T2 subscription must survive T1 project removal"
        assert t2_sub.status == SubscriptionStatus.ACCEPTED
        assert t2_sub.direction == SyncDirection.BOTH

        # Leader 2's Team 2 subscription still ACCEPTED
        l2_sub = subs_repo.get(conn, "leader2.laptop", "team-2", "owner/repo")
        assert l2_sub is not None
        assert l2_sub.status == SubscriptionStatus.ACCEPTED

        # Alice's Team 1 subscription should be DECLINED (remove_project declines all)
        t1_sub = subs_repo.get(conn, "alice.laptop", "team-1", "owner/repo")
        assert t1_sub is not None
        assert t1_sub.status == SubscriptionStatus.DECLINED

        # Leader 1's Team 1 subscription should also be DECLINED
        l1_sub = subs_repo.get(conn, "leader1.desktop", "team-1", "owner/repo")
        assert l1_sub is not None
        assert l1_sub.status == SubscriptionStatus.DECLINED

        # Phase 3 for Team 2 still produces correct device sets
        suffix = derive_folder_suffix("owner/repo")
        all_accepted = subs_repo.list_accepted_for_suffix(conn, suffix)
        # Only Team 2 subs should be accepted (Team 1 subs are DECLINED)
        assert all(s.team_name == "team-2" for s in all_accepted), (
            f"Only T2 subs should be accepted, got: "
            f"{[(s.team_name, s.member_tag, s.status.value) for s in all_accepted]}"
        )
        accepted_tags = {s.member_tag for s in all_accepted}
        assert "alice.laptop" in accepted_tags
        assert "leader2.laptop" in accepted_tags

    async def test_phase3_device_lists_cross_team_after_leave(self, conn, stack):
        """Phase 3 computes correct device set when Alice is in T2 only.

        Ensures that after leaving T1, Phase 3 includes Alice's device in
        outbox device lists for T2's project folders but NOT T1's.
        """
        ctx = await _setup_two_teams_shared_project(conn, stack)
        team_svc = stack["team_svc"]
        teams_repo = stack["teams"]

        # Alice leaves Team 1
        await team_svc.leave_team(
            conn,
            team_name="team-1",
            member_tag="alice.laptop",
        )

        # Phase 3 for Team 2 (as leader 2's machine)
        recon_svc = ReconciliationService(
            **{k: v for k, v in stack.items()
               if k in ("teams", "members", "projects", "subs", "events")},
            devices=stack["devices"],
            folders=stack["folders"],
            metadata=stack["metadata"],
            my_member_tag="leader2.laptop",
            my_device_id="DEV-L2",
        )

        stack["folders"].set_folder_devices.reset_mock()

        t2 = teams_repo.get(conn, "team-2")
        assert t2 is not None
        await recon_svc.phase_device_lists(conn, t2)

        # Verify set_folder_devices was called and includes both L2 and Alice
        assert stack["folders"].set_folder_devices.call_count > 0

        # Collect all device sets passed to set_folder_devices
        all_device_sets = [
            call.args[1] if len(call.args) > 1 else call.kwargs.get("device_ids", set())
            for call in stack["folders"].set_folder_devices.call_args_list
        ]
        # At least one call should include both DEV-L2 and DEV-ALICE
        has_both = any(
            "DEV-L2" in ds and "DEV-ALICE" in ds
            for ds in all_device_sets
        )
        assert has_both, (
            f"Phase 3 device sets should include both DEV-L2 and DEV-ALICE: {all_device_sets}"
        )

    async def test_alice_device_not_unpaired_when_in_other_team(self, conn, stack):
        """When Alice is removed from T1, her device is NOT unpaired because she's in T2."""
        ctx = await _setup_two_teams_shared_project(conn, stack)
        team_svc = stack["team_svc"]

        stack["devices"].unpair.reset_mock()

        # L1 removes Alice from Team 1
        await team_svc.remove_member(
            conn,
            team_name="team-1",
            by_device="DEV-L1",
            member_tag="alice.laptop",
        )

        # Alice's device should NOT be unpaired — she's still in Team 2
        stack["devices"].unpair.assert_not_called()

        # Alice's Team 2 subscription is unaffected
        t2_sub = stack["subs"].get(conn, "alice.laptop", "team-2", "owner/repo")
        assert t2_sub is not None
        assert t2_sub.status == SubscriptionStatus.ACCEPTED

    async def test_events_logged_correctly_across_teams(self, conn, stack):
        """Event log correctly attributes events to their respective teams."""
        ctx = await _setup_two_teams_shared_project(conn, stack)
        events_repo = stack["events"]

        # Check Team 1 events
        t1_events = events_repo.query(conn, team="team-1", limit=100)
        t1_types = {e.event_type.value for e in t1_events}
        assert "team_created" in t1_types
        assert "project_shared" in t1_types
        assert "member_added" in t1_types
        assert "subscription_accepted" in t1_types

        # Check Team 2 events
        t2_events = events_repo.query(conn, team="team-2", limit=100)
        t2_types = {e.event_type.value for e in t2_events}
        assert "team_created" in t2_types
        assert "project_shared" in t2_types
        assert "member_added" in t2_types
        assert "subscription_accepted" in t2_types

        # Dissolve Team 1 and verify event isolation
        await stack["team_svc"].dissolve_team(
            conn,
            team_name="team-1",
            by_device="DEV-L1",
        )

        # Team 2 events should not contain team_dissolved
        t2_events_after = events_repo.query(conn, team="team-2", limit=100)
        t2_types_after = {e.event_type.value for e in t2_events_after}
        assert "team_dissolved" not in t2_types_after, (
            "team_dissolved event should be logged against team-1, not team-2"
        )

    async def test_folder_suffix_shared_across_teams(self, conn, stack):
        """Both teams produce the same folder_suffix for the same git_identity."""
        ctx = await _setup_two_teams_shared_project(conn, stack)
        projects_repo = stack["projects"]

        p1 = projects_repo.get(conn, "team-1", "owner/repo")
        p2 = projects_repo.get(conn, "team-2", "owner/repo")

        assert p1 is not None and p2 is not None
        assert p1.folder_suffix == p2.folder_suffix
        assert p1.folder_suffix == derive_folder_suffix("owner/repo")

    async def test_list_accepted_for_suffix_spans_both_teams(self, conn, stack):
        """list_accepted_for_suffix returns subs from BOTH teams before any cleanup."""
        ctx = await _setup_two_teams_shared_project(conn, stack)
        subs_repo = stack["subs"]

        suffix = derive_folder_suffix("owner/repo")
        all_accepted = subs_repo.list_accepted_for_suffix(conn, suffix)

        # Should include: L1 (auto-created on share), Alice (T1), L2 (auto-created), Alice (T2)
        assert len(all_accepted) == 4, (
            f"Expected 4 accepted subs (2 per team), got {len(all_accepted)}: "
            f"{[(s.team_name, s.member_tag) for s in all_accepted]}"
        )

        teams_in_subs = {s.team_name for s in all_accepted}
        assert teams_in_subs == {"team-1", "team-2"}

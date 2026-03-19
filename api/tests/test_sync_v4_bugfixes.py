"""Tests for sync v4 bugfixes: cross-team safety, state machine, dissolution."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import sqlite3

import pytest
from unittest.mock import MagicMock, AsyncMock

from db.schema import ensure_schema

from domain.team import Team, InvalidTransitionError
from domain.member import Member, MemberStatus
from domain.subscription import Subscription, SubscriptionStatus, SyncDirection
from repositories.team_repo import TeamRepository
from repositories.member_repo import MemberRepository
from repositories.project_repo import ProjectRepository
from repositories.subscription_repo import SubscriptionRepository
from repositories.event_repo import EventRepository
from services.sync.team_service import TeamService
from services.sync.project_service import ProjectService
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


async def _setup_two_teams_shared_project(conn, stack):
    """Helper: create 2 teams sharing the same project (org/webapp).

    Team alpha: leader=alice, member=dave
    Team beta:  leader=bob, member=alice
    Both share org/webapp (same git_identity → same folder_suffix).
    """
    team_svc = stack["team_svc"]
    project_svc = stack["project_svc"]

    # Create teams
    await team_svc.create_team(
        conn, name="alpha", leader_member_tag="alice.mac", leader_device_id="DEV-ALICE",
    )
    await team_svc.create_team(
        conn, name="beta", leader_member_tag="bob.linux", leader_device_id="DEV-BOB",
    )

    # Add cross-members
    await team_svc.add_member(
        conn, team_name="alpha", by_device="DEV-ALICE",
        new_member_tag="dave.win", new_device_id="DEV-DAVE",
    )
    await team_svc.add_member(
        conn, team_name="beta", by_device="DEV-BOB",
        new_member_tag="alice.mac", new_device_id="DEV-ALICE",
    )

    # Activate members BEFORE sharing (so share_project creates OFFERED subs)
    dave = stack["members"].get(conn, "alpha", "dave.win")
    stack["members"].save(conn, dave.activate())
    alice_beta = stack["members"].get(conn, "beta", "alice.mac")
    stack["members"].save(conn, alice_beta.activate())

    # Share same project in both teams
    await project_svc.share_project(
        conn, team_name="alpha", by_device="DEV-ALICE",
        git_identity="org/webapp", encoded_name="-org-webapp",
    )
    await project_svc.share_project(
        conn, team_name="beta", by_device="DEV-BOB",
        git_identity="org/webapp", encoded_name="-org-webapp",
    )

    # All members accept subscriptions
    await project_svc.accept_subscription(
        conn, member_tag="dave.win", team_name="alpha",
        git_identity="org/webapp", direction=SyncDirection.BOTH,
    )
    await project_svc.accept_subscription(
        conn, member_tag="alice.mac", team_name="beta",
        git_identity="org/webapp", direction=SyncDirection.BOTH,
    )


# ==============================================================================
# Bug 1: Phase 3 cross-team device list pollution
# ==============================================================================

class TestBug1CrossTeamDeviceListIsolation:
    """Phase 3 must compute device lists per-team, not as cross-team union."""

    async def test_device_lists_are_team_scoped(self, conn, stack):
        """Dave (alpha only) should NOT appear in beta's device lists."""
        await _setup_two_teams_shared_project(conn, stack)

        # Build reconciliation for alpha (alice's perspective)
        recon = ReconciliationService(
            **{k: stack[k] for k in ("teams", "members", "projects", "subs", "events")},
            devices=stack["devices"],
            folders=stack["folders"],
            metadata=stack["metadata"],
            my_member_tag="alice.mac",
            my_device_id="DEV-ALICE",
        )

        # Run Phase 3 for team alpha
        alpha = stack["teams"].get(conn, "alpha")
        await recon.phase_device_lists(conn, alpha)

        # Get the device sets that were applied to folders
        calls = stack["folders"].set_folder_devices.call_args_list

        # Extract all device sets applied during alpha's Phase 3
        alpha_device_sets = [set(call.args[1]) if len(call.args) > 1 else set(call.kwargs.get("device_ids", []))
                            for call in calls]

        # Dave (DEV-DAVE) should be in alpha's device sets
        # But let's verify bob (DEV-BOB, beta leader) is NOT in alpha's device sets
        for device_set in alpha_device_sets:
            assert "DEV-BOB" not in device_set, \
                "Beta leader's device leaked into alpha's folder device lists"

    async def test_cross_team_member_excluded_from_device_set(self, conn, stack):
        """Members from other teams with same project must not pollute device lists."""
        await _setup_two_teams_shared_project(conn, stack)

        recon = ReconciliationService(
            **{k: stack[k] for k in ("teams", "members", "projects", "subs", "events")},
            devices=stack["devices"],
            folders=stack["folders"],
            metadata=stack["metadata"],
            my_member_tag="bob.linux",
            my_device_id="DEV-BOB",
        )

        stack["folders"].set_folder_devices.reset_mock()

        # Run Phase 3 for team beta
        beta = stack["teams"].get(conn, "beta")
        await recon.phase_device_lists(conn, beta)

        calls = stack["folders"].set_folder_devices.call_args_list
        for call in calls:
            device_set = set(call.args[1]) if len(call.args) > 1 else set()
            assert "DEV-DAVE" not in device_set, \
                "Alpha member Dave leaked into beta's folder device lists"


# ==============================================================================
# Bug 2: DECLINED subscription reopen
# ==============================================================================

class TestBug2DeclinedReopen:
    """DECLINED subscriptions can be reopened back to OFFERED."""

    def test_reopen_transitions_declined_to_offered(self):
        sub = Subscription(
            member_tag="bob.linux", team_name="team1",
            project_git_identity="org/repo",
            status=SubscriptionStatus.DECLINED,
        )
        reopened = sub.reopen()
        assert reopened.status == SubscriptionStatus.OFFERED

    def test_reopen_from_non_declined_raises(self):
        sub = Subscription(
            member_tag="bob.linux", team_name="team1",
            project_git_identity="org/repo",
            status=SubscriptionStatus.OFFERED,
        )
        with pytest.raises(InvalidTransitionError, match="DECLINED"):
            sub.reopen()

    def test_reopen_from_accepted_raises(self):
        sub = Subscription(
            member_tag="bob.linux", team_name="team1",
            project_git_identity="org/repo",
            status=SubscriptionStatus.ACCEPTED,
        )
        with pytest.raises(InvalidTransitionError, match="DECLINED"):
            sub.reopen()

    async def test_reopen_then_accept_full_flow(self, conn, stack):
        """Decline → reopen → accept is a valid lifecycle."""
        team_svc = stack["team_svc"]
        project_svc = stack["project_svc"]

        # Setup: team with member, shared project
        await team_svc.create_team(
            conn, name="t1", leader_member_tag="alice.mac", leader_device_id="DEV-A",
        )
        await team_svc.add_member(
            conn, team_name="t1", by_device="DEV-A",
            new_member_tag="bob.linux", new_device_id="DEV-B",
        )
        # Activate bob
        bob = stack["members"].get(conn, "t1", "bob.linux")
        stack["members"].save(conn, bob.activate())

        await project_svc.share_project(
            conn, team_name="t1", by_device="DEV-A",
            git_identity="org/repo",
        )

        # Bob declines
        sub = await project_svc.decline_subscription(
            conn, member_tag="bob.linux", team_name="t1", git_identity="org/repo",
        )
        assert sub.status == SubscriptionStatus.DECLINED

        # Bob reopens
        sub = await project_svc.reopen_subscription(
            conn, member_tag="bob.linux", team_name="t1", git_identity="org/repo",
        )
        assert sub.status == SubscriptionStatus.OFFERED

        # Bob accepts with direction
        sub = await project_svc.accept_subscription(
            conn, member_tag="bob.linux", team_name="t1",
            git_identity="org/repo", direction=SyncDirection.RECEIVE,
        )
        assert sub.status == SubscriptionStatus.ACCEPTED
        assert sub.direction == SyncDirection.RECEIVE


# ==============================================================================
# Bug 3: Team dissolution notifies remote members
# ==============================================================================

class TestBug3DissolutionNotification:
    """dissolve_team() must write removal signals for all non-leader members."""

    async def test_dissolution_writes_removal_signals(self, conn, stack, meta_base):
        team_svc = stack["team_svc"]

        # Create team with 2 members
        await team_svc.create_team(
            conn, name="t1", leader_member_tag="alice.mac", leader_device_id="DEV-A",
        )
        await team_svc.add_member(
            conn, team_name="t1", by_device="DEV-A",
            new_member_tag="bob.linux", new_device_id="DEV-B",
        )
        await team_svc.add_member(
            conn, team_name="t1", by_device="DEV-A",
            new_member_tag="carol.air", new_device_id="DEV-C",
        )

        # Dissolve team
        await team_svc.dissolve_team(conn, team_name="t1", by_device="DEV-A")

        # Verify removal signals were written for bob and carol
        meta_dir = meta_base / "karma-meta--t1" / "removed"
        assert (meta_dir / "bob.linux.json").exists(), \
            "Removal signal missing for bob"
        assert (meta_dir / "carol.air.json").exists(), \
            "Removal signal missing for carol"

    async def test_dissolution_no_removal_signal_for_leader(self, conn, stack, meta_base):
        team_svc = stack["team_svc"]

        await team_svc.create_team(
            conn, name="t1", leader_member_tag="alice.mac", leader_device_id="DEV-A",
        )
        await team_svc.add_member(
            conn, team_name="t1", by_device="DEV-A",
            new_member_tag="bob.linux", new_device_id="DEV-B",
        )

        await team_svc.dissolve_team(conn, team_name="t1", by_device="DEV-A")

        meta_dir = meta_base / "karma-meta--t1" / "removed"
        assert not (meta_dir / "alice.mac.json").exists(), \
            "Leader should NOT get a removal signal"

    async def test_dissolution_signal_triggers_auto_leave(self, conn, stack, meta_base):
        """Simulates: leader dissolves, bob's reconciliation detects signal → auto-leaves."""
        team_svc = stack["team_svc"]

        await team_svc.create_team(
            conn, name="t1", leader_member_tag="alice.mac", leader_device_id="DEV-A",
        )
        await team_svc.add_member(
            conn, team_name="t1", by_device="DEV-A",
            new_member_tag="bob.linux", new_device_id="DEV-B",
        )

        # Dissolve writes removal signals
        await team_svc.dissolve_team(conn, team_name="t1", by_device="DEV-A")

        # Now simulate bob's machine: recreate team in a fresh DB
        bob_conn = sqlite3.connect(":memory:")
        bob_conn.row_factory = sqlite3.Row
        bob_conn.execute("PRAGMA foreign_keys=ON")
        ensure_schema(bob_conn)

        # Bob's machine has the team (from earlier Phase 0 discovery)
        stack["teams"].save(bob_conn, Team(
            name="t1", leader_device_id="DEV-A", leader_member_tag="alice.mac",
        ))
        bob_member = Member.from_member_tag(
            member_tag="bob.linux", team_name="t1",
            device_id="DEV-B", status=MemberStatus.ACTIVE,
        )
        stack["members"].save(bob_conn, bob_member)

        # Bob's reconciliation reads metadata — finds removal signal
        recon = ReconciliationService(
            **{k: stack[k] for k in ("teams", "members", "projects", "subs", "events")},
            devices=stack["devices"],
            folders=stack["folders"],
            metadata=stack["metadata"],
            my_member_tag="bob.linux",
            my_device_id="DEV-B",
        )

        team = stack["teams"].get(bob_conn, "t1")
        await recon.phase_metadata(bob_conn, team)

        # Bob's team should be deleted (auto-leave triggered)
        assert stack["teams"].get(bob_conn, "t1") is None, \
            "Bob's team should be deleted after auto-leave"


# ==============================================================================
# Bug 4: Leader self-removal guard
# ==============================================================================

class TestBug4LeaderSelfRemovalGuard:
    """Leader cannot remove themselves — must dissolve instead."""

    async def test_leader_cannot_self_remove(self, conn, stack):
        team_svc = stack["team_svc"]

        await team_svc.create_team(
            conn, name="t1", leader_member_tag="alice.mac", leader_device_id="DEV-A",
        )

        with pytest.raises(InvalidTransitionError, match="leader"):
            await team_svc.remove_member(
                conn, team_name="t1", by_device="DEV-A", member_tag="alice.mac",
            )

    async def test_leader_can_remove_others(self, conn, stack):
        team_svc = stack["team_svc"]

        await team_svc.create_team(
            conn, name="t1", leader_member_tag="alice.mac", leader_device_id="DEV-A",
        )
        await team_svc.add_member(
            conn, team_name="t1", by_device="DEV-A",
            new_member_tag="bob.linux", new_device_id="DEV-B",
        )

        removed = await team_svc.remove_member(
            conn, team_name="t1", by_device="DEV-A", member_tag="bob.linux",
        )
        assert removed.status == MemberStatus.REMOVED

    def test_domain_model_blocks_leader_removal(self):
        team = Team(
            name="t1", leader_device_id="DEV-A", leader_member_tag="alice.mac",
        )
        member = Member.from_member_tag(
            member_tag="alice.mac", team_name="t1",
            device_id="DEV-A", status=MemberStatus.ACTIVE,
        )
        with pytest.raises(InvalidTransitionError, match="leader"):
            team.remove_member(member, by_device="DEV-A")


# ==============================================================================
# Bug 5: change_direction cross-team outbox safety
# ==============================================================================

class TestBug5ChangeDirectionCrossTeamSafety:
    """Changing direction should not delete outbox if another team needs it."""

    async def test_outbox_preserved_when_other_team_needs_it(self, conn, stack):
        """Bob has BOTH in alpha, SEND in beta (same project).
        Changing alpha to RECEIVE should NOT delete outbox."""
        await _setup_two_teams_shared_project(conn, stack)
        project_svc = stack["project_svc"]

        # Bob accepts in both teams: BOTH in alpha (via add_member OFFERED),
        # but bob isn't in alpha. Let's set up bob in alpha too.
        # Actually, let's create a simpler scenario:
        # alice has ACCEPTED/BOTH in alpha (leader auto-accept)
        # alice has ACCEPTED/BOTH in beta (accepted above)
        # Change alpha direction to RECEIVE → should NOT delete outbox

        stack["folders"].remove_outbox_folder.reset_mock()

        await project_svc.change_direction(
            conn, member_tag="alice.mac", team_name="alpha",
            git_identity="org/webapp", direction=SyncDirection.RECEIVE,
        )

        # Outbox should NOT be removed because beta still has BOTH
        stack["folders"].remove_outbox_folder.assert_not_called()

    async def test_outbox_removed_when_no_other_team_needs_it(self, conn, stack):
        """If alice only has one team, changing to RECEIVE should delete outbox."""
        team_svc = stack["team_svc"]
        project_svc = stack["project_svc"]

        await team_svc.create_team(
            conn, name="solo", leader_member_tag="eve.ubuntu", leader_device_id="DEV-E",
        )
        await project_svc.share_project(
            conn, team_name="solo", by_device="DEV-E",
            git_identity="org/solo-repo", encoded_name="-org-solo-repo",
        )

        stack["folders"].remove_outbox_folder.reset_mock()

        await project_svc.change_direction(
            conn, member_tag="eve.ubuntu", team_name="solo",
            git_identity="org/solo-repo", direction=SyncDirection.RECEIVE,
        )

        # Outbox SHOULD be removed — no other team has this project
        stack["folders"].remove_outbox_folder.assert_called_once()

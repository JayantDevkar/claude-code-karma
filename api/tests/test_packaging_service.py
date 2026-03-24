"""Tests for PackagingService.resolve_packagable_projects()."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import sqlite3

import pytest

from db.schema import ensure_schema
from domain.member import Member
from domain.project import SharedProject
from domain.subscription import Subscription, SubscriptionStatus, SyncDirection
from domain.team import Team
from repositories.member_repo import MemberRepository
from repositories.project_repo import ProjectRepository
from repositories.subscription_repo import SubscriptionRepository
from repositories.team_repo import TeamRepository
from services.sync.packaging_service import PackagingService


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA foreign_keys=ON")
    ensure_schema(c)
    return c


@pytest.fixture
def setup(conn):
    """Pre-populate: team 'alpha', member 'jay.mac1', project 'org/repo' (shared)."""
    TeamRepository().save(conn, Team(
        name="alpha", leader_device_id="DEV1", leader_member_tag="jay.mac1",
    ))
    MemberRepository().save(conn, Member(
        member_tag="jay.mac1", team_name="alpha",
        device_id="DEV1", user_id="jay", machine_tag="mac1",
    ))
    ProjectRepository().save(conn, SharedProject(
        team_name="alpha", git_identity="org/repo",
        encoded_name="-Users-jay-repo", folder_suffix="org-repo",
    ))
    return conn


class TestResolvePackagableProjects:
    """Tests for PackagingService.resolve_packagable_projects."""

    def test_returns_accepted_send_subscription(self, setup):
        """Accepted subscription with direction=send should be included."""
        conn = setup
        sub = Subscription(
            member_tag="jay.mac1", team_name="alpha",
            project_git_identity="org/repo",
        ).accept(SyncDirection.SEND)
        SubscriptionRepository().save(conn, sub)

        svc = PackagingService(member_tag="jay.mac1")
        results = svc.resolve_packagable_projects(conn)

        assert len(results) == 1
        assert results[0]["team_name"] == "alpha"
        assert results[0]["git_identity"] == "org/repo"
        assert results[0]["encoded_name"] == "-Users-jay-repo"
        assert results[0]["folder_suffix"] == "org-repo"

    def test_returns_accepted_both_subscription(self, setup):
        """Accepted subscription with direction=both should be included."""
        conn = setup
        sub = Subscription(
            member_tag="jay.mac1", team_name="alpha",
            project_git_identity="org/repo",
        ).accept(SyncDirection.BOTH)
        SubscriptionRepository().save(conn, sub)

        svc = PackagingService(member_tag="jay.mac1")
        results = svc.resolve_packagable_projects(conn)

        assert len(results) == 1
        assert results[0]["team_name"] == "alpha"

    def test_skips_receive_only_subscription(self, setup):
        """Accepted subscription with direction=receive should NOT be included."""
        conn = setup
        sub = Subscription(
            member_tag="jay.mac1", team_name="alpha",
            project_git_identity="org/repo",
        ).accept(SyncDirection.RECEIVE)
        SubscriptionRepository().save(conn, sub)

        svc = PackagingService(member_tag="jay.mac1")
        results = svc.resolve_packagable_projects(conn)

        assert len(results) == 0

    def test_skips_offered_subscription(self, setup):
        """Offered (not yet accepted) subscription should NOT be included."""
        conn = setup
        sub = Subscription(
            member_tag="jay.mac1", team_name="alpha",
            project_git_identity="org/repo",
        )
        SubscriptionRepository().save(conn, sub)

        svc = PackagingService(member_tag="jay.mac1")
        results = svc.resolve_packagable_projects(conn)

        assert len(results) == 0

    def test_skips_declined_subscription(self, setup):
        """Declined subscription should NOT be included."""
        conn = setup
        sub = Subscription(
            member_tag="jay.mac1", team_name="alpha",
            project_git_identity="org/repo",
        ).accept(SyncDirection.BOTH).decline()
        SubscriptionRepository().save(conn, sub)

        svc = PackagingService(member_tag="jay.mac1")
        results = svc.resolve_packagable_projects(conn)

        assert len(results) == 0

    def test_skips_removed_project(self, setup):
        """Accepted sub but project status=removed should NOT be included."""
        conn = setup
        # Remove the project
        proj = ProjectRepository().get(conn, "alpha", "org/repo")
        ProjectRepository().save(conn, proj.remove())

        sub = Subscription(
            member_tag="jay.mac1", team_name="alpha",
            project_git_identity="org/repo",
        ).accept(SyncDirection.BOTH)
        SubscriptionRepository().save(conn, sub)

        svc = PackagingService(member_tag="jay.mac1")
        results = svc.resolve_packagable_projects(conn)

        assert len(results) == 0

    def test_filters_by_team_name(self, setup):
        """When team_name param is given, only that team's projects are returned."""
        conn = setup
        # Add a second team + project
        TeamRepository().save(conn, Team(
            name="beta", leader_device_id="DEV1", leader_member_tag="jay.mac1",
        ))
        MemberRepository().save(conn, Member(
            member_tag="jay.mac1", team_name="beta",
            device_id="DEV1", user_id="jay", machine_tag="mac1",
        ))
        ProjectRepository().save(conn, SharedProject(
            team_name="beta", git_identity="org/repo2",
            encoded_name="-Users-jay-repo2", folder_suffix="org-repo2",
        ))

        # Accept subs for both teams
        for tn, gi in [("alpha", "org/repo"), ("beta", "org/repo2")]:
            sub = Subscription(
                member_tag="jay.mac1", team_name=tn, project_git_identity=gi,
            ).accept(SyncDirection.BOTH)
            SubscriptionRepository().save(conn, sub)

        svc = PackagingService(member_tag="jay.mac1")

        # Filter to alpha only
        results = svc.resolve_packagable_projects(conn, team_name="alpha")
        assert len(results) == 1
        assert results[0]["team_name"] == "alpha"

        # Filter to beta only
        results = svc.resolve_packagable_projects(conn, team_name="beta")
        assert len(results) == 1
        assert results[0]["team_name"] == "beta"

    def test_filters_by_git_identity(self, setup):
        """When git_identity param is given, only matching projects are returned."""
        conn = setup
        # Add a second project to the same team
        ProjectRepository().save(conn, SharedProject(
            team_name="alpha", git_identity="org/other",
            encoded_name="-Users-jay-other", folder_suffix="org-other",
        ))
        for gi in ["org/repo", "org/other"]:
            sub = Subscription(
                member_tag="jay.mac1", team_name="alpha", project_git_identity=gi,
            ).accept(SyncDirection.BOTH)
            SubscriptionRepository().save(conn, sub)

        svc = PackagingService(member_tag="jay.mac1")
        results = svc.resolve_packagable_projects(conn, git_identity="org/other")

        assert len(results) == 1
        assert results[0]["git_identity"] == "org/other"

    def test_dedup_same_project_two_teams(self, setup):
        """Same project in two teams produces two entries (different dedup keys)."""
        conn = setup
        # Add beta team with the SAME git_identity
        TeamRepository().save(conn, Team(
            name="beta", leader_device_id="DEV1", leader_member_tag="jay.mac1",
        ))
        MemberRepository().save(conn, Member(
            member_tag="jay.mac1", team_name="beta",
            device_id="DEV1", user_id="jay", machine_tag="mac1",
        ))
        ProjectRepository().save(conn, SharedProject(
            team_name="beta", git_identity="org/repo",
            encoded_name="-Users-jay-repo", folder_suffix="org-repo",
        ))

        # Accept subs for both teams
        for tn in ["alpha", "beta"]:
            sub = Subscription(
                member_tag="jay.mac1", team_name=tn,
                project_git_identity="org/repo",
            ).accept(SyncDirection.BOTH)
            SubscriptionRepository().save(conn, sub)

        svc = PackagingService(member_tag="jay.mac1")
        results = svc.resolve_packagable_projects(conn)

        assert len(results) == 2
        team_names = {r["team_name"] for r in results}
        assert team_names == {"alpha", "beta"}

    def test_dedup_same_encoded_same_team(self, setup):
        """Multiple subs for same (encoded_name, team_name) should be deduped to one entry."""
        conn = setup
        # Create two projects in same team with same encoded_name but different git_identity
        ProjectRepository().save(conn, SharedProject(
            team_name="alpha", git_identity="org/repo-fork",
            encoded_name="-Users-jay-repo", folder_suffix="org-repo-fork",
        ))
        for gi in ["org/repo", "org/repo-fork"]:
            sub = Subscription(
                member_tag="jay.mac1", team_name="alpha", project_git_identity=gi,
            ).accept(SyncDirection.SEND)
            SubscriptionRepository().save(conn, sub)

        svc = PackagingService(member_tag="jay.mac1")
        results = svc.resolve_packagable_projects(conn)

        # Both share encoded_name "-Users-jay-repo" + team "alpha" → dedup to 1
        assert len(results) == 1

    def test_empty_when_no_subscriptions(self, setup):
        """No subscriptions at all returns empty list."""
        svc = PackagingService(member_tag="jay.mac1")
        results = svc.resolve_packagable_projects(setup)
        assert results == []

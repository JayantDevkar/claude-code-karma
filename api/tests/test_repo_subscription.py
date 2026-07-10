import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import sqlite3
import pytest
from db.schema import ensure_schema
from domain.team import Team
from domain.member import Member
from domain.project import SharedProject
from domain.subscription import Subscription, SubscriptionStatus, SyncDirection
from repositories.team_repo import TeamRepository
from repositories.member_repo import MemberRepository
from repositories.project_repo import ProjectRepository
from repositories.subscription_repo import SubscriptionRepository


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA foreign_keys=ON")
    ensure_schema(c)
    return c


@pytest.fixture
def conn_setup(conn):
    """Pre-populated connection: team + member + project."""
    TeamRepository().save(conn, Team(name="t", leader_device_id="D", leader_member_tag="j.m"))
    MemberRepository().save(conn, Member(
        member_tag="a.l", team_name="t", device_id="D2", user_id="a", machine_tag="l",
    ))
    ProjectRepository().save(conn, SharedProject(
        team_name="t", git_identity="o/r", folder_suffix="o-r",
    ))
    return conn


@pytest.fixture
def repo():
    return SubscriptionRepository()


class TestSubscriptionRepoSave:
    def test_save_new_subscription(self, conn_setup, repo):
        sub = Subscription(member_tag="a.l", team_name="t", project_git_identity="o/r")
        repo.save(conn_setup, sub)
        result = repo.get(conn_setup, "a.l", "t", "o/r")
        assert result is not None
        assert result.status == SubscriptionStatus.OFFERED
        assert result.direction == SyncDirection.BOTH

    def test_save_upsert_updates_status(self, conn_setup, repo):
        sub = Subscription(member_tag="a.l", team_name="t", project_git_identity="o/r")
        repo.save(conn_setup, sub)
        accepted = sub.accept(SyncDirection.RECEIVE)
        repo.save(conn_setup, accepted)
        result = repo.get(conn_setup, "a.l", "t", "o/r")
        assert result.status == SubscriptionStatus.ACCEPTED
        assert result.direction == SyncDirection.RECEIVE


class TestSubscriptionRepoGet:
    def test_get_nonexistent_returns_none(self, conn_setup, repo):
        assert repo.get(conn_setup, "nobody.nowhere", "t", "o/r") is None


class TestSubscriptionRepoListForMember:
    def test_list_for_member(self, conn_setup, repo):
        # Add a second project
        ProjectRepository().save(conn_setup, SharedProject(
            team_name="t", git_identity="o/r2", folder_suffix="o-r2",
        ))
        repo.save(conn_setup, Subscription(member_tag="a.l", team_name="t", project_git_identity="o/r"))
        repo.save(conn_setup, Subscription(member_tag="a.l", team_name="t", project_git_identity="o/r2"))
        subs = repo.list_for_member(conn_setup, "a.l")
        assert len(subs) == 2

    def test_list_for_member_returns_empty_when_none(self, conn_setup, repo):
        assert repo.list_for_member(conn_setup, "nobody.here") == []


class TestSubscriptionRepoListForProject:
    def test_list_for_project(self, conn_setup, repo):
        # Add a second member
        MemberRepository().save(conn_setup, Member(
            member_tag="b.x", team_name="t", device_id="D3", user_id="b", machine_tag="x",
        ))
        repo.save(conn_setup, Subscription(member_tag="a.l", team_name="t", project_git_identity="o/r"))
        repo.save(conn_setup, Subscription(member_tag="b.x", team_name="t", project_git_identity="o/r"))
        subs = repo.list_for_project(conn_setup, "t", "o/r")
        assert len(subs) == 2
        tags = {s.member_tag for s in subs}
        assert tags == {"a.l", "b.x"}


class TestSubscriptionRepoListAcceptedForSuffix:
    def test_list_accepted_for_suffix(self, conn_setup, repo):
        # Save one offered, one accepted subscription
        sub_offered = Subscription(member_tag="a.l", team_name="t", project_git_identity="o/r")
        repo.save(conn_setup, sub_offered)
        # Add second member with accepted sub
        MemberRepository().save(conn_setup, Member(
            member_tag="b.x", team_name="t", device_id="D3", user_id="b", machine_tag="x",
        ))
        sub_accepted = Subscription(
            member_tag="b.x", team_name="t", project_git_identity="o/r",
            status=SubscriptionStatus.ACCEPTED,
        )
        repo.save(conn_setup, sub_accepted)

        results = repo.list_accepted_for_suffix(conn_setup, "o-r")
        assert len(results) == 1
        assert results[0].member_tag == "b.x"
        assert results[0].status == SubscriptionStatus.ACCEPTED

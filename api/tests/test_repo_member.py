import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import sqlite3
import pytest
from db.schema import ensure_schema
from domain.team import Team
from domain.member import Member, MemberStatus
from repositories.team_repo import TeamRepository
from repositories.member_repo import MemberRepository


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA foreign_keys=ON")
    ensure_schema(c)
    return c


@pytest.fixture
def conn_with_team(conn):
    """Connection with a team already inserted (needed for FK constraints)."""
    TeamRepository().save(conn, Team(name="t", leader_device_id="D", leader_member_tag="j.m"))
    return conn


@pytest.fixture
def repo():
    return MemberRepository()


class TestMemberRepoSave:
    def test_save_new_member(self, conn_with_team, repo):
        m = Member(
            member_tag="a.l", team_name="t", device_id="D2",
            user_id="a", machine_tag="l",
        )
        repo.save(conn_with_team, m)
        result = repo.get(conn_with_team, "t", "a.l")
        assert result is not None
        assert result.member_tag == "a.l"
        assert result.status == MemberStatus.ADDED

    def test_save_upsert_updates_status(self, conn_with_team, repo):
        m = Member(
            member_tag="a.l", team_name="t", device_id="D2",
            user_id="a", machine_tag="l",
        )
        repo.save(conn_with_team, m)
        activated = m.activate()
        repo.save(conn_with_team, activated)
        result = repo.get(conn_with_team, "t", "a.l")
        assert result.status == MemberStatus.ACTIVE


class TestMemberRepoGet:
    def test_get_nonexistent_returns_none(self, conn_with_team, repo):
        assert repo.get(conn_with_team, "t", "nobody.nowhere") is None

    def test_get_by_device(self, conn_with_team, repo):
        m = Member(
            member_tag="a.l", team_name="t", device_id="DEV-X",
            user_id="a", machine_tag="l",
        )
        repo.save(conn_with_team, m)
        results = repo.get_by_device(conn_with_team, "DEV-X")
        assert len(results) == 1
        assert results[0].member_tag == "a.l"

    def test_get_by_device_returns_empty_for_unknown(self, conn_with_team, repo):
        results = repo.get_by_device(conn_with_team, "UNKNOWN")
        assert results == []


class TestMemberRepoListForTeam:
    def test_list_for_team(self, conn_with_team, repo):
        repo.save(conn_with_team, Member(
            member_tag="a.l", team_name="t", device_id="D2", user_id="a", machine_tag="l",
        ))
        repo.save(conn_with_team, Member(
            member_tag="b.x", team_name="t", device_id="D3", user_id="b", machine_tag="x",
        ))
        members = repo.list_for_team(conn_with_team, "t")
        assert len(members) == 2
        tags = {m.member_tag for m in members}
        assert tags == {"a.l", "b.x"}

    def test_list_for_nonexistent_team_returns_empty(self, conn_with_team, repo):
        assert repo.list_for_team(conn_with_team, "nosuchteam") == []


class TestMemberRepoGetAllByMemberTag:
    def test_returns_members_across_teams(self, conn, repo):
        TeamRepository().save(conn, Team(name="t1", leader_device_id="D1", leader_member_tag="jay.mac"))
        TeamRepository().save(conn, Team(name="t2", leader_device_id="D1", leader_member_tag="jay.mac"))
        m1 = Member(team_name="t1", member_tag="jay.mac", device_id="D1", user_id="jay", machine_tag="mac")
        m2 = Member(team_name="t2", member_tag="jay.mac", device_id="D1", user_id="jay", machine_tag="mac")
        repo.save(conn, m1)
        repo.save(conn, m2)
        results = repo.get_all_by_member_tag(conn, "jay.mac")
        assert len(results) == 2
        assert {r.team_name for r in results} == {"t1", "t2"}

    def test_returns_empty_for_unknown_tag(self, conn, repo):
        assert repo.get_all_by_member_tag(conn, "nobody.nope") == []


class TestMemberRepoGetByUserId:
    def test_returns_members_by_user_id(self, conn, repo):
        TeamRepository().save(conn, Team(name="t1", leader_device_id="D1", leader_member_tag="jay.mac"))
        repo.save(conn, Member(team_name="t1", member_tag="jay.mac", device_id="D1", user_id="jay", machine_tag="mac"))
        results = repo.get_by_user_id(conn, "jay")
        assert len(results) == 1
        assert results[0].member_tag == "jay.mac"

    def test_returns_empty_for_unknown_user(self, conn, repo):
        assert repo.get_by_user_id(conn, "nobody") == []


class TestMemberRepoRemoval:
    def test_was_removed_false_initially(self, conn_with_team, repo):
        assert repo.was_removed(conn_with_team, "t", "DEV-X") is False

    def test_record_and_check_removal(self, conn_with_team, repo):
        repo.record_removal(conn_with_team, "t", "DEV-X", "a.l")
        assert repo.was_removed(conn_with_team, "t", "DEV-X") is True

    def test_record_removal_without_member_tag(self, conn_with_team, repo):
        repo.record_removal(conn_with_team, "t", "DEV-Y")
        assert repo.was_removed(conn_with_team, "t", "DEV-Y") is True

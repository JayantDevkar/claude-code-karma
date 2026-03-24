import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import sqlite3
import pytest
from db.schema import ensure_schema
from domain.team import Team, TeamStatus
from repositories.team_repo import TeamRepository


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA foreign_keys=ON")
    ensure_schema(c)
    return c


@pytest.fixture
def repo():
    return TeamRepository()


class TestTeamRepoSave:
    def test_save_new_team(self, conn, repo):
        team = Team(name="t", leader_device_id="D", leader_member_tag="j.m")
        repo.save(conn, team)
        result = repo.get(conn, "t")
        assert result is not None
        assert result.name == "t"
        assert result.status == TeamStatus.ACTIVE

    def test_save_updates_existing(self, conn, repo):
        team = Team(name="t", leader_device_id="D", leader_member_tag="j.m")
        repo.save(conn, team)
        dissolved = team.dissolve(by_device="D")
        repo.save(conn, dissolved)
        result = repo.get(conn, "t")
        assert result.status == TeamStatus.DISSOLVED


class TestTeamRepoGet:
    def test_get_nonexistent_returns_none(self, conn, repo):
        assert repo.get(conn, "nope") is None


class TestTeamRepoList:
    def test_list_all(self, conn, repo):
        repo.save(conn, Team(name="a", leader_device_id="D1", leader_member_tag="j.m1"))
        repo.save(conn, Team(name="b", leader_device_id="D2", leader_member_tag="j.m2"))
        teams = repo.list_all(conn)
        assert len(teams) == 2
        names = {t.name for t in teams}
        assert names == {"a", "b"}


class TestTeamRepoDelete:
    def test_delete_team(self, conn, repo):
        repo.save(conn, Team(name="t", leader_device_id="D", leader_member_tag="j.m"))
        repo.delete(conn, "t")
        assert repo.get(conn, "t") is None


class TestTeamRepoGetByLeader:
    def test_get_by_leader(self, conn, repo):
        repo.save(conn, Team(name="t1", leader_device_id="D", leader_member_tag="j.m"))
        repo.save(conn, Team(name="t2", leader_device_id="D", leader_member_tag="j.m"))
        repo.save(conn, Team(name="t3", leader_device_id="OTHER", leader_member_tag="a.l"))
        teams = repo.get_by_leader(conn, "D")
        assert len(teams) == 2

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import sqlite3
import pytest
from db.schema import ensure_schema
from domain.team import Team
from domain.project import SharedProject, SharedProjectStatus, derive_folder_suffix
from repositories.team_repo import TeamRepository
from repositories.project_repo import ProjectRepository


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA foreign_keys=ON")
    ensure_schema(c)
    return c


@pytest.fixture
def conn_with_team(conn):
    TeamRepository().save(conn, Team(name="t", leader_device_id="D", leader_member_tag="j.m"))
    return conn


@pytest.fixture
def repo():
    return ProjectRepository()


class TestProjectRepoSave:
    def test_save_new_project(self, conn_with_team, repo):
        p = SharedProject(
            team_name="t", git_identity="owner/repo",
            folder_suffix="owner-repo",
        )
        repo.save(conn_with_team, p)
        result = repo.get(conn_with_team, "t", "owner/repo")
        assert result is not None
        assert result.git_identity == "owner/repo"
        assert result.status == SharedProjectStatus.SHARED
        assert result.encoded_name is None

    def test_save_upsert_updates_status(self, conn_with_team, repo):
        p = SharedProject(
            team_name="t", git_identity="o/r", folder_suffix="o-r",
        )
        repo.save(conn_with_team, p)
        removed = p.remove()
        repo.save(conn_with_team, removed)
        result = repo.get(conn_with_team, "t", "o/r")
        assert result.status == SharedProjectStatus.REMOVED

    def test_save_with_encoded_name(self, conn_with_team, repo):
        p = SharedProject(
            team_name="t", git_identity="o/r",
            encoded_name="-Users-me-repo", folder_suffix="o-r",
        )
        repo.save(conn_with_team, p)
        result = repo.get(conn_with_team, "t", "o/r")
        assert result.encoded_name == "-Users-me-repo"


class TestProjectRepoGet:
    def test_get_nonexistent_returns_none(self, conn_with_team, repo):
        assert repo.get(conn_with_team, "t", "no/such") is None


class TestProjectRepoListForTeam:
    def test_list_for_team(self, conn_with_team, repo):
        repo.save(conn_with_team, SharedProject(
            team_name="t", git_identity="o/r1", folder_suffix="o-r1",
        ))
        repo.save(conn_with_team, SharedProject(
            team_name="t", git_identity="o/r2", folder_suffix="o-r2",
        ))
        projects = repo.list_for_team(conn_with_team, "t")
        assert len(projects) == 2
        identities = {p.git_identity for p in projects}
        assert identities == {"o/r1", "o/r2"}

    def test_list_excludes_removed_by_default(self, conn_with_team, repo):
        repo.save(conn_with_team, SharedProject(
            team_name="t", git_identity="o/active", folder_suffix="o-active",
        ))
        removed = SharedProject(
            team_name="t", git_identity="o/gone", folder_suffix="o-gone",
        ).remove()
        repo.save(conn_with_team, removed)
        projects = repo.list_for_team(conn_with_team, "t")
        assert len(projects) == 1
        assert projects[0].git_identity == "o/active"

    def test_list_includes_removed_when_requested(self, conn_with_team, repo):
        repo.save(conn_with_team, SharedProject(
            team_name="t", git_identity="o/active", folder_suffix="o-active",
        ))
        removed = SharedProject(
            team_name="t", git_identity="o/gone", folder_suffix="o-gone",
        ).remove()
        repo.save(conn_with_team, removed)
        projects = repo.list_for_team(conn_with_team, "t", include_removed=True)
        assert len(projects) == 2

    def test_list_for_nonexistent_team_returns_empty(self, conn_with_team, repo):
        assert repo.list_for_team(conn_with_team, "nope") == []


class TestProjectRepoFindBySuffix:
    def test_find_by_suffix(self, conn_with_team, repo):
        repo.save(conn_with_team, SharedProject(
            team_name="t", git_identity="jayant/karma",
            folder_suffix=derive_folder_suffix("jayant/karma"),
        ))
        results = repo.find_by_suffix(conn_with_team, "jayant-karma")
        assert len(results) == 1
        assert results[0].git_identity == "jayant/karma"

    def test_find_by_suffix_no_match(self, conn_with_team, repo):
        assert repo.find_by_suffix(conn_with_team, "no-such-suffix") == []


class TestProjectRepoFindByGitIdentity:
    def test_find_by_git_identity_across_teams(self, conn, repo):
        TeamRepository().save(conn, Team(name="t1", leader_device_id="D1", leader_member_tag="j.m"))
        TeamRepository().save(conn, Team(name="t2", leader_device_id="D2", leader_member_tag="j.m"))
        repo.save(conn, SharedProject(team_name="t1", git_identity="o/r", folder_suffix="o-r"))
        repo.save(conn, SharedProject(team_name="t2", git_identity="o/r", folder_suffix="o-r"))
        results = repo.find_by_git_identity(conn, "o/r")
        assert len(results) == 2
        team_names = {p.team_name for p in results}
        assert team_names == {"t1", "t2"}

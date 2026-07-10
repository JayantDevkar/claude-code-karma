import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import sqlite3
import pytest
from db.schema import ensure_schema


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA foreign_keys=ON")
    ensure_schema(c)
    return c


class TestV19Tables:
    def test_sync_teams_exists(self, conn):
        conn.execute("INSERT INTO sync_teams (name, leader_device_id, leader_member_tag) VALUES ('t', 'D', 'j.m')")
        row = conn.execute("SELECT * FROM sync_teams WHERE name='t'").fetchone()
        assert row["status"] == "active"

    def test_sync_members_exists(self, conn):
        conn.execute("INSERT INTO sync_teams (name, leader_device_id, leader_member_tag) VALUES ('t', 'D', 'j.m')")
        conn.execute(
            "INSERT INTO sync_members (team_name, member_tag, device_id, user_id, machine_tag) "
            "VALUES ('t', 'j.m', 'D', 'j', 'm')"
        )
        row = conn.execute("SELECT * FROM sync_members WHERE member_tag='j.m'").fetchone()
        assert row["status"] == "added"
        assert row["updated_at"] is not None

    def test_sync_projects_pk_is_git_identity(self, conn):
        conn.execute("INSERT INTO sync_teams (name, leader_device_id, leader_member_tag) VALUES ('t', 'D', 'j.m')")
        conn.execute(
            "INSERT INTO sync_projects (team_name, git_identity, folder_suffix) "
            "VALUES ('t', 'owner/repo', 'owner-repo')"
        )
        row = conn.execute("SELECT * FROM sync_projects WHERE git_identity='owner/repo'").fetchone()
        assert row["encoded_name"] is None  # nullable
        assert row["status"] == "shared"

    def test_sync_subscriptions_exists(self, conn):
        conn.execute("INSERT INTO sync_teams (name, leader_device_id, leader_member_tag) VALUES ('t', 'D', 'j.m')")
        conn.execute(
            "INSERT INTO sync_members (team_name, member_tag, device_id, user_id, machine_tag) "
            "VALUES ('t', 'a.l', 'D2', 'a', 'l')"
        )
        conn.execute(
            "INSERT INTO sync_projects (team_name, git_identity, folder_suffix) "
            "VALUES ('t', 'o/r', 'o-r')"
        )
        conn.execute(
            "INSERT INTO sync_subscriptions (member_tag, team_name, project_git_identity) "
            "VALUES ('a.l', 't', 'o/r')"
        )
        row = conn.execute("SELECT * FROM sync_subscriptions").fetchone()
        assert row["status"] == "offered"
        assert row["direction"] == "both"

    def test_sync_events_uses_git_identity_column(self, conn):
        conn.execute(
            "INSERT INTO sync_events (event_type, team_name, project_git_identity) "
            "VALUES ('team_created', 't', 'o/r')"
        )
        row = conn.execute("SELECT * FROM sync_events").fetchone()
        assert row["project_git_identity"] == "o/r"


class TestV19Cascades:
    def test_delete_team_cascades_members(self, conn):
        conn.execute("INSERT INTO sync_teams (name, leader_device_id, leader_member_tag) VALUES ('t', 'D', 'j.m')")
        conn.execute(
            "INSERT INTO sync_members (team_name, member_tag, device_id, user_id, machine_tag) "
            "VALUES ('t', 'a.l', 'D2', 'a', 'l')"
        )
        conn.execute("DELETE FROM sync_teams WHERE name='t'")
        assert conn.execute("SELECT COUNT(*) FROM sync_members").fetchone()[0] == 0

    def test_delete_team_cascades_subscriptions(self, conn):
        conn.execute("INSERT INTO sync_teams (name, leader_device_id, leader_member_tag) VALUES ('t', 'D', 'j.m')")
        conn.execute(
            "INSERT INTO sync_members (team_name, member_tag, device_id, user_id, machine_tag) "
            "VALUES ('t', 'a.l', 'D2', 'a', 'l')"
        )
        conn.execute(
            "INSERT INTO sync_projects (team_name, git_identity, folder_suffix) VALUES ('t', 'o/r', 'o-r')"
        )
        conn.execute(
            "INSERT INTO sync_subscriptions (member_tag, team_name, project_git_identity) "
            "VALUES ('a.l', 't', 'o/r')"
        )
        conn.execute("DELETE FROM sync_teams WHERE name='t'")
        assert conn.execute("SELECT COUNT(*) FROM sync_subscriptions").fetchone()[0] == 0


class TestV19Constraints:
    def test_team_status_check(self, conn):
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO sync_teams (name, leader_device_id, leader_member_tag, status) "
                "VALUES ('t', 'D', 'j.m', 'invalid')"
            )

    def test_member_status_check(self, conn):
        conn.execute("INSERT INTO sync_teams (name, leader_device_id, leader_member_tag) VALUES ('t', 'D', 'j.m')")
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO sync_members (team_name, member_tag, device_id, user_id, machine_tag, status) "
                "VALUES ('t', 'a.l', 'D2', 'a', 'l', 'invalid')"
            )

    def test_subscription_direction_check(self, conn):
        conn.execute("INSERT INTO sync_teams (name, leader_device_id, leader_member_tag) VALUES ('t', 'D', 'j.m')")
        conn.execute(
            "INSERT INTO sync_members (team_name, member_tag, device_id, user_id, machine_tag) "
            "VALUES ('t', 'a.l', 'D2', 'a', 'l')"
        )
        conn.execute(
            "INSERT INTO sync_projects (team_name, git_identity, folder_suffix) VALUES ('t', 'o/r', 'o-r')"
        )
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO sync_subscriptions (member_tag, team_name, project_git_identity, direction) "
                "VALUES ('a.l', 't', 'o/r', 'invalid')"
            )

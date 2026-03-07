"""Tests for sync_queries CRUD functions."""

import sqlite3

import pytest

from db.schema import ensure_schema


@pytest.fixture
def conn():
    """In-memory SQLite with schema applied."""
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA foreign_keys=ON")
    ensure_schema(c)
    return c


class TestTeamCRUD:
    def test_create_team(self, conn):
        from db.sync_queries import create_team, list_teams

        result = create_team(conn, "alpha", "syncthing")
        assert result["name"] == "alpha"
        teams = list_teams(conn)
        assert len(teams) == 1
        assert teams[0]["name"] == "alpha"

    def test_create_duplicate_team_raises(self, conn):
        from db.sync_queries import create_team

        create_team(conn, "alpha", "syncthing")
        with pytest.raises(sqlite3.IntegrityError):
            create_team(conn, "alpha", "syncthing")

    def test_delete_team_cascades(self, conn):
        from db.sync_queries import create_team, delete_team, add_member, list_members

        create_team(conn, "alpha", "syncthing")
        add_member(conn, "alpha", "alice", device_id="DEVICE-A")
        delete_team(conn, "alpha")
        assert list_members(conn, "alpha") == []

    def test_get_team(self, conn):
        from db.sync_queries import create_team, get_team

        create_team(conn, "alpha", "syncthing")
        team = get_team(conn, "alpha")
        assert team["name"] == "alpha"
        assert get_team(conn, "nonexistent") is None


class TestMemberCRUD:
    def test_add_and_list_members(self, conn):
        from db.sync_queries import create_team, add_member, list_members

        create_team(conn, "alpha", "syncthing")
        add_member(conn, "alpha", "alice", device_id="DEV-ALICE")
        add_member(conn, "alpha", "bob", device_id="DEV-BOB")
        members = list_members(conn, "alpha")
        assert len(members) == 2
        names = {m["name"] for m in members}
        assert names == {"alice", "bob"}

    def test_remove_member(self, conn):
        from db.sync_queries import create_team, add_member, remove_member, list_members

        create_team(conn, "alpha", "syncthing")
        add_member(conn, "alpha", "alice", device_id="DEV-ALICE")
        remove_member(conn, "alpha", "alice")
        assert list_members(conn, "alpha") == []

    def test_get_member_by_device_id(self, conn):
        from db.sync_queries import create_team, add_member, get_member_by_device_id

        create_team(conn, "alpha", "syncthing")
        add_member(conn, "alpha", "alice", device_id="DEV-ALICE")
        member = get_member_by_device_id(conn, "DEV-ALICE")
        assert member["name"] == "alice"
        assert member["team_name"] == "alpha"


class TestTeamProjectCRUD:
    def test_add_and_list_projects(self, conn):
        from db.sync_queries import create_team, add_team_project, list_team_projects

        create_team(conn, "alpha", "syncthing")
        # Insert a project in the projects table first (FK requirement)
        conn.execute("INSERT INTO projects (encoded_name) VALUES (?)", ("-Users-me-app",))
        add_team_project(conn, "alpha", "-Users-me-app", "/Users/me/app")
        projects = list_team_projects(conn, "alpha")
        assert len(projects) == 1
        assert projects[0]["project_encoded_name"] == "-Users-me-app"

    def test_remove_project(self, conn):
        from db.sync_queries import create_team, add_team_project, remove_team_project, list_team_projects

        create_team(conn, "alpha", "syncthing")
        conn.execute("INSERT INTO projects (encoded_name) VALUES (?)", ("-Users-me-app",))
        add_team_project(conn, "alpha", "-Users-me-app", "/Users/me/app")
        remove_team_project(conn, "alpha", "-Users-me-app")
        assert list_team_projects(conn, "alpha") == []


class TestSyncEvents:
    def test_log_and_query_events(self, conn):
        from db.sync_queries import create_team, log_event, query_events

        create_team(conn, "alpha", "syncthing")
        log_event(conn, "team_created", team_name="alpha")
        log_event(conn, "member_added", team_name="alpha", member_name="alice")
        events = query_events(conn, limit=10)
        assert len(events) == 2

    def test_query_events_filters(self, conn):
        from db.sync_queries import create_team, log_event, query_events

        create_team(conn, "alpha", "syncthing")
        create_team(conn, "beta", "syncthing")
        log_event(conn, "team_created", team_name="alpha")
        log_event(conn, "team_created", team_name="beta")
        log_event(conn, "member_added", team_name="alpha", member_name="alice")
        alpha_events = query_events(conn, team_name="alpha", limit=10)
        assert len(alpha_events) == 2
        member_events = query_events(conn, event_type="member_added", limit=10)
        assert len(member_events) == 1

    def test_get_known_devices(self, conn):
        from db.sync_queries import create_team, add_member, get_known_devices

        create_team(conn, "alpha", "syncthing")
        add_member(conn, "alpha", "alice", device_id="DEV-ALICE")
        add_member(conn, "alpha", "bob", device_id="DEV-BOB")
        known = get_known_devices(conn)
        assert known["DEV-ALICE"] == ("alice", "alpha")
        assert known["DEV-BOB"] == ("bob", "alpha")

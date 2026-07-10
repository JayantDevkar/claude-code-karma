import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import sqlite3
import pytest
from db.schema import ensure_schema
from domain.events import SyncEvent, SyncEventType
from repositories.event_repo import EventRepository


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA foreign_keys=ON")
    ensure_schema(c)
    return c


@pytest.fixture
def repo():
    return EventRepository()


class TestEventRepoLog:
    def test_log_returns_id(self, conn, repo):
        event = SyncEvent(event_type=SyncEventType.team_created, team_name="t")
        event_id = repo.log(conn, event)
        assert isinstance(event_id, int)
        assert event_id >= 1

    def test_log_increments_id(self, conn, repo):
        e1 = repo.log(conn, SyncEvent(event_type=SyncEventType.team_created, team_name="t"))
        e2 = repo.log(conn, SyncEvent(event_type=SyncEventType.team_dissolved, team_name="t"))
        assert e2 > e1

    def test_log_with_detail(self, conn, repo):
        event = SyncEvent(
            event_type=SyncEventType.member_added,
            team_name="t",
            member_tag="a.l",
            detail={"device_id": "DEV-1", "added_by": "j.m"},
        )
        repo.log(conn, event)
        results = repo.query(conn, team="t")
        assert len(results) == 1
        assert results[0].detail["device_id"] == "DEV-1"
        assert results[0].detail["added_by"] == "j.m"

    def test_log_with_no_detail(self, conn, repo):
        event = SyncEvent(event_type=SyncEventType.team_created, team_name="t")
        repo.log(conn, event)
        results = repo.query(conn, team="t")
        assert results[0].detail is None

    def test_log_with_all_fields(self, conn, repo):
        event = SyncEvent(
            event_type=SyncEventType.session_packaged,
            team_name="t",
            member_tag="j.m",
            project_git_identity="owner/repo",
            session_uuid="abc-123",
            detail={"branches": ["main"]},
        )
        repo.log(conn, event)
        results = repo.query(conn, team="t")
        r = results[0]
        assert r.project_git_identity == "owner/repo"
        assert r.session_uuid == "abc-123"
        assert r.member_tag == "j.m"


class TestEventRepoQuery:
    def test_query_all_returns_latest_first(self, conn, repo):
        repo.log(conn, SyncEvent(event_type=SyncEventType.team_created, team_name="t"))
        repo.log(conn, SyncEvent(event_type=SyncEventType.member_added, team_name="t"))
        results = repo.query(conn)
        assert len(results) == 2
        # Latest first
        assert results[0].event_type == SyncEventType.member_added
        assert results[1].event_type == SyncEventType.team_created

    def test_query_filter_by_team(self, conn, repo):
        repo.log(conn, SyncEvent(event_type=SyncEventType.team_created, team_name="team-a"))
        repo.log(conn, SyncEvent(event_type=SyncEventType.team_created, team_name="team-b"))
        results = repo.query(conn, team="team-a")
        assert len(results) == 1
        assert results[0].team_name == "team-a"

    def test_query_filter_by_event_type(self, conn, repo):
        repo.log(conn, SyncEvent(event_type=SyncEventType.team_created, team_name="t"))
        repo.log(conn, SyncEvent(event_type=SyncEventType.member_added, team_name="t", member_tag="a.l"))
        repo.log(conn, SyncEvent(event_type=SyncEventType.member_added, team_name="t", member_tag="b.x"))
        results = repo.query(conn, event_type="member_added")
        assert len(results) == 2
        assert all(r.event_type == SyncEventType.member_added for r in results)

    def test_query_filter_by_team_and_type(self, conn, repo):
        repo.log(conn, SyncEvent(event_type=SyncEventType.member_added, team_name="t1"))
        repo.log(conn, SyncEvent(event_type=SyncEventType.member_added, team_name="t2"))
        repo.log(conn, SyncEvent(event_type=SyncEventType.team_created, team_name="t1"))
        results = repo.query(conn, team="t1", event_type="member_added")
        assert len(results) == 1
        assert results[0].team_name == "t1"
        assert results[0].event_type == SyncEventType.member_added

    def test_query_limit(self, conn, repo):
        for i in range(10):
            repo.log(conn, SyncEvent(event_type=SyncEventType.team_created, team_name=f"t{i}"))
        results = repo.query(conn, limit=3)
        assert len(results) == 3

    def test_query_empty_returns_empty_list(self, conn, repo):
        assert repo.query(conn) == []

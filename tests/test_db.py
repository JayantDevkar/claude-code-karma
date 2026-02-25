"""
Tests for the SQLite metadata index (db module).

Tests schema creation, indexing, incremental sync, FTS, and cleanup.
Uses an in-memory SQLite database for isolation.
"""

import json
import sqlite3

# Ensure api/ is on path
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from db.schema import SCHEMA_VERSION, ensure_schema


@pytest.fixture
def mem_db():
    """Create an in-memory SQLite database with schema applied."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    ensure_schema(conn)
    return conn


def _insert_test_session(conn, uuid="test-uuid", **overrides):
    """
    Insert a test session with comprehensive defaults.

    Shared helper used by all test classes. Pass keyword overrides
    to customize any field.
    """
    defaults = {
        "uuid": uuid,
        "slug": "test-slug",
        "project_encoded_name": "-Users-me-repo",
        "project_path": "/Users/me/repo",
        "start_time": "2026-01-15T10:00:00+00:00",
        "end_time": "2026-01-15T10:30:00+00:00",
        "message_count": 42,
        "duration_seconds": 1800.0,
        "input_tokens": 50000,
        "output_tokens": 1500,
        "cache_creation_tokens": 1000,
        "cache_read_tokens": 30000,
        "total_cost": 0.25,
        "initial_prompt": "Fix the login bug",
        "git_branch": "main",
        "models_used": json.dumps(["claude-sonnet-4-20250514"]),
        "session_titles": json.dumps(["Fix login bug"]),
        "is_continuation_marker": 0,
        "was_compacted": 0,
        "compaction_count": 0,
        "file_snapshot_count": 0,
        "subagent_count": 3,
        "jsonl_mtime": 1705312200.0,
        "jsonl_size": 45000,
    }
    defaults.update(overrides)
    cols = ", ".join(defaults.keys())
    placeholders = ", ".join("?" * len(defaults))
    conn.execute(
        f"INSERT OR REPLACE INTO sessions ({cols}) VALUES ({placeholders})",
        list(defaults.values()),
    )
    conn.commit()


class TestSchema:
    def test_schema_version(self, mem_db):
        row = mem_db.execute("SELECT MAX(version) FROM schema_version").fetchone()
        assert row[0] == SCHEMA_VERSION

    def test_tables_exist(self, mem_db):
        tables = {
            r[0]
            for r in mem_db.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        }
        assert "sessions" in tables
        assert "session_tools" in tables
        assert "session_skills" in tables
        assert "subagent_invocations" in tables
        assert "subagent_tools" in tables
        assert "message_uuids" in tables
        assert "projects" in tables
        assert "sessions_fts" in tables

    def test_idempotent(self, mem_db):
        """Calling ensure_schema twice should not raise."""
        ensure_schema(mem_db)
        row = mem_db.execute("SELECT COUNT(*) FROM schema_version").fetchone()
        assert row[0] == 1

    def test_migration_v1_to_v2(self):
        """Test v1→v2 migration adds subagent_tools table."""
        # Create a v1 database manually
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")

        # Apply v1 schema (everything except subagent_tools)
        # We simulate this by applying full schema then dropping subagent_tools and setting version to 1
        from db.schema import SCHEMA_SQL

        conn.executescript(SCHEMA_SQL)
        conn.execute("DROP TABLE IF EXISTS subagent_tools")
        conn.execute("INSERT OR REPLACE INTO schema_version (version) VALUES (1)")
        conn.commit()

        # Verify subagent_tools doesn't exist
        tables = {
            r[0]
            for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        }
        assert "subagent_tools" not in tables

        # Run migration
        ensure_schema(conn)

        # Verify subagent_tools now exists
        tables = {
            r[0]
            for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        }
        assert "subagent_tools" in tables

        # Verify version is current (migrates through v2 and v3)
        version = conn.execute("SELECT MAX(version) FROM schema_version").fetchone()[0]
        assert version == SCHEMA_VERSION

        conn.close()

    def test_subagent_tools_cascade_delete(self, mem_db):
        """Test subagent_tools rows are cascade-deleted when invocation is deleted."""
        _insert_test_session(mem_db)
        # Insert invocation
        mem_db.execute(
            """INSERT INTO subagent_invocations
               (session_uuid, agent_id, subagent_type, input_tokens, output_tokens, cost_usd, duration_seconds, started_at)
               VALUES ('test-uuid', 'agent-1', 'executor', 100, 50, 0.01, 5.0, '2026-01-15T10:00:00')"""
        )
        inv_id = mem_db.execute("SELECT last_insert_rowid()").fetchone()[0]

        # Insert tool usage
        mem_db.execute(
            "INSERT INTO subagent_tools (invocation_id, tool_name, count) VALUES (?, 'Read', 10)",
            (inv_id,),
        )
        mem_db.execute(
            "INSERT INTO subagent_tools (invocation_id, tool_name, count) VALUES (?, 'Edit', 3)",
            (inv_id,),
        )
        mem_db.commit()

        # Verify tools exist
        assert mem_db.execute("SELECT COUNT(*) FROM subagent_tools").fetchone()[0] == 2

        # Delete invocation
        mem_db.execute("DELETE FROM subagent_invocations WHERE id = ?", (inv_id,))
        mem_db.commit()

        # Verify cascade delete
        assert mem_db.execute("SELECT COUNT(*) FROM subagent_tools").fetchone()[0] == 0

    def test_indexes_exist(self, mem_db):
        indexes = {
            r[0]
            for r in mem_db.execute(
                "SELECT name FROM sqlite_master WHERE type='index' AND name LIKE 'idx_%'"
            ).fetchall()
        }
        assert "idx_sessions_project" in indexes
        assert "idx_sessions_start" in indexes
        assert "idx_sessions_slug" in indexes
        assert "idx_tools_name" in indexes
        assert "idx_subagent_type" in indexes
        assert "idx_subagent_tools_invocation" in indexes
        assert "idx_message_session" in indexes


class TestSessionCRUD:
    def test_insert_and_query(self, mem_db):
        _insert_test_session(mem_db)
        row = mem_db.execute("SELECT * FROM sessions WHERE uuid = 'test-uuid'").fetchone()
        assert row["slug"] == "test-slug"
        assert row["message_count"] == 42
        assert row["input_tokens"] == 50000
        assert row["total_cost"] == 0.25

    def test_upsert(self, mem_db):
        _insert_test_session(mem_db, message_count=10)
        _insert_test_session(mem_db, message_count=42)  # INSERT OR REPLACE
        count = mem_db.execute("SELECT COUNT(*) FROM sessions").fetchone()[0]
        assert count == 1
        row = mem_db.execute("SELECT message_count FROM sessions").fetchone()
        assert row[0] == 42

    def test_project_filter(self, mem_db):
        _insert_test_session(mem_db, uuid="s1", project_encoded_name="-Users-me-repo")
        _insert_test_session(mem_db, uuid="s2", project_encoded_name="-Users-me-other")
        rows = mem_db.execute(
            "SELECT uuid FROM sessions WHERE project_encoded_name = ?",
            ("-Users-me-repo",),
        ).fetchall()
        assert len(rows) == 1
        assert rows[0]["uuid"] == "s1"

    def test_ordering_by_start_time(self, mem_db):
        _insert_test_session(mem_db, uuid="old", start_time="2026-01-01T00:00:00+00:00")
        _insert_test_session(mem_db, uuid="new", start_time="2026-02-01T00:00:00+00:00")
        rows = mem_db.execute("SELECT uuid FROM sessions ORDER BY start_time DESC").fetchall()
        assert rows[0]["uuid"] == "new"
        assert rows[1]["uuid"] == "old"

    def test_cascade_delete(self, mem_db):
        _insert_test_session(mem_db)
        mem_db.execute(
            "INSERT INTO session_tools (session_uuid, tool_name, count) VALUES ('test-uuid', 'Read', 5)"
        )
        mem_db.execute(
            "INSERT INTO session_skills (session_uuid, skill_name, count) VALUES ('test-uuid', 'commit', 2)"
        )
        mem_db.commit()

        mem_db.execute("DELETE FROM sessions WHERE uuid = 'test-uuid'")
        mem_db.commit()

        assert mem_db.execute("SELECT COUNT(*) FROM session_tools").fetchone()[0] == 0
        assert mem_db.execute("SELECT COUNT(*) FROM session_skills").fetchone()[0] == 0


class TestFTS:
    def test_search_by_prompt(self, mem_db):
        _insert_test_session(
            mem_db,
            "s1",
            initial_prompt="Fix the authentication bug",
            project_encoded_name="-test",
            project_path="/test",
        )
        _insert_test_session(
            mem_db,
            "s2",
            initial_prompt="Add new dashboard widget",
            project_encoded_name="-test",
            project_path="/test",
        )

        rows = mem_db.execute(
            "SELECT uuid FROM sessions_fts WHERE sessions_fts MATCH 'authentication'"
        ).fetchall()
        assert len(rows) == 1
        assert rows[0]["uuid"] == "s1"

    def test_search_by_title(self, mem_db):
        _insert_test_session(
            mem_db,
            "s1",
            session_titles=json.dumps(["Refactoring auth module"]),
            project_encoded_name="-test",
            project_path="/test",
        )
        _insert_test_session(
            mem_db,
            "s2",
            session_titles=json.dumps(["Adding tests"]),
            project_encoded_name="-test",
            project_path="/test",
        )

        rows = mem_db.execute(
            "SELECT uuid FROM sessions_fts WHERE sessions_fts MATCH 'refactoring'"
        ).fetchall()
        assert len(rows) == 1

    def test_search_by_slug(self, mem_db):
        _insert_test_session(
            mem_db,
            "s1",
            slug="breezy-chasing-dusk",
            project_encoded_name="-test",
            project_path="/test",
        )
        _insert_test_session(
            mem_db,
            "s2",
            slug="calm-flowing-river",
            project_encoded_name="-test",
            project_path="/test",
        )

        rows = mem_db.execute(
            "SELECT uuid FROM sessions_fts WHERE sessions_fts MATCH 'breezy'"
        ).fetchall()
        assert len(rows) == 1

    def test_fts_update_trigger(self, mem_db):
        _insert_test_session(
            mem_db,
            "s1",
            initial_prompt="old prompt",
            project_encoded_name="-test",
            project_path="/test",
        )

        # Update the prompt
        mem_db.execute(
            "UPDATE sessions SET initial_prompt = 'new refactored prompt' WHERE uuid = 's1'"
        )
        mem_db.commit()

        # Old term should not match
        rows = mem_db.execute(
            "SELECT uuid FROM sessions_fts WHERE sessions_fts MATCH 'old'"
        ).fetchall()
        assert len(rows) == 0

        # New term should match
        rows = mem_db.execute(
            "SELECT uuid FROM sessions_fts WHERE sessions_fts MATCH 'refactored'"
        ).fetchall()
        assert len(rows) == 1


class TestAggregation:
    def _insert_sessions(self, conn):
        for i, (project, tokens, cost) in enumerate(
            [
                ("-proj-a", 10000, 0.10),
                ("-proj-a", 20000, 0.20),
                ("-proj-b", 5000, 0.05),
            ]
        ):
            conn.execute(
                """INSERT INTO sessions
                   (uuid, project_encoded_name, input_tokens, total_cost, jsonl_mtime, message_count)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (f"uuid-{i}", project, tokens, cost, 0.0, 1),
            )
        conn.execute(
            "INSERT INTO session_tools (session_uuid, tool_name, count) VALUES ('uuid-0', 'Read', 10)"
        )
        conn.execute(
            "INSERT INTO session_tools (session_uuid, tool_name, count) VALUES ('uuid-1', 'Read', 5)"
        )
        conn.execute(
            "INSERT INTO session_tools (session_uuid, tool_name, count) VALUES ('uuid-1', 'Edit', 3)"
        )
        conn.commit()

    def test_global_aggregation(self, mem_db):
        self._insert_sessions(mem_db)
        row = mem_db.execute(
            "SELECT COUNT(*) as cnt, SUM(input_tokens) as tokens, SUM(total_cost) as cost FROM sessions"
        ).fetchone()
        assert row["cnt"] == 3
        assert row["tokens"] == 35000
        assert abs(row["cost"] - 0.35) < 0.001

    def test_per_project_aggregation(self, mem_db):
        self._insert_sessions(mem_db)
        rows = mem_db.execute(
            """SELECT project_encoded_name, COUNT(*) as cnt, SUM(input_tokens) as tokens
               FROM sessions GROUP BY project_encoded_name ORDER BY cnt DESC"""
        ).fetchall()
        assert rows[0]["project_encoded_name"] == "-proj-a"
        assert rows[0]["cnt"] == 2
        assert rows[0]["tokens"] == 30000

    def test_tool_aggregation(self, mem_db):
        self._insert_sessions(mem_db)
        rows = mem_db.execute(
            """SELECT tool_name, SUM(count) as total
               FROM session_tools GROUP BY tool_name ORDER BY total DESC"""
        ).fetchall()
        assert rows[0]["tool_name"] == "Read"
        assert rows[0]["total"] == 15


class TestQueryAllSessions:
    """Tests for db.queries.query_all_sessions — the main SQL query function."""

    def _populate(self, conn):
        """Insert a variety of sessions for query testing."""
        # Need projects table populated for project_options
        _insert_test_session(
            conn,
            "s1",
            project_encoded_name="-Users-me-repo",
            project_path="/Users/me/repo",
            initial_prompt="Fix authentication bug",
            session_titles=json.dumps(["Auth fix"]),
            start_time="2026-01-15T10:00:00+00:00",
            end_time="2026-01-15T10:30:00+00:00",
            git_branch="main",
        )
        _insert_test_session(
            conn,
            "s2",
            project_encoded_name="-Users-me-repo",
            project_path="/Users/me/repo",
            initial_prompt="Add dashboard widget",
            session_titles=json.dumps(["Dashboard widget"]),
            start_time="2026-01-16T10:00:00+00:00",
            end_time="2026-01-16T10:30:00+00:00",
            git_branch="feature/dashboard",
        )
        _insert_test_session(
            conn,
            "s3",
            project_encoded_name="-Users-me-other",
            project_path="/Users/me/other",
            initial_prompt="Refactor tests",
            session_titles=json.dumps(["Test refactor"]),
            start_time="2026-01-17T10:00:00+00:00",
            end_time="2026-01-17T10:30:00+00:00",
            git_branch="main",
        )
        # Update projects summary table
        conn.execute("DELETE FROM projects")
        conn.execute(
            """INSERT INTO projects (encoded_name, project_path, session_count, last_activity)
               SELECT project_encoded_name, project_path, COUNT(*), MAX(start_time)
               FROM sessions GROUP BY project_encoded_name"""
        )
        conn.commit()

    def test_no_filters(self, mem_db):
        from db.queries import query_all_sessions

        self._populate(mem_db)
        result = query_all_sessions(mem_db)
        assert result["total"] == 3
        assert len(result["sessions"]) == 3
        # Sorted by start_time DESC
        assert result["sessions"][0]["uuid"] == "s3"

    def test_project_filter(self, mem_db):
        from db.queries import query_all_sessions

        self._populate(mem_db)
        result = query_all_sessions(mem_db, project="-Users-me-repo")
        assert result["total"] == 2
        assert all(s["project_encoded_name"] == "-Users-me-repo" for s in result["sessions"])

    def test_fts_search_prompts(self, mem_db):
        from db.queries import query_all_sessions

        self._populate(mem_db)
        result = query_all_sessions(mem_db, search="authentication", scope="prompts")
        assert result["total"] == 1
        assert result["sessions"][0]["uuid"] == "s1"

    def test_fts_search_titles(self, mem_db):
        from db.queries import query_all_sessions

        self._populate(mem_db)
        result = query_all_sessions(mem_db, search="dashboard", scope="titles")
        assert result["total"] == 1
        assert result["sessions"][0]["uuid"] == "s2"

    def test_fts_search_both(self, mem_db):
        from db.queries import query_all_sessions

        self._populate(mem_db)
        # "refactor" appears in s3's prompt ("Refactor tests") and title ("Test refactor")
        result = query_all_sessions(mem_db, search="refactor", scope="both")
        assert result["total"] == 1
        assert result["sessions"][0]["uuid"] == "s3"

    def test_status_completed(self, mem_db):
        from db.queries import query_all_sessions

        self._populate(mem_db)
        # All sessions have old end_time, so all should be "completed"
        result = query_all_sessions(mem_db, status="completed")
        assert result["total"] == 3

    def test_status_active(self, mem_db):
        from db.queries import query_all_sessions

        self._populate(mem_db)
        # All sessions have old end_time, none should be "active"
        result = query_all_sessions(mem_db, status="active")
        assert result["total"] == 0

    def test_status_counts(self, mem_db):
        from db.queries import query_all_sessions

        self._populate(mem_db)
        result = query_all_sessions(mem_db)
        sc = result["status_counts"]
        assert sc["active"] + sc["completed"] == 3
        assert sc["error"] == 0

    def test_pagination(self, mem_db):
        from db.queries import query_all_sessions

        self._populate(mem_db)
        result = query_all_sessions(mem_db, limit=2, offset=0)
        assert result["total"] == 3
        assert len(result["sessions"]) == 2

        result2 = query_all_sessions(mem_db, limit=2, offset=2)
        assert result2["total"] == 3
        assert len(result2["sessions"]) == 1

    def test_malformed_fts_input(self, mem_db):
        from db.queries import query_all_sessions

        self._populate(mem_db)
        # Malformed FTS input should not raise, should return gracefully
        result = query_all_sessions(mem_db, search='foo(bar"baz')
        assert isinstance(result, dict)
        assert "sessions" in result
        assert "total" in result

    def test_project_options(self, mem_db):
        from db.queries import query_all_sessions

        self._populate(mem_db)
        result = query_all_sessions(mem_db)
        opts = result["project_options"]
        assert len(opts) == 2
        names = {o["encoded_name"] for o in opts}
        assert "-Users-me-repo" in names
        assert "-Users-me-other" in names


class TestPlanQueries:
    """Tests for slug-based query functions used by the plans router."""

    def test_query_session_by_slug_found(self, mem_db):
        from db.queries import query_session_by_slug

        _insert_test_session(mem_db, "s1", slug="breezy-morning-sky")
        row = query_session_by_slug(mem_db, "breezy-morning-sky")
        assert row is not None
        assert row["uuid"] == "s1"
        assert row["slug"] == "breezy-morning-sky"
        assert row["project_encoded_name"] == "-Users-me-repo"

    def test_query_session_by_slug_not_found(self, mem_db):
        from db.queries import query_session_by_slug

        _insert_test_session(mem_db, "s1", slug="existing-slug")
        row = query_session_by_slug(mem_db, "nonexistent-slug")
        assert row is None

    def test_query_session_by_slug_picks_latest(self, mem_db):
        from db.queries import query_session_by_slug

        _insert_test_session(
            mem_db,
            "old-uuid",
            slug="shared-slug",
            start_time="2026-01-01T00:00:00+00:00",
        )
        _insert_test_session(
            mem_db,
            "new-uuid",
            slug="shared-slug",
            start_time="2026-02-01T00:00:00+00:00",
        )
        row = query_session_by_slug(mem_db, "shared-slug")
        assert row is not None
        assert row["uuid"] == "new-uuid"

    def test_query_sessions_by_slugs_batch(self, mem_db):
        from db.queries import query_sessions_by_slugs

        _insert_test_session(mem_db, "s1", slug="slug-a")
        _insert_test_session(mem_db, "s2", slug="slug-b")
        result = query_sessions_by_slugs(mem_db, ["slug-a", "slug-b", "slug-missing"])
        assert len(result) == 2
        assert "slug-a" in result
        assert "slug-b" in result
        assert "slug-missing" not in result
        assert result["slug-a"]["uuid"] == "s1"

    def test_query_sessions_by_slugs_empty(self, mem_db):
        from db.queries import query_sessions_by_slugs

        result = query_sessions_by_slugs(mem_db, [])
        assert result == {}


# ---------------------------------------------------------------------------
# Phase 1: Global Aggregation Query Tests
# ---------------------------------------------------------------------------


class TestDashboardStats:
    """Tests for db.queries.query_dashboard_stats — dashboard period aggregation."""

    def _populate(self, conn):
        """Insert sessions spanning today, yesterday, and last week."""
        from datetime import timedelta

        # Use UTC date to match the query which uses datetime.now(timezone.utc).date()
        today = datetime.now(timezone.utc).date()
        yesterday = today - timedelta(days=1)
        last_week = today - timedelta(days=5)

        _insert_test_session(
            conn,
            "today-1",
            start_time=f"{today.isoformat()}T09:00:00+00:00",
            end_time=f"{today.isoformat()}T09:30:00+00:00",
            duration_seconds=1800.0,
            project_encoded_name="-proj-a",
        )
        _insert_test_session(
            conn,
            "today-2",
            start_time=f"{today.isoformat()}T14:00:00+00:00",
            end_time=f"{today.isoformat()}T14:45:00+00:00",
            duration_seconds=2700.0,
            project_encoded_name="-proj-b",
        )
        _insert_test_session(
            conn,
            "yesterday-1",
            start_time=f"{yesterday.isoformat()}T10:00:00+00:00",
            end_time=f"{yesterday.isoformat()}T11:00:00+00:00",
            duration_seconds=3600.0,
            project_encoded_name="-proj-a",
        )
        _insert_test_session(
            conn,
            "lastweek-1",
            start_time=f"{last_week.isoformat()}T10:00:00+00:00",
            end_time=f"{last_week.isoformat()}T10:15:00+00:00",
            duration_seconds=900.0,
            project_encoded_name="-proj-c",
        )
        conn.commit()

    def test_today_stats(self, mem_db):
        from db.queries import query_dashboard_stats

        self._populate(mem_db)
        today = datetime.now(timezone.utc).date()
        start = datetime.combine(today, datetime.min.time(), tzinfo=timezone.utc)
        end = datetime.combine(today, datetime.max.time(), tzinfo=timezone.utc)
        result = query_dashboard_stats(mem_db, start, end)
        assert result is not None
        assert result["session_count"] == 2
        assert result["projects_active"] == 2
        assert result["total_duration"] == 4500.0  # 1800 + 2700

    def test_yesterday_stats(self, mem_db):
        from datetime import timedelta

        from db.queries import query_dashboard_stats

        self._populate(mem_db)
        yesterday = (datetime.now(timezone.utc) - timedelta(days=1)).date()
        start = datetime.combine(yesterday, datetime.min.time(), tzinfo=timezone.utc)
        end = datetime.combine(yesterday, datetime.max.time(), tzinfo=timezone.utc)
        result = query_dashboard_stats(mem_db, start, end)
        assert result is not None
        assert result["session_count"] == 1
        assert result["projects_active"] == 1

    def test_empty_range_returns_none(self, mem_db):
        from db.queries import query_dashboard_stats

        self._populate(mem_db)
        # Far future range with no sessions
        start = datetime(2030, 1, 1, tzinfo=timezone.utc)
        end = datetime(2030, 1, 2, tzinfo=timezone.utc)
        result = query_dashboard_stats(mem_db, start, end)
        assert result is None

    def test_empty_db(self, mem_db):
        from db.queries import query_dashboard_stats

        start = datetime(2026, 1, 1, tzinfo=timezone.utc)
        end = datetime(2026, 12, 31, tzinfo=timezone.utc)
        result = query_dashboard_stats(mem_db, start, end)
        assert result is None


class TestAnalyticsQuery:
    """Tests for db.queries.query_analytics — aggregated analytics."""

    def _populate(self, conn):
        """Insert sessions with tokens, tools, and models for analytics."""
        _insert_test_session(
            conn,
            "a1",
            project_encoded_name="-proj-a",
            input_tokens=10000,
            output_tokens=500,
            cache_read_tokens=2000,
            cache_creation_tokens=1000,
            total_cost=0.10,
            duration_seconds=600.0,
            models_used=json.dumps(["claude-opus-4-5-20250514"]),
            start_time="2026-01-15T10:00:00+00:00",
        )
        _insert_test_session(
            conn,
            "a2",
            project_encoded_name="-proj-a",
            input_tokens=20000,
            output_tokens=1000,
            cache_read_tokens=5000,
            cache_creation_tokens=500,
            total_cost=0.25,
            duration_seconds=1200.0,
            models_used=json.dumps(["claude-sonnet-4-5-20250514", "claude-opus-4-5-20250514"]),
            start_time="2026-01-16T14:00:00+00:00",
        )
        _insert_test_session(
            conn,
            "a3",
            project_encoded_name="-proj-b",
            input_tokens=5000,
            output_tokens=200,
            cache_read_tokens=0,
            cache_creation_tokens=0,
            total_cost=0.05,
            duration_seconds=300.0,
            models_used=json.dumps(["claude-haiku-3-5-20250514"]),
            start_time="2026-01-17T08:00:00+00:00",
        )
        # Tools
        conn.execute("INSERT INTO session_tools VALUES ('a1', 'Read', 10)")
        conn.execute("INSERT INTO session_tools VALUES ('a1', 'Edit', 3)")
        conn.execute("INSERT INTO session_tools VALUES ('a2', 'Read', 20)")
        conn.execute("INSERT INTO session_tools VALUES ('a2', 'Bash', 5)")
        conn.execute("INSERT INTO session_tools VALUES ('a3', 'Read', 2)")
        conn.commit()

    def test_global_totals(self, mem_db):
        from db.queries import query_analytics

        self._populate(mem_db)
        result = query_analytics(mem_db)
        totals = result["totals"]
        assert totals["total_sessions"] == 3
        assert totals["total_input"] == 35000
        assert totals["total_output"] == 1700
        assert totals["total_cache_read"] == 7000
        assert totals["total_cache_creation"] == 1500
        assert abs(totals["total_cost"] - 0.40) < 0.001
        assert totals["total_duration"] == 2100.0
        assert totals["projects_active"] == 2

    def test_project_filter(self, mem_db):
        from db.queries import query_analytics

        self._populate(mem_db)
        result = query_analytics(mem_db, project="-proj-a")
        assert result["totals"]["total_sessions"] == 2
        assert result["totals"]["total_input"] == 30000
        assert result["totals"]["projects_active"] == 1

    def test_date_range_filter(self, mem_db):
        from db.queries import query_analytics

        self._populate(mem_db)
        start = datetime(2026, 1, 16, tzinfo=timezone.utc)
        end = datetime(2026, 1, 17, 23, 59, 59, tzinfo=timezone.utc)
        result = query_analytics(mem_db, start_dt=start, end_dt=end)
        assert result["totals"]["total_sessions"] == 2  # a2 and a3

    def test_tool_aggregation(self, mem_db):
        from db.queries import query_analytics

        self._populate(mem_db)
        result = query_analytics(mem_db)
        assert result["tools"]["Read"] == 32  # 10 + 20 + 2
        assert result["tools"]["Edit"] == 3
        assert result["tools"]["Bash"] == 5

    def test_models_used_raw(self, mem_db):
        from db.queries import query_analytics

        self._populate(mem_db)
        result = query_analytics(mem_db)
        # models_used_list now contains pre-parsed model names from json_each()
        assert len(result["models_used_list"]) > 0
        assert "claude-opus-4-5-20250514" in result["models_used_list"]

    def test_start_times(self, mem_db):
        from db.queries import query_analytics

        self._populate(mem_db)
        result = query_analytics(mem_db)
        assert len(result["start_times"]) == 3
        assert all(isinstance(t, str) for t in result["start_times"])

    def test_empty_db(self, mem_db):
        from db.queries import query_analytics

        result = query_analytics(mem_db)
        assert result["totals"]["total_sessions"] == 0
        assert result["tools"] == {}
        assert result["models_used_list"] == []
        assert result["start_times"] == []


class TestSkillUsage:
    """Tests for db.queries.query_skill_usage — skill aggregation."""

    def _populate(self, conn):
        _insert_test_session(conn, "s1", project_encoded_name="-proj-a")
        _insert_test_session(conn, "s2", project_encoded_name="-proj-a")
        _insert_test_session(conn, "s3", project_encoded_name="-proj-b")
        conn.execute("INSERT INTO session_skills VALUES ('s1', 'commit', 5)")
        conn.execute("INSERT INTO session_skills VALUES ('s1', 'oh-my-claudecode:plan', 2)")
        conn.execute("INSERT INTO session_skills VALUES ('s2', 'commit', 3)")
        conn.execute("INSERT INTO session_skills VALUES ('s3', 'commit', 1)")
        conn.execute("INSERT INTO session_skills VALUES ('s3', 'review-pr', 4)")
        conn.commit()

    def test_global_usage(self, mem_db):
        from db.queries import query_skill_usage

        self._populate(mem_db)
        result = query_skill_usage(mem_db)
        # commit: 5+3+1=9, review-pr: 4, oh-my-claudecode:plan: 2
        assert len(result) == 3
        assert result[0]["skill_name"] == "commit"
        assert result[0]["total_count"] == 9

    def test_project_filter(self, mem_db):
        from db.queries import query_skill_usage

        self._populate(mem_db)
        result = query_skill_usage(mem_db, project="-proj-a")
        skills = {r["skill_name"]: r["total_count"] for r in result}
        assert skills["commit"] == 8  # 5+3
        assert skills["oh-my-claudecode:plan"] == 2
        assert "review-pr" not in skills

    def test_limit(self, mem_db):
        from db.queries import query_skill_usage

        self._populate(mem_db)
        result = query_skill_usage(mem_db, limit=1)
        assert len(result) == 1
        assert result[0]["skill_name"] == "commit"

    def test_empty_db(self, mem_db):
        from db.queries import query_skill_usage

        result = query_skill_usage(mem_db)
        assert result == []


class TestSessionsBySkill:
    """Tests for db.queries.query_sessions_by_skill — find sessions using a skill."""

    def _populate(self, conn):
        _insert_test_session(
            conn,
            "s1",
            project_encoded_name="-proj-a",
            start_time="2026-01-15T10:00:00+00:00",
            models_used=json.dumps(["claude-opus-4-5"]),
            session_titles=json.dumps(["Fix auth"]),
            git_branch="main",
        )
        _insert_test_session(
            conn,
            "s2",
            project_encoded_name="-proj-a",
            start_time="2026-01-16T10:00:00+00:00",
            models_used=json.dumps(["claude-sonnet-4-5"]),
            session_titles=json.dumps(["Add feature"]),
            git_branch="feature",
        )
        _insert_test_session(
            conn,
            "s3",
            project_encoded_name="-proj-b",
            start_time="2026-01-17T10:00:00+00:00",
        )
        conn.execute("INSERT INTO session_skills VALUES ('s1', 'commit', 1)")
        conn.execute("INSERT INTO session_skills VALUES ('s2', 'commit', 2)")
        conn.execute("INSERT INTO session_skills VALUES ('s3', 'review-pr', 1)")
        conn.commit()

    def test_find_sessions(self, mem_db):
        from db.queries import query_sessions_by_skill

        self._populate(mem_db)
        result = query_sessions_by_skill(mem_db, "commit")
        assert result["total"] == 2
        assert len(result["sessions"]) == 2
        # Sorted by start_time DESC
        assert result["sessions"][0]["uuid"] == "s2"
        assert result["sessions"][1]["uuid"] == "s1"

    def test_json_fields_parsed(self, mem_db):
        from db.queries import query_sessions_by_skill

        self._populate(mem_db)
        result = query_sessions_by_skill(mem_db, "commit")
        s2 = result["sessions"][0]
        assert s2["models_used"] == ["claude-sonnet-4-5"]
        assert s2["session_titles"] == ["Add feature"]
        assert s2["git_branches"] == ["feature"]

    def test_pagination(self, mem_db):
        from db.queries import query_sessions_by_skill

        self._populate(mem_db)
        result = query_sessions_by_skill(mem_db, "commit", limit=1, offset=0)
        assert result["total"] == 2
        assert len(result["sessions"]) == 1
        assert result["sessions"][0]["uuid"] == "s2"

        result2 = query_sessions_by_skill(mem_db, "commit", limit=1, offset=1)
        assert result2["total"] == 2
        assert len(result2["sessions"]) == 1
        assert result2["sessions"][0]["uuid"] == "s1"

    def test_no_matches(self, mem_db):
        from db.queries import query_sessions_by_skill

        self._populate(mem_db)
        result = query_sessions_by_skill(mem_db, "nonexistent-skill")
        assert result["total"] == 0
        assert result["sessions"] == []


# ---------------------------------------------------------------------------
# Phase 2: Project-Level Query Tests
# ---------------------------------------------------------------------------


class TestProjectSessions:
    """Tests for db.queries.query_project_sessions — paginated project sessions."""

    def _populate(self, conn):
        for i in range(5):
            _insert_test_session(
                conn,
                f"ps-{i}",
                project_encoded_name="-proj-a",
                message_count=10 + i,
                start_time=f"2026-01-{15 + i:02d}T10:00:00+00:00",
                input_tokens=1000 * (i + 1),
                models_used=json.dumps(["claude-opus-4-5"]),
                session_titles=json.dumps([f"Session {i}"]),
                git_branch="main",
            )
        # Empty session (should be excluded)
        _insert_test_session(
            conn,
            "ps-empty",
            project_encoded_name="-proj-a",
            message_count=0,
        )
        # Different project
        _insert_test_session(
            conn,
            "ps-other",
            project_encoded_name="-proj-b",
            message_count=5,
        )
        conn.commit()

    def test_basic_query(self, mem_db):
        from db.queries import query_project_sessions

        self._populate(mem_db)
        result = query_project_sessions(mem_db, "-proj-a")
        assert result["total"] == 5  # excludes empty
        assert len(result["sessions"]) == 5

    def test_excludes_empty_sessions(self, mem_db):
        from db.queries import query_project_sessions

        self._populate(mem_db)
        result = query_project_sessions(mem_db, "-proj-a")
        uuids = [s["uuid"] for s in result["sessions"]]
        assert "ps-empty" not in uuids

    def test_sorted_desc(self, mem_db):
        from db.queries import query_project_sessions

        self._populate(mem_db)
        result = query_project_sessions(mem_db, "-proj-a")
        # Most recent first
        assert result["sessions"][0]["uuid"] == "ps-4"
        assert result["sessions"][-1]["uuid"] == "ps-0"

    def test_pagination(self, mem_db):
        from db.queries import query_project_sessions

        self._populate(mem_db)
        result = query_project_sessions(mem_db, "-proj-a", limit=2, offset=0)
        assert result["total"] == 5
        assert len(result["sessions"]) == 2
        assert result["sessions"][0]["uuid"] == "ps-4"

        result2 = query_project_sessions(mem_db, "-proj-a", limit=2, offset=2)
        assert len(result2["sessions"]) == 2
        assert result2["sessions"][0]["uuid"] == "ps-2"

    def test_no_limit(self, mem_db):
        from db.queries import query_project_sessions

        self._populate(mem_db)
        result = query_project_sessions(mem_db, "-proj-a", limit=None)
        assert len(result["sessions"]) == 5

    def test_json_fields_parsed(self, mem_db):
        from db.queries import query_project_sessions

        self._populate(mem_db)
        result = query_project_sessions(mem_db, "-proj-a", limit=1)
        s = result["sessions"][0]
        assert isinstance(s["models_used"], list)
        assert isinstance(s["session_titles"], list)
        assert isinstance(s["git_branches"], list)

    def test_other_project_excluded(self, mem_db):
        from db.queries import query_project_sessions

        self._populate(mem_db)
        result = query_project_sessions(mem_db, "-proj-a")
        uuids = [s["uuid"] for s in result["sessions"]]
        assert "ps-other" not in uuids

    def test_nonexistent_project(self, mem_db):
        from db.queries import query_project_sessions

        self._populate(mem_db)
        result = query_project_sessions(mem_db, "-nonexistent")
        assert result["total"] == 0
        assert result["sessions"] == []


class TestProjectBranches:
    """Tests for db.queries.query_project_branches — branch aggregation."""

    def _populate(self, conn):
        _insert_test_session(
            conn,
            "b1",
            project_encoded_name="-proj-a",
            git_branch="main",
            start_time="2026-01-15T10:00:00+00:00",
            end_time="2026-01-15T11:00:00+00:00",
        )
        _insert_test_session(
            conn,
            "b2",
            project_encoded_name="-proj-a",
            git_branch="main",
            start_time="2026-01-16T10:00:00+00:00",
            end_time="2026-01-16T11:00:00+00:00",
        )
        _insert_test_session(
            conn,
            "b3",
            project_encoded_name="-proj-a",
            git_branch="feature/auth",
            start_time="2026-01-17T10:00:00+00:00",
            end_time="2026-01-17T11:00:00+00:00",
        )
        # Most recent session is on feature/auth
        _insert_test_session(
            conn,
            "b4",
            project_encoded_name="-proj-a",
            git_branch="feature/auth",
            start_time="2026-01-18T10:00:00+00:00",
            end_time="2026-01-18T11:00:00+00:00",
        )
        # Session with no branch
        _insert_test_session(
            conn,
            "b5",
            project_encoded_name="-proj-a",
            git_branch=None,
            start_time="2026-01-19T10:00:00+00:00",
        )
        conn.commit()

    def test_branch_counts(self, mem_db):
        from db.queries import query_project_branches

        self._populate(mem_db)
        result = query_project_branches(mem_db, "-proj-a")
        branches = {b["name"]: b["session_count"] for b in result["branches"]}
        assert branches["main"] == 2
        assert branches["feature/auth"] == 2
        assert len(result["branches"]) == 2  # null branch excluded

    def test_active_branch(self, mem_db):
        from db.queries import query_project_branches

        self._populate(mem_db)
        result = query_project_branches(mem_db, "-proj-a")
        # b4 is most recent (Jan 18), on feature/auth
        assert result["active_branch"] == "feature/auth"

    def test_sorted_by_last_active(self, mem_db):
        from db.queries import query_project_branches

        self._populate(mem_db)
        result = query_project_branches(mem_db, "-proj-a")
        # feature/auth has later end_time than main
        assert result["branches"][0]["name"] == "feature/auth"

    def test_no_branches(self, mem_db):
        from db.queries import query_project_branches

        _insert_test_session(
            mem_db,
            "nb1",
            project_encoded_name="-proj-x",
            git_branch=None,
        )
        mem_db.commit()
        result = query_project_branches(mem_db, "-proj-x")
        assert result["branches"] == []
        assert result["active_branch"] is None

    def test_nonexistent_project(self, mem_db):
        from db.queries import query_project_branches

        result = query_project_branches(mem_db, "-nonexistent")
        assert result["branches"] == []
        assert result["active_branch"] is None


class TestProjectChains:
    """Tests for db.queries.query_project_chains — session chain detection."""

    def _populate(self, conn):
        # Chain: slug "happy-morning" with 3 sessions
        _insert_test_session(
            conn,
            "c1",
            project_encoded_name="-proj-a",
            slug="happy-morning",
            message_count=10,
            start_time="2026-01-15T10:00:00+00:00",
            was_compacted=0,
            is_continuation_marker=0,
            compaction_count=0,
            initial_prompt="Start project",
        )
        _insert_test_session(
            conn,
            "c2",
            project_encoded_name="-proj-a",
            slug="happy-morning",
            message_count=15,
            start_time="2026-01-15T11:00:00+00:00",
            was_compacted=1,
            is_continuation_marker=1,
            compaction_count=1,
            initial_prompt="Continue project",
        )
        _insert_test_session(
            conn,
            "c3",
            project_encoded_name="-proj-a",
            slug="happy-morning",
            message_count=20,
            start_time="2026-01-15T12:00:00+00:00",
            was_compacted=1,
            is_continuation_marker=1,
            compaction_count=2,
            initial_prompt="Finish project",
        )
        # Single session (not a chain)
        _insert_test_session(
            conn,
            "s1",
            project_encoded_name="-proj-a",
            slug="lonely-star",
            message_count=5,
            start_time="2026-01-16T10:00:00+00:00",
        )
        # Empty session with a slug (should be excluded)
        _insert_test_session(
            conn,
            "e1",
            project_encoded_name="-proj-a",
            slug="happy-morning",
            message_count=0,
        )
        conn.commit()

    def test_chain_detected(self, mem_db):
        from db.queries import query_project_chains

        self._populate(mem_db)
        result = query_project_chains(mem_db, "-proj-a")
        assert "happy-morning" in result["chains"]
        assert len(result["chains"]["happy-morning"]) == 3

    def test_single_session_excluded_from_chains(self, mem_db):
        from db.queries import query_project_chains

        self._populate(mem_db)
        result = query_project_chains(mem_db, "-proj-a")
        assert "lonely-star" not in result["chains"]

    def test_chain_ordered_by_start_time(self, mem_db):
        from db.queries import query_project_chains

        self._populate(mem_db)
        result = query_project_chains(mem_db, "-proj-a")
        chain = result["chains"]["happy-morning"]
        assert chain[0]["uuid"] == "c1"
        assert chain[1]["uuid"] == "c2"
        assert chain[2]["uuid"] == "c3"

    def test_chain_node_fields(self, mem_db):
        from db.queries import query_project_chains

        self._populate(mem_db)
        result = query_project_chains(mem_db, "-proj-a")
        node = result["chains"]["happy-morning"][1]  # c2
        assert node["was_compacted"] == 1
        assert node["is_continuation_marker"] == 1
        assert node["compaction_count"] == 1
        assert node["initial_prompt"] == "Continue project"

    def test_counts(self, mem_db):
        from db.queries import query_project_chains

        self._populate(mem_db)
        result = query_project_chains(mem_db, "-proj-a")
        assert result["chained_sessions"] == 3
        assert result["total_sessions"] == 4  # 3 chained + 1 single (excludes empty)

    def test_empty_sessions_excluded(self, mem_db):
        from db.queries import query_project_chains

        self._populate(mem_db)
        result = query_project_chains(mem_db, "-proj-a")
        all_uuids = [s["uuid"] for chain in result["chains"].values() for s in chain]
        assert "e1" not in all_uuids

    def test_no_chains(self, mem_db):
        from db.queries import query_project_chains

        _insert_test_session(
            mem_db,
            "solo",
            project_encoded_name="-proj-x",
            slug="unique-slug",
            message_count=5,
        )
        mem_db.commit()
        result = query_project_chains(mem_db, "-proj-x")
        assert result["chains"] == {}
        assert result["total_sessions"] == 1
        assert result["chained_sessions"] == 0

    def test_nonexistent_project(self, mem_db):
        from db.queries import query_project_chains

        result = query_project_chains(mem_db, "-nonexistent")
        assert result["chains"] == {}
        assert result["total_sessions"] == 0


class TestSessionLookup:
    """Tests for db.queries.query_session_lookup — fast slug/UUID lookup."""

    def _populate(self, conn):
        _insert_test_session(
            conn,
            "abc12345-6789-0000-1111-222233334444",
            project_encoded_name="-proj-a",
            slug="breezy-morning",
            message_count=10,
            start_time="2026-01-15T10:00:00+00:00",
            initial_prompt="Fix the auth bug",
        )
        _insert_test_session(
            conn,
            "def98765-4321-0000-1111-222233334444",
            project_encoded_name="-proj-a",
            slug="sunny-afternoon",
            message_count=20,
            start_time="2026-01-16T10:00:00+00:00",
            initial_prompt="Add dashboard",
        )
        # Empty session (should not match)
        _insert_test_session(
            conn,
            "empty-0000-0000-0000-000000000000",
            project_encoded_name="-proj-a",
            slug="empty-session",
            message_count=0,
        )
        conn.commit()

    def test_exact_uuid(self, mem_db):
        from db.queries import query_session_lookup

        self._populate(mem_db)
        result = query_session_lookup(mem_db, "-proj-a", "abc12345-6789-0000-1111-222233334444")
        assert result is not None
        assert result["uuid"] == "abc12345-6789-0000-1111-222233334444"
        assert result["matched_by"] == "uuid"

    def test_uuid_prefix(self, mem_db):
        from db.queries import query_session_lookup

        self._populate(mem_db)
        result = query_session_lookup(mem_db, "-proj-a", "abc12345")
        assert result is not None
        assert result["uuid"] == "abc12345-6789-0000-1111-222233334444"
        assert result["matched_by"] == "uuid_prefix"

    def test_slug_match(self, mem_db):
        from db.queries import query_session_lookup

        self._populate(mem_db)
        result = query_session_lookup(mem_db, "-proj-a", "breezy-morning")
        assert result is not None
        assert result["uuid"] == "abc12345-6789-0000-1111-222233334444"
        assert result["matched_by"] == "slug"

    def test_slug_with_uuid_like_chars(self, mem_db):
        """Slugs like 'abc-def' contain only hex chars and hyphens, looking UUID-like."""
        from db.queries import query_session_lookup

        self._populate(mem_db)
        # "breezy-morning" doesn't look UUID-like, test one that does
        _insert_test_session(
            mem_db,
            "real-uuid-here",
            project_encoded_name="-proj-a",
            slug="abc-def",
            message_count=5,
        )
        mem_db.commit()
        result = query_session_lookup(mem_db, "-proj-a", "abc-def")
        assert result is not None
        assert result["matched_by"] == "slug"

    def test_not_found(self, mem_db):
        from db.queries import query_session_lookup

        self._populate(mem_db)
        result = query_session_lookup(mem_db, "-proj-a", "nonexistent")
        assert result is None

    def test_wrong_project(self, mem_db):
        from db.queries import query_session_lookup

        self._populate(mem_db)
        result = query_session_lookup(mem_db, "-proj-b", "breezy-morning")
        assert result is None

    def test_empty_identifier(self, mem_db):
        from db.queries import query_session_lookup

        self._populate(mem_db)
        result = query_session_lookup(mem_db, "-proj-a", "")
        assert result is None

    def test_whitespace_identifier(self, mem_db):
        from db.queries import query_session_lookup

        self._populate(mem_db)
        result = query_session_lookup(mem_db, "-proj-a", "   ")
        assert result is None

    def test_empty_sessions_excluded(self, mem_db):
        from db.queries import query_session_lookup

        self._populate(mem_db)
        result = query_session_lookup(mem_db, "-proj-a", "empty-session")
        assert result is None

    def test_result_fields(self, mem_db):
        from db.queries import query_session_lookup

        self._populate(mem_db)
        result = query_session_lookup(mem_db, "-proj-a", "breezy-morning")
        assert result["slug"] == "breezy-morning"
        assert result["project_encoded_name"] == "-proj-a"
        assert result["message_count"] == 10
        assert result["initial_prompt"] == "Fix the auth bug"


class TestAgentUsageQuery:
    """Tests for db.queries.query_agent_usage — agent aggregation."""

    def _populate(self, conn):
        """Insert test sessions and subagent invocations."""
        _insert_test_session(conn, "s1", project_encoded_name="-proj-a")
        _insert_test_session(conn, "s2", project_encoded_name="-proj-a")
        _insert_test_session(conn, "s3", project_encoded_name="-proj-b")

        conn.execute(
            """INSERT INTO subagent_invocations
               (session_uuid, agent_id, subagent_type, input_tokens, output_tokens, cost_usd, duration_seconds, started_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                "s1",
                "agent-1",
                "oh-my-claudecode:executor",
                1000,
                500,
                0.05,
                10.0,
                "2026-01-15T10:00:00+00:00",
            ),
        )
        conn.execute(
            """INSERT INTO subagent_invocations
               (session_uuid, agent_id, subagent_type, input_tokens, output_tokens, cost_usd, duration_seconds, started_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                "s1",
                "agent-2",
                "oh-my-claudecode:explore",
                500,
                200,
                0.02,
                5.0,
                "2026-01-15T10:01:00+00:00",
            ),
        )
        conn.execute(
            """INSERT INTO subagent_invocations
               (session_uuid, agent_id, subagent_type, input_tokens, output_tokens, cost_usd, duration_seconds, started_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                "s2",
                "agent-3",
                "oh-my-claudecode:executor",
                2000,
                800,
                0.08,
                15.0,
                "2026-01-16T10:00:00+00:00",
            ),
        )
        conn.execute(
            """INSERT INTO subagent_invocations
               (session_uuid, agent_id, subagent_type, input_tokens, output_tokens, cost_usd, duration_seconds, started_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                "s3",
                "agent-4",
                "oh-my-claudecode:architect",
                3000,
                1000,
                0.15,
                20.0,
                "2026-01-17T10:00:00+00:00",
            ),
        )
        conn.commit()

    def test_empty_db(self, mem_db):
        from db.queries import query_agent_usage

        result = query_agent_usage(mem_db)
        assert result["agents"] == []
        assert result["total_runs"] == 0
        assert result["total_cost"] == 0.0

    def test_single_type(self, mem_db):
        from db.queries import query_agent_usage

        self._populate(mem_db)
        result = query_agent_usage(mem_db)
        # Find executor agent
        executor = next(
            a for a in result["agents"] if a["subagent_type"] == "oh-my-claudecode:executor"
        )
        assert executor["total_runs"] == 2
        assert abs(executor["total_cost_usd"] - 0.13) < 0.001  # 0.05 + 0.08
        assert "-proj-a" in executor["projects"]

    def test_multiple_types(self, mem_db):
        from db.queries import query_agent_usage

        self._populate(mem_db)
        result = query_agent_usage(mem_db)
        assert len(result["agents"]) == 3  # executor, explore, architect
        # Sorted by total_runs DESC (executor=2 first)
        assert result["agents"][0]["subagent_type"] == "oh-my-claudecode:executor"
        assert result["agents"][0]["total_runs"] == 2

    def test_project_grouping(self, mem_db):
        from db.queries import query_agent_usage

        self._populate(mem_db)
        result = query_agent_usage(mem_db)
        executor = next(
            a for a in result["agents"] if a["subagent_type"] == "oh-my-claudecode:executor"
        )
        # Projects list should contain -proj-a (via GROUP_CONCAT)
        assert "-proj-a" in executor["projects"]

    def test_cost_token_aggregation(self, mem_db):
        from db.queries import query_agent_usage

        self._populate(mem_db)
        result = query_agent_usage(mem_db)
        assert result["total_runs"] == 4
        assert abs(result["total_cost"] - 0.30) < 0.001  # 0.05 + 0.02 + 0.08 + 0.15


class TestAgentDetailQuery:
    """Tests for db.queries.query_agent_detail — agent detail view."""

    def _populate(self, conn):
        """Insert test sessions and subagent invocations."""
        _insert_test_session(conn, "s1", project_encoded_name="-proj-a")
        _insert_test_session(conn, "s2", project_encoded_name="-proj-a")
        _insert_test_session(conn, "s3", project_encoded_name="-proj-b")

        conn.execute(
            """INSERT INTO subagent_invocations
               (session_uuid, agent_id, subagent_type, input_tokens, output_tokens, cost_usd, duration_seconds, started_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                "s1",
                "agent-1",
                "oh-my-claudecode:executor",
                1000,
                500,
                0.05,
                10.0,
                "2026-01-15T10:00:00+00:00",
            ),
        )
        conn.execute(
            """INSERT INTO subagent_invocations
               (session_uuid, agent_id, subagent_type, input_tokens, output_tokens, cost_usd, duration_seconds, started_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                "s1",
                "agent-2",
                "oh-my-claudecode:explore",
                500,
                200,
                0.02,
                5.0,
                "2026-01-15T10:01:00+00:00",
            ),
        )
        conn.execute(
            """INSERT INTO subagent_invocations
               (session_uuid, agent_id, subagent_type, input_tokens, output_tokens, cost_usd, duration_seconds, started_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                "s2",
                "agent-3",
                "oh-my-claudecode:executor",
                2000,
                800,
                0.08,
                15.0,
                "2026-01-16T10:00:00+00:00",
            ),
        )
        conn.execute(
            """INSERT INTO subagent_invocations
               (session_uuid, agent_id, subagent_type, input_tokens, output_tokens, cost_usd, duration_seconds, started_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                "s3",
                "agent-4",
                "oh-my-claudecode:architect",
                3000,
                1000,
                0.15,
                20.0,
                "2026-01-17T10:00:00+00:00",
            ),
        )
        conn.commit()

    def test_found(self, mem_db):
        from db.queries import query_agent_detail

        self._populate(mem_db)
        result = query_agent_detail(mem_db, "oh-my-claudecode:executor")
        assert result is not None
        assert result["total_runs"] == 2
        assert result["total_input_tokens"] == 3000  # 1000 + 2000
        assert result["total_output_tokens"] == 1300  # 500 + 800

    def test_not_found(self, mem_db):
        from db.queries import query_agent_detail

        self._populate(mem_db)
        result = query_agent_detail(mem_db, "nonexistent")
        assert result is None

    def test_per_project_breakdown(self, mem_db):
        from db.queries import query_agent_detail

        self._populate(mem_db)
        result = query_agent_detail(mem_db, "oh-my-claudecode:executor")
        assert result is not None
        assert "-proj-a" in result["usage_by_project"]
        assert result["usage_by_project"]["-proj-a"] == 2

    def test_projects_list(self, mem_db):
        from db.queries import query_agent_detail

        self._populate(mem_db)
        result = query_agent_detail(mem_db, "oh-my-claudecode:executor")
        assert result is not None
        assert result["projects"] == ["-proj-a"]

    def test_top_tools(self, mem_db):
        """top_tools returns tool counts from subagent_tools table."""
        _insert_test_session(mem_db, "s1", project_encoded_name="-proj")
        mem_db.execute(
            "INSERT INTO subagent_invocations (session_uuid, agent_id, subagent_type, input_tokens, output_tokens, cost_usd, duration_seconds, started_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                "s1",
                "agent-1",
                "oh-my-claudecode:executor",
                100,
                50,
                0.01,
                10.0,
                "2025-01-01T10:00:00",
            ),
        )
        inv_id = mem_db.execute("SELECT last_insert_rowid()").fetchone()[0]
        mem_db.executemany(
            "INSERT INTO subagent_tools (invocation_id, tool_name, count) VALUES (?, ?, ?)",
            [(inv_id, "Read", 5), (inv_id, "Edit", 3), (inv_id, "Bash", 1)],
        )
        mem_db.commit()

        from db.queries import query_agent_detail

        result = query_agent_detail(mem_db, "oh-my-claudecode:executor")
        assert result is not None
        assert result["top_tools"] == {"Read": 5, "Edit": 3, "Bash": 1}

    def test_top_tools_empty(self, mem_db):
        """top_tools returns empty dict when no tool data exists."""
        _insert_test_session(mem_db, "s1", project_encoded_name="-proj")
        mem_db.execute(
            "INSERT INTO subagent_invocations (session_uuid, agent_id, subagent_type, input_tokens, output_tokens, cost_usd, duration_seconds, started_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                "s1",
                "agent-1",
                "oh-my-claudecode:executor",
                100,
                50,
                0.01,
                10.0,
                "2025-01-01T10:00:00",
            ),
        )
        mem_db.commit()

        from db.queries import query_agent_detail

        result = query_agent_detail(mem_db, "oh-my-claudecode:executor")
        assert result is not None
        assert result["top_tools"] == {}


class TestAgentHistoryQuery:
    """Tests for db.queries.query_agent_history — agent invocation history."""

    def _populate(self, conn):
        """Insert test sessions and subagent invocations."""
        _insert_test_session(conn, "s1", project_encoded_name="-proj-a")
        _insert_test_session(conn, "s2", project_encoded_name="-proj-a")
        _insert_test_session(conn, "s3", project_encoded_name="-proj-b")

        conn.execute(
            """INSERT INTO subagent_invocations
               (session_uuid, agent_id, subagent_type, input_tokens, output_tokens, cost_usd, duration_seconds, started_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                "s1",
                "agent-1",
                "oh-my-claudecode:executor",
                1000,
                500,
                0.05,
                10.0,
                "2026-01-15T10:00:00+00:00",
            ),
        )
        conn.execute(
            """INSERT INTO subagent_invocations
               (session_uuid, agent_id, subagent_type, input_tokens, output_tokens, cost_usd, duration_seconds, started_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                "s1",
                "agent-2",
                "oh-my-claudecode:explore",
                500,
                200,
                0.02,
                5.0,
                "2026-01-15T10:01:00+00:00",
            ),
        )
        conn.execute(
            """INSERT INTO subagent_invocations
               (session_uuid, agent_id, subagent_type, input_tokens, output_tokens, cost_usd, duration_seconds, started_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                "s2",
                "agent-3",
                "oh-my-claudecode:executor",
                2000,
                800,
                0.08,
                15.0,
                "2026-01-16T10:00:00+00:00",
            ),
        )
        conn.execute(
            """INSERT INTO subagent_invocations
               (session_uuid, agent_id, subagent_type, input_tokens, output_tokens, cost_usd, duration_seconds, started_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                "s3",
                "agent-4",
                "oh-my-claudecode:architect",
                3000,
                1000,
                0.15,
                20.0,
                "2026-01-17T10:00:00+00:00",
            ),
        )
        conn.commit()

    def test_pagination(self, mem_db):
        from db.queries import query_agent_history

        self._populate(mem_db)
        result = query_agent_history(mem_db, "oh-my-claudecode:executor", limit=1, offset=0)
        assert len(result["invocations"]) == 1
        assert result["total"] == 2

    def test_total_count(self, mem_db):
        from db.queries import query_agent_history

        self._populate(mem_db)
        result = query_agent_history(mem_db, "oh-my-claudecode:executor")
        assert result["total"] == 2

    def test_ordering(self, mem_db):
        from db.queries import query_agent_history

        self._populate(mem_db)
        result = query_agent_history(mem_db, "oh-my-claudecode:executor")
        # Most recent first (2026-01-16)
        assert "2026-01-16" in result["invocations"][0]["started_at"]

    def test_empty_results(self, mem_db):
        from db.queries import query_agent_history

        self._populate(mem_db)
        result = query_agent_history(mem_db, "nonexistent")
        assert result["invocations"] == []
        assert result["total"] == 0


class TestConnectionLifecycle:
    """Tests for reader/writer connection separation."""

    @pytest.fixture(autouse=True)
    def _setup_db_path(self, tmp_path, monkeypatch):
        """Point SQLite DB to a temp directory for isolation."""
        db_file = tmp_path / "karma.db"
        monkeypatch.setattr("db.connection.get_db_path", lambda: db_file)
        # Reset writer singleton between tests
        import db.connection as conn_mod

        conn_mod._writer = None
        yield
        # Cleanup writer after test
        if conn_mod._writer is not None:
            conn_mod._writer.close()
            conn_mod._writer = None

    def test_writer_creates_db_and_schema(self, tmp_path):
        from db.connection import get_db_path, get_writer_db

        conn = get_writer_db()
        assert get_db_path().exists()
        # Schema should be applied
        tables = {
            r[0]
            for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        }
        assert "sessions" in tables
        assert "sessions_fts" in tables

    def test_writer_is_singleton(self):
        from db.connection import get_writer_db

        conn1 = get_writer_db()
        conn2 = get_writer_db()
        assert conn1 is conn2

    def test_writer_uses_wal_mode(self):
        from db.connection import get_writer_db

        conn = get_writer_db()
        mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
        assert mode == "wal"

    def test_read_connection_after_writer(self):
        from db.connection import create_read_connection, get_writer_db

        get_writer_db()  # Ensure DB exists
        reader = create_read_connection()
        try:
            tables = {
                r[0]
                for r in reader.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                ).fetchall()
            }
            assert "sessions" in tables
        finally:
            reader.close()

    def test_read_connection_is_not_singleton(self):
        from db.connection import create_read_connection, get_writer_db

        get_writer_db()
        r1 = create_read_connection()
        r2 = create_read_connection()
        try:
            assert r1 is not r2
        finally:
            r1.close()
            r2.close()

    def test_read_connection_is_readonly(self):
        from db.connection import create_read_connection, get_writer_db

        get_writer_db()
        reader = create_read_connection()
        try:
            with pytest.raises(sqlite3.OperationalError):
                reader.execute("INSERT INTO projects (encoded_name) VALUES ('test')")
        finally:
            reader.close()

    def test_concurrent_read_during_write(self):
        """Reader can query while writer has an open transaction."""
        from db.connection import create_read_connection, get_writer_db

        writer = get_writer_db()

        # Insert a row and commit so readers can see it
        writer.execute(
            """INSERT INTO sessions (uuid, project_encoded_name, jsonl_mtime, message_count)
               VALUES ('visible', '-test', 0.0, 1)"""
        )
        writer.commit()

        # Start a new write transaction (uncommitted)
        writer.execute(
            """INSERT INTO sessions (uuid, project_encoded_name, jsonl_mtime, message_count)
               VALUES ('invisible', '-test', 0.0, 1)"""
        )

        # Reader should see committed data but not the uncommitted row
        reader = create_read_connection()
        try:
            count = reader.execute("SELECT COUNT(*) FROM sessions").fetchone()[0]
            assert count == 1  # Only 'visible', not 'invisible'
        finally:
            reader.close()

        writer.rollback()

    def test_close_db_clears_writer(self):
        import db.connection as conn_mod
        from db.connection import close_db, get_writer_db

        get_writer_db()
        assert conn_mod._writer is not None
        close_db()
        assert conn_mod._writer is None

    def test_read_fails_before_writer(self, tmp_path):
        """create_read_connection fails if DB file doesn't exist yet."""
        from db.connection import create_read_connection

        with pytest.raises(sqlite3.OperationalError):
            create_read_connection()


# ---------------------------------------------------------------------------
# Phase 3: Continuation & Message UUID Query Tests
# ---------------------------------------------------------------------------


class TestMigrationV2ToV3:
    """Test v2→v3 migration adds message_uuids table."""

    def test_migration_creates_table(self):
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")

        # Apply full schema then simulate v2 state
        from db.schema import SCHEMA_SQL

        conn.executescript(SCHEMA_SQL)
        conn.execute("DROP TABLE IF EXISTS message_uuids")
        conn.execute("INSERT OR REPLACE INTO schema_version (version) VALUES (2)")
        conn.commit()

        # Verify message_uuids doesn't exist
        tables = {
            r[0]
            for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        }
        assert "message_uuids" not in tables

        # Run migration
        ensure_schema(conn)

        # Verify message_uuids now exists
        tables = {
            r[0]
            for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        }
        assert "message_uuids" in tables

        # Verify index exists
        indexes = {
            r[0]
            for r in conn.execute("SELECT name FROM sqlite_master WHERE type='index'").fetchall()
        }
        assert "idx_message_session" in indexes

        # Verify version is 3
        version = conn.execute("SELECT MAX(version) FROM schema_version").fetchone()[0]
        assert version == SCHEMA_VERSION

        conn.close()


class TestSourceSessionQuery:
    """Tests for db.queries.query_source_session."""

    def test_found(self, mem_db):
        from db.queries import query_source_session

        _insert_test_session(
            mem_db,
            "src-uuid",
            slug="my-slug",
            project_encoded_name="-proj-a",
            end_time="2026-01-15T10:30:00+00:00",
            is_continuation_marker=1,
        )
        result = query_source_session(mem_db, "src-uuid")
        assert result is not None
        assert result["uuid"] == "src-uuid"
        assert result["slug"] == "my-slug"
        assert result["project_encoded_name"] == "-proj-a"
        assert result["end_time"] == "2026-01-15T10:30:00+00:00"
        assert result["is_continuation_marker"] == 1

    def test_not_found(self, mem_db):
        from db.queries import query_source_session

        result = query_source_session(mem_db, "nonexistent")
        assert result is None


class TestContinuationQuery:
    """Tests for db.queries.query_continuation_session."""

    def _populate(self, conn):
        # Source session (continuation marker)
        _insert_test_session(
            conn,
            "source-uuid",
            slug="shared-slug",
            project_encoded_name="-proj-a",
            start_time="2026-01-15T10:00:00+00:00",
            end_time="2026-01-15T10:30:00+00:00",
            is_continuation_marker=1,
            message_count=2,
        )
        # Continuation session (same slug, not a marker)
        _insert_test_session(
            conn,
            "continuation-uuid",
            slug="shared-slug",
            project_encoded_name="-proj-a",
            start_time="2026-01-15T10:31:00+00:00",
            end_time="2026-01-15T11:00:00+00:00",
            is_continuation_marker=0,
            message_count=20,
        )
        # Another marker session (should be skipped)
        _insert_test_session(
            conn,
            "another-marker",
            slug="shared-slug",
            project_encoded_name="-proj-a",
            start_time="2026-01-15T10:32:00+00:00",
            is_continuation_marker=1,
            message_count=1,
        )
        conn.commit()

    def test_slug_match(self, mem_db):
        from db.queries import query_continuation_session

        self._populate(mem_db)
        result = query_continuation_session(
            mem_db,
            project="-proj-a",
            source_uuid="source-uuid",
            slug="shared-slug",
            source_end_time="2026-01-15T10:30:00+00:00",
        )
        assert result is not None
        assert result["uuid"] == "continuation-uuid"
        assert result["slug"] == "shared-slug"

    def test_time_proximity_fallback(self, mem_db):
        from db.queries import query_continuation_session

        # Insert source with unique slug
        _insert_test_session(
            mem_db,
            "time-source",
            slug="unique-source-slug",
            project_encoded_name="-proj-b",
            end_time="2026-01-15T10:30:00+00:00",
            message_count=5,
        )
        # Insert candidate starting within 60s
        _insert_test_session(
            mem_db,
            "time-candidate",
            slug="different-slug",
            project_encoded_name="-proj-b",
            start_time="2026-01-15T10:30:30+00:00",
            is_continuation_marker=0,
            message_count=10,
        )
        mem_db.commit()
        result = query_continuation_session(
            mem_db,
            project="-proj-b",
            source_uuid="time-source",
            slug="unique-source-slug",
            source_end_time="2026-01-15T10:30:00+00:00",
        )
        assert result is not None
        assert result["uuid"] == "time-candidate"

    def test_no_match(self, mem_db):
        from db.queries import query_continuation_session

        _insert_test_session(
            mem_db,
            "lonely",
            slug="lonely-slug",
            project_encoded_name="-proj-c",
            message_count=5,
        )
        mem_db.commit()
        result = query_continuation_session(
            mem_db,
            project="-proj-c",
            source_uuid="lonely",
            slug="lonely-slug",
            source_end_time="2026-01-15T10:30:00+00:00",
        )
        assert result is None

    def test_skips_continuation_markers(self, mem_db):
        from db.queries import query_continuation_session

        self._populate(mem_db)
        # The "another-marker" has is_continuation_marker=1, should be skipped
        result = query_continuation_session(
            mem_db,
            project="-proj-a",
            source_uuid="source-uuid",
            slug="shared-slug",
            source_end_time="2026-01-15T10:30:00+00:00",
        )
        assert result is not None
        assert result["uuid"] == "continuation-uuid"  # Not another-marker


class TestMessageUuidQuery:
    """Tests for db.queries.query_session_by_message_uuid."""

    def test_found(self, mem_db):
        from db.queries import query_session_by_message_uuid

        _insert_test_session(
            mem_db,
            "session-1",
            slug="test-slug",
            project_encoded_name="-proj-a",
        )
        mem_db.execute(
            "INSERT INTO message_uuids (message_uuid, session_uuid) VALUES (?, ?)",
            ("msg-uuid-123", "session-1"),
        )
        mem_db.commit()
        result = query_session_by_message_uuid(mem_db, "msg-uuid-123")
        assert result is not None
        assert result["session_uuid"] == "session-1"
        assert result["slug"] == "test-slug"
        assert result["project_encoded_name"] == "-proj-a"

    def test_not_found(self, mem_db):
        from db.queries import query_session_by_message_uuid

        result = query_session_by_message_uuid(mem_db, "nonexistent-msg")
        assert result is None

    def test_cascade_delete(self, mem_db):
        """message_uuids rows are cascade-deleted when session is deleted."""
        _insert_test_session(mem_db, "session-1", project_encoded_name="-proj-a")
        mem_db.execute(
            "INSERT INTO message_uuids (message_uuid, session_uuid) VALUES (?, ?)",
            ("msg-1", "session-1"),
        )
        mem_db.execute(
            "INSERT INTO message_uuids (message_uuid, session_uuid) VALUES (?, ?)",
            ("msg-2", "session-1"),
        )
        mem_db.commit()

        # Verify they exist
        count = mem_db.execute("SELECT COUNT(*) FROM message_uuids").fetchone()[0]
        assert count == 2

        # Delete the session
        mem_db.execute("DELETE FROM sessions WHERE uuid = 'session-1'")
        mem_db.commit()

        # Verify cascade delete
        count = mem_db.execute("SELECT COUNT(*) FROM message_uuids").fetchone()[0]
        assert count == 0

    def test_multiple_messages_per_session(self, mem_db):
        from db.queries import query_session_by_message_uuid

        _insert_test_session(mem_db, "session-1", project_encoded_name="-proj-a")
        for i in range(5):
            mem_db.execute(
                "INSERT INTO message_uuids (message_uuid, session_uuid) VALUES (?, ?)",
                (f"msg-{i}", "session-1"),
            )
        mem_db.commit()

        # Each message UUID should resolve to the same session
        for i in range(5):
            result = query_session_by_message_uuid(mem_db, f"msg-{i}")
            assert result is not None
            assert result["session_uuid"] == "session-1"

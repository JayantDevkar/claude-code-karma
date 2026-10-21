"""
Referential-integrity regression tests for issue #107.

Orphaned child rows (e.g. subagent_tools whose invocation is gone) can only
appear when a parent row is deleted without its children AND foreign-key
enforcement is off on that connection. These tests pin both halves:

- ensure_schema must leave PRAGMA foreign_keys ON after every migration path
- every session-delete path in the indexer must clear child rows explicitly,
  so correctness never depends on the cascade
- the repair migration must remove orphans already on disk
- the health check must surface any violation that slips through
"""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from db import indexer
from db.schema import SCHEMA_SQL, SCHEMA_VERSION, ensure_schema

# ============================================================================
# Helpers
# ============================================================================


def _db_at_version(version: int, *, foreign_keys: bool) -> sqlite3.Connection:
    """Full current schema, then rewind schema_version to simulate an old DB."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute(f"PRAGMA foreign_keys={'ON' if foreign_keys else 'OFF'}")
    conn.executescript(SCHEMA_SQL)
    conn.execute("DELETE FROM schema_version")
    conn.execute("INSERT INTO schema_version (version) VALUES (?)", (version,))
    conn.commit()
    return conn


def _seed_session_tree(conn: sqlite3.Connection, uuid: str = "s1") -> int:
    """Insert a session with one row in every session-scoped child table."""
    conn.execute(
        "INSERT OR IGNORE INTO projects (encoded_name, display_name, slug) VALUES ('-foo', 'foo', 'foo')"
    )
    conn.execute(
        "INSERT INTO sessions (uuid, project_encoded_name, jsonl_mtime, subagent_count) "
        "VALUES (?, '-foo', 1.0, 1)",
        (uuid,),
    )
    conn.execute("INSERT INTO session_tools VALUES (?, 'Read', 1)", (uuid,))
    conn.execute(
        "INSERT INTO session_skills (session_uuid, skill_name, invocation_source, count) "
        "VALUES (?, 'commit', 'skill_tool', 1)",
        (uuid,),
    )
    conn.execute(
        "INSERT INTO session_commands (session_uuid, command_name, invocation_source, count) "
        "VALUES (?, 'review', 'slash_command', 1)",
        (uuid,),
    )
    conn.execute("INSERT INTO message_uuids VALUES (?, ?)", (f"m-{uuid}", uuid))
    conn.execute("INSERT INTO session_leaf_refs VALUES (?, ?)", (uuid, f"leaf-{uuid}"))
    conn.execute(
        "INSERT INTO subagent_invocations (session_uuid, agent_id, subagent_type) "
        "VALUES (?, 'a1', 'Explore')",
        (uuid,),
    )
    inv_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    conn.execute("INSERT INTO subagent_tools VALUES (?, 'Grep', 2)", (inv_id,))
    conn.execute(
        "INSERT INTO subagent_skills (invocation_id, skill_name, invocation_source, count) "
        "VALUES (?, 'tdd', 'skill_tool', 1)",
        (inv_id,),
    )
    conn.execute(
        "INSERT INTO subagent_commands (invocation_id, command_name, invocation_source, count) "
        "VALUES (?, 'plan', 'slash_command', 1)",
        (inv_id,),
    )
    conn.execute(
        "INSERT INTO background_shells (session_uuid, tool_use_id, tool_name, command, spawned_at) "
        "VALUES (?, ?, 'Bash', 'sleep 1', '2026-10-01T00:00:00Z')",
        (uuid, f"tu-{uuid}"),
    )
    shell_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    conn.execute(
        "INSERT INTO shell_polls (shell_row_id, polled_at, tool_use_id) "
        "VALUES (?, '2026-10-01T00:00:01Z', ?)",
        (shell_id, f"poll-{uuid}"),
    )
    conn.execute(
        "INSERT INTO cron_jobs (session_uuid, tool_use_id, cron_expression, prompt, created_at, ttl_expires_at) "
        "VALUES (?, ?, '* * * * *', 'p', '2026-10-01T00:00:00Z', '2026-10-02T00:00:00Z')",
        (uuid, f"cron-{uuid}"),
    )
    conn.execute(
        "INSERT INTO cron_state_snapshots (session_uuid, captured_at, trigger_event, payload_json) "
        "VALUES (?, '2026-10-01T00:00:00Z', 'CronList', '{}')",
        (uuid,),
    )
    conn.commit()
    return inv_id


SESSION_CHILD_TABLES = [
    "session_tools",
    "session_skills",
    "session_commands",
    "message_uuids",
    "session_leaf_refs",
    "subagent_invocations",
    "background_shells",
    "cron_jobs",
    "cron_state_snapshots",
]


def _rows_for_session(conn: sqlite3.Connection, uuid: str) -> dict[str, int]:
    counts = {
        t: conn.execute(f"SELECT COUNT(*) FROM {t} WHERE session_uuid = ?", (uuid,)).fetchone()[0]
        for t in SESSION_CHILD_TABLES
    }
    counts["sessions"] = conn.execute(
        "SELECT COUNT(*) FROM sessions WHERE uuid = ?", (uuid,)
    ).fetchone()[0]
    counts["subagent_tools"] = conn.execute("SELECT COUNT(*) FROM subagent_tools").fetchone()[0]
    counts["subagent_skills"] = conn.execute("SELECT COUNT(*) FROM subagent_skills").fetchone()[0]
    counts["subagent_commands"] = conn.execute("SELECT COUNT(*) FROM subagent_commands").fetchone()[
        0
    ]
    counts["shell_polls"] = conn.execute("SELECT COUNT(*) FROM shell_polls").fetchone()[0]
    return counts


def _fk_violations(conn: sqlite3.Connection) -> list:
    return conn.execute("PRAGMA foreign_key_check").fetchall()


# ============================================================================
# 1. Migrations must not leave foreign keys disabled
# ============================================================================


class TestMigrationKeepsForeignKeysOn:
    def test_upgrade_through_v19_keeps_foreign_keys_on(self):
        # v19 rebuilds background_shells with PRAGMA foreign_keys=OFF; the re-enable
        # must take effect for the rest of the connection's life.
        conn = _db_at_version(18, foreign_keys=True)
        assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1

        ensure_schema(conn)

        assert (
            conn.execute("SELECT MAX(version) FROM schema_version").fetchone()[0] == SCHEMA_VERSION
        )
        assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1

    def test_cascade_works_after_upgrade_through_v19(self):
        conn = _db_at_version(18, foreign_keys=True)
        ensure_schema(conn)

        _seed_session_tree(conn)
        conn.execute("DELETE FROM subagent_invocations WHERE session_uuid = 's1'")
        conn.commit()

        assert conn.execute("SELECT COUNT(*) FROM subagent_tools").fetchone()[0] == 0

    def test_upgrade_from_v10_keeps_shell_polls_and_foreign_keys_on(self):
        # v10's DML opens a transaction before v19 runs, so v19's PRAGMA OFF would be
        # ignored and DROP TABLE background_shells would cascade-wipe shell_polls.
        conn = _db_at_version(10, foreign_keys=True)
        _seed_session_tree(conn)

        ensure_schema(conn)

        assert conn.execute("SELECT COUNT(*) FROM shell_polls").fetchone()[0] == 1
        assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1


class TestV24ReindexesLocalCommandPrompts:
    def test_only_sessions_with_a_local_command_prompt_are_reindexed(self):
        conn = _db_at_version(23, foreign_keys=True)
        conn.execute(
            "INSERT INTO projects (encoded_name, display_name, slug) VALUES ('-foo', 'foo', 'foo')"
        )
        for uuid, prompt in [
            ("caveat", "<local-command-caveat>The command below was run</local-command-caveat>"),
            (
                "command",
                "<command-name>/clear</command-name>\n<command-message>clear</command-message>",
            ),
            ("typed", "Fix the login bug"),
        ]:
            conn.execute(
                "INSERT INTO sessions (uuid, project_encoded_name, jsonl_mtime, initial_prompt) "
                "VALUES (?, '-foo', 10.0, ?)",
                (uuid, prompt),
            )
        conn.commit()

        ensure_schema(conn)

        mtimes = dict(conn.execute("SELECT uuid, jsonl_mtime FROM sessions").fetchall())
        assert mtimes == {"caveat": 9.0, "command": 9.0, "typed": 10.0}


# ============================================================================
# 2. Indexer delete paths must not depend on the cascade
# ============================================================================


class TestDeleteSessionRowsWithoutCascade:
    def test_helper_clears_every_child_table(self):
        conn = _db_at_version(SCHEMA_VERSION, foreign_keys=False)
        _seed_session_tree(conn, "s1")
        _seed_session_tree(conn, "s2")

        indexer._delete_session_rows(conn, ["s1"])
        conn.commit()

        gone = _rows_for_session(conn, "s1")
        assert {
            k: v for k, v in gone.items() if k.startswith("session") or k in SESSION_CHILD_TABLES
        } == {k: 0 for k in gone if k.startswith("session") or k in SESSION_CHILD_TABLES}
        # Only s2's grandchildren remain
        assert gone["subagent_tools"] == 1
        assert gone["subagent_skills"] == 1
        assert gone["subagent_commands"] == 1
        assert gone["shell_polls"] == 1
        assert _fk_violations(conn) == []

    def test_empty_jsonl_reindex_leaves_no_orphans(self, tmp_path):
        conn = _db_at_version(SCHEMA_VERSION, foreign_keys=False)
        _seed_session_tree(conn, "s1")
        jsonl = tmp_path / "s1.jsonl"
        jsonl.write_text("")

        indexer._index_session(conn, jsonl, "-foo", jsonl.stat().st_mtime, 0)
        conn.commit()

        assert conn.execute("SELECT COUNT(*) FROM sessions WHERE uuid='s1'").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM subagent_tools").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM background_shells").fetchone()[0] == 0
        assert _fk_violations(conn) == []

    def test_stale_cleanup_removes_shell_and_cron_rows(self, tmp_path):
        conn = _db_at_version(SCHEMA_VERSION, foreign_keys=False)
        _seed_session_tree(conn, "s1")
        (tmp_path / "-foo").mkdir()  # project dir exists but the JSONL is gone

        indexer._cleanup_stale_sessions(conn, tmp_path)

        assert conn.execute("SELECT COUNT(*) FROM sessions").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM background_shells").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM shell_polls").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM cron_jobs").fetchone()[0] == 0
        assert _fk_violations(conn) == []


# ============================================================================
# 3. Repair migration removes orphans already on disk
# ============================================================================


class TestOrphanRepairMigration:
    def test_migration_removes_orphan_rows(self):
        conn = _db_at_version(19, foreign_keys=False)
        inv_id = _seed_session_tree(conn, "live")
        # Orphans: children whose parents were deleted with FK off
        conn.execute("INSERT INTO subagent_tools VALUES (999999, 'Read', 5)")
        conn.execute(
            "INSERT INTO subagent_skills (invocation_id, skill_name, invocation_source, count) "
            "VALUES (999999, 'x', 'skill_tool', 1)"
        )
        conn.execute(
            "INSERT INTO subagent_commands (invocation_id, command_name, invocation_source, count) "
            "VALUES (999999, 'y', 'slash_command', 1)"
        )
        conn.execute(
            "INSERT INTO background_shells (session_uuid, tool_use_id, tool_name, command, spawned_at) "
            "VALUES ('ghost', 'tu-ghost', 'Bash', 'ls', '2026-10-01T00:00:00Z')"
        )
        ghost_shell = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        conn.execute(
            "INSERT INTO shell_polls (shell_row_id, polled_at, tool_use_id) "
            "VALUES (?, '2026-10-01T00:00:01Z', 'poll-ghost')",
            (ghost_shell,),
        )
        conn.execute(
            "INSERT INTO cron_jobs (session_uuid, tool_use_id, cron_expression, prompt, created_at, ttl_expires_at) "
            "VALUES ('ghost', 'cron-ghost', '* * * * *', 'p', '2026-10-01T00:00:00Z', '2026-10-02T00:00:00Z')"
        )
        conn.commit()
        # The ghost shell's poll is not an FK violation (its shell row exists) but must go too.
        assert len(_fk_violations(conn)) == 5

        ensure_schema(conn)

        assert _fk_violations(conn) == []
        # Live rows untouched
        assert (
            conn.execute(
                "SELECT count FROM subagent_tools WHERE invocation_id = ?", (inv_id,)
            ).fetchone()[0]
            == 2
        )
        assert conn.execute("SELECT COUNT(*) FROM background_shells").fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM shell_polls").fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM cron_jobs").fetchone()[0] == 1


# ============================================================================
# 4. Health check surfaces violations
# ============================================================================


class TestHealthReportsForeignKeyViolations:
    def test_health_counts_fk_violations(self):
        conn = _db_at_version(SCHEMA_VERSION, foreign_keys=False)
        conn.execute("INSERT INTO subagent_tools VALUES (424242, 'Read', 1)")
        conn.commit()

        metrics = indexer._log_db_health(conn)

        assert metrics["fk_violations"] == 1

    def test_health_reports_zero_when_clean(self):
        conn = _db_at_version(SCHEMA_VERSION, foreign_keys=True)
        _seed_session_tree(conn)

        metrics = indexer._log_db_health(conn)

        assert metrics["fk_violations"] == 0

    def test_health_counts_orphan_shells_on_upgraded_db(self):
        # The v19 rebuild left background_shells without an FK to sessions, so
        # pragma_foreign_key_check alone cannot see orphaned shells there.
        conn = _db_at_version(18, foreign_keys=True)
        ensure_schema(conn)
        assert conn.execute("PRAGMA foreign_key_list(background_shells)").fetchall() == []
        conn.execute("PRAGMA foreign_keys=OFF")
        conn.execute(
            "INSERT INTO background_shells (session_uuid, tool_use_id, tool_name, command, spawned_at) "
            "VALUES ('ghost', 'tu-ghost', 'Bash', 'ls', '2026-10-01T00:00:00Z')"
        )
        conn.commit()

        metrics = indexer._log_db_health(conn)

        assert metrics["fk_violations"] == 1


# ============================================================================
# 5. Re-indexing a session must not cascade-delete its children
# ============================================================================


class TestReindexPreservesSessionChildren:
    def test_reindex_keeps_cron_rows_and_ids(self, sample_session_jsonl):
        conn = _db_at_version(SCHEMA_VERSION, foreign_keys=True)
        encoded = sample_session_jsonl.parent.name
        uuid = sample_session_jsonl.stem
        stat = sample_session_jsonl.stat()
        indexer._index_session(conn, sample_session_jsonl, encoded, stat.st_mtime, stat.st_size)
        conn.execute(
            "INSERT INTO cron_jobs (session_uuid, tool_use_id, cron_expression, prompt, created_at, ttl_expires_at) "
            "VALUES (?, 'cron-x', '* * * * *', 'p', '2026-10-01T00:00:00Z', '2026-10-02T00:00:00Z')",
            (uuid,),
        )
        cron_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        conn.execute(
            "INSERT INTO cron_state_snapshots (session_uuid, captured_at, trigger_event, payload_json) "
            "VALUES (?, '2026-10-01T00:00:00Z', 'CronList', '{}')",
            (uuid,),
        )
        conn.execute("UPDATE sessions SET needs_shell_cron_reindex = 0 WHERE uuid = ?", (uuid,))
        conn.commit()

        indexer._index_session(conn, sample_session_jsonl, encoded, stat.st_mtime + 1, stat.st_size)
        conn.commit()

        assert conn.execute("SELECT id FROM cron_jobs").fetchall()[0][0] == cron_id
        assert conn.execute("SELECT COUNT(*) FROM cron_state_snapshots").fetchone()[0] == 1
        assert (
            conn.execute(
                "SELECT needs_shell_cron_reindex FROM sessions WHERE uuid = ?", (uuid,)
            ).fetchone()[0]
            == 0
        )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

"""Tests for the v25 migration restoring the background_shells → sessions FK (issue #132)."""

from __future__ import annotations

import re
import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from db import indexer
from db.schema import SCHEMA_SQL, SCHEMA_VERSION, _restore_background_shells_fk, ensure_schema

# ============================================================================
# Fixtures + helpers
# ============================================================================

# background_shells as v13 created it; v18 appended output_file_path.
_V13_SHELLS_DDL = """
CREATE TABLE background_shells (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    session_uuid       TEXT    NOT NULL,
    tool_use_id        TEXT    NOT NULL,
    shell_id           TEXT,
    tool_name          TEXT    NOT NULL CHECK (tool_name IN ('Bash','Monitor')),
    command            TEXT    NOT NULL,
    command_truncated  INTEGER NOT NULL DEFAULT 0 CHECK (command_truncated IN (0,1)),
    description        TEXT,
    is_persistent      INTEGER NOT NULL DEFAULT 0 CHECK (is_persistent IN (0,1)),
    timeout_ms         INTEGER,
    spawned_at         TEXT    NOT NULL,
    terminated_at      TEXT,
    terminated_by      TEXT    CHECK (terminated_by IN ('kill','natural','timeout','session_end')),
    exit_code          INTEGER,
    poll_count         INTEGER NOT NULL DEFAULT 0,
    total_output_bytes INTEGER NOT NULL DEFAULT 0,
    last_output_at     TEXT,
    spawn_message_uuid TEXT,
    {v18_column}
    CHECK ((terminated_at IS NULL) = (terminated_by IS NULL)),
    FOREIGN KEY (session_uuid) REFERENCES sessions(uuid) ON DELETE CASCADE,
    UNIQUE(tool_use_id)
)
"""

# background_shells as the v19 rebuild left it: no FK to sessions.
_V19_SHELLS_DDL = """
CREATE TABLE background_shells (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    session_uuid       TEXT    NOT NULL,
    tool_use_id        TEXT    NOT NULL,
    shell_id           TEXT,
    tool_name          TEXT    NOT NULL CHECK (tool_name IN ('Bash','Monitor','Manual')),
    command            TEXT    NOT NULL,
    command_truncated  INTEGER NOT NULL DEFAULT 0 CHECK (command_truncated IN (0,1)),
    description        TEXT,
    is_persistent      INTEGER NOT NULL DEFAULT 0 CHECK (is_persistent IN (0,1)),
    timeout_ms         INTEGER,
    spawned_at         TEXT    NOT NULL,
    terminated_at      TEXT,
    terminated_by      TEXT    CHECK (terminated_by IN ('kill','natural','timeout','session_end')),
    exit_code          INTEGER,
    poll_count         INTEGER NOT NULL DEFAULT 0,
    total_output_bytes INTEGER NOT NULL DEFAULT 0,
    last_output_at     TEXT,
    spawn_message_uuid TEXT,
    output_file_path   TEXT,
    CHECK ((terminated_at IS NULL) = (terminated_by IS NULL)),
    UNIQUE(tool_use_id)
)
"""

_SHELLS_DDL_AT = {
    13: _V13_SHELLS_DDL.format(v18_column=""),
    18: _V13_SHELLS_DDL.format(v18_column="output_file_path TEXT,"),
    24: _V19_SHELLS_DDL,
}

_SHELLS_INDEXES = (
    "CREATE INDEX idx_bg_shells_session ON background_shells(session_uuid, spawned_at DESC)",
    "CREATE INDEX idx_bg_shells_shell_id ON background_shells(shell_id) WHERE shell_id IS NOT NULL",
    "CREATE INDEX idx_bg_shells_spawned ON background_shells(spawned_at DESC)",
)


def _db_at(version: int, shells_ddl: str | None = None) -> sqlite3.Connection:
    """Current schema stamped at `version`, with background_shells replaced by `shells_ddl`."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA_SQL)
    if shells_ddl is not None:
        conn.execute("DROP TABLE background_shells")
        conn.execute(shells_ddl)
        for sql in _SHELLS_INDEXES:
            conn.execute(sql)
    conn.execute("DELETE FROM schema_version")
    conn.execute("INSERT INTO schema_version (version) VALUES (?)", (version,))
    conn.commit()
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def _fresh_db() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    ensure_schema(conn)
    return conn


def _seed(conn: sqlite3.Connection) -> None:
    """Two sessions, each with a Bash and a Monitor shell, each shell with two polls."""
    conn.execute(
        "INSERT INTO projects (encoded_name, display_name, slug) VALUES ('-foo', 'foo', 'foo')"
    )
    for uuid in ("s1", "s2"):
        conn.execute(
            "INSERT INTO sessions (uuid, project_encoded_name, jsonl_mtime) VALUES (?, '-foo', 1.0)",
            (uuid,),
        )
        conn.execute(
            "INSERT INTO background_shells (session_uuid, tool_use_id, shell_id, tool_name, "
            "command, command_truncated, description, timeout_ms, spawned_at, terminated_at, "
            "terminated_by, exit_code, poll_count, total_output_bytes, last_output_at, "
            "spawn_message_uuid) VALUES (?, ?, ?, 'Bash', 'npm test', 1, 'tests', 600000, "
            "'2026-10-01T00:00:00Z', '2026-10-01T00:05:00Z', 'natural', 0, 2, 2048, "
            "'2026-10-01T00:04:00Z', ?)",
            (uuid, f"tu-bash-{uuid}", f"b-{uuid}", f"msg-{uuid}"),
        )
        conn.execute(
            "INSERT INTO background_shells (session_uuid, tool_use_id, tool_name, command, "
            "is_persistent, spawned_at) VALUES (?, ?, 'Monitor', 'tail -f log', 1, "
            "'2026-10-01T00:01:00Z')",
            (uuid, f"tu-mon-{uuid}"),
        )
    shell_ids = [r[0] for r in conn.execute("SELECT id FROM background_shells ORDER BY id")]
    conn.executemany(
        "INSERT INTO shell_polls (shell_row_id, polled_at, output_bytes, tool_use_id) "
        "VALUES (?, ?, 1024, ?)",
        [
            (shell_id, f"2026-10-01T00:0{n}:00Z", f"poll-{shell_id}-{n}")
            for shell_id in shell_ids
            for n in (2, 3)
        ],
    )
    conn.commit()


def _rows(conn: sqlite3.Connection, table: str) -> list[dict]:
    return [dict(r) for r in conn.execute(f"SELECT * FROM {table} ORDER BY id")]


def _fk_list(conn: sqlite3.Connection, table: str) -> list[tuple]:
    return [tuple(r) for r in conn.execute(f"PRAGMA foreign_key_list({table})")]


def _normalized(sql: str | None) -> str | None:
    """DDL with comments, quotes and whitespace differences removed."""
    if sql is None:
        return None
    return " ".join(re.sub(r"--[^\n]*", "", sql).replace('"', "").split())


def _shells_schema(conn: sqlite3.Connection) -> list[tuple]:
    return [
        (r["type"], r["name"], _normalized(r["sql"]))
        for r in conn.execute(
            "SELECT type, name, sql FROM sqlite_master "
            "WHERE tbl_name = 'background_shells' ORDER BY type, name"
        )
    ]


# ============================================================================
# v25 restores the FK on upgraded DBs
# ============================================================================


class TestV25RestoresShellsForeignKey:
    @pytest.mark.parametrize("start_version", [13, 18, 24])
    def test_upgraded_table_matches_fresh_install(self, start_version):
        conn = _db_at(start_version, _SHELLS_DDL_AT[start_version])
        fresh = _fresh_db()

        ensure_schema(conn)

        assert (
            conn.execute("SELECT MAX(version) FROM schema_version").fetchone()[0] == SCHEMA_VERSION
        )
        assert _fk_list(conn, "background_shells") == _fk_list(fresh, "background_shells")
        assert [(fk[2], fk[3], fk[4], fk[6]) for fk in _fk_list(conn, "background_shells")] == [
            ("sessions", "session_uuid", "uuid", "CASCADE")
        ]
        table_sql = conn.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name='background_shells'"
        ).fetchone()[0]
        assert "REFERENCES sessions(uuid) ON DELETE CASCADE" in table_sql
        assert _shells_schema(conn) == _shells_schema(fresh)
        assert _fk_list(conn, "shell_polls") == _fk_list(fresh, "shell_polls")
        assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1

    @pytest.mark.parametrize("start_version", [13, 18, 24])
    def test_shells_and_polls_survive(self, start_version):
        conn = _db_at(start_version, _SHELLS_DDL_AT[start_version])
        _seed(conn)
        shells_before = _rows(conn, "background_shells")
        polls_before = _rows(conn, "shell_polls")
        assert (len(shells_before), len(polls_before)) == (4, 8)

        ensure_schema(conn)

        shells_after = _rows(conn, "background_shells")
        assert [{k: r[k] for k in shells_before[0]} for r in shells_after] == shells_before
        assert _rows(conn, "shell_polls") == polls_before
        assert conn.execute("PRAGMA foreign_key_check").fetchall() == []

    def test_orphaned_shells_are_dropped_with_their_polls(self):
        conn = _db_at(24, _V19_SHELLS_DDL)
        _seed(conn)
        conn.execute(
            "INSERT INTO background_shells (session_uuid, tool_use_id, tool_name, command, "
            "spawned_at) VALUES ('ghost', 'tu-ghost', 'Bash', 'ls', '2026-10-01T00:00:00Z')"
        )
        ghost_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        conn.execute(
            "INSERT INTO shell_polls (shell_row_id, polled_at, tool_use_id) "
            "VALUES (?, '2026-10-01T00:00:01Z', 'poll-ghost')",
            (ghost_id,),
        )
        conn.commit()

        ensure_schema(conn)

        assert conn.execute("SELECT COUNT(*) FROM background_shells").fetchone()[0] == 4
        assert conn.execute("SELECT COUNT(*) FROM shell_polls").fetchone()[0] == 8
        assert (
            conn.execute(
                "SELECT COUNT(*) FROM shell_polls WHERE shell_row_id = ?", (ghost_id,)
            ).fetchone()[0]
            == 0
        )
        assert conn.execute("PRAGMA foreign_key_check").fetchall() == []

    @pytest.mark.parametrize("start_version", [18, 24])
    def test_deleting_a_session_cascades_to_its_shells(self, start_version):
        conn = _db_at(start_version, _SHELLS_DDL_AT[start_version])
        _seed(conn)
        ensure_schema(conn)

        conn.execute("DELETE FROM sessions WHERE uuid = 's1'")
        conn.commit()

        assert [
            r[0] for r in conn.execute("SELECT DISTINCT session_uuid FROM background_shells")
        ] == ["s2"]
        assert conn.execute("SELECT COUNT(*) FROM shell_polls").fetchone()[0] == 4
        assert conn.execute("PRAGMA foreign_key_check").fetchall() == []


# ============================================================================
# v25 leaves a table that already has the FK alone
# ============================================================================


class TestV25NoOpWhenForeignKeyPresent:
    def test_fresh_install_upgraded_from_v24_is_not_rebuilt(self):
        conn = _db_at(24)
        _seed(conn)
        master_before = conn.execute(
            "SELECT name, rootpage, sql FROM sqlite_master WHERE tbl_name = 'background_shells' "
            "ORDER BY name"
        ).fetchall()
        shells_before = _rows(conn, "background_shells")
        polls_before = _rows(conn, "shell_polls")

        ensure_schema(conn)

        assert (
            conn.execute("SELECT MAX(version) FROM schema_version").fetchone()[0] == SCHEMA_VERSION
        )
        master_after = conn.execute(
            "SELECT name, rootpage, sql FROM sqlite_master WHERE tbl_name = 'background_shells' "
            "ORDER BY name"
        ).fetchall()
        assert [tuple(r) for r in master_after] == [tuple(r) for r in master_before]
        assert _rows(conn, "background_shells") == shells_before
        assert _rows(conn, "shell_polls") == polls_before

    def test_second_run_after_upgrade_is_a_no_op(self):
        conn = _db_at(24, _V19_SHELLS_DDL)
        _seed(conn)
        ensure_schema(conn)
        schema_before = _shells_schema(conn)

        assert _restore_background_shells_fk(conn) is False

        assert _shells_schema(conn) == schema_before
        assert conn.execute("SELECT COUNT(*) FROM shell_polls").fetchone()[0] == 8


# ============================================================================
# Health check still sees orphaned shells if a table somehow lacks the FK
# ============================================================================


def test_health_counts_orphan_shells_when_fk_is_missing():
    # A parallel branch could stamp a version >= 25 without having run v25.
    conn = _db_at(SCHEMA_VERSION, _V19_SHELLS_DDL)
    ensure_schema(conn)
    assert _fk_list(conn, "background_shells") == []
    conn.execute(
        "INSERT INTO background_shells (session_uuid, tool_use_id, tool_name, command, "
        "spawned_at) VALUES ('ghost', 'tu-ghost', 'Bash', 'ls', '2026-10-01T00:00:00Z')"
    )
    conn.commit()

    assert indexer._count_orphan_rows(conn) == 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

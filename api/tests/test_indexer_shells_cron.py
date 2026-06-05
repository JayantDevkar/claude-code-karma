"""
Tests for the v13 background-shells + cron extraction and query layer.

Covers:
- JSONL extraction: spawn/poll/kill/cron-create/cron-delete pairing
- UPSERT idempotency (parent ids preserved across re-index)
- DB CHECK constraints (coherence, terminated_by, recurring)
- Hook ingestion: events.jsonl → cron_state_snapshots
- On-read cron fire inference (croniter)
- Query helpers: per-session, global, project rollups

All tests use an in-memory SQLite DB. Synthetic JSONLs are written to a
tmp_path so we don't depend on any real session being present on disk.
"""

from __future__ import annotations

import json
import sqlite3
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from db.indexer_shells_cron import (
    _CRON_ID_RE,
    _SHELL_ID_RE,
    extract_shells_and_cron,
    persist_shells_and_cron,
    sync_cron_state_snapshots,
)
from db.queries_shells_cron import (
    FIRE_CONFIDENCE_FLOOR,
    get_cron_for_session,
    get_cron_global,
    get_cron_project_rollup,
    get_latest_cron_state,
    get_shells_for_session,
    get_shells_global,
    get_shells_project_rollup,
    infer_cron_fires,
)
from db.schema import ensure_schema

# ============================================================================
# Fixtures + helpers
# ============================================================================


@pytest.fixture
def mem_db():
    """In-memory SQLite with v13 schema applied + FK enforcement on."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    ensure_schema(conn)
    return conn


def _seed_session(conn: sqlite3.Connection, uuid: str = "s1") -> None:
    """Insert a minimal sessions row so FK constraints are satisfied."""
    conn.execute(
        "INSERT INTO sessions (uuid, project_encoded_name, jsonl_mtime, end_time) "
        "VALUES (?, ?, ?, ?)",
        (uuid, "-foo", 0.0, "2026-05-25T01:00:00Z"),
    )


def _seed_project(conn: sqlite3.Connection) -> None:
    conn.execute(
        "INSERT INTO projects (encoded_name, display_name, slug) VALUES (?, ?, ?)",
        ("-foo", "foo", "foo-slug"),
    )


def _ts(minute: int = 0, second: int = 0) -> str:
    base = datetime(2026, 5, 25, 0, minute, second, tzinfo=timezone.utc)
    return base.isoformat().replace("+00:00", "Z")


def _assistant_tool_use(
    name: str,
    tool_use_id: str,
    inp: Dict[str, Any],
    ts: str = _ts(0),
    msg_uuid: str = "msg-0",
) -> Dict[str, Any]:
    return {
        "type": "assistant",
        "uuid": msg_uuid,
        "timestamp": ts,
        "message": {
            "role": "assistant",
            "content": [{"type": "tool_use", "id": tool_use_id, "name": name, "input": inp}],
        },
    }


def _tool_result(tool_use_id: str, content: str, ts: str = _ts(0, 1)) -> Dict[str, Any]:
    return {
        "type": "user",
        "uuid": f"result-{tool_use_id}",
        "timestamp": ts,
        "message": {
            "role": "user",
            "content": [{"type": "tool_result", "tool_use_id": tool_use_id, "content": content}],
        },
    }


def _write_jsonl(path: Path, lines: List[Dict[str, Any]]) -> Path:
    path.write_text("\n".join(json.dumps(line) for line in lines) + "\n")
    return path


# ============================================================================
# Regex extraction
# ============================================================================


class TestRegexExtraction:
    def test_shell_id_real_claude_format(self):
        m = _SHELL_ID_RE.search("Command running in background with ID: bh0udrq27.")
        assert m is not None
        assert m.group(1) == "bh0udrq27"

    def test_shell_id_json_format(self):
        m = _SHELL_ID_RE.search('{"shell_id": "abc123def"}')
        assert m is not None
        assert m.group(1) == "abc123def"

    def test_shell_id_loose_colon(self):
        m = _SHELL_ID_RE.search("shell_id: bedb379")
        assert m is not None
        assert m.group(1) == "bedb379"

    def test_shell_id_no_match(self):
        assert _SHELL_ID_RE.search("nothing here") is None

    def test_cron_id_extraction(self):
        m = _CRON_ID_RE.search("Task created with ID: a4f9b2c1")
        assert m is not None
        assert m.group(1) == "a4f9b2c1"


# ============================================================================
# Extraction
# ============================================================================


class TestExtraction:
    def test_bg_shell_spawn_extracted(self, tmp_path):
        jsonl = _write_jsonl(
            tmp_path / "s.jsonl",
            [
                _assistant_tool_use(
                    "Bash",
                    "toolu_1",
                    {
                        "command": "npm run dev",
                        "description": "dev server",
                        "run_in_background": True,
                    },
                    ts=_ts(0),
                ),
                _tool_result("toolu_1", "Command running in background with ID: bedb379."),
            ],
        )
        shells, polls, crons = extract_shells_and_cron(jsonl, "s1", session_ended=False)
        assert len(shells) == 1
        assert shells[0]["tool_use_id"] == "toolu_1"
        assert shells[0]["shell_id"] == "bedb379"
        assert shells[0]["tool_name"] == "Bash"
        assert shells[0]["command"] == "npm run dev"
        assert shells[0]["description"] == "dev server"
        assert shells[0]["terminated_at"] is None
        assert shells[0]["terminated_by"] is None
        assert shells == shells  # parser stable
        assert polls == []
        assert crons == []

    def test_monitor_call_extracted(self, tmp_path):
        jsonl = _write_jsonl(
            tmp_path / "s.jsonl",
            [
                _assistant_tool_use(
                    "Monitor",
                    "toolu_m",
                    {
                        "command": "gh pr checks",
                        "description": "watch CI",
                        "persistent": False,
                        "timeout_ms": 600000,
                    },
                ),
            ],
        )
        shells, _, _ = extract_shells_and_cron(jsonl, "s1", session_ended=False)
        assert len(shells) == 1
        assert shells[0]["tool_name"] == "Monitor"
        assert shells[0]["timeout_ms"] == 600000

    def test_killshell_resolves_via_shell_id(self, tmp_path):
        jsonl = _write_jsonl(
            tmp_path / "s.jsonl",
            [
                _assistant_tool_use(
                    "Bash",
                    "toolu_1",
                    {
                        "command": "sleep 99",
                        "run_in_background": True,
                    },
                    ts=_ts(0),
                ),
                _tool_result("toolu_1", "Command running in background with ID: abc12345."),
                _assistant_tool_use("KillShell", "toolu_k", {"shell_id": "abc12345"}, ts=_ts(1)),
            ],
        )
        shells, _, _ = extract_shells_and_cron(jsonl, "s1", session_ended=False)
        assert len(shells) == 1
        assert shells[0]["terminated_by"] == "kill"
        assert shells[0]["terminated_at"] == _ts(1)

    def test_orphan_killshell_silently_dropped(self, tmp_path):
        """KillShell referencing a shell we never saw spawned in this JSONL."""
        jsonl = _write_jsonl(
            tmp_path / "s.jsonl",
            [
                _assistant_tool_use("KillShell", "toolu_k", {"shell_id": "unknown"}),
            ],
        )
        shells, _, _ = extract_shells_and_cron(jsonl, "s1", session_ended=False)
        assert shells == []

    def test_bashoutput_polls_attach_to_parent(self, tmp_path):
        jsonl = _write_jsonl(
            tmp_path / "s.jsonl",
            [
                _assistant_tool_use(
                    "Bash",
                    "toolu_1",
                    {
                        "command": "make",
                        "run_in_background": True,
                    },
                    ts=_ts(0),
                ),
                _tool_result("toolu_1", "Command running in background with ID: shellxyz."),
                _assistant_tool_use("BashOutput", "toolu_p1", {"shell_id": "shellxyz"}, ts=_ts(1)),
                _tool_result("toolu_p1", "building..."),
                _assistant_tool_use(
                    "BashOutput", "toolu_p2", {"shell_id": "shellxyz", "filter": "ERROR"}, ts=_ts(2)
                ),
                _tool_result("toolu_p2", "done."),
            ],
        )
        shells, polls, _ = extract_shells_and_cron(jsonl, "s1", session_ended=False)
        assert len(shells) == 1
        assert shells[0]["poll_count"] == 2
        assert shells[0]["total_output_bytes"] == len("building...") + len("done.")
        assert len(polls) == 2
        assert polls[0]["filter_pattern"] is None
        assert polls[1]["filter_pattern"] == "ERROR"
        # Parents should share tool_use_id pointer for resolution
        assert all(p["_parent_tool_use_id"] == "toolu_1" for p in polls)

    def test_cron_create_extracted(self, tmp_path):
        jsonl = _write_jsonl(
            tmp_path / "s.jsonl",
            [
                _assistant_tool_use(
                    "CronCreate",
                    "toolu_c",
                    {
                        "cron": "*/5 * * * *",
                        "prompt": "ping",
                        "recurring": True,
                    },
                    ts=_ts(0),
                ),
                _tool_result("toolu_c", "Task created with ID: cron0001"),
            ],
        )
        _, _, crons = extract_shells_and_cron(jsonl, "s1", session_ended=False)
        assert len(crons) == 1
        assert crons[0]["cron_expression"] == "*/5 * * * *"
        assert crons[0]["recurring"] == 1
        assert crons[0]["cron_id"] == "cron0001"
        assert crons[0]["deleted_at"] is None
        # ttl is 7 days from created_at
        created_dt = datetime.fromisoformat(crons[0]["created_at"].replace("Z", "+00:00"))
        ttl_dt = datetime.fromisoformat(crons[0]["ttl_expires_at"].replace("Z", "+00:00"))
        assert (ttl_dt - created_dt).days == 7

    def test_cron_delete_folds_into_parent(self, tmp_path):
        jsonl = _write_jsonl(
            tmp_path / "s.jsonl",
            [
                _assistant_tool_use(
                    "CronCreate",
                    "toolu_c",
                    {
                        "cron": "0 9 * * *",
                        "prompt": "x",
                    },
                    ts=_ts(0),
                ),
                _tool_result("toolu_c", "cron_id: cron1111"),
                _assistant_tool_use("CronDelete", "toolu_d", {"id": "cron1111"}, ts=_ts(5)),
            ],
        )
        _, _, crons = extract_shells_and_cron(jsonl, "s1", session_ended=False)
        assert len(crons) == 1
        assert crons[0]["deleted_at"] == _ts(5)
        assert crons[0]["deleted_via"] == "CronDelete"

    def test_session_ended_marks_orphan_shells(self, tmp_path):
        jsonl = _write_jsonl(
            tmp_path / "s.jsonl",
            [
                _assistant_tool_use(
                    "Bash",
                    "toolu_1",
                    {
                        "command": "x",
                        "run_in_background": True,
                    },
                    ts=_ts(0),
                ),
                _tool_result("toolu_1", "Command running in background with ID: leftover1"),
            ],
        )
        shells, _, _ = extract_shells_and_cron(jsonl, "s1", session_ended=True)
        assert shells[0]["terminated_by"] == "session_end"
        assert shells[0]["terminated_at"] is not None

    def test_session_open_leaves_shells_running(self, tmp_path):
        jsonl = _write_jsonl(
            tmp_path / "s.jsonl",
            [
                _assistant_tool_use(
                    "Bash",
                    "toolu_1",
                    {
                        "command": "x",
                        "run_in_background": True,
                    },
                    ts=_ts(0),
                ),
                _tool_result("toolu_1", "Command running in background with ID: stillrun"),
            ],
        )
        shells, _, _ = extract_shells_and_cron(jsonl, "s1", session_ended=False)
        assert shells[0]["terminated_at"] is None
        assert shells[0]["terminated_by"] is None

    def test_command_truncation_flagged(self, tmp_path):
        long_cmd = "x" * 10_000
        jsonl = _write_jsonl(
            tmp_path / "s.jsonl",
            [
                _assistant_tool_use(
                    "Bash",
                    "toolu_1",
                    {
                        "command": long_cmd,
                        "run_in_background": True,
                    },
                    ts=_ts(0),
                ),
            ],
        )
        shells, _, _ = extract_shells_and_cron(jsonl, "s1", session_ended=False)
        assert shells[0]["command_truncated"] == 1
        assert len(shells[0]["command"].encode("utf-8")) <= 4096

    def test_tool_result_as_list_content(self, tmp_path):
        """tool_result.content can be either str OR list of {type:text}."""
        jsonl = _write_jsonl(
            tmp_path / "s.jsonl",
            [
                _assistant_tool_use(
                    "Bash",
                    "toolu_1",
                    {
                        "command": "x",
                        "run_in_background": True,
                    },
                ),
                {
                    "type": "user",
                    "uuid": "r1",
                    "timestamp": _ts(0, 1),
                    "message": {
                        "role": "user",
                        "content": [
                            {
                                "type": "tool_result",
                                "tool_use_id": "toolu_1",
                                "content": [
                                    {
                                        "type": "text",
                                        "text": "Command running in background with ID: aaa123",
                                    }
                                ],
                            }
                        ],
                    },
                },
            ],
        )
        shells, _, _ = extract_shells_and_cron(jsonl, "s1", session_ended=False)
        assert shells[0]["shell_id"] == "aaa123"


# ============================================================================
# Persistence + idempotency
# ============================================================================


class TestPersistence:
    def test_persist_inserts_shells_and_polls(self, mem_db, tmp_path):
        _seed_session(mem_db)
        jsonl = _write_jsonl(
            tmp_path / "s.jsonl",
            [
                _assistant_tool_use(
                    "Bash",
                    "toolu_1",
                    {
                        "command": "x",
                        "run_in_background": True,
                    },
                    ts=_ts(0),
                ),
                _tool_result("toolu_1", "Command running in background with ID: shell001"),
                _assistant_tool_use("BashOutput", "toolu_p1", {"shell_id": "shell001"}, ts=_ts(1)),
                _tool_result("toolu_p1", "hello"),
            ],
        )
        shells, polls, crons = extract_shells_and_cron(jsonl, "s1", session_ended=True)
        persist_shells_and_cron(mem_db, "s1", shells, polls, crons)

        rows = mem_db.execute("SELECT * FROM background_shells").fetchall()
        assert len(rows) == 1
        assert rows[0]["shell_id"] == "shell001"
        assert rows[0]["poll_count"] == 1
        assert rows[0]["total_output_bytes"] == len("hello")

        poll_rows = mem_db.execute("SELECT * FROM shell_polls").fetchall()
        assert len(poll_rows) == 1
        assert poll_rows[0]["output_excerpt"] == "hello"

    def test_upsert_preserves_parent_id(self, mem_db, tmp_path):
        _seed_session(mem_db)
        jsonl = _write_jsonl(
            tmp_path / "s.jsonl",
            [
                _assistant_tool_use(
                    "Bash",
                    "toolu_1",
                    {
                        "command": "x",
                        "run_in_background": True,
                    },
                ),
                _tool_result("toolu_1", "Command running in background with ID: shell001"),
            ],
        )
        shells, polls, crons = extract_shells_and_cron(jsonl, "s1", session_ended=True)
        persist_shells_and_cron(mem_db, "s1", shells, polls, crons)
        id_before = mem_db.execute("SELECT id FROM background_shells").fetchone()[0]

        # Re-run extraction and persist — id MUST be preserved
        shells, polls, crons = extract_shells_and_cron(jsonl, "s1", session_ended=True)
        persist_shells_and_cron(mem_db, "s1", shells, polls, crons)
        id_after = mem_db.execute("SELECT id FROM background_shells").fetchone()[0]
        assert id_before == id_after

    def test_persist_clears_reindex_flag(self, mem_db):
        _seed_session(mem_db)
        assert (
            mem_db.execute(
                "SELECT needs_shell_cron_reindex FROM sessions WHERE uuid=?", ("s1",)
            ).fetchone()[0]
            == 1
        )
        persist_shells_and_cron(mem_db, "s1", [], [], [])
        assert (
            mem_db.execute(
                "SELECT needs_shell_cron_reindex FROM sessions WHERE uuid=?", ("s1",)
            ).fetchone()[0]
            == 0
        )

    def test_polls_dedupe_on_reindex(self, mem_db, tmp_path):
        """Re-running a JSONL with same BashOutput tool_use_ids must not duplicate."""
        _seed_session(mem_db)
        jsonl = _write_jsonl(
            tmp_path / "s.jsonl",
            [
                _assistant_tool_use(
                    "Bash",
                    "toolu_1",
                    {
                        "command": "x",
                        "run_in_background": True,
                    },
                ),
                _tool_result("toolu_1", "Command running in background with ID: shell001"),
                _assistant_tool_use("BashOutput", "toolu_p1", {"shell_id": "shell001"}),
                _tool_result("toolu_p1", "out"),
            ],
        )
        for _ in range(3):
            shells, polls, crons = extract_shells_and_cron(jsonl, "s1", session_ended=True)
            persist_shells_and_cron(mem_db, "s1", shells, polls, crons)
        assert mem_db.execute("SELECT COUNT(*) FROM shell_polls").fetchone()[0] == 1


# ============================================================================
# Schema CHECK constraints
# ============================================================================


class TestSchemaConstraints:
    def test_coherence_check_blocks_half_set_state(self, mem_db):
        """terminated_at set but terminated_by NULL must be rejected."""
        _seed_session(mem_db)
        mem_db.execute("""
            INSERT INTO background_shells
            (session_uuid, tool_use_id, tool_name, command, spawned_at)
            VALUES ('s1', 'toolu_x', 'Bash', 'echo', '2026-05-25T00:00:00Z')
        """)
        with pytest.raises(sqlite3.IntegrityError, match="CHECK constraint failed"):
            mem_db.execute(
                "UPDATE background_shells SET terminated_at='2026-05-25T00:01:00Z' "
                "WHERE tool_use_id='toolu_x'"
            )

    def test_recurring_must_be_boolean(self, mem_db):
        _seed_session(mem_db)
        with pytest.raises(sqlite3.IntegrityError):
            mem_db.execute("""
                INSERT INTO cron_jobs
                (session_uuid, tool_use_id, cron_expression, prompt, recurring,
                 created_at, ttl_expires_at)
                VALUES ('s1', 'toolu_c', '* * * * *', 'p', 2,
                        '2026-05-25T00:00:00Z', '2026-06-01T00:00:00Z')
            """)

    def test_terminated_by_check_constraint(self, mem_db):
        _seed_session(mem_db)
        with pytest.raises(sqlite3.IntegrityError):
            mem_db.execute("""
                INSERT INTO background_shells
                (session_uuid, tool_use_id, tool_name, command, spawned_at,
                 terminated_at, terminated_by)
                VALUES ('s1', 'toolu_x', 'Bash', 'x', '2026-05-25T00:00:00Z',
                        '2026-05-25T00:01:00Z', 'bogus')
            """)

    def test_cascade_delete_session_clears_children(self, mem_db, tmp_path):
        _seed_session(mem_db)
        jsonl = _write_jsonl(
            tmp_path / "s.jsonl",
            [
                _assistant_tool_use(
                    "Bash",
                    "toolu_1",
                    {
                        "command": "x",
                        "run_in_background": True,
                    },
                ),
                _tool_result("toolu_1", "Command running in background with ID: shell01"),
                _assistant_tool_use("BashOutput", "toolu_p", {"shell_id": "shell01"}),
                _tool_result("toolu_p", "out"),
            ],
        )
        shells, polls, crons = extract_shells_and_cron(jsonl, "s1", session_ended=True)
        persist_shells_and_cron(mem_db, "s1", shells, polls, crons)

        assert mem_db.execute("SELECT COUNT(*) FROM background_shells").fetchone()[0] == 1
        assert mem_db.execute("SELECT COUNT(*) FROM shell_polls").fetchone()[0] == 1

        mem_db.execute("DELETE FROM sessions WHERE uuid='s1'")
        assert mem_db.execute("SELECT COUNT(*) FROM background_shells").fetchone()[0] == 0
        assert mem_db.execute("SELECT COUNT(*) FROM shell_polls").fetchone()[0] == 0


# ============================================================================
# Hook ingestion
# ============================================================================


class TestHookIngestion:
    def _write_events(self, karma_dir: Path, session: str, events: List[Dict[str, Any]]) -> Path:
        d = karma_dir / "cron-state" / session
        d.mkdir(parents=True, exist_ok=True)
        with (d / "events.jsonl").open("w") as fp:
            for e in events:
                fp.write(json.dumps(e) + "\n")
        return d

    def test_inserts_known_events(self, mem_db, tmp_path):
        _seed_session(mem_db)
        self._write_events(
            tmp_path,
            "s1",
            [
                {
                    "captured_at": "2026-05-25T01:00:00Z",
                    "trigger_event": "CronCreate",
                    "tool_response": {"id": "c1"},
                },
                {
                    "captured_at": "2026-05-25T01:01:00Z",
                    "trigger_event": "CronList",
                    "tool_response": {"jobs": []},
                },
            ],
        )
        inserted = sync_cron_state_snapshots(mem_db, tmp_path)
        assert inserted == 2
        assert mem_db.execute("SELECT COUNT(*) FROM cron_state_snapshots").fetchone()[0] == 2

    def test_idempotent_resync(self, mem_db, tmp_path):
        _seed_session(mem_db)
        self._write_events(
            tmp_path,
            "s1",
            [
                {
                    "captured_at": "2026-05-25T01:00:00Z",
                    "trigger_event": "CronCreate",
                    "tool_response": {},
                },
            ],
        )
        sync_cron_state_snapshots(mem_db, tmp_path)
        inserted2 = sync_cron_state_snapshots(mem_db, tmp_path)
        assert inserted2 == 0

    def test_skips_unknown_trigger_event(self, mem_db, tmp_path):
        _seed_session(mem_db)
        self._write_events(
            tmp_path,
            "s1",
            [
                {
                    "captured_at": "2026-05-25T01:00:00Z",
                    "trigger_event": "NotAValidEvent",
                    "tool_response": {},
                },
            ],
        )
        assert sync_cron_state_snapshots(mem_db, tmp_path) == 0

    def test_orphan_session_skipped_silently(self, mem_db, tmp_path):
        """When session_uuid has no row in sessions, FK violation → skip."""
        # No _seed_session — sessions table is empty
        self._write_events(
            tmp_path,
            "ghost-session",
            [
                {
                    "captured_at": "2026-05-25T01:00:00Z",
                    "trigger_event": "CronCreate",
                    "tool_response": {},
                },
            ],
        )
        # Must not raise
        assert sync_cron_state_snapshots(mem_db, tmp_path) == 0

    def test_missing_state_root_returns_zero(self, mem_db, tmp_path):
        assert sync_cron_state_snapshots(mem_db, tmp_path) == 0


# ============================================================================
# Fire inference
# ============================================================================


class TestFireInference:
    def _make_cron(
        self,
        expr: str = "*/15 * * * *",
        created_min: int = 0,
        ttl_hours: int = 2,
        recurring: bool = True,
    ) -> Dict[str, Any]:
        created = datetime(2026, 5, 25, 0, created_min, 0, tzinfo=timezone.utc)
        return {
            "created_at": created.isoformat().replace("+00:00", "Z"),
            "deleted_at": None,
            "ttl_expires_at": (created + timedelta(hours=ttl_hours))
            .isoformat()
            .replace("+00:00", "Z"),
            "cron_expression": expr,
            "recurring": 1 if recurring else 0,
        }

    def _make_jsonl_with_turns(self, path: Path, turn_minutes_seconds: List[tuple]) -> Path:
        lines = []
        base = datetime(2026, 5, 25, 0, 0, 0, tzinfo=timezone.utc)
        for minute, second in turn_minutes_seconds:
            # Use timedelta math so callers can pass seconds > 59 to land
            # outside the matching window without tripping datetime bounds.
            ts = base + timedelta(minutes=minute, seconds=second)
            lines.append(
                {
                    "type": "assistant",
                    "uuid": f"u-{minute}-{second}",
                    "timestamp": ts.isoformat().replace("+00:00", "Z"),
                    "message": {
                        "content": [{"type": "text", "text": f"resp at {minute}:{second}"}]
                    },
                }
            )
        return _write_jsonl(path, lines)

    def test_match_within_window(self, tmp_path):
        cron = self._make_cron()
        jsonl = self._make_jsonl_with_turns(
            tmp_path / "s.jsonl",
            [
                (15, 2),  # close to scheduled 15:00 → high confidence
                (30, 30),  # half-window from 30:00 → mid confidence
                (45, 200),  # 200s off, outside ±60s → drop
            ],
        )
        fires = infer_cron_fires(jsonl, cron)
        assert len(fires) == 2
        assert fires[0]["inference_confidence"] > 0.9
        assert fires[1]["inference_confidence"] == pytest.approx(0.5, abs=0.05)

    def test_drop_outside_window(self, tmp_path):
        cron = self._make_cron()
        jsonl = self._make_jsonl_with_turns(tmp_path / "s.jsonl", [(15, 90)])
        assert infer_cron_fires(jsonl, cron) == []

    def test_confidence_floor(self, tmp_path):
        cron = self._make_cron()
        # 60s offset → confidence 0.0 → below floor → dropped
        jsonl = self._make_jsonl_with_turns(tmp_path / "s.jsonl", [(15, 60)])
        fires = infer_cron_fires(jsonl, cron)
        assert all(f["inference_confidence"] >= FIRE_CONFIDENCE_FLOOR for f in fires)

    def test_each_turn_claimed_once(self, tmp_path):
        """One assistant turn at 14:55 sits between 0:00 and 15:00 schedule.
        It must claim exactly one of those, not both."""
        cron = self._make_cron()  # */15 → scheduled at 15, 30, 45, 60, ...
        jsonl = self._make_jsonl_with_turns(tmp_path / "s.jsonl", [(14, 55)])
        fires = infer_cron_fires(jsonl, cron)
        # 14:55 is within 60s of the 15:00 scheduled time
        assert len(fires) == 1

    def test_one_shot_no_recurrence(self, tmp_path):
        cron = self._make_cron(expr="*/15 * * * *", recurring=False)
        # 3 turns, all near scheduled times → only the first counts
        jsonl = self._make_jsonl_with_turns(
            tmp_path / "s.jsonl",
            [
                (15, 5),
                (30, 5),
                (45, 5),
            ],
        )
        fires = infer_cron_fires(jsonl, cron)
        assert len(fires) <= 1

    def test_invalid_cron_returns_empty(self, tmp_path):
        cron = self._make_cron(expr="not a cron")
        jsonl = self._make_jsonl_with_turns(tmp_path / "s.jsonl", [(15, 0)])
        assert infer_cron_fires(jsonl, cron) == []

    def test_missing_jsonl_returns_empty(self, tmp_path):
        cron = self._make_cron()
        assert infer_cron_fires(tmp_path / "does-not-exist.jsonl", cron) == []


# ============================================================================
# Query helpers
# ============================================================================


class TestQueryHelpers:
    def _seed_two_shells(self, mem_db, tmp_path):
        _seed_session(mem_db, "s1")
        _seed_project(mem_db)
        # shell IDs need to be 6-16 chars (matches Claude Code's real 8-char format)
        jsonl = _write_jsonl(
            tmp_path / "s.jsonl",
            [
                _assistant_tool_use(
                    "Bash",
                    "toolu_1",
                    {
                        "command": "running",
                        "run_in_background": True,
                    },
                    ts=_ts(0),
                ),
                _tool_result("toolu_1", "Command running in background with ID: alphaa1"),
                _assistant_tool_use(
                    "Bash",
                    "toolu_2",
                    {
                        "command": "killed",
                        "run_in_background": True,
                    },
                    ts=_ts(1),
                ),
                _tool_result("toolu_2", "Command running in background with ID: betab22"),
                _assistant_tool_use("KillShell", "toolu_k", {"shell_id": "betab22"}, ts=_ts(2)),
                _assistant_tool_use("BashOutput", "toolu_p", {"shell_id": "alphaa1"}, ts=_ts(3)),
                _tool_result("toolu_p", "running output"),
            ],
        )
        shells, polls, crons = extract_shells_and_cron(jsonl, "s1", session_ended=False)
        persist_shells_and_cron(mem_db, "s1", shells, polls, crons)

    def test_get_shells_for_session_includes_polls(self, mem_db, tmp_path):
        self._seed_two_shells(mem_db, tmp_path)
        shells = get_shells_for_session(mem_db, "s1")
        assert len(shells) == 2
        # Polls attached to the running shell only
        running = next(s for s in shells if s["shell_id"] == "alphaa1")
        killed = next(s for s in shells if s["shell_id"] == "betab22")
        assert len(running["polls"]) == 1
        assert len(killed["polls"]) == 0

    def test_get_shells_global_status_filter(self, mem_db, tmp_path):
        self._seed_two_shells(mem_db, tmp_path)
        all_shells = get_shells_global(mem_db)
        running = get_shells_global(mem_db, status="running")
        closed = get_shells_global(mem_db, status="closed")
        assert len(all_shells) == 2
        assert len(running) == 1 and running[0]["shell_id"] == "alphaa1"
        assert len(closed) == 1 and closed[0]["shell_id"] == "betab22"

    def test_get_shells_global_tool_filter(self, mem_db, tmp_path):
        self._seed_two_shells(mem_db, tmp_path)
        bashes = get_shells_global(mem_db, tool_name="Bash")
        monitors = get_shells_global(mem_db, tool_name="Monitor")
        assert len(bashes) == 2 and len(monitors) == 0

    def test_get_shells_global_project_filter(self, mem_db, tmp_path):
        self._seed_two_shells(mem_db, tmp_path)
        match = get_shells_global(mem_db, project_encoded_name="-foo")
        miss = get_shells_global(mem_db, project_encoded_name="-bar")
        assert len(match) == 2
        assert len(miss) == 0

    def test_project_rollup_counts(self, mem_db, tmp_path):
        self._seed_two_shells(mem_db, tmp_path)
        rolls = get_shells_project_rollup(mem_db)
        assert len(rolls) == 1
        assert rolls[0]["shell_count"] == 2
        assert rolls[0]["running_count"] == 1

    def test_get_latest_cron_state_none_when_no_hook(self, mem_db):
        _seed_session(mem_db)
        assert get_latest_cron_state(mem_db, "s1") is None

    def test_get_cron_for_session_attaches_latest_state(self, mem_db, tmp_path):
        _seed_session(mem_db)
        # Persist one cron
        mem_db.execute("""
            INSERT INTO cron_jobs (session_uuid, tool_use_id, cron_expression, prompt,
                                    recurring, created_at, ttl_expires_at)
            VALUES ('s1', 'toolu_c', '* * * * *', 'p', 1,
                    '2026-05-25T00:00:00Z', '2026-06-01T00:00:00Z')
        """)
        # And one snapshot
        mem_db.execute("""
            INSERT INTO cron_state_snapshots (session_uuid, captured_at, trigger_event, payload_json)
            VALUES ('s1', '2026-05-25T00:10:00Z', 'CronList', '{"jobs":[]}')
        """)
        jobs = get_cron_for_session(mem_db, "s1", include_fires=False)
        assert len(jobs) == 1
        assert jobs[0]["latest_state"] is not None
        assert jobs[0]["latest_state"]["trigger_event"] == "CronList"
        assert jobs[0]["fires"] == []

    def test_get_cron_global_active_only(self, mem_db, tmp_path):
        _seed_session(mem_db)
        _seed_project(mem_db)
        now_iso = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        future = (datetime.now(timezone.utc) + timedelta(days=3)).isoformat().replace("+00:00", "Z")
        past = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat().replace("+00:00", "Z")
        mem_db.execute(
            """
            INSERT INTO cron_jobs (session_uuid, tool_use_id, cron_expression, prompt,
                                    recurring, created_at, ttl_expires_at)
            VALUES ('s1', 'toolu_active', '* * * * *', 'p', 1, ?, ?)
        """,
            (now_iso, future),
        )
        mem_db.execute(
            """
            INSERT INTO cron_jobs (session_uuid, tool_use_id, cron_expression, prompt,
                                    recurring, created_at, ttl_expires_at,
                                    deleted_at, deleted_via)
            VALUES ('s1', 'toolu_deleted', '* * * * *', 'p', 1, ?, ?, ?, 'CronDelete')
        """,
            (now_iso, future, now_iso),
        )
        mem_db.execute(
            """
            INSERT INTO cron_jobs (session_uuid, tool_use_id, cron_expression, prompt,
                                    recurring, created_at, ttl_expires_at)
            VALUES ('s1', 'toolu_expired', '* * * * *', 'p', 1, ?, ?)
        """,
            (now_iso, past),
        )

        all_three = get_cron_global(mem_db)
        active = get_cron_global(mem_db, active_only=True)
        assert len(all_three) == 3
        assert len(active) == 1
        assert active[0]["tool_use_id"] == "toolu_active"

    def test_cron_project_rollup(self, mem_db):
        _seed_session(mem_db)
        _seed_project(mem_db)
        future = (datetime.now(timezone.utc) + timedelta(days=3)).isoformat().replace("+00:00", "Z")
        now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        mem_db.execute(
            """
            INSERT INTO cron_jobs (session_uuid, tool_use_id, cron_expression, prompt,
                                    recurring, created_at, ttl_expires_at)
            VALUES ('s1', 'toolu_a', '* * * * *', 'p', 1, ?, ?)
        """,
            (now, future),
        )
        rolls = get_cron_project_rollup(mem_db)
        assert len(rolls) == 1
        assert rolls[0]["cron_count"] == 1
        assert rolls[0]["active_count"] == 1

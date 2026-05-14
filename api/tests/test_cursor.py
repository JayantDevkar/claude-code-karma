"""
Tests for the Cursor IDE session integration (api/cursor/ + indexer + service layer).

Covers:
- Path detection (graceful when Cursor not installed)
- Parser correctness on synthetic Cursor data shapes
- Tool registry + MCP re-prefix + file path extraction
- Plan YAML front-matter parsing
- Indexer end-to-end against a synthetic Cursor state.vscdb
- Service-layer helpers (cursor.api) returning correct dict shapes
- Schema v11 migration + idempotency
"""

import json
import sqlite3
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from cursor.bubble import extract_bubble_row
from cursor.composer import extract_meta, get_bubble_headers
from cursor.paths import detect_cursor_install
from cursor.plans import _parse_frontmatter, _parse_plan
from cursor.tools import (
    TOOL_INT_NAME_REGISTRY,
    extract_file_path,
    extract_mcp_server_name,
    extract_tool_call_row,
    is_mcp_tool_call,
    resolve_tool_name,
)


# =============================================================================
# Path detection
# =============================================================================


def test_detect_cursor_install_returns_bool():
    """detect_cursor_install never raises; returns True/False based on disk state."""
    result = detect_cursor_install()
    assert isinstance(result, bool)


def test_detect_cursor_install_false_when_missing(tmp_path, monkeypatch):
    """When the global DB path doesn't exist, returns False."""
    monkeypatch.setenv("HOME", str(tmp_path))
    with patch("cursor.paths.cursor_global_db_path") as mock_path:
        mock_path.return_value = tmp_path / "nonexistent.db"
        assert detect_cursor_install() is False


# =============================================================================
# Composer parsing
# =============================================================================


def test_extract_meta_minimal_composer():
    """A composer with only the required-ish fields produces a clean meta row."""
    composer = {
        "composerId": "abc-123",
        "name": "Test session",
        "unifiedMode": "agent",
        "modelConfig": {"modelName": "claude-4.5-opus"},
        "contextTokensUsed": 1500,
        "createdOnBranch": "main",
    }
    meta = extract_meta("abc-123", composer)
    assert meta["session_uuid"] == "abc-123"
    assert meta["unified_mode"] == "agent"
    assert meta["model_name"] == "claude-4.5-opus"
    assert meta["context_tokens_used"] == 1500
    assert meta["name"] == "Test session"
    assert meta["created_on_branch"] == "main"
    assert meta["is_agentic"] == 0  # absent boolean defaults to 0


def test_extract_meta_handles_missing_fields():
    """Composer with NO known fields still produces a valid row (no crashes)."""
    meta = extract_meta("xyz", {})
    assert meta["session_uuid"] == "xyz"
    assert meta["unified_mode"] is None
    assert meta["model_name"] is None
    assert meta["context_tokens_used"] is None
    assert meta["referenced_plans_json"] is None
    assert meta["todos_json"] is None


def test_extract_meta_serializes_lists_to_json():
    composer = {
        "composerId": "id1",
        "subComposerIds": ["sub-1", "sub-2"],
        "subagentComposerIds": ["sub-3"],
        "todos": [{"content": "do this", "status": "pending"}],
    }
    meta = extract_meta("id1", composer)
    parsed = json.loads(meta["sub_composer_ids_json"])
    assert parsed == ["sub-1", "sub-2", "sub-3"]
    assert json.loads(meta["todos_json"]) == [
        {"content": "do this", "status": "pending"}
    ]


def test_get_bubble_headers_returns_list():
    composer = {"fullConversationHeadersOnly": [{"bubbleId": "b1", "type": 1}]}
    headers = get_bubble_headers(composer)
    assert headers == [{"bubbleId": "b1", "type": 1}]


def test_get_bubble_headers_missing_field():
    assert get_bubble_headers({}) == []


# =============================================================================
# Bubble parsing
# =============================================================================


def test_extract_bubble_row_user_message():
    header = {"bubbleId": "bub-1", "type": 1}
    bubble = {"text": "hello world", "createdAt": "2026-03-12T10:30:00Z"}
    row = extract_bubble_row("comp-1", 0, header, bubble)
    assert row["session_uuid"] == "comp-1"
    assert row["bubble_id"] == "bub-1"
    assert row["bubble_type"] == 1
    assert row["text_full"] == "hello world"
    assert row["text_preview"] == "hello world"
    assert row["has_thinking"] == 0
    assert row["has_tool_call"] == 0
    assert row["created_at_ms"] is not None


def test_extract_bubble_row_assistant_with_thinking():
    header = {"bubbleId": "bub-2", "type": 2}
    bubble = {
        "text": "Let me look at this.",
        "capabilityType": 30,
        "thinking": {"text": "I need to check the file", "type": "extended"},
        "thinkingDurationMs": 12345,
    }
    row = extract_bubble_row("comp-1", 1, header, bubble)
    assert row["bubble_type"] == 2
    assert row["capability_type"] == 30
    assert row["has_thinking"] == 1
    assert row["thinking_duration_ms"] == 12345


def test_extract_bubble_row_assistant_with_tool_call():
    header = {"bubbleId": "bub-3", "type": 2}
    bubble = {
        "text": "",
        "capabilityType": 15,
        "toolFormerData": {
            "tool": 40,
            "name": "read_file_v2",
            "rawArgs": '{"path": "/tmp/x"}',
            "result": '{"contents": "..."}',
            "status": "completed",
        },
    }
    row = extract_bubble_row("comp-1", 2, header, bubble)
    assert row["has_tool_call"] == 1
    assert row["capability_type"] == 15
    # Result + rawArgs are stripped from raw_json (we capture them in cursor_tool_call)
    parsed = json.loads(row["raw_json"])
    assert "result" not in parsed["toolFormerData"]
    assert "rawArgs" not in parsed["toolFormerData"]
    # But the lean metadata stays
    assert parsed["toolFormerData"]["name"] == "read_file_v2"


def test_extract_bubble_row_truncates_preview():
    long_text = "a" * 500
    row = extract_bubble_row(
        "c", 0, {"bubbleId": "b", "type": 1}, {"text": long_text}
    )
    assert len(row["text_preview"]) == 200
    assert row["text_full"] == long_text


# =============================================================================
# Tool registry + extraction
# =============================================================================


def test_tool_registry_known_ints():
    """The validated registry has at least the core tool ints we use."""
    assert TOOL_INT_NAME_REGISTRY[40] == "read_file_v2"
    assert TOOL_INT_NAME_REGISTRY[15] == "run_terminal_command_v2"
    assert TOOL_INT_NAME_REGISTRY[42] == "glob_file_search"


def test_resolve_tool_name_prefers_explicit_name():
    bubble = {"toolFormerData": {"tool": 999, "name": "my_tool"}}
    assert resolve_tool_name(bubble) == "my_tool"


def test_resolve_tool_name_falls_back_to_int():
    bubble = {"toolFormerData": {"tool": 40}}
    assert resolve_tool_name(bubble) == "read_file_v2"


def test_resolve_tool_name_unknown_int():
    """Unknown ints get `tool_<N>` as a safe placeholder."""
    bubble = {"toolFormerData": {"tool": 999}}
    assert resolve_tool_name(bubble) == "tool_999"


def test_resolve_tool_name_no_tool_call():
    assert resolve_tool_name({"text": "no tool here"}) is None


def test_is_mcp_tool_call_detects_tool_19():
    assert is_mcp_tool_call({"toolFormerData": {"tool": 19}}) is True
    assert is_mcp_tool_call({"toolFormerData": {"tool": 40}}) is False
    assert is_mcp_tool_call({}) is False


def test_extract_mcp_server_name_from_raw_args():
    bubble = {
        "toolFormerData": {
            "tool": 19,
            "rawArgs": '{"serverName": "coderoots", "name": "query"}',
        }
    }
    assert extract_mcp_server_name(bubble) == "coderoots"


def test_extract_mcp_server_name_handles_malformed_args():
    bubble = {"toolFormerData": {"tool": 19, "rawArgs": "not json"}}
    assert extract_mcp_server_name(bubble) is None


def test_extract_tool_call_row_re_prefixes_mcp():
    """MCP tool calls (tool=19) get rewritten as mcp__{server}__{tool}."""
    bubble = {
        "toolFormerData": {
            "tool": 19,
            "name": "query",
            "rawArgs": '{"serverName": "coderoots"}',
            "result": '{"ok": true}',
            "status": "completed",
            "toolCallId": "toolu_x",
        }
    }
    row = extract_tool_call_row("c1", "b1", bubble)
    assert row["tool_name"] == "mcp__coderoots__query"
    assert row["tool_int"] == 19
    assert row["tool_call_id"] == "toolu_x"


def test_extract_tool_call_row_keeps_native_name():
    bubble = {
        "toolFormerData": {
            "tool": 40,
            "name": "read_file_v2",
            "rawArgs": '{"path": "/tmp/x"}',
            "status": "completed",
        }
    }
    row = extract_tool_call_row("c1", "b1", bubble)
    assert row["tool_name"] == "read_file_v2"


def test_extract_tool_call_row_returns_none_for_no_tool():
    assert extract_tool_call_row("c1", "b1", {"text": "hi"}) is None


def test_extract_file_path_path_key():
    assert extract_file_path("read_file_v2", '{"path": "/x/y.py"}') == "/x/y.py"


def test_extract_file_path_file_path_key():
    """Edit-family tools use file_path, not path."""
    assert extract_file_path("edit_file", '{"file_path": "/a/b.py"}') == "/a/b.py"


def test_extract_file_path_target_file_key():
    assert (
        extract_file_path("read_file", '{"target_file": "/legacy/path"}')
        == "/legacy/path"
    )


def test_extract_file_path_missing_key():
    assert extract_file_path("read_file_v2", '{"limit": 100}') is None


def test_extract_file_path_malformed_json():
    assert extract_file_path("read_file_v2", "not json") is None


# =============================================================================
# Plan parsing
# =============================================================================


def test_parse_frontmatter_yaml_when_pyyaml_available():
    text = """name: Test Plan
overview: a quick test
todos:
  - id: t1
    content: first todo
    status: pending
"""
    parsed = _parse_frontmatter(text)
    assert parsed["name"] == "Test Plan"
    assert parsed["overview"] == "a quick test"
    assert isinstance(parsed["todos"], list)
    assert parsed["todos"][0]["id"] == "t1"


def test_parse_plan_full_file(tmp_path):
    """End-to-end: parse a .plan.md file with front-matter + body."""
    plan_path = tmp_path / "my_test_plan_01234567.plan.md"
    plan_path.write_text(
        "---\n"
        "name: My Test Plan\n"
        "overview: test overview\n"
        "---\n\n"
        "# Body Heading\n\nThis is the plan body.\n",
        encoding="utf-8",
    )
    plan = _parse_plan(plan_path)
    assert plan is not None
    assert plan.slug == "my_test_plan"
    assert plan.plan_id == "01234567"
    assert plan.name == "My Test Plan"
    assert plan.overview == "test overview"
    assert "Body Heading" in plan.body_md
    assert plan.file_mtime_ms > 0


def test_parse_plan_without_frontmatter(tmp_path):
    plan_path = tmp_path / "no_fm_aabbccdd.plan.md"
    plan_path.write_text("# Just a heading\n\nNo frontmatter.\n", encoding="utf-8")
    plan = _parse_plan(plan_path)
    assert plan is not None
    assert plan.name is None
    assert plan.overview is None
    assert "Just a heading" in plan.body_md


# =============================================================================
# Schema v11 migration
# =============================================================================


def _v10_seed_schema(conn: sqlite3.Connection) -> None:
    """Create a v10-shaped schema (sessions + session_tools 2-tuple PK)."""
    conn.executescript("""
        CREATE TABLE schema_version (
            version INTEGER PRIMARY KEY,
            applied_at TEXT DEFAULT (datetime('now'))
        );
        INSERT INTO schema_version (version) VALUES (10);
        CREATE TABLE sessions (
            uuid TEXT PRIMARY KEY,
            slug TEXT,
            project_encoded_name TEXT NOT NULL,
            project_path TEXT,
            jsonl_mtime REAL NOT NULL,
            jsonl_size INTEGER DEFAULT 0,
            session_source TEXT,
            source_encoded_name TEXT,
            indexed_at TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE session_tools (
            session_uuid TEXT NOT NULL,
            tool_name TEXT NOT NULL,
            count INTEGER DEFAULT 1,
            PRIMARY KEY (session_uuid, tool_name)
        );
        CREATE TABLE session_skills (
            session_uuid TEXT NOT NULL,
            skill_name TEXT NOT NULL,
            invocation_source TEXT NOT NULL DEFAULT 'skill_tool',
            count INTEGER DEFAULT 1,
            PRIMARY KEY (session_uuid, skill_name, invocation_source)
        );
        CREATE TABLE session_commands (
            session_uuid TEXT NOT NULL,
            command_name TEXT NOT NULL,
            invocation_source TEXT NOT NULL DEFAULT 'slash_command',
            count INTEGER DEFAULT 1,
            PRIMARY KEY (session_uuid, command_name, invocation_source)
        );
        CREATE TABLE subagent_skills (
            invocation_id INTEGER NOT NULL,
            skill_name TEXT NOT NULL,
            invocation_source TEXT NOT NULL DEFAULT 'skill_tool',
            count INTEGER DEFAULT 1,
            PRIMARY KEY (invocation_id, skill_name, invocation_source)
        );
        CREATE TABLE subagent_commands (
            invocation_id INTEGER NOT NULL,
            command_name TEXT NOT NULL,
            invocation_source TEXT NOT NULL DEFAULT 'slash_command',
            count INTEGER DEFAULT 1,
            PRIMARY KEY (invocation_id, command_name, invocation_source)
        );
    """)


def test_v11_migration_adds_cursor_tables():
    """Migrating from v10 → v11 creates all 6 Cursor tables."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    _v10_seed_schema(conn)

    from db.schema import ensure_schema

    ensure_schema(conn)

    cursor_tables = {
        row[0]
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'cursor_%'"
        )
    }
    assert cursor_tables == {
        "cursor_session_meta",
        "cursor_bubble",
        "cursor_tool_call",
        "cursor_plan",
        "cursor_mcp_server",
        "cursor_mcp_tool",
    }


def test_v11_migration_rebuilds_session_tools_pk():
    """After migration, session_tools has the 3-tuple PK including invocation_source."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    _v10_seed_schema(conn)

    from db.schema import ensure_schema

    ensure_schema(conn)
    cols = [(c[1], c[5]) for c in conn.execute("PRAGMA table_info(session_tools)")]
    assert ("session_uuid", 1) in cols
    assert ("tool_name", 2) in cols
    assert ("invocation_source", 3) in cols


def test_v11_migration_adds_cursor_workspace_hash_to_sessions():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    _v10_seed_schema(conn)

    from db.schema import ensure_schema

    ensure_schema(conn)
    cols = {c[1] for c in conn.execute("PRAGMA table_info(sessions)")}
    assert "cursor_workspace_hash" in cols


def test_v11_migration_backfills_session_source():
    """Existing NULL session_source rows get backfilled to 'claude_code'."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    _v10_seed_schema(conn)
    conn.execute(
        "INSERT INTO sessions (uuid, project_encoded_name, jsonl_mtime) "
        "VALUES ('u-null', '-Users-me', 1.0)"
    )
    conn.execute(
        "INSERT INTO sessions (uuid, project_encoded_name, jsonl_mtime, session_source) "
        "VALUES ('u-desktop', '-Users-me', 1.0, 'desktop')"
    )

    from db.schema import ensure_schema

    ensure_schema(conn)
    sources = {
        row[0]: row[1]
        for row in conn.execute(
            "SELECT uuid, session_source FROM sessions ORDER BY uuid"
        )
    }
    assert sources["u-null"] == "claude_code"
    assert sources["u-desktop"] == "desktop"


def test_v11_migration_is_idempotent():
    """Running ensure_schema multiple times after v11 is a no-op."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    _v10_seed_schema(conn)

    from db.schema import ensure_schema

    ensure_schema(conn)
    v1 = conn.execute("SELECT MAX(version) FROM schema_version").fetchone()[0]
    ensure_schema(conn)
    ensure_schema(conn)
    v2 = conn.execute("SELECT MAX(version) FROM schema_version").fetchone()[0]
    assert v1 == v2 == 11


# =============================================================================
# Indexer + service-layer helpers (against synthetic fixture DB)
# =============================================================================


@pytest.fixture
def synthetic_cursor_dbs(tmp_path):
    """
    Build a minimal Cursor storage tree:
    - one global state.vscdb with cursorDiskKV rows for 2 composers
    - one workspaceStorage/<hash>/{workspace.json, state.vscdb}
    Returns (global_db_path, workspace_storage_dir).
    """
    global_db = tmp_path / "state.vscdb"
    ws_root = tmp_path / "workspaceStorage"
    ws_dir = ws_root / "abc123abc123abc1"
    ws_dir.mkdir(parents=True)

    # workspace.json maps hash → folder URI
    (ws_dir / "workspace.json").write_text(
        json.dumps({"folder": f"file://{tmp_path}/repo"}),
        encoding="utf-8",
    )

    # Per-workspace state.vscdb has the composer ID list
    ws_state = ws_dir / "state.vscdb"
    ws_conn = sqlite3.connect(str(ws_state))
    ws_conn.execute(
        "CREATE TABLE ItemTable (key TEXT PRIMARY KEY, value BLOB)"
    )
    ws_conn.execute(
        "INSERT INTO ItemTable (key, value) VALUES (?, ?)",
        (
            "composer.composerData",
            json.dumps(
                {"allComposers": [{"composerId": "comp-1"}, {"composerId": "comp-2"}]}
            ),
        ),
    )
    ws_conn.commit()
    ws_conn.close()

    # Global state.vscdb has the actual conversation data
    gconn = sqlite3.connect(str(global_db))
    gconn.execute("CREATE TABLE ItemTable (key TEXT PRIMARY KEY, value BLOB)")
    gconn.execute("CREATE TABLE cursorDiskKV (key TEXT PRIMARY KEY, value BLOB)")

    # Composer 1: 2 bubbles (user + assistant with tool call)
    composer1 = {
        "composerId": "comp-1",
        "name": "First test session",
        "unifiedMode": "agent",
        "modelConfig": {"modelName": "claude-4.5-opus"},
        "createdAt": 1700000000000,
        "lastUpdatedAt": 1700000100000,
        "contextTokensUsed": 500,
        "fullConversationHeadersOnly": [
            {"bubbleId": "bub-1a", "type": 1},
            {"bubbleId": "bub-1b", "type": 2},
        ],
    }
    bubble_1a = {"text": "fix the bug in main.py", "createdAt": "2026-01-01T00:00:00Z"}
    bubble_1b = {
        "text": "",
        "capabilityType": 15,
        "toolFormerData": {
            "tool": 40,
            "name": "read_file_v2",
            "rawArgs": '{"path": "/tmp/main.py"}',
            "result": '{"contents": "..."}',
            "status": "completed",
            "toolCallId": "toolu_a",
        },
    }

    # Composer 2: empty (no bubbles in cursorDiskKV — exercises the "missing bubble" skip path)
    composer2 = {
        "composerId": "comp-2",
        "name": "Empty session",
        "unifiedMode": "chat",
        "createdAt": 1700001000000,
        "lastUpdatedAt": 1700001000000,
        "fullConversationHeadersOnly": [{"bubbleId": "missing", "type": 1}],
    }

    for key, value in (
        ("composerData:comp-1", composer1),
        ("composerData:comp-2", composer2),
        ("bubbleId:comp-1:bub-1a", bubble_1a),
        ("bubbleId:comp-1:bub-1b", bubble_1b),
    ):
        gconn.execute(
            "INSERT INTO cursorDiskKV (key, value) VALUES (?, ?)",
            (key, json.dumps(value)),
        )
    gconn.commit()
    gconn.close()

    return global_db, ws_root


def _run_indexer_with_fixture(synthetic_cursor_dbs, tmp_path):
    """Run the indexer against a synthetic Cursor fixture into a fresh metadata.db."""
    global_db, ws_root = synthetic_cursor_dbs
    metadata_db = tmp_path / "metadata.db"

    from cursor import indexer as cursor_indexer
    from db.schema import ensure_schema

    conn = sqlite3.connect(str(metadata_db))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    ensure_schema(conn)

    with (
        patch("cursor.paths.cursor_global_db_path", return_value=global_db),
        patch("cursor.paths.cursor_workspace_storage_dir", return_value=ws_root),
        patch("cursor.paths.detect_cursor_install", return_value=True),
        patch("cursor.indexer.cursor_global_db_path", return_value=global_db),
        patch("cursor.indexer.detect_cursor_install", return_value=True),
        patch("cursor.workspace.cursor_workspace_storage_dir", return_value=ws_root),
    ):
        stats = cursor_indexer.run_cursor_full_index(conn)
    return conn, stats


def test_indexer_writes_sessions_and_bubbles(synthetic_cursor_dbs, tmp_path):
    conn, stats = _run_indexer_with_fixture(synthetic_cursor_dbs, tmp_path)
    assert stats["composers_total"] == 2
    assert stats["composers_indexed"] == 2
    assert stats["bubbles_written"] == 2  # comp-2 has 1 header but missing bubble row
    assert stats["tool_calls_written"] == 1
    assert stats["errors"] == 0

    cursor_session_count = conn.execute(
        "SELECT COUNT(*) FROM sessions WHERE session_source='cursor'"
    ).fetchone()[0]
    assert cursor_session_count == 2

    # Tools row written with invocation_source='cursor'
    tool_rows = list(
        conn.execute(
            "SELECT tool_name, invocation_source, count FROM session_tools "
            "WHERE invocation_source = 'cursor'"
        )
    )
    assert ("read_file_v2", "cursor", 1) in [tuple(r) for r in tool_rows]


def test_indexer_populates_cursor_session_meta(synthetic_cursor_dbs, tmp_path):
    conn, _ = _run_indexer_with_fixture(synthetic_cursor_dbs, tmp_path)
    meta = conn.execute(
        "SELECT unified_mode, model_name, context_tokens_used, name FROM cursor_session_meta "
        "WHERE session_uuid = 'comp-1'"
    ).fetchone()
    assert meta is not None
    assert meta[0] == "agent"
    assert meta[1] == "claude-4.5-opus"
    assert meta[2] == 500
    assert meta[3] == "First test session"


def test_indexer_writes_tool_call_with_file_path(synthetic_cursor_dbs, tmp_path):
    conn, _ = _run_indexer_with_fixture(synthetic_cursor_dbs, tmp_path)
    row = conn.execute(
        "SELECT tool_name, file_path, tool_int FROM cursor_tool_call "
        "WHERE session_uuid = 'comp-1'"
    ).fetchone()
    assert row[0] == "read_file_v2"
    assert row[1] == "/tmp/main.py"
    assert row[2] == 40


def test_indexer_incremental_skips_unchanged(synthetic_cursor_dbs, tmp_path):
    """Re-running the indexer should skip composers with unchanged lastUpdatedAt."""
    conn, stats1 = _run_indexer_with_fixture(synthetic_cursor_dbs, tmp_path)
    assert stats1["composers_indexed"] == 2

    # Second pass with same fixture
    global_db, ws_root = synthetic_cursor_dbs
    from cursor import indexer as cursor_indexer

    with (
        patch("cursor.paths.cursor_global_db_path", return_value=global_db),
        patch("cursor.paths.cursor_workspace_storage_dir", return_value=ws_root),
        patch("cursor.paths.detect_cursor_install", return_value=True),
        patch("cursor.indexer.cursor_global_db_path", return_value=global_db),
        patch("cursor.indexer.detect_cursor_install", return_value=True),
        patch("cursor.workspace.cursor_workspace_storage_dir", return_value=ws_root),
    ):
        stats2 = cursor_indexer.run_cursor_full_index(conn)
    assert stats2["composers_skipped"] >= 1


# =============================================================================
# cursor.api helpers
# =============================================================================


def test_get_session_source_returns_cursor(synthetic_cursor_dbs, tmp_path):
    conn, _ = _run_indexer_with_fixture(synthetic_cursor_dbs, tmp_path)
    from cursor.api import get_session_source

    assert get_session_source(conn, "comp-1") == "cursor"
    assert get_session_source(conn, "nonexistent") is None


def test_list_cursor_projects_returns_workspace(synthetic_cursor_dbs, tmp_path):
    conn, _ = _run_indexer_with_fixture(synthetic_cursor_dbs, tmp_path)
    from cursor.api import list_cursor_projects

    projects = list_cursor_projects(conn)
    assert len(projects) == 1
    assert projects[0]["encoded_name"].startswith("cursor:")
    assert projects[0]["session_source"] == "cursor"


def test_get_cursor_session_detail_shape(synthetic_cursor_dbs, tmp_path):
    conn, _ = _run_indexer_with_fixture(synthetic_cursor_dbs, tmp_path)
    from cursor.api import get_cursor_session_detail

    detail = get_cursor_session_detail(conn, "comp-1")
    assert detail is not None
    assert detail["uuid"] == "comp-1"
    assert detail["message_count"] == 2
    assert detail["models_used"] == ["claude-4.5-opus"]
    assert "read_file_v2" in detail["tools_used"]
    assert detail["tools_used"]["read_file_v2"] == 1
    assert detail["session_source"] == "cursor"


def test_get_cursor_session_timeline_chronological(synthetic_cursor_dbs, tmp_path):
    conn, _ = _run_indexer_with_fixture(synthetic_cursor_dbs, tmp_path)
    from cursor.api import get_cursor_session_timeline

    events = get_cursor_session_timeline(conn, "comp-1")
    assert len(events) == 2
    assert events[0]["event_type"] == "user_message"
    assert events[1]["event_type"] == "tool_call"


def test_get_cursor_session_file_activity(synthetic_cursor_dbs, tmp_path):
    conn, _ = _run_indexer_with_fixture(synthetic_cursor_dbs, tmp_path)
    from cursor.api import get_cursor_session_file_activity

    activity = get_cursor_session_file_activity(conn, "comp-1")
    assert len(activity) == 1
    assert activity[0]["path"] == "/tmp/main.py"
    assert activity[0]["tool_name"] == "read_file_v2"
    assert activity[0]["operation"] == "read"


def test_get_cursor_project_analytics(synthetic_cursor_dbs, tmp_path):
    conn, _ = _run_indexer_with_fixture(synthetic_cursor_dbs, tmp_path)
    from cursor.api import get_cursor_project_analytics, list_cursor_projects

    project = list_cursor_projects(conn)[0]
    analytics = get_cursor_project_analytics(conn, project["encoded_name"])
    assert analytics is not None
    assert analytics["totals"]["session_count"] == 2
    assert analytics["session_source"] == "cursor"
    tools = {t["tool_name"]: t["calls"] for t in analytics["tool_usage"]}
    assert tools.get("read_file_v2") == 1


def test_list_cursor_skill_items_returns_tracking_flag():
    """Cursor skill items always carry tracking_unavailable=True."""
    from cursor.api import list_cursor_skill_items

    items = list_cursor_skill_items()
    for item in items:
        assert item["source"] == "cursor"
        assert item["tracking_unavailable"] is True


def test_list_cursor_builtin_agents_shape():
    """Built-in agents have fixed names: agent/chat/plan/debug/edit."""
    from cursor.api import list_cursor_builtin_agent_summaries

    names = {a["name"] for a in list_cursor_builtin_agent_summaries()}
    assert names == {"agent", "chat", "plan", "debug", "edit"}


def test_is_cursor_project_encoded_name():
    from cursor.api import is_cursor_project_encoded_name

    assert is_cursor_project_encoded_name("cursor:abc123")
    assert not is_cursor_project_encoded_name("-Users-me-repo")
    assert not is_cursor_project_encoded_name("")

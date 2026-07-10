"""
End-to-end roundtrip test: remote session with ALL resources →
find_remote_session() → verify data → index_remote_sessions() → verify SQLite.
"""

import json
import sqlite3
from pathlib import Path
from unittest.mock import patch

import pytest

from db.indexer import index_remote_sessions
from db.schema import ensure_schema
from services.remote_sessions import find_remote_session


def _make_full_jsonl(uuid: str) -> str:
    """Build JSONL with user + assistant messages."""
    lines = [
        json.dumps({
            "type": "user",
            "uuid": f"msg-{uuid}",
            "message": {"role": "user", "content": "Build feature X"},
            "timestamp": "2026-03-03T12:00:00.000Z",
            "sessionId": "roundtrip-slug",
        }),
        json.dumps({
            "type": "assistant",
            "uuid": f"resp-{uuid}",
            "message": {
                "role": "assistant",
                "content": [{"type": "text", "text": "On it."}],
                "model": "claude-sonnet-4-20250514",
                "usage": {"input_tokens": 100, "output_tokens": 50},
            },
            "timestamp": "2026-03-03T12:00:05.000Z",
        }),
    ]
    return "\n".join(lines) + "\n"


@pytest.fixture
def full_roundtrip_env(tmp_path):
    """Create a complete roundtrip environment with all resource types."""
    karma_base = tmp_path / ".claude_karma"
    karma_base.mkdir()

    user_id = "alice"
    encoded = "-Users-alice-acme"
    uuid = "roundtrip-001"

    alice_dir = karma_base / "remote-sessions" / user_id / encoded
    sessions_dir = alice_dir / "sessions"
    sessions_dir.mkdir(parents=True)

    # JSONL
    (sessions_dir / f"{uuid}.jsonl").write_text(_make_full_jsonl(uuid))

    # Subagent
    sub_dir = sessions_dir / uuid / "subagents"
    sub_dir.mkdir(parents=True)
    (sub_dir / "agent-aaa.jsonl").write_text(
        json.dumps({
            "type": "user",
            "message": {"role": "user", "content": "sub task"},
            "timestamp": "2026-03-03T12:01:00Z",
        })
        + "\n"
    )

    # Tool result
    tr_dir = sessions_dir / uuid / "tool-results"
    tr_dir.mkdir(parents=True)
    (tr_dir / "toolu_xyz.txt").write_text("file content here")

    # Todos
    todos_dir = alice_dir / "todos"
    todos_dir.mkdir()
    (todos_dir / f"{uuid}-item.json").write_text(
        json.dumps([{"content": "Fix bug", "status": "pending"}])
    )

    # Tasks
    task_dir = alice_dir / "tasks" / uuid
    task_dir.mkdir(parents=True)
    (task_dir / "1.json").write_text(
        json.dumps({
            "id": "1",
            "subject": "Parse CLI args",
            "description": "Implement argument parsing",
            "status": "in_progress",
        })
    )

    # File-history
    fh_dir = alice_dir / "file-history" / uuid
    fh_dir.mkdir(parents=True)
    (fh_dir / "snapshot.json").write_text('{"file": "main.py"}')

    # Debug log
    debug_dir = alice_dir / "debug"
    debug_dir.mkdir()
    (debug_dir / f"{uuid}.txt").write_text("DEBUG: started")

    # Sync config (local user != alice)
    (karma_base / "sync-config.json").write_text(
        json.dumps({"user_id": "local-me", "machine_id": "my-mac"})
    )

    return {
        "karma_base": karma_base,
        "user_id": user_id,
        "encoded": encoded,
        "uuid": uuid,
    }


@pytest.fixture(autouse=True)
def _clear_cache():
    """Clear caches before each test."""
    import services.remote_sessions as mod

    mod._local_user_cache = None
    mod._local_user_cache_time = 0.0
    mod._project_mapping_cache = None
    mod._project_mapping_cache_time = 0.0
    yield
    mod._local_user_cache = None
    mod._local_user_cache_time = 0.0
    mod._project_mapping_cache = None
    mod._project_mapping_cache_time = 0.0


class TestFullRoundtrip:
    def test_find_remote_session_resolves_all_resources(self, full_roundtrip_env):
        """find_remote_session should resolve all resource types."""
        env = full_roundtrip_env

        with patch("services.remote_sessions.settings") as mock_settings:
            mock_settings.karma_base = env["karma_base"]
            result = find_remote_session(env["uuid"])

        assert result is not None
        assert result.user_id == "alice"

        session = result.session
        assert session.message_count >= 2

        # All resource types accessible
        assert len(session.list_todos()) >= 1
        assert len(session.list_tasks()) >= 1
        assert len(session.list_subagents()) >= 1
        assert len(session.list_tool_results()) >= 1
        assert session.has_file_history is True
        assert session.has_debug_log is True
        assert "DEBUG: started" in session.read_debug_log()

    def test_indexer_picks_up_remote_session(self, full_roundtrip_env):
        """index_remote_sessions should index the session into SQLite."""
        from unittest.mock import PropertyMock

        from config import Settings

        env = full_roundtrip_env

        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        ensure_schema(conn)

        with (
            patch.object(
                Settings, "karma_base",
                new_callable=PropertyMock, return_value=env["karma_base"],
            ),
            patch("services.remote_sessions.get_project_mapping", return_value={}),
        ):
            stats = index_remote_sessions(conn)

        assert stats["indexed"] >= 1
        assert stats["errors"] == 0

        # Verify indexed data
        row = conn.execute(
            "SELECT * FROM sessions WHERE uuid = ?", (env["uuid"],)
        ).fetchone()
        assert row is not None
        assert row["source"] == "remote"
        assert row["remote_user_id"] == "alice"
        assert row["message_count"] >= 2

        conn.close()

    def test_full_pipeline(self, full_roundtrip_env):
        """Full pipeline: find → verify resources → index → verify DB row."""
        from unittest.mock import PropertyMock

        from config import Settings

        env = full_roundtrip_env

        # Step 1: Find and verify session
        with patch("services.remote_sessions.settings") as mock_settings:
            mock_settings.karma_base = env["karma_base"]
            result = find_remote_session(env["uuid"])

        assert result is not None
        session = result.session

        # Verify all resources
        assert session.message_count >= 2
        assert len(session.list_todos()) >= 1
        assert len(session.list_tasks()) >= 1
        assert len(session.list_subagents()) >= 1
        assert session.has_file_history is True
        assert session.has_debug_log is True

        # Step 2: Index into SQLite
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        ensure_schema(conn)

        with (
            patch.object(
                Settings, "karma_base",
                new_callable=PropertyMock, return_value=env["karma_base"],
            ),
            patch("services.remote_sessions.get_project_mapping", return_value={}),
        ):
            stats = index_remote_sessions(conn)

        # Step 3: Verify DB row
        assert stats["indexed"] >= 1
        assert stats["errors"] == 0

        row = conn.execute(
            "SELECT * FROM sessions WHERE uuid = ?", (env["uuid"],)
        ).fetchone()
        assert row is not None
        assert row["source"] == "remote"
        assert row["remote_user_id"] == "alice"
        assert row["message_count"] >= 2
        assert row["project_encoded_name"] == env["encoded"]

        conn.close()

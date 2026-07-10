"""Tests for remote sessions API router (requires fastapi)."""

import json
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from main import app

client = TestClient(app)


@pytest.fixture
def remote_sessions_dir(tmp_path: Path) -> Path:
    """Create fake remote sessions directory."""
    remote = tmp_path / "remote-sessions"

    # Alice's sessions
    alice_proj = remote / "alice" / "-Users-alice-acme"
    alice_proj.mkdir(parents=True)

    manifest = {
        "version": 1,
        "user_id": "alice",
        "machine_id": "alice-mbp",
        "project_path": "/Users/alice/acme",
        "project_encoded": "-Users-alice-acme",
        "synced_at": "2026-03-03T14:00:00Z",
        "session_count": 2,
        "sessions": [
            {"uuid": "sess-001", "mtime": "2026-03-03T12:00:00Z", "size_bytes": 1000},
            {"uuid": "sess-002", "mtime": "2026-03-03T13:00:00Z", "size_bytes": 2000},
        ],
    }
    (alice_proj / "manifest.json").write_text(json.dumps(manifest))

    sessions_dir = alice_proj / "sessions"
    sessions_dir.mkdir()
    (sessions_dir / "sess-001.jsonl").write_text(
        '{"type":"user","uuid":"msg-1","message":{"role":"user","content":"hello"}}\n'
    )
    (sessions_dir / "sess-002.jsonl").write_text(
        '{"type":"user","uuid":"msg-2","message":{"role":"user","content":"build X"}}\n'
    )

    return remote


class TestRemoteSessionsRouter:
    def test_load_manifest_helper(self, remote_sessions_dir):
        """Test the _load_manifest helper directly."""
        from routers.remote_sessions import _load_manifest

        with patch("routers.remote_sessions.REMOTE_SESSIONS_DIR", remote_sessions_dir):
            manifest = _load_manifest("alice", "-Users-alice-acme")
            assert manifest is not None
            assert manifest["user_id"] == "alice"
            assert manifest["session_count"] == 2

    def test_load_manifest_returns_none_for_missing(self, remote_sessions_dir):
        from routers.remote_sessions import _load_manifest

        with patch("routers.remote_sessions.REMOTE_SESSIONS_DIR", remote_sessions_dir):
            assert _load_manifest("nonexistent", "nope") is None


# ============================================================================
# Integration tests: session detail endpoints via remote fallback
# ============================================================================


def _make_session_jsonl(uuid: str, prompt: str = "hello") -> str:
    """Build minimal valid JSONL for a session."""
    lines = [
        json.dumps({
            "type": "user",
            "uuid": f"msg-{uuid}",
            "message": {"role": "user", "content": prompt},
            "timestamp": "2026-03-03T12:00:00.000Z",
        }),
        json.dumps({
            "type": "assistant",
            "uuid": f"resp-{uuid}",
            "message": {
                "role": "assistant",
                "content": [{"type": "text", "text": "ok"}],
                "model": "claude-sonnet-4-20250514",
                "usage": {"input_tokens": 100, "output_tokens": 50},
            },
            "timestamp": "2026-03-03T12:00:01.000Z",
        }),
    ]
    return "\n".join(lines) + "\n"


@pytest.fixture
def karma_base_with_resources(tmp_path: Path) -> Path:
    """Create a complete remote session environment with all resource types."""
    karma = tmp_path / ".claude_karma"
    karma.mkdir()

    encoded = "-Users-jayant-acme"
    alice_dir = karma / "remote-sessions" / "alice" / encoded

    # Session JSONL
    sessions_dir = alice_dir / "sessions"
    sessions_dir.mkdir(parents=True)
    (sessions_dir / "sess-integration.jsonl").write_text(
        _make_session_jsonl("integration", "Build a CLI tool")
    )

    # Subagent
    sub_dir = sessions_dir / "sess-integration" / "subagents"
    sub_dir.mkdir(parents=True)
    (sub_dir / "agent-abc.jsonl").write_text(
        json.dumps({
            "type": "user",
            "message": {"role": "user", "content": "sub task"},
            "timestamp": "2026-03-03T12:01:00Z",
        }) + "\n"
    )

    # Tool result
    tr_dir = sessions_dir / "sess-integration" / "tool-results"
    tr_dir.mkdir(parents=True)
    (tr_dir / "toolu_xyz.txt").write_text("tool output")

    # Todos (claude_base_dir = alice_dir, so todos_dir = alice_dir / "todos")
    todos_dir = alice_dir / "todos"
    todos_dir.mkdir()
    (todos_dir / "sess-integration-item.json").write_text(
        json.dumps([{"content": "Remote todo", "status": "pending"}])
    )

    # Tasks (tasks_dir = alice_dir / "tasks" / "sess-integration")
    task_dir = alice_dir / "tasks" / "sess-integration"
    task_dir.mkdir(parents=True)
    (task_dir / "1.json").write_text(
        json.dumps({"id": "1", "subject": "Parse CLI args", "description": "Implement argument parsing for the CLI tool", "status": "in_progress"})
    )

    # Sync config (needed so local user != "alice", preventing outbox skip)
    (karma / "sync-config.json").write_text(
        json.dumps({"user_id": "local-me", "machine_id": "my-mac"})
    )

    return karma


@pytest.fixture(autouse=True)
def _clear_remote_cache():
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


class TestRemoteSessionEndpoints:
    """Integration tests: session endpoints work for remote sessions via fallback.

    Strategy: patch the internal functions in services.remote_sessions to point
    at the test data, and patch config.settings.claude_base to a nonexistent
    dir so the local project scan in find_session_with_project() misses,
    triggering the remote fallback path.
    """

    @staticmethod
    def _patches(karma_base):
        """Return an ExitStack with patches for remote session fallback.

        Patches Settings class properties so all code paths that access
        settings.projects_dir and settings.karma_base get test values.
        """
        from contextlib import ExitStack
        from unittest.mock import PropertyMock

        from config import Settings

        stack = ExitStack()
        # Make local project scan miss (nonexistent projects_dir)
        stack.enter_context(
            patch.object(
                Settings,
                "projects_dir",
                new_callable=PropertyMock,
                return_value=karma_base / "nonexistent" / "projects",
            )
        )
        # Route karma_base to test data (used by remote session lookup)
        stack.enter_context(
            patch.object(
                Settings,
                "karma_base",
                new_callable=PropertyMock,
                return_value=karma_base,
            )
        )
        return stack

    def test_session_detail_endpoint(self, karma_base_with_resources):
        """GET /sessions/{uuid} should return full detail for remote sessions."""
        with self._patches(karma_base_with_resources):
            response = client.get("/sessions/sess-integration")

        assert response.status_code == 200
        data = response.json()
        assert data["uuid"] == "sess-integration"
        assert data["message_count"] >= 2

    def test_todos_endpoint(self, karma_base_with_resources):
        """GET /sessions/{uuid}/todos should return remote session todos."""
        with self._patches(karma_base_with_resources):
            response = client.get("/sessions/sess-integration/todos")

        assert response.status_code == 200
        todos = response.json()
        assert len(todos) >= 1
        assert todos[0]["content"] == "Remote todo"

    def test_tasks_endpoint(self, karma_base_with_resources):
        """GET /sessions/{uuid}/tasks should return remote session tasks."""
        with self._patches(karma_base_with_resources):
            response = client.get("/sessions/sess-integration/tasks")

        assert response.status_code == 200
        tasks = response.json()
        assert len(tasks) >= 1

    def test_subagents_endpoint(self, karma_base_with_resources):
        """GET /sessions/{uuid}/subagents should work for remote sessions."""
        with self._patches(karma_base_with_resources):
            response = client.get("/sessions/sess-integration/subagents")

        assert response.status_code == 200
        data = response.json()
        assert len(data) >= 1

    def test_timeline_endpoint(self, karma_base_with_resources):
        """GET /sessions/{uuid}/timeline should work for remote sessions."""
        with self._patches(karma_base_with_resources):
            response = client.get("/sessions/sess-integration/timeline")

        assert response.status_code == 200
        events = response.json()
        assert len(events) >= 1

    def test_file_activity_endpoint(self, karma_base_with_resources):
        """GET /sessions/{uuid}/file-activity should work for remote sessions."""
        with self._patches(karma_base_with_resources):
            response = client.get("/sessions/sess-integration/file-activity")

        # Should return 200 even if no file activity in the JSONL
        assert response.status_code == 200

    def test_tools_endpoint(self, karma_base_with_resources):
        """GET /sessions/{uuid}/tools should work for remote sessions."""
        with self._patches(karma_base_with_resources):
            response = client.get("/sessions/sess-integration/tools")

        assert response.status_code == 200

    def test_nonexistent_session_returns_404(self, karma_base_with_resources):
        """GET /sessions/{uuid} should return 404 for nonexistent remote sessions."""
        with self._patches(karma_base_with_resources):
            response = client.get("/sessions/nonexistent-uuid")

        assert response.status_code == 404

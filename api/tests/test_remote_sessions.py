"""Tests for remote sessions API endpoints."""

import json
from pathlib import Path
from unittest.mock import patch

import pytest


@pytest.fixture
def remote_sessions_dir(tmp_path: Path) -> Path:
    """Create fake remote sessions directory."""
    remote = tmp_path / "remote-sessions"

    # Alice's sessions
    alice_proj = remote / "alice" / "-Users-alice-acme"
    alice_proj.mkdir(parents=True)

    # Manifest
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

    # Session files
    sessions_dir = alice_proj / "sessions"
    sessions_dir.mkdir()
    (sessions_dir / "sess-001.jsonl").write_text(
        '{"type":"user","uuid":"msg-1","message":{"role":"user","content":"hello"}}\n'
    )
    (sessions_dir / "sess-002.jsonl").write_text(
        '{"type":"user","uuid":"msg-2","message":{"role":"user","content":"build X"}}\n'
    )

    return remote


class TestRemoteManifestParsing:
    def test_manifest_loads_correctly(self, remote_sessions_dir):
        manifest_path = remote_sessions_dir / "alice" / "-Users-alice-acme" / "manifest.json"
        manifest = json.loads(manifest_path.read_text())
        assert manifest["user_id"] == "alice"
        assert manifest["session_count"] == 2
        assert len(manifest["sessions"]) == 2

    def test_session_files_exist(self, remote_sessions_dir):
        sessions_dir = remote_sessions_dir / "alice" / "-Users-alice-acme" / "sessions"
        assert (sessions_dir / "sess-001.jsonl").exists()
        assert (sessions_dir / "sess-002.jsonl").exists()


class TestRemoteSessionsRouter:
    def test_load_manifest_helper(self, remote_sessions_dir):
        """Test the _load_manifest helper directly."""
        import sys
        sys.path.insert(0, str(Path(__file__).parent.parent))

        from routers.remote_sessions import _load_manifest

        with patch("routers.remote_sessions.REMOTE_SESSIONS_DIR", remote_sessions_dir):
            manifest = _load_manifest("alice", "-Users-alice-acme")
            assert manifest is not None
            assert manifest["user_id"] == "alice"
            assert manifest["session_count"] == 2

    def test_load_manifest_returns_none_for_missing(self, remote_sessions_dir):
        import sys
        sys.path.insert(0, str(Path(__file__).parent.parent))

        from routers.remote_sessions import _load_manifest

        with patch("routers.remote_sessions.REMOTE_SESSIONS_DIR", remote_sessions_dir):
            assert _load_manifest("nonexistent", "nope") is None

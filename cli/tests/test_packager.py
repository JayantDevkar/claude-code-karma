"""Tests for session packager."""

from pathlib import Path

import pytest

from karma.packager import SessionPackager


@pytest.fixture
def mock_claude_project(tmp_path: Path) -> Path:
    """Create a fake ~/.claude/projects/-My-project/ directory."""
    project_dir = tmp_path / ".claude" / "projects" / "-My-project"
    project_dir.mkdir(parents=True)

    # Session 1: simple JSONL
    s1 = project_dir / "session-uuid-001.jsonl"
    s1.write_text('{"type":"user","message":{"role":"user","content":"hello"}}\n')

    # Session 2: with subagents directory
    s2 = project_dir / "session-uuid-002.jsonl"
    s2.write_text('{"type":"user","message":{"role":"user","content":"build X"}}\n')
    sub_dir = project_dir / "session-uuid-002" / "subagents"
    sub_dir.mkdir(parents=True)
    (sub_dir / "agent-abc.jsonl").write_text('{"type":"agent"}\n')

    # Tool results
    tr_dir = project_dir / "session-uuid-002" / "tool-results"
    tr_dir.mkdir(parents=True)
    (tr_dir / "toolu_123.txt").write_text("tool output here")

    return project_dir


class TestSessionPackager:
    def test_discover_sessions(self, mock_claude_project):
        packager = SessionPackager(
            project_dir=mock_claude_project,
            user_id="alice",
            machine_id="test-mac",
        )
        sessions = packager.discover_sessions()
        assert len(sessions) == 2
        uuids = {s.uuid for s in sessions}
        assert "session-uuid-001" in uuids
        assert "session-uuid-002" in uuids

    def test_package_creates_staging_dir(self, mock_claude_project, tmp_path):
        staging = tmp_path / "staging"
        packager = SessionPackager(
            project_dir=mock_claude_project,
            user_id="alice",
            machine_id="test-mac",
        )
        packager.package(staging_dir=staging)

        assert staging.exists()
        assert (staging / "manifest.json").exists()
        assert (staging / "sessions" / "session-uuid-001.jsonl").exists()
        assert (staging / "sessions" / "session-uuid-002.jsonl").exists()
        assert (staging / "sessions" / "session-uuid-002" / "subagents" / "agent-abc.jsonl").exists()
        assert (staging / "sessions" / "session-uuid-002" / "tool-results" / "toolu_123.txt").exists()

    def test_manifest_content(self, mock_claude_project, tmp_path):
        staging = tmp_path / "staging"
        packager = SessionPackager(
            project_dir=mock_claude_project,
            user_id="alice",
            machine_id="test-mac",
        )
        manifest = packager.package(staging_dir=staging)

        assert manifest.user_id == "alice"
        assert manifest.machine_id == "test-mac"
        assert manifest.session_count == 2
        assert manifest.version == 1
        assert len(manifest.sessions) == 2

    def test_previous_cid_recorded_in_manifest(self, mock_claude_project, tmp_path):
        staging = tmp_path / "staging"
        packager = SessionPackager(
            project_dir=mock_claude_project,
            user_id="alice",
            machine_id="test-mac",
            last_sync_cid="QmPrevious",
        )
        manifest = packager.package(staging_dir=staging)
        assert manifest.session_count == 2
        assert manifest.previous_cid == "QmPrevious"


class TestSyncManifest:
    def test_manifest_default_sync_backend_is_none(self):
        from karma.manifest import SyncManifest
        m = SyncManifest(
            user_id="alice",
            machine_id="mac",
            project_path="/foo",
            project_encoded="-foo",
            session_count=0,
            sessions=[],
        )
        assert m.sync_backend is None

    def test_manifest_sync_backend_set(self):
        from karma.manifest import SyncManifest
        m = SyncManifest(
            user_id="alice",
            machine_id="mac",
            project_path="/foo",
            project_encoded="-foo",
            session_count=0,
            sessions=[],
            sync_backend="syncthing",
        )
        assert m.sync_backend == "syncthing"

    def test_manifest_sync_backend_in_dump(self):
        from karma.manifest import SyncManifest
        m = SyncManifest(
            user_id="alice",
            machine_id="mac",
            project_path="/foo",
            project_encoded="-foo",
            session_count=0,
            sessions=[],
            sync_backend="ipfs",
        )
        data = m.model_dump()
        assert data["sync_backend"] == "ipfs"

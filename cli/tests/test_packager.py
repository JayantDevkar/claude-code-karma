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


class TestSessionEntryMetadata:
    def test_session_entry_default_no_worktree(self):
        from karma.manifest import SessionEntry
        entry = SessionEntry(uuid="abc", mtime="2026-01-01T00:00:00Z", size_bytes=100)
        assert entry.worktree_name is None
        assert entry.git_branch is None

    def test_session_entry_with_worktree(self):
        from karma.manifest import SessionEntry
        entry = SessionEntry(
            uuid="abc",
            mtime="2026-01-01T00:00:00Z",
            size_bytes=100,
            worktree_name="syncthing-sync-design",
            git_branch="worktree-syncthing-sync-design",
        )
        assert entry.worktree_name == "syncthing-sync-design"
        assert entry.git_branch == "worktree-syncthing-sync-design"

    def test_session_entry_worktree_in_dump(self):
        from karma.manifest import SessionEntry
        entry = SessionEntry(
            uuid="abc",
            mtime="2026-01-01T00:00:00Z",
            size_bytes=100,
            worktree_name="feat-x",
        )
        data = entry.model_dump()
        assert data["worktree_name"] == "feat-x"
        assert data["git_branch"] is None


@pytest.fixture
def mock_project_with_worktree(tmp_path: Path) -> dict:
    """Create a main project dir + one worktree dir."""
    projects_dir = tmp_path / ".claude" / "projects"

    # Main project
    main_dir = projects_dir / "-Users-jay-GitHub-karma"
    main_dir.mkdir(parents=True)
    (main_dir / "session-main-001.jsonl").write_text(
        '{"type":"user","message":{"role":"user","content":"hello"}}\n'
    )

    # Worktree
    wt_dir = projects_dir / "-Users-jay-GitHub-karma--claude-worktrees-feat-a"
    wt_dir.mkdir(parents=True)
    (wt_dir / "session-wt-001.jsonl").write_text(
        '{"type":"user","message":{"role":"user","content":"worktree work"}}\n'
    )
    # Worktree session with subagent
    (wt_dir / "session-wt-002.jsonl").write_text(
        '{"type":"user","message":{"role":"user","content":"more work"}}\n'
    )
    sub_dir = wt_dir / "session-wt-002" / "subagents"
    sub_dir.mkdir(parents=True)
    (sub_dir / "agent-x.jsonl").write_text('{"type":"agent"}\n')

    return {
        "main_dir": main_dir,
        "wt_dir": wt_dir,
        "projects_dir": projects_dir,
    }


class TestPackagerWithWorktrees:
    def test_discover_includes_worktree_sessions(self, mock_project_with_worktree):
        dirs = mock_project_with_worktree
        packager = SessionPackager(
            project_dir=dirs["main_dir"],
            user_id="jay",
            machine_id="mac",
            extra_dirs=[dirs["wt_dir"]],
        )
        sessions = packager.discover_sessions()
        uuids = {s.uuid for s in sessions}
        assert "session-main-001" in uuids
        assert "session-wt-001" in uuids
        assert "session-wt-002" in uuids
        assert len(sessions) == 3

    def test_worktree_sessions_tagged_with_worktree_name(self, mock_project_with_worktree):
        dirs = mock_project_with_worktree
        packager = SessionPackager(
            project_dir=dirs["main_dir"],
            user_id="jay",
            machine_id="mac",
            extra_dirs=[dirs["wt_dir"]],
        )
        sessions = packager.discover_sessions()
        wt_sessions = [s for s in sessions if s.worktree_name is not None]
        assert len(wt_sessions) == 2
        assert all(s.worktree_name == "feat-a" for s in wt_sessions)

    def test_package_copies_worktree_subagents(self, mock_project_with_worktree, tmp_path):
        dirs = mock_project_with_worktree
        staging = tmp_path / "staging"
        packager = SessionPackager(
            project_dir=dirs["main_dir"],
            user_id="jay",
            machine_id="mac",
            extra_dirs=[dirs["wt_dir"]],
        )
        packager.package(staging_dir=staging)
        assert (staging / "sessions" / "session-wt-002" / "subagents" / "agent-x.jsonl").exists()

    def test_manifest_counts_all_sessions(self, mock_project_with_worktree, tmp_path):
        dirs = mock_project_with_worktree
        staging = tmp_path / "staging"
        packager = SessionPackager(
            project_dir=dirs["main_dir"],
            user_id="jay",
            machine_id="mac",
            extra_dirs=[dirs["wt_dir"]],
        )
        manifest = packager.package(staging_dir=staging)
        assert manifest.session_count == 3

    def test_no_extra_dirs_works_like_before(self, mock_claude_project, tmp_path):
        """Backward compat: no extra_dirs = original behavior."""
        staging = tmp_path / "staging"
        packager = SessionPackager(
            project_dir=mock_claude_project,
            user_id="alice",
            machine_id="test-mac",
        )
        manifest = packager.package(staging_dir=staging)
        assert manifest.session_count == 2


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

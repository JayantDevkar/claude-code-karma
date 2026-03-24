"""Tests for session packager."""

import json
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


class TestIncrementalPackaging:
    def test_skip_unchanged_sessions(self, mock_claude_project, tmp_path):
        """Second package should skip files that haven't changed."""
        staging = tmp_path / "staging"
        packager = SessionPackager(
            project_dir=mock_claude_project,
            user_id="alice",
            machine_id="test-mac",
        )

        # First package
        manifest1 = packager.package(staging_dir=staging)
        assert manifest1.session_count == 2

        # Record mtime of a copied file
        copied = staging / "sessions" / "session-uuid-001.jsonl"
        mtime_after_first = copied.stat().st_mtime

        import time
        time.sleep(0.05)  # ensure mtime difference is detectable

        # Second package (no source changes)
        manifest2 = packager.package(staging_dir=staging)
        assert manifest2.session_count == 2

        # File should NOT have been re-copied (mtime unchanged)
        mtime_after_second = copied.stat().st_mtime
        assert mtime_after_first == mtime_after_second

    def test_repackage_modified_session(self, mock_claude_project, tmp_path):
        """Modified source file should be re-copied."""
        staging = tmp_path / "staging"
        packager = SessionPackager(
            project_dir=mock_claude_project,
            user_id="alice",
            machine_id="test-mac",
        )

        packager.package(staging_dir=staging)
        copied = staging / "sessions" / "session-uuid-001.jsonl"
        mtime_before = copied.stat().st_mtime

        import time
        time.sleep(0.05)

        # Modify source
        src = mock_claude_project / "session-uuid-001.jsonl"
        src.write_text('{"type":"user","message":{"role":"user","content":"updated"}}\n')

        packager.package(staging_dir=staging)
        mtime_after = copied.stat().st_mtime
        assert mtime_after > mtime_before


class TestTaskSyncing:
    def test_package_copies_task_files(self, tmp_path):
        """Tasks from ~/.claude/tasks/{uuid}/ should be copied."""
        claude_dir = tmp_path / ".claude"
        project_dir = claude_dir / "projects" / "-My-project"
        project_dir.mkdir(parents=True)
        (project_dir / "session-abc.jsonl").write_text(
            '{"type":"user","message":{"role":"user","content":"hello"}}\n'
        )

        # Create task dir: .claude/tasks/session-abc/
        tasks_dir = claude_dir / "tasks" / "session-abc"
        tasks_dir.mkdir(parents=True)
        (tasks_dir / "1.json").write_text(
            '{"id":"1","subject":"Fix bug","status":"completed"}\n'
        )
        (tasks_dir / "2.json").write_text(
            '{"id":"2","subject":"Add test","status":"pending"}\n'
        )

        staging = tmp_path / "staging"
        packager = SessionPackager(
            project_dir=project_dir,
            user_id="alice",
            machine_id="mac",
        )
        packager.package(staging_dir=staging)

        assert (staging / "tasks" / "session-abc" / "1.json").exists()
        assert (staging / "tasks" / "session-abc" / "2.json").exists()

    def test_package_skips_missing_task_dir(self, mock_claude_project, tmp_path):
        """Sessions without task dirs should not cause errors."""
        staging = tmp_path / "staging"
        packager = SessionPackager(
            project_dir=mock_claude_project,
            user_id="alice",
            machine_id="mac",
        )
        manifest = packager.package(staging_dir=staging)
        assert manifest.session_count == 2
        # tasks dir should not exist if no tasks
        assert not (staging / "tasks").exists()

    def test_package_copies_worktree_tasks(self, tmp_path):
        """Tasks for worktree sessions should also be copied."""
        claude_dir = tmp_path / ".claude"
        main_dir = claude_dir / "projects" / "-Users-jay-karma"
        main_dir.mkdir(parents=True)
        (main_dir / "main-s.jsonl").write_text('{"type":"user","message":{"role":"user","content":"hi"}}\n')

        wt_dir = claude_dir / "projects" / "-Users-jay-karma--claude-worktrees-feat"
        wt_dir.mkdir(parents=True)
        (wt_dir / "wt-s.jsonl").write_text('{"type":"user","message":{"role":"user","content":"hi"}}\n')

        # Task for worktree session
        tasks_dir = claude_dir / "tasks" / "wt-s"
        tasks_dir.mkdir(parents=True)
        (tasks_dir / "1.json").write_text('{"id":"1","subject":"WT task","status":"pending"}\n')

        staging = tmp_path / "staging"
        packager = SessionPackager(
            project_dir=main_dir,
            user_id="jay",
            machine_id="mac",
            extra_dirs=[wt_dir],
        )
        packager.package(staging_dir=staging)

        assert (staging / "tasks" / "wt-s" / "1.json").exists()


class TestFileHistorySyncing:
    def test_package_copies_file_history(self, tmp_path):
        """File-history directories should be copied to staging."""
        claude_dir = tmp_path / ".claude"
        project_dir = claude_dir / "projects" / "-Users-test-repo"
        project_dir.mkdir(parents=True)

        uuid = "sess-fh-001"
        (project_dir / f"{uuid}.jsonl").write_text(
            '{"type":"user","message":{"role":"user","content":"hi"}}\n'
        )

        # Create file-history for this session
        fh_dir = claude_dir / "file-history" / uuid
        fh_dir.mkdir(parents=True)
        (fh_dir / "snapshot-1.json").write_text('{"file": "main.py", "content": "print(1)"}')

        staging = tmp_path / "staging"
        packager = SessionPackager(
            project_dir=project_dir,
            user_id="test",
            machine_id="test-machine",
        )
        packager.package(staging)

        staged_fh = staging / "file-history" / uuid / "snapshot-1.json"
        assert staged_fh.exists()
        assert staged_fh.read_text() == '{"file": "main.py", "content": "print(1)"}'

    def test_package_skips_missing_file_history(self, mock_claude_project, tmp_path):
        """Sessions without file-history should not cause errors."""
        staging = tmp_path / "staging"
        packager = SessionPackager(
            project_dir=mock_claude_project,
            user_id="alice",
            machine_id="mac",
        )
        manifest = packager.package(staging_dir=staging)
        assert manifest.session_count == 2
        assert not (staging / "file-history").exists()

    def test_incremental_package_file_history(self, tmp_path):
        """Re-packaging should not fail or duplicate file-history."""
        claude_dir = tmp_path / ".claude"
        project_dir = claude_dir / "projects" / "-Users-test-repo"
        project_dir.mkdir(parents=True)

        uuid = "sess-fh-002"
        (project_dir / f"{uuid}.jsonl").write_text(
            '{"type":"user","message":{"role":"user","content":"hi"}}\n'
        )

        fh_dir = claude_dir / "file-history" / uuid
        fh_dir.mkdir(parents=True)
        (fh_dir / "snapshot.json").write_text('{"file": "main.py"}')

        staging = tmp_path / "staging"
        packager = SessionPackager(
            project_dir=project_dir,
            user_id="test",
            machine_id="test-machine",
        )

        # First package
        packager.package(staging)
        assert (staging / "file-history" / uuid / "snapshot.json").exists()

        # Second package (should not crash)
        packager.package(staging)
        assert (staging / "file-history" / uuid / "snapshot.json").exists()


class TestDebugLogSyncing:
    def test_package_copies_debug_logs(self, tmp_path):
        """Debug log files should be copied to staging."""
        claude_dir = tmp_path / ".claude"
        project_dir = claude_dir / "projects" / "-Users-test-repo"
        project_dir.mkdir(parents=True)

        uuid = "sess-debug-001"
        (project_dir / f"{uuid}.jsonl").write_text(
            '{"type":"user","message":{"role":"user","content":"hi"}}\n'
        )

        debug_dir = claude_dir / "debug"
        debug_dir.mkdir(parents=True)
        (debug_dir / f"{uuid}.txt").write_text("DEBUG: session started\nDEBUG: tool called")

        staging = tmp_path / "staging"
        packager = SessionPackager(
            project_dir=project_dir,
            user_id="test",
            machine_id="test-machine",
        )
        packager.package(staging)

        staged_debug = staging / "debug" / f"{uuid}.txt"
        assert staged_debug.exists()
        assert "DEBUG: session started" in staged_debug.read_text()

    def test_package_skips_missing_debug_logs(self, mock_claude_project, tmp_path):
        """Sessions without debug logs should not cause errors."""
        staging = tmp_path / "staging"
        packager = SessionPackager(
            project_dir=mock_claude_project,
            user_id="alice",
            machine_id="mac",
        )
        manifest = packager.package(staging_dir=staging)
        assert manifest.session_count == 2
        assert not (staging / "debug").exists()

    def test_package_copies_worktree_debug_logs(self, tmp_path):
        """Debug logs for worktree sessions should also be copied."""
        claude_dir = tmp_path / ".claude"
        main_dir = claude_dir / "projects" / "-Users-jay-karma"
        main_dir.mkdir(parents=True)
        (main_dir / "main-s.jsonl").write_text('{"type":"user","message":{"role":"user","content":"hi"}}\n')

        wt_dir = claude_dir / "projects" / "-Users-jay-karma--claude-worktrees-feat"
        wt_dir.mkdir(parents=True)
        (wt_dir / "wt-s.jsonl").write_text('{"type":"user","message":{"role":"user","content":"hi"}}\n')

        # Debug log for worktree session
        debug_dir = claude_dir / "debug"
        debug_dir.mkdir(parents=True)
        (debug_dir / "wt-s.txt").write_text("DEBUG: worktree session")

        staging = tmp_path / "staging"
        packager = SessionPackager(
            project_dir=main_dir,
            user_id="jay",
            machine_id="mac",
            extra_dirs=[wt_dir],
        )
        packager.package(staging_dir=staging)

        assert (staging / "debug" / "wt-s.txt").exists()


class TestSyncManifest:
    def test_manifest_git_identity_in_dump(self):
        from karma.manifest import SyncManifest
        m = SyncManifest(
            user_id="alice",
            machine_id="mac",
            project_path="/foo",
            project_encoded="-foo",
            session_count=0,
            sessions=[],
        )
        data = m.model_dump()
        assert data["git_identity"] is None


class TestPackagerTitles:
    def test_package_creates_titles_json(self, mock_claude_project, tmp_path):
        """Verify titles.json is created alongside manifest.json."""
        staging = tmp_path / "staging"
        packager = SessionPackager(
            project_dir=mock_claude_project,
            user_id="alice",
            machine_id="test-mac",
        )
        packager.package(staging_dir=staging)

        assert (staging / "manifest.json").exists()
        assert (staging / "titles.json").exists()

        import json
        data = json.loads((staging / "titles.json").read_text())
        assert data["version"] == 1
        assert "titles" in data
        assert "updated_at" in data

    def test_package_preserves_existing_titles(self, mock_claude_project, tmp_path):
        """Pre-populated titles.json should not be overwritten by packaging."""
        staging = tmp_path / "staging"
        staging.mkdir(parents=True)

        # Pre-populate titles.json with an existing title
        from karma.titles_io import write_title
        titles_path = staging / "titles.json"
        write_title(titles_path, "session-uuid-001", "My Title", "haiku")

        # Verify it was written
        from karma.titles_io import read_titles
        pre_titles = read_titles(titles_path)
        assert "session-uuid-001" in pre_titles
        assert pre_titles["session-uuid-001"]["title"] == "My Title"

        # Now package — should preserve the existing title
        packager = SessionPackager(
            project_dir=mock_claude_project,
            user_id="alice",
            machine_id="test-mac",
        )
        packager.package(staging_dir=staging)

        post_titles = read_titles(titles_path)
        assert "session-uuid-001" in post_titles
        assert post_titles["session-uuid-001"]["title"] == "My Title"
        assert post_titles["session-uuid-001"]["source"] == "haiku"


class TestLiveSessionExclusion:
    """Live (in-progress) sessions should not be packaged for sync."""

    def test_live_session_excluded_from_discovery(self, mock_claude_project, monkeypatch):
        """A session whose UUID appears as LIVE should be excluded."""
        from karma import packager

        # Simulate session-uuid-001 being live
        monkeypatch.setattr(
            packager, "_get_live_session_uuids", lambda: {"session-uuid-001"}
        )

        p = SessionPackager(
            project_dir=mock_claude_project,
            user_id="alice",
            machine_id="test-mac",
        )
        sessions = p.discover_sessions()
        uuids = {s.uuid for s in sessions}
        assert "session-uuid-001" not in uuids
        assert "session-uuid-002" in uuids
        assert len(sessions) == 1

    def test_ended_session_not_excluded(self, mock_claude_project, monkeypatch):
        """ENDED sessions should pass through (empty live set)."""
        from karma import packager

        monkeypatch.setattr(packager, "_get_live_session_uuids", lambda: set())

        p = SessionPackager(
            project_dir=mock_claude_project,
            user_id="alice",
            machine_id="test-mac",
        )
        sessions = p.discover_sessions()
        assert len(sessions) == 2

    def test_exclude_live_false_skips_filter(self, mock_claude_project, monkeypatch):
        """exclude_live=False should bypass the filter entirely."""
        from karma import packager

        monkeypatch.setattr(
            packager,
            "_get_live_session_uuids",
            lambda: {"session-uuid-001", "session-uuid-002"},
        )

        p = SessionPackager(
            project_dir=mock_claude_project,
            user_id="alice",
            machine_id="test-mac",
        )
        sessions = p.discover_sessions(exclude_live=False)
        assert len(sessions) == 2

    def test_live_session_not_packaged(self, mock_claude_project, tmp_path, monkeypatch):
        """Live session JSONL should not be copied to staging dir."""
        from karma import packager

        monkeypatch.setattr(
            packager, "_get_live_session_uuids", lambda: {"session-uuid-001"}
        )

        staging = tmp_path / "staging"
        p = SessionPackager(
            project_dir=mock_claude_project,
            user_id="alice",
            machine_id="test-mac",
        )
        manifest = p.package(staging_dir=staging)

        assert manifest.session_count == 1
        assert not (staging / "sessions" / "session-uuid-001.jsonl").exists()
        assert (staging / "sessions" / "session-uuid-002.jsonl").exists()

    def test_no_live_sessions_dir_packages_all(self, mock_claude_project, tmp_path, monkeypatch):
        """When hooks aren't configured (no live-sessions dir), all sessions are packaged."""
        from karma import packager

        # _get_live_session_uuids returns empty set when dir doesn't exist
        monkeypatch.setattr(packager, "_get_live_session_uuids", lambda: set())

        staging = tmp_path / "staging"
        p = SessionPackager(
            project_dir=mock_claude_project,
            user_id="alice",
            machine_id="test-mac",
        )
        manifest = p.package(staging_dir=staging)
        assert manifest.session_count == 2


class TestGetLiveSessionUuids:
    """Unit tests for the _get_live_session_uuids helper."""

    def test_returns_empty_when_dir_missing(self, monkeypatch):
        from karma.packager import _get_live_session_uuids
        from karma import config

        # Point KARMA_BASE at a non-existent directory
        monkeypatch.setattr(config, "KARMA_BASE", Path("/tmp/nonexistent-karma-test"))
        # Re-import to pick up monkeypatched KARMA_BASE
        import importlib
        from karma import packager
        importlib.reload(packager)
        from karma.packager import _get_live_session_uuids as reloaded

        result = reloaded()
        assert result == set()

        # Restore
        importlib.reload(config)
        importlib.reload(packager)

    def test_collects_live_uuids(self, tmp_path, monkeypatch):
        from karma import packager, config
        import importlib

        live_dir = tmp_path / "live-sessions"
        live_dir.mkdir(parents=True)

        # LIVE session
        (live_dir / "happy-slug.json").write_text(json.dumps({
            "session_id": "uuid-live-1",
            "session_ids": ["uuid-live-1", "uuid-old-resumed"],
            "state": "LIVE",
        }))
        # ENDED session (should NOT be collected)
        (live_dir / "done-slug.json").write_text(json.dumps({
            "session_id": "uuid-ended",
            "session_ids": ["uuid-ended"],
            "state": "ENDED",
        }))
        # WAITING session
        (live_dir / "waiting-slug.json").write_text(json.dumps({
            "session_id": "uuid-waiting",
            "session_ids": ["uuid-waiting"],
            "state": "WAITING",
        }))

        monkeypatch.setattr(config, "KARMA_BASE", tmp_path)
        importlib.reload(packager)
        from karma.packager import _get_live_session_uuids as reloaded

        result = reloaded()
        assert "uuid-live-1" in result
        assert "uuid-old-resumed" in result
        assert "uuid-waiting" in result
        assert "uuid-ended" not in result

        importlib.reload(config)
        importlib.reload(packager)

    def test_stale_live_session_not_excluded(self, tmp_path, monkeypatch):
        """Sessions idle > 30 min are considered crashed — should be packaged."""
        from datetime import datetime, timezone, timedelta
        from karma import packager, config
        import importlib

        live_dir = tmp_path / "live-sessions"
        live_dir.mkdir(parents=True)

        now = datetime.now(timezone.utc)

        # Recent LIVE session (5 min ago) — should be excluded
        (live_dir / "recent.json").write_text(json.dumps({
            "session_id": "uuid-recent",
            "session_ids": ["uuid-recent"],
            "state": "LIVE",
            "updated_at": (now - timedelta(minutes=5)).isoformat(),
        }))
        # Stale LIVE session (2 hours ago) — crashed, should NOT be excluded
        (live_dir / "crashed.json").write_text(json.dumps({
            "session_id": "uuid-crashed",
            "session_ids": ["uuid-crashed"],
            "state": "LIVE",
            "updated_at": (now - timedelta(hours=2)).isoformat(),
        }))
        # Stale WAITING session (45 min ago) — also crashed
        (live_dir / "stuck.json").write_text(json.dumps({
            "session_id": "uuid-stuck",
            "session_ids": ["uuid-stuck"],
            "state": "WAITING",
            "updated_at": (now - timedelta(minutes=45)).isoformat(),
        }))

        monkeypatch.setattr(config, "KARMA_BASE", tmp_path)
        importlib.reload(packager)
        from karma.packager import _get_live_session_uuids as reloaded

        result = reloaded()
        assert "uuid-recent" in result       # recent → still excluded
        assert "uuid-crashed" not in result   # 2h stale → packaged
        assert "uuid-stuck" not in result     # 45m stale → packaged

        importlib.reload(config)
        importlib.reload(packager)

    def test_skips_corrupt_json(self, tmp_path, monkeypatch):
        from karma import packager, config
        import importlib

        live_dir = tmp_path / "live-sessions"
        live_dir.mkdir(parents=True)

        (live_dir / "corrupt.json").write_text("not valid json {{{{")
        (live_dir / "good.json").write_text(json.dumps({
            "session_id": "uuid-good",
            "session_ids": ["uuid-good"],
            "state": "LIVE",
        }))

        monkeypatch.setattr(config, "KARMA_BASE", tmp_path)
        importlib.reload(packager)
        from karma.packager import _get_live_session_uuids as reloaded

        result = reloaded()
        assert "uuid-good" in result

        importlib.reload(config)
        importlib.reload(packager)


class TestPerDeviceSessionLimit:
    """Tests for per-device session limit override via metadata file."""

    def test_metadata_overrides_team_limit(self, tmp_path, monkeypatch):
        """Per-device session_limit in metadata should override team setting."""
        from karma import config, packager
        import importlib

        # Create metadata file with per-device override
        meta_dir = tmp_path / "metadata-folders" / "acme" / "members"
        meta_dir.mkdir(parents=True)
        (meta_dir / "jay.jay-mac.json").write_text(json.dumps({
            "member_tag": "jay.jay-mac",
            "session_limit": "recent_10",
        }))

        monkeypatch.setattr(config, "KARMA_BASE", tmp_path)
        importlib.reload(packager)
        from karma.packager import get_session_limit as reloaded

        # Team says "all" but device metadata says "recent_10"
        result = reloaded("all", tmp_path, team_name="acme", member_tag="jay.jay-mac")
        assert result == 10

        importlib.reload(config)
        importlib.reload(packager)

    def test_falls_back_to_team_limit(self, tmp_path, monkeypatch):
        """Without metadata file, should use team setting."""
        from karma import config, packager
        import importlib

        monkeypatch.setattr(config, "KARMA_BASE", tmp_path)
        importlib.reload(packager)
        from karma.packager import get_session_limit as reloaded

        result = reloaded("recent_100", tmp_path, team_name="acme", member_tag="jay.jay-mac")
        assert result == 100

        importlib.reload(config)
        importlib.reload(packager)

    def test_metadata_all_uses_team_limit(self, tmp_path, monkeypatch):
        """If metadata says 'all', use team setting (no override)."""
        from karma import config, packager
        import importlib

        meta_dir = tmp_path / "metadata-folders" / "acme" / "members"
        meta_dir.mkdir(parents=True)
        (meta_dir / "jay.jay-mac.json").write_text(json.dumps({
            "member_tag": "jay.jay-mac",
            "session_limit": "all",
        }))

        monkeypatch.setattr(config, "KARMA_BASE", tmp_path)
        importlib.reload(packager)
        from karma.packager import get_session_limit as reloaded

        # Metadata says "all", team says "recent_100" — metadata "all" is still valid
        result = reloaded("recent_100", tmp_path, team_name="acme", member_tag="jay.jay-mac")
        assert result is None  # "all" → None (unlimited)

        importlib.reload(config)
        importlib.reload(packager)

    def test_no_team_name_skips_metadata(self, tmp_path):
        """Without team_name param, should not check metadata."""
        from karma.packager import get_session_limit

        result = get_session_limit("recent_10", tmp_path)
        assert result == 10

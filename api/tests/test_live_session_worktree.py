"""
Tests for worktree session handling bugs:

Bug 1: Desktop worktree live sessions get wrong project mapping.
  resolved_project_encoded_name returns home dir prefix instead of real project
  because _extract_project_prefix_from_worktree returns a non-project prefix
  and the code returns early, skipping the git_root fallback.

Bug 2: Session reconciler only checks same directory for newer JSONL.
  Cross-worktree/real-project session handoffs are missed.
"""

import json
import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent.parent))


# =============================================================================
# Bug 1: resolved_project_encoded_name for Desktop worktrees
# =============================================================================


class TestResolvedProjectEncodedNameDesktopWorktree:
    """Desktop worktree live sessions should resolve to the real project,
    not to the home directory prefix."""

    def _make_live_session_state(
        self,
        transcript_path: str,
        git_root: str | None = None,
        cwd: str = "/tmp/test",
    ):
        """Helper to create a LiveSessionState with minimal required fields."""
        from models.live_session import LiveSessionState

        return LiveSessionState(
            session_id="test-uuid-1234",
            slug="test-slug",
            state="LIVE",
            cwd=cwd,
            transcript_path=transcript_path,
            permission_mode="default",
            last_hook="PostToolUse",
            updated_at="2026-03-06T00:00:00+00:00",
            started_at="2026-03-06T00:00:00+00:00",
            git_root=git_root,
        )

    def test_desktop_worktree_falls_through_to_git_root(self, tmp_path):
        """Desktop worktree prefix (-Users-test) is not a real project dir.
        Should fall through to git_root-based resolution."""
        projects_dir = tmp_path / "projects"
        # Real project exists
        real_project = projects_dir / "-Users-test-Documents-myproject"
        real_project.mkdir(parents=True)
        # Home dir prefix does NOT exist as a project
        # (no projects_dir / "-Users-test" directory)

        # Desktop worktree transcript path
        transcript = (
            projects_dir
            / "-Users-test--claude-worktrees-myproject-focused-jepsen"
            / "abc123.jsonl"
        )

        state = self._make_live_session_state(
            transcript_path=str(transcript),
            git_root="/Users/test/Documents/myproject",
        )

        with patch("config.settings") as mock_settings:
            mock_settings.projects_dir = projects_dir
            result = state.resolved_project_encoded_name

        # Should resolve to the real project via git_root, NOT "-Users-test"
        assert result == "-Users-test-Documents-myproject"

    def test_cli_worktree_still_uses_prefix(self, tmp_path):
        """CLI worktree prefix IS the real project. Should still work."""
        projects_dir = tmp_path / "projects"
        real_project = projects_dir / "-Users-test-Documents-myproject"
        real_project.mkdir(parents=True)

        transcript = (
            projects_dir
            / "-Users-test-Documents-myproject--claude-worktrees-fix-branch"
            / "abc123.jsonl"
        )

        state = self._make_live_session_state(
            transcript_path=str(transcript),
            git_root="/Users/test/Documents/myproject",
        )

        with patch("config.settings") as mock_settings:
            mock_settings.projects_dir = projects_dir
            result = state.resolved_project_encoded_name

        # CLI worktree prefix matches real project - should use prefix directly
        assert result == "-Users-test-Documents-myproject"

    def test_desktop_worktree_no_git_root_returns_primary(self, tmp_path):
        """Desktop worktree without git_root: best effort, return primary."""
        projects_dir = tmp_path / "projects"
        projects_dir.mkdir(parents=True)

        transcript = (
            projects_dir
            / "-Users-test--claude-worktrees-myproject-focused-jepsen"
            / "abc123.jsonl"
        )

        state = self._make_live_session_state(
            transcript_path=str(transcript),
            git_root=None,  # No git_root available
        )

        with patch("config.settings") as mock_settings:
            mock_settings.projects_dir = projects_dir
            result = state.resolved_project_encoded_name

        # Without git_root, falls back to primary (worktree encoded name)
        assert result == "-Users-test--claude-worktrees-myproject-focused-jepsen"

    def test_regular_session_unaffected(self):
        """Regular (non-worktree) sessions should work as before."""
        state = self._make_live_session_state(
            transcript_path="/home/user/.claude/projects/-Users-test-myproject/abc123.jsonl",
            git_root="/Users/test/myproject",
        )

        result = state.resolved_project_encoded_name
        # Regular session - project_encoded_name extracted from transcript path
        assert result == "-Users-test-myproject"


# =============================================================================
# Bug 2: Session reconciler cross-directory detection
# =============================================================================


class TestReconcilerCrossDirectory:
    """Session reconciler should detect newer JSONL files in the real project
    directory, not just the worktree directory."""

    def test_detects_newer_jsonl_in_git_root_project_dir(self, tmp_path):
        """Worktree session should be reconciled when a newer JSONL exists
        in the real project directory (derived from git_root)."""
        import time

        from services.session_reconciler import _has_newer_jsonl

        # Worktree project dir (where stuck session lives)
        wt_dir = tmp_path / "worktree-project"
        wt_dir.mkdir()
        stuck_session = wt_dir / "stuck-uuid.jsonl"
        stuck_session.write_text('{"type": "user"}')
        stuck_mtime = stuck_session.stat().st_mtime

        # Real project dir (where new session was started)
        real_dir = tmp_path / "real-project"
        real_dir.mkdir()

        # Wait a tiny bit to ensure newer mtime
        time.sleep(0.05)

        newer_session = real_dir / "new-uuid.jsonl"
        newer_session.write_text('{"type": "user"}')

        # Standard check: only looks in wt_dir - should NOT find newer
        assert not _has_newer_jsonl(wt_dir, stuck_mtime, "stuck-uuid")

        # With additional_dirs: should find newer in real_dir
        assert _has_newer_jsonl(
            wt_dir, stuck_mtime, "stuck-uuid", additional_dirs=[real_dir]
        )

    def test_no_false_positive_without_newer_files(self, tmp_path):
        """Should not reconcile when no newer files exist anywhere."""
        from services.session_reconciler import _has_newer_jsonl

        wt_dir = tmp_path / "worktree-project"
        wt_dir.mkdir()
        session = wt_dir / "session-uuid.jsonl"
        session.write_text('{"type": "user"}')
        session_mtime = session.stat().st_mtime

        real_dir = tmp_path / "real-project"
        real_dir.mkdir()
        # No files in real_dir

        assert not _has_newer_jsonl(
            wt_dir, session_mtime, "session-uuid", additional_dirs=[real_dir]
        )

    def test_reconcile_once_uses_git_root(self, tmp_path):
        """_reconcile_once should compute the real project dir from git_root
        and pass it to _has_newer_jsonl."""
        import time

        # Create worktree project dir with stuck session
        wt_project_dir = tmp_path / "projects" / "-Users-test--claude-worktrees-myproj-wt1"
        wt_project_dir.mkdir(parents=True)
        stuck_jsonl = wt_project_dir / "stuck-uuid.jsonl"
        stuck_jsonl.write_text('{"type": "user"}')

        # Create real project dir with newer session
        real_project_dir = tmp_path / "projects" / "-Users-test-Documents-myproj"
        real_project_dir.mkdir(parents=True)
        time.sleep(0.05)
        newer_jsonl = real_project_dir / "new-uuid.jsonl"
        newer_jsonl.write_text('{"type": "user"}')

        # Create live session state file (simulating stuck worktree session)
        live_dir = tmp_path / "live-sessions"
        live_dir.mkdir(parents=True)
        state_data = {
            "session_id": "stuck-uuid",
            "slug": "test-slug",
            "state": "LIVE",
            "cwd": "/Users/test/.claude-worktrees/myproj/wt1",
            "transcript_path": str(stuck_jsonl),
            "permission_mode": "default",
            "last_hook": "PostToolUse",
            "updated_at": "2026-03-05T00:00:00+00:00",
            "started_at": "2026-03-05T00:00:00+00:00",
            "git_root": "/Users/test/Documents/myproj",
        }
        state_file = live_dir / "test-slug.json"
        state_file.write_text(json.dumps(state_data))

        with patch(
            "services.session_reconciler.list_live_session_files",
            return_value=[state_file],
        ), patch("config.settings") as mock_settings:
            mock_settings.projects_dir = tmp_path / "projects"

            from services.session_reconciler import _reconcile_once

            count = _reconcile_once(idle_threshold=0)

        # Should have reconciled the stuck session
        assert count == 1

        # Verify state file was updated to ENDED
        updated = json.loads(state_file.read_text())
        assert updated["state"] == "ENDED"
        assert updated["end_reason"] == "session_handoff"

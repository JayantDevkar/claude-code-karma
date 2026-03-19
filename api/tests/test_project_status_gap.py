import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import json
from datetime import datetime, timezone, timedelta
import pytest


def _write_live_session(live_dir, slug, session_id, encoded_name, state="RUNNING", idle_minutes=0):
    now = datetime.now(timezone.utc)
    updated = now - timedelta(minutes=idle_minutes)
    data = {
        "session_id": session_id,
        "state": state,
        "transcript_path": f"/Users/me/.claude/projects/{encoded_name}/{session_id}.jsonl",
        "updated_at": updated.isoformat(),
    }
    (live_dir / f"{slug}.json").write_text(json.dumps(data))


@pytest.fixture
def live_sessions_dir(tmp_path):
    live_dir = tmp_path / "live-sessions"
    live_dir.mkdir()
    return live_dir


class TestGetActiveCounts:
    def test_empty_dir_returns_empty(self, live_sessions_dir):
        from routers.sync_teams import _get_active_counts
        assert _get_active_counts(live_sessions_dir) == {}

    def test_running_session_counted(self, live_sessions_dir):
        from routers.sync_teams import _get_active_counts
        _write_live_session(live_sessions_dir, "s1", "uuid-1", "-Users-me-repo", state="RUNNING")
        result = _get_active_counts(live_sessions_dir)
        assert result.get("-Users-me-repo", 0) == 1

    def test_ended_session_not_counted(self, live_sessions_dir):
        from routers.sync_teams import _get_active_counts
        _write_live_session(live_sessions_dir, "s1", "uuid-1", "-Users-me-repo", state="ENDED")
        result = _get_active_counts(live_sessions_dir)
        assert result.get("-Users-me-repo", 0) == 0

    def test_stale_session_not_counted(self, live_sessions_dir):
        from routers.sync_teams import _get_active_counts
        _write_live_session(live_sessions_dir, "s1", "uuid-1", "-Users-me-repo", state="RUNNING", idle_minutes=35)
        result = _get_active_counts(live_sessions_dir)
        assert result.get("-Users-me-repo", 0) == 0

    def test_multiple_projects(self, live_sessions_dir):
        from routers.sync_teams import _get_active_counts
        _write_live_session(live_sessions_dir, "s1", "uuid-1", "-Users-me-a", state="RUNNING")
        _write_live_session(live_sessions_dir, "s2", "uuid-2", "-Users-me-a", state="RUNNING")
        _write_live_session(live_sessions_dir, "s3", "uuid-3", "-Users-me-b", state="RUNNING")
        result = _get_active_counts(live_sessions_dir)
        assert result["-Users-me-a"] == 2
        assert result["-Users-me-b"] == 1

    def test_worktree_resolution_with_git_root(self, live_sessions_dir):
        from routers.sync_teams import _get_active_counts
        now = datetime.now(timezone.utc)
        data = {
            "session_id": "uuid-wt",
            "state": "RUNNING",
            "transcript_path": "/Users/me/.claude/projects/-Users-me--claude-worktrees-repo-focused-jepsen/uuid-wt.jsonl",
            "updated_at": now.isoformat(),
            "git_root": "/Users/me/repo",
        }
        (live_sessions_dir / "wt.json").write_text(json.dumps(data))
        result = _get_active_counts(live_sessions_dir)
        # Should resolve to -Users-me-repo, not the worktree encoded name
        assert result.get("-Users-me-repo", 0) == 1
        assert "-Users-me--claude-worktrees-repo-focused-jepsen" not in result

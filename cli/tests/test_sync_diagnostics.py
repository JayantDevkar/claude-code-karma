"""Diagnostic tests that verify the sync pipeline state.

These tests use the REAL filesystem (not mocks) to verify the actual
state of the sync pipeline on this machine. They document what IS,
not what SHOULD BE, so they serve as regression tests after fixes.
"""

import json
from pathlib import Path

import pytest


PROJECTS_DIR = Path.home() / ".claude" / "projects"
KARMA_BASE = Path.home() / ".claude_karma"
MAIN_ENCODED = "-Users-jayantdevkar-Documents-GitHub-claude-karma"


@pytest.mark.skipif(
    not PROJECTS_DIR.exists(), reason="No ~/.claude/projects/ on this machine"
)
class TestSyncDiagnostics:
    def test_cli_worktree_dirs_exist(self):
        """CLI worktree dirs should exist in ~/.claude/projects/."""
        from karma.worktree_discovery import find_worktree_dirs

        wt_dirs = find_worktree_dirs(MAIN_ENCODED, PROJECTS_DIR)
        # We know there are at least 5 CLI worktree dirs
        assert len(wt_dirs) >= 5, (
            f"Expected >=5 CLI worktree dirs, found {len(wt_dirs)}: "
            f"{[d.name for d in wt_dirs]}"
        )

    def test_desktop_worktrees_now_discoverable(self):
        """After fix: Desktop worktrees should be found by find_desktop_worktree_dirs."""
        from karma.worktree_discovery import find_desktop_worktree_dirs

        desktop_dirs = find_desktop_worktree_dirs(
            project_name="claude-karma",
            projects_dir=PROJECTS_DIR,
        )
        # Should find focused-jepsen and lucid-villani
        assert len(desktop_dirs) >= 2, (
            f"Expected >=2 Desktop worktree dirs, found {len(desktop_dirs)}"
        )

    def test_all_worktrees_discovered(self):
        """After fix: find_all_worktree_dirs finds both CLI and Desktop worktrees."""
        from karma.worktree_discovery import find_all_worktree_dirs

        all_dirs = find_all_worktree_dirs(
            MAIN_ENCODED,
            "/Users/jayantdevkar/Documents/GitHub/claude-karma",
            PROJECTS_DIR,
        )
        # CLI worktrees (>=5) + Desktop worktrees (>=2)
        assert len(all_dirs) >= 7, (
            f"Expected >=7 total worktree dirs, found {len(all_dirs)}"
        )

    def test_config_team_name_vs_watch_process(self):
        """Config should have a team; watch may be running with wrong name."""
        config_path = KARMA_BASE / "sync-config.json"
        if not config_path.exists():
            pytest.skip("No sync config")

        config = json.loads(config_path.read_text())
        teams = list(config.get("teams", {}).keys())
        assert len(teams) >= 1, "Should have at least one team"
        # Document: the team is NOT called 'beta'
        assert "beta" not in teams, (
            "Team 'beta' should not exist (was renamed)"
        )

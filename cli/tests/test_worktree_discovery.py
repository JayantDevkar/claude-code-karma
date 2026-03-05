"""Tests for worktree discovery."""

from pathlib import Path
import pytest
from karma.worktree_discovery import is_worktree_dir, find_worktree_dirs


class TestIsWorktreeDir:
    def test_cli_worktree_pattern(self):
        assert is_worktree_dir(
            "-Users-jay-GitHub-karma--claude-worktrees-feature-x"
        ) is True

    def test_superpowers_worktree_pattern(self):
        assert is_worktree_dir(
            "-Users-jay-GitHub-karma--worktrees-feature-y"
        ) is True

    def test_desktop_worktree_pattern(self):
        assert is_worktree_dir(
            "-Users-jay--claude-worktrees-karma-focused-jepsen"
        ) is True

    def test_normal_project_not_worktree(self):
        assert is_worktree_dir(
            "-Users-jay-Documents-GitHub-claude-karma"
        ) is False

    def test_empty_string(self):
        assert is_worktree_dir("") is False


class TestFindWorktreeDirs:
    def test_finds_cli_worktrees(self, tmp_path):
        """CLI worktrees: {project}/.claude/worktrees/{name}"""
        projects_dir = tmp_path / "projects"
        main = projects_dir / "-Users-jay-GitHub-karma"
        wt1 = projects_dir / "-Users-jay-GitHub-karma--claude-worktrees-feat-a"
        wt2 = projects_dir / "-Users-jay-GitHub-karma--claude-worktrees-feat-b"
        for d in (main, wt1, wt2):
            d.mkdir(parents=True)
            (d / "session.jsonl").write_text('{"type":"user"}\n')
        result = find_worktree_dirs(
            "-Users-jay-GitHub-karma", projects_dir
        )
        assert len(result) == 2
        assert wt1 in result
        assert wt2 in result

    def test_finds_superpowers_worktrees(self, tmp_path):
        projects_dir = tmp_path / "projects"
        main = projects_dir / "-Users-jay-GitHub-karma"
        wt = projects_dir / "-Users-jay-GitHub-karma--worktrees-fix-bug"
        for d in (main, wt):
            d.mkdir(parents=True)
        result = find_worktree_dirs(
            "-Users-jay-GitHub-karma", projects_dir
        )
        assert wt in result

    def test_ignores_unrelated_projects(self, tmp_path):
        projects_dir = tmp_path / "projects"
        main = projects_dir / "-Users-jay-GitHub-karma"
        unrelated = projects_dir / "-Users-jay-GitHub-other--claude-worktrees-x"
        for d in (main, unrelated):
            d.mkdir(parents=True)
        result = find_worktree_dirs(
            "-Users-jay-GitHub-karma", projects_dir
        )
        assert len(result) == 0

    def test_returns_empty_when_no_worktrees(self, tmp_path):
        projects_dir = tmp_path / "projects"
        main = projects_dir / "-Users-jay-GitHub-karma"
        main.mkdir(parents=True)
        result = find_worktree_dirs(
            "-Users-jay-GitHub-karma", projects_dir
        )
        assert result == []

    def test_returns_empty_when_projects_dir_missing(self, tmp_path):
        result = find_worktree_dirs(
            "-Users-jay-GitHub-karma", tmp_path / "nonexistent"
        )
        assert result == []

"""Tests for worktree discovery."""

from pathlib import Path
import pytest
from karma.worktree_discovery import (
    is_worktree_dir,
    find_worktree_dirs,
    find_desktop_worktree_dirs,
    project_name_from_path,
    find_all_worktree_dirs,
)


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


class TestProjectNameFromPath:
    def test_unix_path(self):
        assert project_name_from_path("/Users/jay/GitHub/claude-karma") == "claude-karma"

    def test_nested_path(self):
        assert project_name_from_path("/Users/jay/Documents/GitHub/my-project") == "my-project"

    def test_trailing_slash(self):
        assert project_name_from_path("/Users/jay/repo/") == "repo"

    def test_windows_path(self):
        assert project_name_from_path("C:\\Users\\jay\\repos\\karma") == "karma"

    def test_single_segment(self):
        assert project_name_from_path("myproject") == "myproject"


class TestFindDesktopWorktreeDirs:
    def test_finds_desktop_worktrees_by_project_name(self, tmp_path):
        projects_dir = tmp_path / "projects"
        worktree_base = tmp_path / ".claude-worktrees"

        main = projects_dir / "-Users-jay-GitHub-claude-karma"
        main.mkdir(parents=True)

        wt_actual = worktree_base / "claude-karma" / "focused-jepsen"
        wt_actual.mkdir(parents=True)

        wt_encoded = projects_dir / "-Users-jay--claude-worktrees-claude-karma-focused-jepsen"
        wt_encoded.mkdir(parents=True)
        (wt_encoded / "session.jsonl").write_text('{"type":"user"}\n')

        result = find_desktop_worktree_dirs(
            project_name="claude-karma",
            projects_dir=projects_dir,
            worktree_base=worktree_base,
        )
        assert len(result) == 1
        assert result[0] == wt_encoded

    def test_finds_multiple_desktop_worktrees(self, tmp_path):
        projects_dir = tmp_path / "projects"
        worktree_base = tmp_path / ".claude-worktrees"

        (projects_dir / "-Users-jay-GitHub-karma").mkdir(parents=True)

        for name in ("focused-jepsen", "lucid-villani"):
            (worktree_base / "karma" / name).mkdir(parents=True)
            wt_enc = projects_dir / f"-Users-jay--claude-worktrees-karma-{name}"
            wt_enc.mkdir(parents=True)
            (wt_enc / "session.jsonl").write_text('{"type":"user"}\n')

        result = find_desktop_worktree_dirs(
            project_name="karma",
            projects_dir=projects_dir,
            worktree_base=worktree_base,
        )
        assert len(result) == 2

    def test_ignores_other_project_worktrees(self, tmp_path):
        projects_dir = tmp_path / "projects"
        worktree_base = tmp_path / ".claude-worktrees"

        (projects_dir / "-Users-jay-GitHub-karma").mkdir(parents=True)

        (worktree_base / "hubdata" / "feat-x").mkdir(parents=True)
        wt_enc = projects_dir / "-Users-jay--claude-worktrees-hubdata-feat-x"
        wt_enc.mkdir(parents=True)

        result = find_desktop_worktree_dirs(
            project_name="karma",
            projects_dir=projects_dir,
            worktree_base=worktree_base,
        )
        assert len(result) == 0

    def test_returns_empty_when_no_worktree_base(self, tmp_path):
        projects_dir = tmp_path / "projects"
        (projects_dir / "-Users-jay-GitHub-karma").mkdir(parents=True)

        result = find_desktop_worktree_dirs(
            project_name="karma",
            projects_dir=projects_dir,
            worktree_base=tmp_path / "nonexistent",
        )
        assert result == []

    def test_returns_empty_when_project_has_no_desktop_worktrees(self, tmp_path):
        projects_dir = tmp_path / "projects"
        worktree_base = tmp_path / ".claude-worktrees"
        worktree_base.mkdir()

        (projects_dir / "-Users-jay-GitHub-karma").mkdir(parents=True)

        result = find_desktop_worktree_dirs(
            project_name="karma",
            projects_dir=projects_dir,
            worktree_base=worktree_base,
        )
        assert result == []

    def test_handles_cleaned_up_worktree_dirs(self, tmp_path):
        projects_dir = tmp_path / "projects"
        worktree_base = tmp_path / ".claude-worktrees"

        (projects_dir / "-Users-jay-GitHub-karma").mkdir(parents=True)
        (worktree_base / "karma").mkdir(parents=True)

        wt_enc = projects_dir / "-Users-jay--claude-worktrees-karma-old-branch"
        wt_enc.mkdir(parents=True)
        (wt_enc / "session.jsonl").write_text('{"type":"user"}\n')

        result = find_desktop_worktree_dirs(
            project_name="karma",
            projects_dir=projects_dir,
            worktree_base=worktree_base,
        )
        assert len(result) == 1


class TestFindAllWorktreeDirs:
    def test_combines_cli_and_desktop_worktrees(self, tmp_path):
        projects_dir = tmp_path / "projects"
        worktree_base = tmp_path / ".claude-worktrees"

        main = projects_dir / "-Users-jay-GitHub-karma"
        main.mkdir(parents=True)

        cli_wt = projects_dir / "-Users-jay-GitHub-karma--claude-worktrees-feat-x"
        cli_wt.mkdir(parents=True)

        (worktree_base / "karma" / "focused-jepsen").mkdir(parents=True)
        desktop_wt = projects_dir / "-Users-jay--claude-worktrees-karma-focused-jepsen"
        desktop_wt.mkdir(parents=True)

        result = find_all_worktree_dirs(
            main_encoded_name="-Users-jay-GitHub-karma",
            project_path="/Users/jay/GitHub/karma",
            projects_dir=projects_dir,
            worktree_base=worktree_base,
        )
        assert len(result) == 2
        assert cli_wt in result
        assert desktop_wt in result

    def test_deduplicates_overlapping_results(self, tmp_path):
        projects_dir = tmp_path / "projects"

        main = projects_dir / "-Users-jay-GitHub-karma"
        main.mkdir(parents=True)

        wt = projects_dir / "-Users-jay-GitHub-karma--claude-worktrees-feat-x"
        wt.mkdir(parents=True)

        result = find_all_worktree_dirs(
            main_encoded_name="-Users-jay-GitHub-karma",
            project_path="/Users/jay/GitHub/karma",
            projects_dir=projects_dir,
        )
        assert result.count(wt) == 1

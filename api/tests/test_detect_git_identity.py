"""Tests for detect_git_identity() utility."""

import subprocess
from unittest.mock import patch

import pytest

import sys
from pathlib import Path

# Add API to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from utils.git import detect_git_identity


def _mock_git_output(url: str):
    """Create a mock for subprocess.run that returns the given URL."""
    return subprocess.CompletedProcess(
        args=[], returncode=0, stdout=f"{url}\n", stderr=""
    )


def _mock_git_failure():
    return subprocess.CompletedProcess(
        args=[], returncode=128, stdout="", stderr="fatal: not a git repository"
    )


class TestSSHUrls:
    @patch("subprocess.run")
    def test_standard_ssh(self, mock_run):
        mock_run.return_value = _mock_git_output("git@github.com:Owner/Repo.git")
        assert detect_git_identity("/some/path") == "owner/repo"

    @patch("subprocess.run")
    def test_ssh_no_dot_git(self, mock_run):
        mock_run.return_value = _mock_git_output("git@github.com:Owner/Repo")
        assert detect_git_identity("/some/path") == "owner/repo"

    @patch("subprocess.run")
    def test_ssh_gitlab(self, mock_run):
        mock_run.return_value = _mock_git_output("git@gitlab.com:MyOrg/MyProject.git")
        assert detect_git_identity("/some/path") == "myorg/myproject"

    @patch("subprocess.run")
    def test_ssh_nested_path(self, mock_run):
        mock_run.return_value = _mock_git_output("git@github.com:org/sub/repo.git")
        assert detect_git_identity("/some/path") == "org/sub/repo"


class TestHTTPSUrls:
    @patch("subprocess.run")
    def test_standard_https(self, mock_run):
        mock_run.return_value = _mock_git_output("https://github.com/Owner/Repo.git")
        assert detect_git_identity("/some/path") == "owner/repo"

    @patch("subprocess.run")
    def test_https_no_dot_git(self, mock_run):
        mock_run.return_value = _mock_git_output("https://github.com/Owner/Repo")
        assert detect_git_identity("/some/path") == "owner/repo"

    @patch("subprocess.run")
    def test_http_url(self, mock_run):
        mock_run.return_value = _mock_git_output("http://github.com/Owner/Repo.git")
        assert detect_git_identity("/some/path") == "owner/repo"


class TestCaseNormalization:
    @patch("subprocess.run")
    def test_uppercase_normalized(self, mock_run):
        mock_run.return_value = _mock_git_output("git@github.com:UPPERCASE/REPO.git")
        assert detect_git_identity("/some/path") == "uppercase/repo"

    @patch("subprocess.run")
    def test_mixed_case(self, mock_run):
        mock_run.return_value = _mock_git_output("https://github.com/JayantDevkar/Claude-Karma.git")
        assert detect_git_identity("/some/path") == "jayantdevkar/claude-karma"


class TestNonGitDirs:
    @patch("subprocess.run")
    def test_not_a_git_repo(self, mock_run):
        mock_run.return_value = _mock_git_failure()
        assert detect_git_identity("/some/path") is None

    @patch("subprocess.run")
    def test_empty_output(self, mock_run):
        mock_run.return_value = subprocess.CompletedProcess(
            args=[], returncode=0, stdout="", stderr=""
        )
        assert detect_git_identity("/some/path") is None

    @patch("subprocess.run")
    def test_timeout(self, mock_run):
        mock_run.side_effect = subprocess.TimeoutExpired(cmd="git", timeout=5)
        assert detect_git_identity("/some/path") is None

    @patch("subprocess.run")
    def test_git_not_installed(self, mock_run):
        mock_run.side_effect = FileNotFoundError("git not found")
        assert detect_git_identity("/some/path") is None

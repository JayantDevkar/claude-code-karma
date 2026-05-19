"""Tests for api/services/git_identity.py."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

_api_dir = Path(__file__).resolve().parent.parent
if str(_api_dir) not in sys.path:
    sys.path.insert(0, str(_api_dir))

from services.git_identity import normalize_git_url, read_git_identity

# ---------------------------------------------------------------------------
# normalize_git_url — pure parser
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "url, expected",
    [
        # https with .git
        ("https://github.com/Owner/Repo.git", "owner/repo"),
        # https without .git
        ("https://github.com/Owner/Repo", "owner/repo"),
        # scp-style ssh with .git
        ("git@github.com:Owner/Repo.git", "owner/repo"),
        # scp-style ssh without .git
        ("git@github.com:Owner/Repo", "owner/repo"),
        # ssh:// scheme
        ("ssh://git@github.com/Owner/Repo.git", "owner/repo"),
        # GitLab — owner/repo extracted naturally
        ("https://gitlab.com/team/project.git", "team/project"),
        # Self-hosted with subgroups — last two segments win
        ("https://gitlab.example.com/group/subgroup/owner/repo.git", "owner/repo"),
        # Mixed case lowercased
        ("HTTPS://GITHUB.COM/UPPER/CASE.git", "upper/case"),
        # Trailing slash tolerated
        ("https://github.com/foo/bar/", "foo/bar"),
        # Whitespace stripped (git config sometimes returns trailing newline)
        ("  https://github.com/foo/bar.git  \n", "foo/bar"),
    ],
)
def test_normalize_git_url_happy_paths(url, expected):
    assert normalize_git_url(url) == expected


@pytest.mark.parametrize(
    "url",
    [
        "",
        None,
        "not-a-url-at-all",
        "/local/path/to/repo",  # local path, not remote
        "https://github.com/",  # no owner/repo
        "https://github.com/onlyone",  # only one segment
        "git@github.com:",  # scp-style with empty path
    ],
)
def test_normalize_git_url_rejects_garbage(url):
    assert normalize_git_url(url) is None


# ---------------------------------------------------------------------------
# read_git_identity — composes the subprocess + parser
# ---------------------------------------------------------------------------


def _make_repo(path: Path, remote_url: str) -> None:
    """Init a bare-bones git repo with origin pointing at `remote_url`.

    Uses a non-empty repo (no commit needed — `git config` works on an
    empty init) and `-c init.defaultBranch=main` to silence the modern
    git hint output.
    """
    subprocess.run(
        ["git", "-c", "init.defaultBranch=main", "init", "-q"],
        cwd=path,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "remote", "add", "origin", remote_url],
        cwd=path,
        check=True,
        capture_output=True,
    )


def test_read_git_identity_real_repo(tmp_path):
    _make_repo(tmp_path, "git@github.com:JayantDevkar/Claude-Code-Karma.git")
    assert read_git_identity(str(tmp_path)) == "jayantdevkar/claude-code-karma"


def test_read_git_identity_https_remote(tmp_path):
    _make_repo(tmp_path, "https://github.com/foo/bar.git")
    assert read_git_identity(str(tmp_path)) == "foo/bar"


def test_read_git_identity_not_a_repo(tmp_path):
    # Empty directory — `git config --get` returns exit code 128
    # ("not a git repository") which we treat as None.
    assert read_git_identity(str(tmp_path)) is None


def test_read_git_identity_repo_with_no_remote(tmp_path):
    subprocess.run(
        ["git", "-c", "init.defaultBranch=main", "init", "-q"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
    )
    # `git config --get` returns exit code 1 when key is absent.
    assert read_git_identity(str(tmp_path)) is None


def test_read_git_identity_none_path_returns_none():
    assert read_git_identity(None) is None
    assert read_git_identity("") is None


def test_read_git_identity_nonexistent_path(tmp_path):
    # `git -C /does/not/exist` returns exit code 128.
    bogus = tmp_path / "does-not-exist"
    assert read_git_identity(str(bogus)) is None


def test_read_git_identity_subdir_returns_parent_remote(tmp_path):
    """Subdirs inherit their parent repo's git config — the same is true
    for our subdir projects (`claude-karma-frontend` etc.), which should
    naturally share git_identity with the main project."""
    _make_repo(tmp_path, "git@github.com:org/repo.git")
    sub = tmp_path / "subdir"
    sub.mkdir()
    assert read_git_identity(str(sub)) == "org/repo"

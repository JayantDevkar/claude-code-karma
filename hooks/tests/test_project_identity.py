"""
Tests for hooks/project_identity.py.

Direct-import unit tests for the pure helpers, plus a subprocess
end-to-end run against a real tmp git repo (skipped without git).
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

_hooks_dir = Path(__file__).resolve().parent.parent
if str(_hooks_dir) not in sys.path:
    sys.path.insert(0, str(_hooks_dir))

import project_identity as pi  # noqa: E402

HOOK = _hooks_dir / "project_identity.py"

requires_git = pytest.mark.skipif(
    shutil.which("git") is None, reason="git not available"
)


NORMALIZE_CASES = [
    ("https://github.com/Owner/Repo.git", "owner/repo"),
    ("https://github.com/Owner/Repo", "owner/repo"),
    ("git@github.com:Owner/Repo.git", "owner/repo"),
    ("ssh://git@github.com/Owner/Repo.git", "owner/repo"),
    ("https://gitlab.example.com/team/sub/Owner/Repo.git", "owner/repo"),
    ("  https://github.com/a/b.git\n", "a/b"),
    ("https://user:token@github.com/Owner/Repo.git", "owner/repo"),
    ("ssh://git@host.example.com:2222/Owner/Repo.git", "owner/repo"),
    ("https://github.com/Owner/Repo/", "owner/repo"),
    ("https://github.com/Owner/Repo.git/", "owner/repo"),
    ("https://github.com/Owner/Repo.GIT", "owner/repo"),
    ("https://dev.azure.com/org/Project/_git/Repo", "project/repo"),
    ("git@ssh.dev.azure.com:v3/org/Project/Repo", "project/repo"),
    ("https://github.com/Owner/_git", "owner/_git"),
    ("ssh://git@host:2222/repo.git", None),
    (
        "ssh://git@host:2222/_git/repo",
        "_git/repo",
    ),  # _git drop only applies at parts[-2] with 3+ segments
    ("", None),
    (None, None),
    ("/local/path/repo", None),
    ("https://github.com/onlyowner", None),
]


@pytest.mark.parametrize("url,expected", NORMALIZE_CASES)
def test_normalize_git_url(url, expected):
    assert pi.normalize_git_url(url) == expected


@pytest.mark.parametrize(
    "cwd,root,expected",
    [
        ("/Users/me/repo", "/Users/me/repo", ""),
        ("/Users/me/repo/", "/Users/me/repo", ""),
        ("/Users/me/repo/api", "/Users/me/repo", "api"),
        ("/Users/me/repo/api/models", "/Users/me/repo", "api/models"),
        ("C:\\Users\\Me\\Repo\\api", "C:/Users/Me/Repo", "api"),
        ("c:\\users\\me\\repo\\Api", "C:/Users/Me/Repo", "Api"),
        ("C:\\Users\\Me\\Repo", "C:/Users/Me/Repo", ""),
        ("/Users/me/repo2", "/Users/me/repo", None),
    ],
)
def test_compute_subdir(cwd, root, expected):
    assert pi.compute_subdir(cwd, root) == expected


def _api_normalize_git_url():
    """Load the API's normalize_git_url without importing the API package.

    Only the function and its two regexes are compiled, so this needs no API
    dependencies and leaks no module names into this test session.
    """
    import ast

    src_path = (
        Path(__file__).resolve().parents[2] / "api" / "services" / "git_identity.py"
    )
    tree = ast.parse(src_path.read_text(encoding="utf-8"))
    keep = [
        node
        for node in tree.body
        if (isinstance(node, ast.FunctionDef) and node.name == "normalize_git_url")
        or (
            isinstance(node, ast.Assign)
            and any(
                getattr(t, "id", None) in ("_SCP_RE", "_URL_RE") for t in node.targets
            )
        )
    ]
    assert len(keep) == 3, (
        "api normalize_git_url or its regexes moved; update this test"
    )
    namespace: dict = {}
    exec("import re\nfrom typing import Optional", namespace)
    exec(
        compile(ast.Module(body=keep, type_ignores=[]), str(src_path), "exec"),
        namespace,
    )
    return namespace["normalize_git_url"]


def test_normalize_git_url_matches_api():
    """The hook can't import the API, so keep its copy in lockstep."""
    api_normalize = _api_normalize_git_url()
    for url, _ in NORMALIZE_CASES:
        assert pi.normalize_git_url(url) == api_normalize(url)


def _git(cwd: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)


def _run_hook(payload: dict) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(HOOK)],
        input=json.dumps(payload, ensure_ascii=False),
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=20,
    )


@pytest.fixture
def project_dir(tmp_path, monkeypatch) -> Path:
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path / "claude"))
    d = tmp_path / "claude" / "projects" / "-encoded"
    d.mkdir(parents=True)
    return d


@requires_git
def test_end_to_end_writes_sidecar(tmp_path, project_dir):
    repo = tmp_path / "repo"
    (repo / "api").mkdir(parents=True)
    _git(repo, "init", "-q")
    _git(repo, "remote", "add", "origin", "git@github.com:Owner/Repo.git")
    cwd = str(repo / "api")

    result = _run_hook({"cwd": cwd, "transcript_path": str(project_dir / "abc.jsonl")})
    assert result.returncode == 0

    data = json.loads((project_dir / pi.SIDECAR_NAME).read_text(encoding="utf-8"))
    assert data == {
        "git_identity": "owner/repo",
        "subdir": "api",
        "project_path": cwd,
        "written_by": "hook",
    }
    assert not list(project_dir.glob(pi.TMP_NAME + "*"))


@requires_git
def test_end_to_end_skips_unchanged(tmp_path, project_dir):
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q")
    _git(repo, "remote", "add", "origin", "https://github.com/a/b.git")
    sidecar = project_dir / pi.SIDECAR_NAME
    sidecar.write_text(
        json.dumps(
            {
                "git_identity": "a/b",
                "subdir": "",
                "project_path": str(repo),
                "written_by": "other",
            }
        ),
        encoding="utf-8",
    )

    result = _run_hook(
        {"cwd": str(repo), "transcript_path": str(project_dir / "abc.jsonl")}
    )
    assert result.returncode == 0
    assert json.loads(sidecar.read_text(encoding="utf-8"))["written_by"] == "other"


@requires_git
def test_end_to_end_no_remote_writes_nothing(tmp_path, project_dir):
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q")

    result = _run_hook(
        {"cwd": str(repo), "transcript_path": str(project_dir / "abc.jsonl")}
    )
    assert result.returncode == 0
    assert not (project_dir / pi.SIDECAR_NAME).exists()


@requires_git
def test_end_to_end_non_ascii_cwd(tmp_path, project_dir):
    repo = tmp_path / "repö-ü"
    repo.mkdir()
    _git(repo, "init", "-q")
    _git(repo, "remote", "add", "origin", "https://github.com/a/b.git")

    result = _run_hook(
        {"cwd": str(repo), "transcript_path": str(project_dir / "abc.jsonl")}
    )
    assert result.returncode == 0
    data = json.loads((project_dir / pi.SIDECAR_NAME).read_text(encoding="utf-8"))
    assert data["project_path"] == str(repo)


@requires_git
def test_end_to_end_refuses_non_project_dir(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q")
    _git(repo, "remote", "add", "origin", "https://github.com/a/b.git")
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()

    result = _run_hook(
        {"cwd": str(repo), "transcript_path": str(elsewhere / "abc.jsonl")}
    )
    assert result.returncode == 0
    assert not (elsewhere / pi.SIDECAR_NAME).exists()


@requires_git
def test_end_to_end_refuses_projects_dir_outside_config(tmp_path, monkeypatch):
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path / "claude"))
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q")
    _git(repo, "remote", "add", "origin", "https://github.com/a/b.git")
    other = tmp_path / "anything" / "projects" / "x"
    other.mkdir(parents=True)

    result = _run_hook({"cwd": str(repo), "transcript_path": str(other / "abc.jsonl")})
    assert result.returncode == 0
    assert not (other / pi.SIDECAR_NAME).exists()


def test_end_to_end_missing_project_dir_is_silent(tmp_path):
    missing = tmp_path / "claude" / "projects" / "-gone"
    result = _run_hook(
        {"cwd": str(tmp_path), "transcript_path": str(missing / "abc.jsonl")}
    )
    assert result.returncode == 0
    assert result.stdout == ""


@pytest.mark.parametrize("stdin", ["", "not json", "[]", "{}"])
def test_bad_input_exits_zero(stdin):
    result = subprocess.run(
        [sys.executable, str(HOOK)],
        input=stdin,
        capture_output=True,
        text=True,
        timeout=20,
    )
    assert result.returncode == 0
    assert result.stdout == ""

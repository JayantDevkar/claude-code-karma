"""Git lookups run one subprocess per path per cache window, shared by /projects and the indexer."""

from __future__ import annotations

import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

import utils
from db import indexer
from db.schema import ensure_schema
from services import git_identity


def _git(*args: str, cwd: Path) -> None:
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)


def _repo(path: Path, remote: str | None = None) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    _git("init", "-q", cwd=path)
    _git(
        "-c",
        "user.email=t@t",
        "-c",
        "user.name=t",
        "commit",
        "-q",
        "--allow-empty",
        "-m",
        "x",
        cwd=path,
    )
    if remote:
        _git("remote", "add", "origin", remote, cwd=path)
    return path


@pytest.fixture
def git_calls(monkeypatch):
    """Count git subprocesses while still running them for real."""
    calls: list[list[str]] = []
    real_run = subprocess.run

    def counting_run(args, *a, **k):
        if args and args[0] == "git":
            calls.append(list(args))
        return real_run(args, *a, **k)

    monkeypatch.setattr(subprocess, "run", counting_run)
    return calls


def test_git_root_is_one_subprocess_then_cached(tmp_path, git_calls):
    repo = _repo(tmp_path / "repo")
    git_calls.clear()

    assert Path(utils.resolve_git_root(str(repo))) == repo.resolve()
    assert Path(utils.resolve_git_root(str(repo))) == repo.resolve()

    assert len(git_calls) == 1


def test_git_root_of_a_submodule_is_its_superproject(tmp_path):
    sub = _repo(tmp_path / "sub")
    sup = _repo(tmp_path / "super")
    _git("-c", "protocol.file.allow=always", "submodule", "add", "-q", str(sub), "mod", cwd=sup)

    assert Path(utils.resolve_git_root(str(sup / "mod"))) == sup.resolve()


def test_git_root_outside_a_repo_is_none_and_cached(tmp_path, git_calls):
    plain = tmp_path / "plain"
    plain.mkdir()
    git_calls.clear()

    assert utils.resolve_git_root(str(plain)) is None
    assert utils.resolve_git_root(str(plain)) is None
    assert len(git_calls) == 1


def test_git_root_timeout_is_not_cached(tmp_path, monkeypatch):
    repo = _repo(tmp_path / "repo")
    real_run = subprocess.run
    outcomes = iter(["timeout", "real"])

    def flaky_run(args, *a, **k):
        if args and args[0] == "git" and next(outcomes) == "timeout":
            raise subprocess.TimeoutExpired(args, 5)
        return real_run(args, *a, **k)

    monkeypatch.setattr(subprocess, "run", flaky_run)

    assert utils.resolve_git_root(str(repo)) is None
    assert Path(utils.resolve_git_root(str(repo))) == repo.resolve()


def test_git_identity_is_cached(tmp_path, git_calls):
    repo = _repo(tmp_path / "repo", remote="git@github.com:org/repo.git")
    git_calls.clear()

    assert git_identity.read_git_identity(str(repo)) == "org/repo"
    assert git_identity.read_git_identity(str(repo)) == "org/repo"
    assert len(git_calls) == 1


def test_index_pass_warms_the_git_root_cache(tmp_path, git_calls):
    repo = _repo(tmp_path / "repo")
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    ensure_schema(conn)
    encoded = str(repo).replace("/", "-")
    conn.execute(
        "INSERT INTO sessions (uuid, project_encoded_name, project_path, jsonl_mtime) "
        "VALUES ('s1', ?, ?, 1.0)",
        (encoded, str(repo)),
    )
    git_calls.clear()

    indexer._update_project_summaries(conn)
    spawned_by_pass = len(git_calls)
    utils.resolve_git_root(str(repo))

    assert spawned_by_pass > 0
    assert len(git_calls) == spawned_by_pass  # /projects then hits the cache

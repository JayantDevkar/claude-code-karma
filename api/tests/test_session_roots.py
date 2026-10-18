"""Extra session roots: merging other machines' synced ~/.claude dirs."""

from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from config import settings
from db import indexer
from db.schema import ensure_schema
from models.project import Project
from services import session_roots
from services.session_roots import (
    SIDECAR_NAME,
    compute_subdir,
    get_remote_dirs,
    read_sidecar,
    session_jsonl_path,
    write_sidecar,
)


def _write_session(project_dir: Path, uuid: str, cwd: str) -> Path:
    project_dir.mkdir(parents=True, exist_ok=True)
    lines = [
        {
            "type": "user",
            "uuid": f"{uuid}-u",
            "sessionId": uuid,
            "cwd": cwd,
            "timestamp": "2026-10-01T10:00:00.000Z",
            "message": {"role": "user", "content": "hello"},
        },
        {
            "type": "assistant",
            "uuid": f"{uuid}-a",
            "parentUuid": f"{uuid}-u",
            "sessionId": uuid,
            "cwd": cwd,
            "timestamp": "2026-10-01T10:00:05.000Z",
            "message": {
                "id": f"msg-{uuid}",
                "role": "assistant",
                "model": "claude-sonnet-4-5",
                "content": [{"type": "text", "text": "hi"}],
                "usage": {"input_tokens": 10, "output_tokens": 5},
            },
        },
    ]
    path = project_dir / f"{uuid}.jsonl"
    path.write_text("\n".join(json.dumps(line) for line in lines) + "\n", encoding="utf-8")
    return path


def _sidecar(project_dir: Path, identity: str, subdir: str = "") -> None:
    project_dir.mkdir(parents=True, exist_ok=True)
    (project_dir / SIDECAR_NAME).write_text(
        json.dumps({"git_identity": identity, "subdir": subdir}), encoding="utf-8"
    )


@pytest.fixture
def machines(tmp_path, monkeypatch):
    """Local ~/.claude plus one synced root named 'laptop'."""
    local = tmp_path / "local" / ".claude"
    (local / "projects").mkdir(parents=True)
    remote = tmp_path / "sync" / "laptop" / ".claude"
    (remote / "projects").mkdir(parents=True)
    monkeypatch.setattr(settings, "claude_base", local)

    def configure(**root_opts):
        entry = {"name": "laptop", "path": str(remote), **root_opts}
        monkeypatch.setattr(settings, "extra_roots", [entry])
        session_roots.clear_cache()

    configure()
    return local / "projects", remote / "projects", configure


# =============================================================================
# Matching
# =============================================================================


def test_no_roots_configured(monkeypatch):
    monkeypatch.setattr(settings, "extra_roots", [])
    assert get_remote_dirs() == ()


def test_sidecar_identity_merges_different_paths(machines):
    local, remote, _ = machines
    _write_session(local / "C--code-karma", "l1", "C:/code/karma")
    _sidecar(local / "C--code-karma", "jayantdevkar/claude-code-karma")
    _write_session(remote / "-home-me-src-karma", "r1", "/home/me/src/karma")
    _sidecar(remote / "-home-me-src-karma", "jayantdevkar/claude-code-karma")

    (rd,) = get_remote_dirs()
    assert rd.canonical == "C--code-karma"
    assert rd.matched_by == "sidecar"


def test_sidecar_subdir_must_match(machines):
    local, remote, configure = machines
    configure(match_by_name=False)
    _write_session(local / "C--code-karma", "l1", "C:/code/karma")
    _sidecar(local / "C--code-karma", "o/karma", "")
    _write_session(remote / "-home-me-karma-api", "r1", "/home/me/karma/api")
    _sidecar(remote / "-home-me-karma-api", "o/karma", "api")

    (rd,) = get_remote_dirs()
    assert rd.matched_by == "standalone"
    assert rd.canonical == "-home-me-karma-api"


def test_project_map_wins(machines):
    local, remote, configure = machines
    configure(project_map={"-home-me-x": "C--elsewhere"})
    _write_session(local / "C--elsewhere", "l1", "C:/elsewhere")
    _write_session(remote / "-home-me-x", "r1", "/home/me/x")

    (rd,) = get_remote_dirs()
    assert (rd.canonical, rd.matched_by) == ("C--elsewhere", "project_map")


def test_path_map_rewrites_remote_path(machines):
    local, remote, configure = machines
    configure(path_map={"/home/me/code": "C:/Users/me"}, match_by_name=False)
    _write_session(local / "C--Users-me-karma", "l1", "C:/Users/me/karma")
    _write_session(remote / "-home-me-code-karma", "r1", "/home/me/code/karma")

    (rd,) = get_remote_dirs()
    assert (rd.canonical, rd.matched_by) == ("C--Users-me-karma", "path_map")


def test_path_map_is_case_insensitive_on_encoded_name(machines):
    local, remote, configure = machines
    configure(path_map={"/home/me": "C:/Users/me"}, match_by_name=False)
    # Claude Code on Windows may write a lowercase drive letter
    _write_session(local / "c--Users-me-karma", "l1", "c:/Users/me/karma")
    _write_session(remote / "-home-me-karma", "r1", "/home/me/karma")

    (rd,) = get_remote_dirs()
    assert rd.canonical == "c--Users-me-karma"


def test_same_encoded_name_merges(machines):
    local, remote, _ = machines
    _write_session(local / "-Users-me-repo", "l1", "/Users/me/repo")
    _write_session(remote / "-Users-me-repo", "r1", "/Users/me/repo")

    (rd,) = get_remote_dirs()
    assert (rd.canonical, rd.matched_by) == ("-Users-me-repo", "same_name")


def test_folder_name_guess_only_when_unique(machines):
    local, remote, _ = machines
    _write_session(local / "C--a-karma", "l1", "C:/a/karma")
    _write_session(remote / "-home-me-karma", "r1", "/home/me/karma")

    (rd,) = get_remote_dirs()
    assert (rd.canonical, rd.matched_by) == ("C--a-karma", "folder_name")

    _write_session(local / "C--b-karma", "l2", "C:/b/karma")
    session_roots.clear_cache()
    (rd,) = get_remote_dirs()
    assert rd.matched_by == "standalone"


def test_folder_name_guess_can_be_disabled(machines):
    local, remote, configure = machines
    configure(match_by_name=False)
    _write_session(local / "C--a-karma", "l1", "C:/a/karma")
    _write_session(remote / "-home-me-karma", "r1", "/home/me/karma")

    (rd,) = get_remote_dirs()
    assert rd.matched_by == "standalone"


def test_invalid_roots_are_ignored(tmp_path, monkeypatch):
    local = tmp_path / ".claude"
    (local / "projects").mkdir(parents=True)
    monkeypatch.setattr(settings, "claude_base", local)
    monkeypatch.setattr(
        settings,
        "extra_roots",
        [
            {"name": "local", "path": str(tmp_path / "a")},  # reserved name
            {"name": "bad name!", "path": str(tmp_path / "b")},
            {"name": "self", "path": str(local)},  # this machine's own dir
            {"name": "ok"},  # no path
        ],
    )
    session_roots.clear_cache()
    assert session_roots.get_extra_roots() == ()


def test_roots_file_is_read(tmp_path, monkeypatch):
    remote = tmp_path / "r" / ".claude"
    (remote / "projects").mkdir(parents=True)
    roots = tmp_path / "extra-roots.json"
    roots.write_text(json.dumps([{"name": "box", "path": str(remote)}]), encoding="utf-8")
    monkeypatch.setattr(settings, "extra_roots", [])
    monkeypatch.setattr(session_roots, "roots_file", lambda: roots)
    session_roots.clear_cache()

    (root,) = session_roots.get_extra_roots()
    assert root.name == "box"
    assert root.projects_dir == remote / "projects"


# =============================================================================
# Sidecars
# =============================================================================


@pytest.mark.parametrize(
    "path,root,expected",
    [
        ("/r/repo", "/r/repo", ""),
        ("/r/repo/api", "/r/repo", "api"),
        ("C:\\R\\Repo\\api\\x", "c:/r/repo", "api/x"),
        ("/elsewhere", "/r/repo", None),
        (None, "/r", None),
        ("/r/repo", None, None),
    ],
)
def test_compute_subdir(path, root, expected):
    assert compute_subdir(path, root) == expected


def test_bad_sidecar_types_do_not_hide_root(machines):
    _, remote, _ = machines
    _write_session(remote / "-home-me-a", "r1", "/home/me/a")
    (remote / "-home-me-a" / SIDECAR_NAME).write_text(
        json.dumps({"git_identity": 7, "subdir": [], "project_path": {"x": 1}}), encoding="utf-8"
    )
    _write_session(remote / "-home-me-b", "r2", "/home/me/b")

    assert sorted(rd.path.name for rd in get_remote_dirs()) == ["-home-me-a", "-home-me-b"]


def test_write_sidecar_skips_path_outside_git_root(tmp_path):
    write_sidecar(tmp_path, "o/repo", "/elsewhere/x", "/r/repo")
    assert read_sidecar(tmp_path) is None


def test_write_sidecar_removes_stale_sidecar_outside_git_root(tmp_path):
    _sidecar(tmp_path, "o/repo", "")  # written by an older version
    write_sidecar(tmp_path, "o/repo", "/elsewhere/x", "/r/repo")
    assert read_sidecar(tmp_path) is None


def test_write_sidecar_keeps_sidecar_when_git_root_unknown(tmp_path):
    _sidecar(tmp_path, "o/repo", "api")
    write_sidecar(tmp_path, "o/repo", "/r/repo/api", None)  # e.g. git timed out
    assert read_sidecar(tmp_path)["subdir"] == "api"


def test_write_sidecar_roundtrip_and_skip_without_identity(tmp_path):
    write_sidecar(tmp_path, None, "/r/repo", "/r/repo")
    assert read_sidecar(tmp_path) is None

    write_sidecar(tmp_path, "o/repo", "/r/repo/api", "/r/repo")
    data = read_sidecar(tmp_path)
    assert data["git_identity"] == "o/repo"
    assert data["subdir"] == "api"


# =============================================================================
# Project model + lookup
# =============================================================================


def test_project_lists_sessions_from_all_machines(machines):
    local, remote, _ = machines
    _write_session(local / "-Users-me-repo", "l1", "/Users/me/repo")
    _write_session(remote / "-Users-me-repo", "r1", "/Users/me/repo")
    # Same session synced back: the local copy wins
    _write_session(remote / "-Users-me-repo", "l1", "/Users/me/repo")

    project = Project.from_encoded_name("-Users-me-repo")
    names = sorted(p.parent.parent.parent.name + "/" + p.stem for p in project.list_session_paths())
    assert names == [".claude/l1", ".claude/r1"]
    assert project.get_session("r1").jsonl_path == remote / "-Users-me-repo" / "r1.jsonl"


def test_remote_only_project(machines):
    _, remote, configure = machines
    configure(match_by_name=False)
    _write_session(remote / "-home-me-solo", "r1", "/home/me/solo")

    project = Project.from_encoded_name("-home-me-solo")
    assert project.path == "/home/me/solo"
    assert project.exists
    assert [p.stem for p in project.list_session_paths()] == ["r1"]
    assert session_roots.standalone_canonicals() == ["-home-me-solo"]


def test_remote_session_uses_remote_claude_base(machines):
    _, remote, _ = machines
    path = _write_session(remote / "-home-me-solo", "r1", "/home/me/solo")

    from models import Session

    assert Session.from_path(path).claude_base_dir == remote.parent
    assert session_jsonl_path("-home-me-solo", "r1") == path


# =============================================================================
# Indexer
# =============================================================================


@pytest.fixture
def mem_db():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    ensure_schema(conn)
    return conn


def test_indexer_merges_remote_sessions(machines, mem_db):
    local, remote, _ = machines
    _write_session(local / "-Users-me-repo", "l1", "/Users/me/repo")
    _write_session(remote / "-Users-me-repo", "r1", "/Users/me/repo")
    _write_session(remote / "-Users-me-repo", "l1", "/Users/me/repo")

    indexer.sync_all_projects(mem_db)

    rows = {
        r["uuid"]: (r["project_encoded_name"], r["source_root"])
        for r in mem_db.execute("SELECT uuid, project_encoded_name, source_root FROM sessions")
    }
    assert rows == {
        "l1": ("-Users-me-repo", None),
        "r1": ("-Users-me-repo", "laptop"),
    }


def test_indexer_drops_sessions_of_removed_root(machines, mem_db, monkeypatch):
    local, remote, _ = machines
    _write_session(local / "-Users-me-repo", "l1", "/Users/me/repo")
    _write_session(remote / "-home-me-solo", "r1", "/home/me/solo")
    indexer.sync_all_projects(mem_db)
    assert mem_db.execute("SELECT COUNT(*) FROM sessions").fetchone()[0] == 2

    monkeypatch.setattr(settings, "extra_roots", [])
    indexer.sync_all_projects(mem_db)

    uuids = [r[0] for r in mem_db.execute("SELECT uuid FROM sessions")]
    assert uuids == ["l1"]


# =============================================================================
# Review regressions
# =============================================================================


@pytest.mark.parametrize("bad", [{"path_map": ["x"]}, {"project_map": "x"}, 42])
def test_bad_root_entry_is_skipped_not_fatal(tmp_path, monkeypatch, bad):
    good = tmp_path / "good" / ".claude"
    (good / "projects").mkdir(parents=True)
    entry = {"name": "bad", "path": str(tmp_path / "b"), **bad} if isinstance(bad, dict) else bad
    monkeypatch.setattr(settings, "extra_roots", [entry, {"name": "good", "path": str(good)}])
    session_roots.clear_cache()
    assert [r.name for r in session_roots.get_extra_roots()] == ["good"]


def test_folder_name_guess_rejects_different_git_remotes(machines):
    local, remote, _ = machines
    _write_session(local / "C--work-api", "l1", "C:/work/api")
    _sidecar(local / "C--work-api", "b/api")
    _write_session(remote / "-home-me-api", "r1", "/home/me/api")
    _sidecar(remote / "-home-me-api", "a/api")

    (rd,) = get_remote_dirs()
    assert rd.matched_by == "standalone"


def test_remote_worktree_follows_its_project(machines):
    local, remote, _ = machines
    _write_session(local / "-Users-me-repo", "l1", "/Users/me/repo")
    _write_session(remote / "-Users-me-repo", "r1", "/Users/me/repo")
    wt = "-Users-me-repo--claude-worktrees-feature"
    _write_session(remote / wt, "r2", "/Users/me/repo/.claude/worktrees/feature")

    by_dir = {rd.path.name: (rd.canonical, rd.matched_by) for rd in get_remote_dirs()}
    assert by_dir[wt] == ("-Users-me-repo", "worktree")


def test_project_map_to_missing_local_dir_is_listed(machines):
    _, remote, configure = machines
    configure(project_map={"-home-me-x": "C--nowhere"}, match_by_name=False)
    _write_session(remote / "-home-me-x", "r1", "/home/me/x")

    assert session_roots.standalone_canonicals() == ["C--nowhere"]


def test_offline_root_keeps_its_sessions(machines, mem_db):
    local, remote, _ = machines
    _write_session(local / "-Users-me-repo", "l1", "/Users/me/repo")
    _write_session(remote / "-home-me-solo", "r1", "/home/me/solo")
    indexer.sync_all_projects(mem_db)

    # Sync drive unmounted: root still configured, dir gone
    remote.rename(remote.parent / "projects-offline")
    indexer.sync_all_projects(mem_db)

    uuids = sorted(r[0] for r in mem_db.execute("SELECT uuid FROM sessions"))
    assert uuids == ["l1", "r1"]


def test_local_copy_reclaims_remote_tagged_row(machines, mem_db):
    local, remote, _ = machines
    remote_copy = _write_session(remote / "-Users-me-repo", "s1", "/Users/me/repo")
    indexer.sync_all_projects(mem_db)
    assert mem_db.execute("SELECT source_root FROM sessions").fetchone()[0] == "laptop"

    # Same file appears locally with the same mtime
    local_copy = _write_session(local / "-Users-me-repo", "s1", "/Users/me/repo")
    import os

    st = remote_copy.stat()
    os.utime(local_copy, (st.st_atime, st.st_mtime))
    indexer.sync_all_projects(mem_db)

    assert mem_db.execute("SELECT source_root FROM sessions").fetchone()[0] is None


def test_same_session_in_two_roots_first_wins(tmp_path, monkeypatch, mem_db):
    local = tmp_path / "local" / ".claude"
    (local / "projects").mkdir(parents=True)
    monkeypatch.setattr(settings, "claude_base", local)
    roots = []
    for name in ("alpha", "beta"):
        base = tmp_path / name / ".claude"
        _write_session(base / "projects" / "-home-me-solo", "s1", "/home/me/solo")
        roots.append({"name": name, "path": str(base)})
    monkeypatch.setattr(settings, "extra_roots", roots)
    session_roots.clear_cache()

    indexer.sync_all_projects(mem_db)
    indexer.sync_all_projects(mem_db)

    rows = mem_db.execute("SELECT source_root FROM sessions").fetchall()
    assert [r[0] for r in rows] == ["alpha"]


def test_build_failure_keeps_roots_so_sessions_survive(machines, mem_db, monkeypatch):
    local, remote, _ = machines
    _write_session(local / "-Users-me-repo", "l1", "/Users/me/repo")
    _write_session(remote / "-home-me-solo", "r1", "/home/me/solo")
    indexer.sync_all_projects(mem_db)
    assert session_roots.get_extra_roots()

    def boom(roots):
        raise OSError("remote vanished mid-scan")

    monkeypatch.setattr(session_roots, "_build", boom)
    indexer.sync_all_projects(mem_db)

    assert [r.name for r in session_roots.get_extra_roots()] == ["laptop"]
    uuids = sorted(r[0] for r in mem_db.execute("SELECT uuid FROM sessions"))
    assert uuids == ["l1", "r1"]

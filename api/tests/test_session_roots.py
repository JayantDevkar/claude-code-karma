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
    local, remote, configure = machines
    configure(match_by_name=True)
    _write_session(local / "C--a-karma", "l1", "C:/a/karma")
    _write_session(remote / "-home-me-karma", "r1", "/home/me/karma")

    (rd,) = get_remote_dirs()
    assert (rd.canonical, rd.matched_by) == ("C--a-karma", "folder_name")

    _write_session(local / "C--b-karma", "l2", "C:/b/karma")
    session_roots.clear_cache()
    (rd,) = get_remote_dirs()
    assert rd.matched_by == "standalone"


def test_folder_name_guess_is_off_by_default(machines):
    local, remote, _ = machines
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
    local, remote, configure = machines
    configure(match_by_name=True)
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


# =============================================================================
# Config robustness, root validation, path_map edge cases, endpoint
# =============================================================================


def _roots_file(tmp_path, monkeypatch, content: str) -> Path:
    roots = tmp_path / "extra-roots.json"
    roots.write_text(content, encoding="utf-8")
    monkeypatch.setattr(settings, "extra_roots", [])
    monkeypatch.setattr(session_roots, "roots_file", lambda: roots)
    session_roots.clear_cache()
    return roots


def test_malformed_roots_file_keeps_previous_roots_and_sessions(tmp_path, monkeypatch, mem_db):
    local = tmp_path / "local" / ".claude"
    (local / "projects").mkdir(parents=True)
    monkeypatch.setattr(settings, "claude_base", local)
    remote = tmp_path / "sync" / "laptop" / ".claude"
    _write_session(remote / "projects" / "-home-me-solo", "r1", "/home/me/solo")
    roots = _roots_file(
        tmp_path, monkeypatch, json.dumps([{"name": "laptop", "path": str(remote)}])
    )
    indexer.sync_all_projects(mem_db)
    assert session_roots.roots_config_ok()

    roots.write_text('[{"name": "laptop", ', encoding="utf-8")  # mid-edit
    indexer.sync_all_projects(mem_db)

    assert not session_roots.roots_config_ok()
    assert [r.name for r in session_roots.get_extra_roots()] == ["laptop"]
    assert [r[0] for r in mem_db.execute("SELECT uuid FROM sessions")] == ["r1"]

    roots.write_text("[]", encoding="utf-8")  # root really removed
    indexer.sync_all_projects(mem_db)
    assert session_roots.roots_config_ok()
    assert mem_db.execute("SELECT COUNT(*) FROM sessions").fetchone()[0] == 0


def test_roots_file_must_hold_a_list(tmp_path, monkeypatch):
    _roots_file(tmp_path, monkeypatch, '{"name": "laptop"}')
    assert session_roots.get_extra_roots() == ()
    assert not session_roots.roots_config_ok()


def test_malformed_roots_file_on_cold_start_keeps_remote_rows(tmp_path, monkeypatch, mem_db):
    local = tmp_path / "local" / ".claude"
    (local / "projects").mkdir(parents=True)
    monkeypatch.setattr(settings, "claude_base", local)
    remote = tmp_path / "sync" / "laptop" / ".claude"
    _write_session(remote / "projects" / "-home-me-solo", "r1", "/home/me/solo")
    roots = _roots_file(
        tmp_path, monkeypatch, json.dumps([{"name": "laptop", "path": str(remote)}])
    )
    indexer.sync_all_projects(mem_db)

    roots.write_text("{", encoding="utf-8")
    session_roots.clear_cache()  # API restart: no previous roots in memory
    indexer.sync_all_projects(mem_db)

    assert session_roots.get_extra_roots() == ()
    assert [r[0] for r in mem_db.execute("SELECT uuid FROM sessions")] == ["r1"]


def test_path_map_drive_root_prefix_is_case_insensitive(machines):
    local, remote, configure = machines
    configure(path_map={"C:/": "/home/me/"})
    _write_session(local / "-home-me-karma", "l1", "/home/me/karma")
    _write_session(remote / "c--karma", "r1", "c:/karma")

    (rd,) = get_remote_dirs()
    assert (rd.canonical, rd.matched_by) == ("-home-me-karma", "path_map")


def test_nested_duplicate_and_file_roots_are_rejected(tmp_path, monkeypatch):
    local = tmp_path / ".claude"
    (local / "projects").mkdir(parents=True)
    monkeypatch.setattr(settings, "claude_base", local)
    good = tmp_path / "sync" / "box" / ".claude"
    (good / "projects").mkdir(parents=True)
    a_file = tmp_path / "roots.txt"
    a_file.write_text("x", encoding="utf-8")
    monkeypatch.setattr(
        settings,
        "extra_roots",
        [
            {"name": "inside", "path": str(local / "projects" / "sub")},
            {"name": "contains", "path": str(tmp_path)},
            {"name": "good", "path": str(good)},
            {"name": "twin", "path": str(good / "projects")},  # same dir, other spelling
            {"name": "file", "path": str(a_file)},
            {"name": "missing", "path": str(tmp_path / "sync" / "offline" / ".claude")},
        ],
    )
    session_roots.clear_cache()
    assert [r.name for r in session_roots.get_extra_roots()] == ["good", "missing"]


def test_path_map_root_prefix_is_ignored(machines):
    _, remote, configure = machines
    configure(path_map={"/": "C:/", "/home/me": "C:/Users/me"})
    (root,) = session_roots.get_extra_roots()
    assert root.path_map == (("/home/me", "C:/Users/me"),)


def test_path_map_posix_prefix_is_case_sensitive(machines):
    local, remote, configure = machines
    configure(path_map={"/home/Me": "C:/Users/me"})
    _write_session(local / "C--Users-me-karma", "l1", "C:/Users/me/karma")
    _write_session(remote / "-home-me-karma", "r1", "/home/me/karma")

    (rd,) = get_remote_dirs()
    assert rd.matched_by == "standalone"


def test_path_map_windows_prefix_is_case_insensitive(machines):
    local, remote, configure = machines
    configure(path_map={"D:/Work": "/home/me"})
    _write_session(local / "-home-me-karma", "l1", "/home/me/karma")
    _write_session(remote / "d--work-karma", "r1", "d:/work/karma")

    (rd,) = get_remote_dirs()
    assert (rd.canonical, rd.matched_by) == ("-home-me-karma", "path_map")


def test_identity_claimed_by_two_local_clones_is_ambiguous(machines):
    local, remote, _ = machines
    for name, cwd in (("C--a-karma", "C:/a/karma"), ("C--b-karma", "C:/b/karma")):
        _write_session(local / name, name, cwd)
        _sidecar(local / name, "o/karma")
    _write_session(remote / "-home-me-karma", "r1", "/home/me/karma")
    _sidecar(remote / "-home-me-karma", "o/karma")

    (rd,) = get_remote_dirs()
    assert rd.matched_by == "standalone"


def test_partial_remote_file_is_reindexed_when_it_grows(machines, mem_db):
    import os

    _, remote, _ = machines
    full = _write_session(remote / "-home-me-solo", "r1", "/home/me/solo")
    data = full.read_bytes()
    st = full.stat()
    full.write_bytes(data[: len(data) // 2])  # copy in progress, final mtime already stamped
    os.utime(full, (st.st_atime, st.st_mtime))
    indexer.sync_all_projects(mem_db)
    size_before = mem_db.execute("SELECT jsonl_size FROM sessions WHERE uuid='r1'").fetchone()[0]

    full.write_bytes(data)
    os.utime(full, (st.st_atime, st.st_mtime))
    indexer.sync_all_projects(mem_db)

    size_after = mem_db.execute("SELECT jsonl_size FROM sessions WHERE uuid='r1'").fetchone()[0]
    assert (size_before, size_after) == (len(data) // 2, len(data))


def test_no_roots_means_no_sidecar_write(tmp_path, monkeypatch, mem_db):
    local = tmp_path / ".claude"
    (local / "projects").mkdir(parents=True)
    monkeypatch.setattr(settings, "claude_base", local)
    repo = tmp_path / "repo"
    repo.mkdir()
    encoded = Project.encode_path(str(repo))
    _write_session(local / "projects" / encoded, "l1", str(repo))
    import services.git_identity
    import utils

    monkeypatch.setattr(services.git_identity, "read_git_identity", lambda p: "o/repo")
    monkeypatch.setattr(utils, "resolve_git_root", lambda p: p)

    monkeypatch.setattr(settings, "extra_roots", [])
    session_roots.clear_cache()
    indexer.sync_all_projects(mem_db)
    assert not (local / "projects" / encoded / SIDECAR_NAME).exists()

    # Nor does it delete a stale one (path outside its repo) without roots
    _sidecar(local / "projects" / encoded, "o/repo", "")
    monkeypatch.setattr(utils, "resolve_git_root", lambda p: str(tmp_path / "elsewhere"))
    indexer.sync_all_projects(mem_db)
    assert read_sidecar(local / "projects" / encoded)["git_identity"] == "o/repo"
    monkeypatch.setattr(utils, "resolve_git_root", lambda p: p)

    other = tmp_path / "sync" / "laptop" / ".claude"
    (other / "projects").mkdir(parents=True)
    monkeypatch.setattr(settings, "extra_roots", [{"name": "laptop", "path": str(other)}])
    session_roots.clear_cache()
    indexer.sync_all_projects(mem_db)
    assert read_sidecar(local / "projects" / encoded)["git_identity"] == "o/repo"


def test_extra_roots_endpoints(machines):
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    from main import app

    _, remote, _ = machines
    _write_session(remote / "-home-me-solo", "r1", "/home/me/solo")
    client = TestClient(app, base_url="http://localhost", client=("127.0.0.1", 50000))

    body = client.get("/extra-roots").json()
    assert body["config_ok"] is True
    assert [r["name"] for r in body["roots"]] == ["laptop"]
    assert body["roots"][0]["project_dirs"][0]["matched_by"] == "standalone"

    _write_session(remote / "-home-me-later", "r2", "/home/me/later")
    assert len(client.get("/extra-roots").json()["roots"][0]["project_dirs"]) == 1  # cached
    assert len(client.post("/extra-roots/refresh").json()["roots"][0]["project_dirs"]) == 2

    assert client.get("/extra-roots", headers={"host": "karma.example.com"}).status_code == 403
    assert (
        client.post("/extra-roots/refresh", headers={"origin": "https://evil"}).status_code == 403
    )


def test_root_dir_that_fails_to_list_does_not_abort_the_pass(tmp_path, monkeypatch, mem_db):
    local = tmp_path / "local" / ".claude"
    (local / "projects").mkdir(parents=True)
    monkeypatch.setattr(settings, "claude_base", local)
    roots = []
    for name in ("alpha", "beta"):
        base = tmp_path / name / ".claude"
        _write_session(base / "projects" / "-home-me-solo", f"{name}-1", "/home/me/solo")
        roots.append({"name": name, "path": str(base)})
    monkeypatch.setattr(settings, "extra_roots", roots)
    session_roots.clear_cache()
    dropped = tmp_path / "alpha" / ".claude" / "projects" / "-home-me-solo"
    real_glob, real_get_remote_dirs = Path.glob, session_roots.get_remote_dirs

    def glob(self, pattern, *args, **kwargs):
        if self == dropped:
            raise OSError("stale file handle")
        return real_glob(self, pattern, *args, **kwargs)

    def get_remote_dirs():
        remote_dirs = real_get_remote_dirs()
        monkeypatch.setattr(Path, "glob", glob)  # mount drops after the dirs were mapped
        return remote_dirs

    monkeypatch.setattr(session_roots, "get_remote_dirs", get_remote_dirs)
    stats = indexer.sync_all_projects(mem_db)

    assert stats["errors"] == 1
    assert [r[0] for r in mem_db.execute("SELECT source_root FROM sessions")] == ["beta"]


def test_extra_roots_env_takes_plain_paths_and_bad_json_does_not_stop_startup(
    tmp_path, monkeypatch
):
    from config import Settings

    (tmp_path / "local" / ".claude" / "projects").mkdir(parents=True)
    monkeypatch.setattr(settings, "claude_base", tmp_path / "local" / ".claude")
    monkeypatch.setattr(session_roots, "roots_file", lambda: tmp_path / "extra-roots.json")
    remote = tmp_path / "sync" / "laptop" / ".claude"
    (remote / "projects").mkdir(parents=True)

    monkeypatch.setattr(settings, "extra_roots", Settings(extra_roots=[str(remote)]).extra_roots)
    session_roots.clear_cache()
    assert [r.name for r in session_roots.get_extra_roots()] == ["laptop"]

    monkeypatch.setenv("CLAUDE_KARMA_EXTRA_ROOTS", json.dumps([str(remote)]))
    monkeypatch.setattr(settings, "extra_roots", Settings().extra_roots)
    session_roots.clear_cache()
    assert [r.name for r in session_roots.get_extra_roots()] == ["laptop"]
    assert session_roots.roots_config_ok()

    for bad in ("[{bad json", '{"path": "/x"}'):
        monkeypatch.setenv("CLAUDE_KARMA_EXTRA_ROOTS", bad)
        monkeypatch.setattr(settings, "extra_roots", Settings().extra_roots)
        session_roots.invalidate()
        assert [r.name for r in session_roots.get_extra_roots()] == ["laptop"]  # previous list
        assert not session_roots.roots_config_ok()


def test_rejected_root_entry_keeps_valid_roots_and_deletes_nothing(tmp_path, monkeypatch, mem_db):
    local = tmp_path / "local" / ".claude"
    (local / "projects").mkdir(parents=True)
    monkeypatch.setattr(settings, "claude_base", local)
    entries = []
    for name in ("laptop", "box"):
        base = tmp_path / "sync" / name / ".claude"
        _write_session(base / "projects" / f"-home-me-{name}", f"{name}-1", f"/home/me/{name}")
        entries.append({"name": name, "path": str(base)})
    roots = _roots_file(tmp_path, monkeypatch, json.dumps(entries))
    indexer.sync_all_projects(mem_db)
    assert session_roots.roots_config_ok()

    entries[1]["path_map"] = ["typo"]  # box's entry is now invalid
    roots.write_text(json.dumps(entries), encoding="utf-8")
    indexer.sync_all_projects(mem_db)

    assert [r.name for r in session_roots.get_extra_roots()] == ["laptop"]
    assert not session_roots.roots_config_ok()
    assert sorted(r[0] for r in mem_db.execute("SELECT source_root FROM sessions")) == [
        "box",
        "laptop",
    ]

"""Every encoded project name Karma builds must be the dir name Claude Code writes."""

from __future__ import annotations

import json
import re
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from config import settings
from db import indexer
from db.schema import ensure_schema
from models.history import get_archived_prompts
from models.live_session import LiveSessionState, SessionState
from models.project import Project
from services.desktop_sessions import extract_worktree_info, get_real_project_encoded_name

# Same real names as hooks/tests/test_project_identity.py
LONG_CWD = "/srv/" + "a" * 120 + "/" + "b" * 120
LONG_DIR = "-srv-" + "a" * 120 + "-" + "b" * 74 + "-ak6yfc"


@pytest.fixture
def mem_db():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    ensure_schema(conn)
    yield conn
    conn.close()


def _write_session(project_dir: Path, uuid: str, cwd: str) -> None:
    project_dir.mkdir(parents=True)
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
    text = "\n".join(json.dumps(line) for line in lines) + "\n"
    (project_dir / f"{uuid}.jsonl").write_text(text, encoding="utf-8")


@pytest.mark.parametrize(
    "path, dir_name",
    [
        ("/opt/acme-app", "-opt-acme-app"),
        ("/opt/acme_app", "-opt-acme-app"),
        ("/opt/site.v1.2", "-opt-site-v1-2"),
        ("/opt/my repo (2)", "-opt-my-repo--2-"),
        ("/opt/acme-app/.worktrees/phase1", "-opt-acme-app--worktrees-phase1"),
        ("C:\\Users\\alice\\.agents\\my_skills", "C--Users-alice--agents-my-skills"),
        ("/home/me/caf\u00e9/\U0001f600x", "-home-me-caf----x"),
        (LONG_CWD, LONG_DIR),
    ],
)
def test_encode_path_matches_claude_code(path, dir_name):
    assert Project.encode_path(path) == dir_name


def test_long_path_is_recovered_from_its_hashed_dir(tmp_path):
    project_dir = tmp_path / LONG_DIR
    project_dir.mkdir()
    (project_dir / "s1.jsonl").write_text(
        json.dumps({"type": "user", "cwd": LONG_CWD}) + "\n", encoding="utf-8"
    )
    assert Project.from_encoded_name(LONG_DIR, claude_projects_dir=tmp_path).path == LONG_CWD


def test_from_path_names_the_real_project_dir(tmp_path):
    repo = tmp_path / "my_repo"
    project = Project.from_path(repo, claude_projects_dir=tmp_path / "projects")
    assert project.encoded_name.endswith("-my-repo")


def test_archived_prompts_link_to_the_real_project_dir(tmp_path):
    line = {
        "display": "hello",
        "timestamp": 1760000000000,
        "project": "/home/me/my_repo",
        "sessionId": "gone-session",
    }
    (tmp_path / "history.jsonl").write_text(json.dumps(line) + "\n", encoding="utf-8")
    (tmp_path / "projects").mkdir()

    projects, _, _ = get_archived_prompts(tmp_path, project_filter="-home-me-my-repo")

    assert [p.encoded_name for p in projects] == ["-home-me-my-repo"]


def _live_state(transcript: Path, git_root: str) -> LiveSessionState:
    now = datetime(2026, 10, 1, 10, 0, 0, tzinfo=timezone.utc)
    return LiveSessionState(
        session_id="s1",
        state=SessionState.LIVE,
        cwd="/work/wt",
        transcript_path=str(transcript),
        last_hook="SessionStart",
        started_at=now,
        updated_at=now,
        git_root=git_root,
    )


@pytest.mark.parametrize(
    "git_root, dir_name",
    [
        ("/home/me/my_repo", "-home-me-my-repo"),
        ("C:\\Users\\me\\my_repo", "C--Users-me-my-repo"),
    ],
)
def test_live_session_falls_back_to_its_git_root_dir(tmp_path, git_root, dir_name):
    projects = tmp_path / "projects"
    (projects / dir_name).mkdir(parents=True)
    (projects / dir_name / "s1.jsonl").write_text("{}\n", encoding="utf-8")

    state = _live_state(projects / "-work-wt" / "s1.jsonl", git_root)

    assert state.resolved_project_encoded_name == dir_name
    assert state.transcript_exists


def test_desktop_origin_cwd_finds_the_real_project_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "claude_base", tmp_path / ".claude")
    (settings.projects_dir / "-Users-me-my-repo").mkdir(parents=True)
    meta = {"u1": {"originCwd": "/Users/me/my_repo"}}

    # A Desktop worktree's prefix is not its project, so only originCwd can find it
    with (
        patch("services.desktop_sessions.load_desktop_metadata", return_value=meta),
        patch("services.desktop_sessions.WORKTREE_BASE", tmp_path / "no-worktrees"),
    ):
        real = get_real_project_encoded_name("-Users-me--claude-worktrees-my-repo-wt", ["u1"])

    assert real == "-Users-me-my-repo"


def test_desktop_worktree_with_underscore_rolls_up_to_its_project(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "claude_base", tmp_path / ".claude")
    (settings.projects_dir / "-Users-me-my-project").mkdir(parents=True)
    base = tmp_path / "claude-worktrees"
    worktree = base / "my_project" / "wt_1"
    worktree.mkdir(parents=True)
    dir_name = re.sub(r"[^a-zA-Z0-9]", "-", str(worktree))

    with (
        patch("services.desktop_sessions.load_desktop_metadata", return_value={}),
        patch("services.desktop_sessions.WORKTREE_BASE", base),
    ):
        assert get_real_project_encoded_name(dir_name, ["u1"]) == "-Users-me-my-project"


@pytest.mark.skipif(sys.platform != "win32", reason="needs a path with a drive letter")
def test_desktop_worktree_info_ignores_drive_letter_case(tmp_path):
    base = tmp_path / "claude-worktrees"
    (base / "proj" / "wt").mkdir(parents=True)
    dir_name = re.sub(r"[^a-zA-Z0-9]", "-", str(base / "proj" / "wt"))

    with patch("services.desktop_sessions.WORKTREE_BASE", base):
        assert extract_worktree_info(dir_name[0].swapcase() + dir_name[1:]) is not None


def test_project_left_with_no_sessions_is_dropped(tmp_path, monkeypatch, mem_db):
    local = tmp_path / ".claude"
    monkeypatch.setattr(settings, "claude_base", local)
    kept = local / "projects" / "-home-me-kept"
    gone = local / "projects" / "-home-me-gone"
    _write_session(kept, "k1", "/home/me/kept")
    _write_session(gone, "g1", "/home/me/gone")
    indexer.sync_all_projects(mem_db)

    (gone / "g1.jsonl").unlink()
    gone.rmdir()
    indexer.sync_all_projects(mem_db)

    names = [r[0] for r in mem_db.execute("SELECT encoded_name FROM projects")]
    assert names == ["-home-me-kept"]

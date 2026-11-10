"""One session UUID stored in two project dirs: the repo's and a worktree's.

Claude Code copies a session's transcript when it moves into a worktree, so
the same ``{uuid}.jsonl`` exists under the repo dir (history up to the move)
and the worktree dir (the same history plus everything after it). Karma must
count the complete copy, not whichever dir it happens to read first.
"""

from __future__ import annotations

import json
import os
import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from config import settings
from db import indexer
from db.schema import ensure_schema
from services import session_roots

REPO = "-home-alice-myrepo"
WORKTREE = "-home-alice-myrepo--claude-worktrees-feature"
OUT_PER_TURN = 100


def _write_turns(project_dir: Path, uuid: str, turns: int) -> Path:
    """A session of `turns` user/assistant pairs; a shorter copy is a prefix of a longer one."""
    project_dir.mkdir(parents=True, exist_ok=True)
    lines = []
    parent = None
    for i in range(turns):
        user = {
            "type": "user",
            "uuid": f"{uuid}-u{i}",
            "parentUuid": parent,
            "sessionId": uuid,
            "cwd": "/home/alice/myrepo",
            "timestamp": f"2026-10-01T10:{i:02d}:00.000Z",
            "message": {"role": "user", "content": f"step {i}"},
        }
        assistant = {
            "type": "assistant",
            "uuid": f"{uuid}-a{i}",
            "parentUuid": user["uuid"],
            "sessionId": uuid,
            "cwd": "/home/alice/myrepo",
            "timestamp": f"2026-10-01T10:{i:02d}:30.000Z",
            "message": {
                "id": f"msg-{uuid}-{i}",
                "role": "assistant",
                "model": "claude-sonnet-4-5",
                "content": [{"type": "text", "text": "done"}],
                "usage": {"input_tokens": 10, "output_tokens": OUT_PER_TURN},
            },
        }
        lines += [user, assistant]
        parent = assistant["uuid"]
    path = project_dir / f"{uuid}.jsonl"
    path.write_text("\n".join(json.dumps(line) for line in lines) + "\n", encoding="utf-8")
    return path


@pytest.fixture
def claude_dirs(tmp_path, monkeypatch):
    """Local ~/.claude and a synced root named 'vps'; returns their projects dirs."""
    local = tmp_path / "local" / ".claude"
    (local / "projects").mkdir(parents=True)
    remote = tmp_path / "sync" / "vps" / ".claude"
    (remote / "projects").mkdir(parents=True)
    monkeypatch.setattr(settings, "claude_base", local)
    monkeypatch.setattr(settings, "extra_roots", [{"name": "vps", "path": str(remote)}])
    session_roots.clear_cache()
    # A local repo dir so the synced worktree dir maps onto the same project
    _write_turns(local / "projects" / REPO, "anchor", 1)
    return local / "projects", remote / "projects"


@pytest.fixture
def mem_db():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    ensure_schema(conn)
    return conn


def _client(monkeypatch):
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    from main import app

    monkeypatch.setattr(settings, "use_sqlite", False)  # never touch the developer's index
    return TestClient(app, base_url="http://localhost", client=("127.0.0.1", 50000))


def _indexed_output_tokens(conn, uuid: str) -> int:
    return conn.execute("SELECT output_tokens FROM sessions WHERE uuid = ?", (uuid,)).fetchone()[0]


@pytest.mark.parametrize("side", ["local", "synced"])
@pytest.mark.parametrize("longer", [WORKTREE, REPO])
def test_index_and_detail_count_the_complete_copy(claude_dirs, mem_db, monkeypatch, side, longer):
    local, remote = claude_dirs
    base = local if side == "local" else remote
    uuid = f"s-{side}-{'wt' if longer == WORKTREE else 'repo'}"
    shorter = REPO if longer == WORKTREE else WORKTREE
    older = _write_turns(base / shorter, uuid, 2)
    _write_turns(base / longer, uuid, 5)
    os.utime(older, (1_700_000_000, 1_700_000_000))  # the copy stopped growing earlier

    indexer.sync_all_projects(mem_db)
    indexer.sync_all_projects(mem_db)  # a second pass must not swap in the other copy

    assert _indexed_output_tokens(mem_db, uuid) == 5 * OUT_PER_TURN
    body = _client(monkeypatch).get(f"/sessions/{uuid}").json()
    assert body["total_output_tokens"] == 5 * OUT_PER_TURN


SUPERPOWERS_WT = "-home-alice-myrepo--worktrees-phase1"
SUB_IN_PER_AGENT = 1000


def _write_agent(project_dir: Path, uuid: str, agent_id: str, turns: int = 1) -> Path:
    subagents = project_dir / uuid / "subagents"
    subagents.mkdir(parents=True, exist_ok=True)
    lines = [
        {
            "type": "assistant",
            "uuid": f"{agent_id}-a{i}",
            "agentId": agent_id,
            "sessionId": uuid,
            "isSidechain": True,
            "timestamp": f"2026-10-01T10:00:{i:02d}.000Z",
            "message": {
                "id": f"msg-{agent_id}-{i}",
                "role": "assistant",
                "model": "claude-sonnet-4-5",
                "content": [{"type": "text", "text": "found it"}],
                "usage": {"input_tokens": SUB_IN_PER_AGENT, "output_tokens": 1},
            },
        }
        for i in range(turns)
    ]
    path = subagents / f"agent-{agent_id}.jsonl"
    path.write_text("\n".join(json.dumps(line) for line in lines) + "\n", encoding="utf-8")
    return path


@pytest.mark.parametrize("side", ["local", "synced"])
@pytest.mark.parametrize("worktree", [SUPERPOWERS_WT, WORKTREE])
def test_subagents_in_a_worktree_dir_count_for_the_session(
    claude_dirs, mem_db, monkeypatch, side, worktree
):
    """The session JSONL stays in the repo dir; its subagents land in a worktree dir."""
    local, remote = claude_dirs
    base = local if side == "local" else remote
    uuid = f"s-sub-{side}-{len(worktree)}"
    _write_turns(base / REPO, uuid, 1)
    _write_agent(base / REPO, uuid, "a1")
    _write_agent(base / worktree, uuid, "a2")
    _write_agent(base / worktree, uuid, "a3")
    # The same agent in both dirs counts once, from its complete copy
    _write_agent(base / REPO, uuid, "a4", turns=1)
    _write_agent(base / worktree, uuid, "a4", turns=2)
    expected = 5 * SUB_IN_PER_AGENT

    indexer.sync_all_projects(mem_db)

    row = mem_db.execute(
        "SELECT subagent_count, subagent_input_tokens FROM sessions WHERE uuid = ?", (uuid,)
    ).fetchone()
    assert tuple(row) == (4, expected)
    body = _client(monkeypatch).get(f"/sessions/{uuid}").json()
    assert body["subagent_input_tokens"] == expected


def test_second_pass_does_not_reindex_duplicate_copies(claude_dirs, mem_db):
    """Two copies under one project must not overwrite each other on every sync."""
    local, _ = claude_dirs
    older = _write_turns(local / REPO, "s-thrash", 2)
    _write_turns(local / WORKTREE, "s-thrash", 5)
    os.utime(older, (1_700_000_000, 1_700_000_000))  # the copy stopped growing earlier

    indexer.sync_all_projects(mem_db)
    stats = indexer.sync_all_projects(mem_db)

    assert stats["indexed"] == 0

"""Automatic Haiku titles for sessions synced from other machines."""

from __future__ import annotations

import json
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from config import settings
from db import indexer
from db.schema import ensure_schema
from services import session_roots, synced_titles
from services.session_title_cache import SessionTitleCache, title_cache
from services.synced_titles import title_synced_sessions

NOW = datetime(2026, 11, 2, 11, 0, tzinfo=timezone.utc)
PROJECT = "-home-alice-shop"


def _write_synced(
    project_dir: Path,
    uuid: str,
    prompt: str,
    end: str = "2026-11-02T10:00:05.000Z",
    cost_state: bool = True,
    truncated: bool = False,
    trailing: tuple[str, ...] = (),
) -> Path:
    project_dir.mkdir(parents=True, exist_ok=True)
    lines = [
        {
            "type": "user",
            "uuid": f"{uuid}-u",
            "sessionId": uuid,
            "cwd": "/home/alice/shop",
            "timestamp": end.replace("00:05.000Z", "00:00.000Z"),
            "message": {"role": "user", "content": prompt},
        },
        {
            "type": "assistant",
            "uuid": f"{uuid}-a",
            "parentUuid": f"{uuid}-u",
            "sessionId": uuid,
            "cwd": "/home/alice/shop",
            "timestamp": end,
            "message": {
                "id": f"msg-{uuid}",
                "role": "assistant",
                "model": "claude-sonnet-4-5",
                "content": [{"type": "text", "text": "Done."}],
                "usage": {"input_tokens": 10, "output_tokens": 5},
            },
        },
    ]
    text = "\n".join(json.dumps(line) for line in lines) + "\n"
    if truncated:
        text += '{"type": "cost-st'
    elif cost_state:
        text += json.dumps({"type": "cost-state", "sessionId": uuid}) + "\n"
    text += "".join(json.dumps({"type": kind, "sessionId": uuid}) + "\n" for kind in trailing)
    path = project_dir / f"{uuid}.jsonl"
    path.write_text(text, encoding="utf-8")
    return path


@pytest.fixture
def machines(tmp_path, monkeypatch):
    """Local ~/.claude plus one synced root named 'vps'."""
    local = tmp_path / "local" / ".claude"
    (local / "projects").mkdir(parents=True)
    remote = tmp_path / "sync" / "vps" / ".claude"
    (remote / "projects").mkdir(parents=True)
    monkeypatch.setattr(settings, "claude_base", local)
    monkeypatch.setattr(settings, "use_sqlite", True)
    # Keep title cache writes out of the real ~/.claude_karma
    monkeypatch.setattr(
        SessionTitleCache, "_cache_path", staticmethod(lambda name: tmp_path / f"{name}.json")
    )
    monkeypatch.setattr(title_cache, "_project_data", {})

    def configure(**root_opts):
        entry = {"name": "vps", "path": str(remote), **root_opts}
        monkeypatch.setattr(settings, "extra_roots", [entry])
        session_roots.clear_cache()

    configure()
    return local / "projects", remote / "projects", configure


@pytest.fixture
def mem_db():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    ensure_schema(conn)
    return conn


class _FakeGenerator:
    def __init__(self):
        self.calls = []
        self.result = ("Fix login redirect", "haiku")

    def __call__(self, prompt, response, git, claude_bin="claude"):
        self.calls.append((prompt, response, git))
        self.claude_bin = claude_bin
        return self.result


@pytest.fixture
def fake(monkeypatch):
    gen = _FakeGenerator()
    monkeypatch.setattr(synced_titles, "load_title_generator", lambda: gen)
    monkeypatch.setattr(synced_titles, "find_claude_cli", lambda: "/opt/claude/bin/claude")
    monkeypatch.setattr(synced_titles, "_fallbacks", {})
    return gen


def _row(conn, uuid):
    return conn.execute("SELECT * FROM sessions WHERE uuid = ?", (uuid,)).fetchone()


def test_ended_synced_session_gets_one_title(machines, mem_db, fake):
    _, remote, configure = machines
    configure(auto_titles=True)
    _write_synced(remote / PROJECT, "r1", "Fix the login redirect")
    indexer.sync_all_projects(mem_db)

    assert title_synced_sessions(mem_db, now=NOW) == 1
    assert fake.calls == [("Fix the login redirect", None, None)]
    assert json.loads(_row(mem_db, "r1")["session_titles"]) == ["Fix login redirect"]
    assert title_synced_sessions(mem_db, now=NOW) == 0 and len(fake.calls) == 1


def test_reindex_does_not_retitle(machines, mem_db, fake):
    _, remote, configure = machines
    configure(auto_titles=True)
    _write_synced(remote / PROJECT, "r1", "Fix the login redirect")
    indexer.sync_all_projects(mem_db)
    assert title_synced_sessions(mem_db, now=NOW) == 1

    mem_db.execute("UPDATE sessions SET jsonl_mtime = jsonl_mtime - 1")
    mem_db.commit()
    indexer.sync_all_projects(mem_db)
    title_synced_sessions(mem_db, now=NOW)

    assert len(fake.calls) == 1 and _row(mem_db, "r1")["title_attempted_at"] is not None


@pytest.mark.parametrize(
    "case", ["flag_off", "no_cost_state", "resumed", "ended_25h_ago", "local_session"]
)
def test_not_titled(case, machines, mem_db, fake):
    local, remote, configure = machines
    configure(auto_titles=case != "flag_off")
    if case == "local_session":
        _write_synced(local / PROJECT, "l1", "Add a cart page")
    elif case == "no_cost_state":
        _write_synced(remote / PROJECT, "r1", "Add a cart page", cost_state=False)
    elif case == "resumed":
        _write_synced(remote / PROJECT, "r1", "Add a cart page", trailing=("system", "user"))
    elif case == "ended_25h_ago":
        _write_synced(remote / PROJECT, "r1", "Add a cart page", end="2026-11-01T10:00:05.000Z")
    else:
        _write_synced(remote / PROJECT, "r1", "Add a cart page")
    indexer.sync_all_projects(mem_db)

    assert title_synced_sessions(mem_db, now=NOW) == 0 and fake.calls == []


def test_resolved_cli_is_passed_to_the_generator(machines, mem_db, fake):
    _, remote, configure = machines
    configure(auto_titles=True)
    _write_synced(remote / PROJECT, "r1", "Fix the login redirect")
    indexer.sync_all_projects(mem_db)

    assert title_synced_sessions(mem_db, now=NOW) == 1
    assert fake.claude_bin == "/opt/claude/bin/claude"


def test_cli_found_outside_path(monkeypatch, tmp_path):
    cli = tmp_path / "bin" / "claude"
    cli.parent.mkdir()
    cli.write_text("#!/bin/sh\n")
    cli.chmod(0o755)
    monkeypatch.setattr(synced_titles.shutil, "which", lambda name: None)
    monkeypatch.setattr(synced_titles, "_CLAUDE_DIRS", (tmp_path / "nope", cli.parent))
    assert synced_titles.find_claude_cli() == str(cli)


def test_missing_cli_marks_nothing_and_warns_once(machines, mem_db, fake, monkeypatch, caplog):
    _, remote, configure = machines
    configure(auto_titles=True)
    _write_synced(remote / PROJECT, "r1", "Fix the login redirect")
    indexer.sync_all_projects(mem_db)
    monkeypatch.setattr(synced_titles, "find_claude_cli", lambda: None)
    monkeypatch.setattr(synced_titles, "_warned_no_cli", False)

    with caplog.at_level("WARNING", logger="services.synced_titles"):
        assert title_synced_sessions(mem_db, now=NOW) == 0
        assert title_synced_sessions(mem_db, now=NOW) == 0
    assert fake.calls == [] and _row(mem_db, "r1")["title_attempted_at"] is None
    assert len([r for r in caplog.records if "claude CLI" in r.message]) == 1


def test_fallback_is_retried_then_given_up(machines, mem_db, fake):
    _, remote, configure = machines
    configure(auto_titles=True)
    _write_synced(remote / PROJECT, "r1", "Fix the login redirect")
    indexer.sync_all_projects(mem_db)
    fake.result = ("Fix the lo", "fallback")

    for _ in range(synced_titles.MAX_FALLBACKS - 1):
        assert title_synced_sessions(mem_db, now=NOW) == 0
        assert _row(mem_db, "r1")["title_attempted_at"] is None
    assert title_synced_sessions(mem_db, now=NOW) == 0
    row = _row(mem_db, "r1")
    assert row["session_titles"] in (None, "", "[]") and row["title_attempted_at"] is not None
    title_synced_sessions(mem_db, now=NOW)
    assert len(fake.calls) == synced_titles.MAX_FALLBACKS


def test_fallback_ends_the_pass(machines, mem_db, fake):
    _, remote, configure = machines
    configure(auto_titles=True)
    _write_synced(remote / PROJECT, "r1", "Fix the login redirect", end="2026-11-02T10:30:05.000Z")
    _write_synced(remote / PROJECT, "r2", "Add a cart page")
    indexer.sync_all_projects(mem_db)
    fake.result = ("Fix the lo", "fallback")

    assert title_synced_sessions(mem_db, now=NOW) == 0
    assert len(fake.calls) == 1 and _row(mem_db, "r2")["title_attempted_at"] is None
    fake.result = ("Fix login redirect", "haiku")
    assert title_synced_sessions(mem_db, now=NOW) == 2


def test_bookkeeping_after_cost_state_still_counts_as_ended(machines, mem_db, fake):
    _, remote, configure = machines
    configure(auto_titles=True)
    trailing = ("file-history-snapshot", "system", "pr-link", "queue-operation")
    _write_synced(remote / PROJECT, "r1", "Fix the login redirect", trailing=trailing)
    indexer.sync_all_projects(mem_db)

    assert title_synced_sessions(mem_db, now=NOW) == 1


def test_unended_sessions_do_not_starve_ended_ones(machines, mem_db, fake):
    _, remote, configure = machines
    configure(auto_titles=True)
    for i in range(synced_titles.AUTO_TITLE_BATCH):
        end = f"2026-11-02T10:{10 + i:02d}:05.000Z"
        _write_synced(remote / PROJECT, f"live{i}", "Still running", end=end, cost_state=False)
    _write_synced(remote / PROJECT, "r1", "Fix the login redirect")
    indexer.sync_all_projects(mem_db)

    assert title_synced_sessions(mem_db, now=NOW) == 1
    assert fake.calls == [("Fix the login redirect", None, None)]


def test_mid_copy_file_is_retried_once_complete(machines, mem_db, fake):
    _, remote, configure = machines
    configure(auto_titles=True)
    _write_synced(remote / PROJECT, "r1", "Fix the login redirect", truncated=True)
    indexer.sync_all_projects(mem_db)

    assert title_synced_sessions(mem_db, now=NOW) == 0
    assert _row(mem_db, "r1")["title_attempted_at"] is None

    _write_synced(remote / PROJECT, "r1", "Fix the login redirect")
    indexer.sync_all_projects(mem_db)
    assert title_synced_sessions(mem_db, now=NOW) == 1


def test_missing_hook_module_is_a_no_op(machines, mem_db, monkeypatch, tmp_path, caplog):
    _, remote, configure = machines
    configure(auto_titles=True)
    _write_synced(remote / PROJECT, "r1", "Fix the login redirect")
    indexer.sync_all_projects(mem_db)
    monkeypatch.setattr(synced_titles, "_HOOK_PATH", tmp_path / "missing.py")
    synced_titles.load_title_generator.cache_clear()
    try:
        with caplog.at_level("WARNING", logger="services.synced_titles"):
            assert title_synced_sessions(mem_db, now=NOW) == 0
            assert title_synced_sessions(mem_db, now=NOW) == 0
    finally:
        synced_titles.load_title_generator.cache_clear()
    assert _row(mem_db, "r1")["title_attempted_at"] is None
    assert len([r for r in caplog.records if "session_title_generator" in r.message]) == 1

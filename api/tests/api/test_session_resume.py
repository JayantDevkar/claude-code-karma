"""Endpoint tests for short-link resolution and focus-or-resume.

Covers:
- ``GET /sessions/resolve/{short_id}`` (exact uuid, prefix, ambiguity →
  newest match, 404, 400)
- ``POST /sessions/{uuid}/resume-in-terminal`` (live → focus, ended →
  launch, invalid uuid 400, unknown 404, missing project dir 409,
  cross-origin 403)

The actual OS launch/focus is mocked; ``services.terminal_launch`` has its
own unit tests. Both the projects dir and the live-sessions dir are
redirected to tmp paths.
"""

from __future__ import annotations

import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import pytest

_tests_dir = Path(__file__).resolve().parent.parent
_api_dir = _tests_dir.parent
if str(_api_dir) not in sys.path:
    sys.path.insert(0, str(_api_dir))

from fastapi import FastAPI
from fastapi.testclient import TestClient

UUID_A = "aaaaaaaa-1111-2222-3333-444444444444"
UUID_B = "aaaaaaaa-5555-6666-7777-888888888888"


def _write_jsonl(projects_dir: Path, encoded: str, uuid: str, cwd: str) -> Path:
    project_dir = projects_dir / encoded
    project_dir.mkdir(parents=True, exist_ok=True)
    jsonl = project_dir / f"{uuid}.jsonl"
    jsonl.write_text(json.dumps({"cwd": cwd, "sessionId": uuid}) + "\n")
    return jsonl


def _write_live_state(
    live_dir: Path, session_id: str, cwd: str, terminal: dict | None, slug: str | None = None
) -> None:
    now = datetime.now(timezone.utc).isoformat()
    data = {
        "session_id": session_id,
        "slug": slug,
        "state": "LIVE",
        "cwd": cwd,
        "transcript_path": f"{cwd}/{session_id}.jsonl",
        "permission_mode": "default",
        "last_hook": "PostToolUse",
        "updated_at": now,
        "started_at": now,
        "session_ids": [session_id],
    }
    if terminal is not None:
        data["terminal"] = terminal
    (live_dir / f"{slug or session_id}.json").write_text(json.dumps(data))


@pytest.fixture
def env(tmp_path, monkeypatch):
    """Test app plus redirected projects and live-sessions dirs."""
    projects_dir = tmp_path / "claude" / "projects"
    projects_dir.mkdir(parents=True)
    live_dir = tmp_path / "live-sessions"
    live_dir.mkdir()

    import models.live_session as live_model
    from routers import sessions

    monkeypatch.setattr(live_model, "get_live_sessions_dir", lambda: live_dir)
    monkeypatch.setattr(sessions.settings, "claude_base", tmp_path / "claude")
    monkeypatch.setattr(sessions.settings, "cors_origins", ["http://localhost:5180"])

    app = FastAPI()
    app.include_router(sessions.router, prefix="/sessions")
    client = TestClient(app)
    return client, projects_dir, live_dir


# ---------------------------------------------------------------------------
# GET /sessions/resolve/{short_id}
# ---------------------------------------------------------------------------


def test_resolve_full_uuid(env):
    client, projects_dir, _ = env
    _write_jsonl(projects_dir, "-Users-test-project", UUID_A, "/Users/test/project")

    res = client.get(f"/sessions/resolve/{UUID_A}")
    assert res.status_code == 200
    body = res.json()
    assert body["uuid"] == UUID_A
    assert body["project_encoded_name"] == "-Users-test-project"
    assert body["slug"] is None


def test_resolve_short_prefix(env):
    client, projects_dir, _ = env
    _write_jsonl(projects_dir, "-Users-test-project", UUID_A, "/Users/test/project")

    res = client.get(f"/sessions/resolve/{UUID_A[:8]}")
    assert res.status_code == 200
    assert res.json()["uuid"] == UUID_A


def test_resolve_ambiguous_prefix_prefers_newest(env):
    client, projects_dir, _ = env
    older = _write_jsonl(projects_dir, "-Users-test-project", UUID_A, "/Users/test/project")
    _write_jsonl(projects_dir, "-Users-test-project", UUID_B, "/Users/test/project")
    old = time.time() - 3600
    os.utime(older, (old, old))

    res = client.get(f"/sessions/resolve/{UUID_A[:8]}")
    assert res.status_code == 200
    assert res.json()["uuid"] == UUID_B


def test_resolve_includes_live_slug(env):
    client, projects_dir, live_dir = env
    _write_jsonl(projects_dir, "-Users-test-project", UUID_A, "/Users/test/project")
    _write_live_state(live_dir, UUID_A, "/Users/test/project", None, slug="brave-quiet-fox")

    res = client.get(f"/sessions/resolve/{UUID_A}")
    assert res.status_code == 200
    assert res.json()["slug"] == "brave-quiet-fox"


def test_resolve_falls_back_to_live_session_before_jsonl_exists(env, tmp_path):
    """A session just past SessionStart has a live record but no JSONL yet —
    the statusline link must still resolve instead of 404ing on startup."""
    client, _, live_dir = env
    cwd = tmp_path / "repo"
    cwd.mkdir()
    _write_live_state(live_dir, UUID_A, str(cwd), None)

    res = client.get(f"/sessions/resolve/{UUID_A[:8]}")
    assert res.status_code == 200
    body = res.json()
    assert body["uuid"] == UUID_A
    from models import Project

    assert body["project_encoded_name"] == Project.encode_path(str(cwd))


def test_resolve_prefers_jsonl_over_live_session_once_it_exists(env, tmp_path):
    client, projects_dir, live_dir = env
    cwd = tmp_path / "repo"
    cwd.mkdir()
    _write_jsonl(projects_dir, "-Users-test-project", UUID_A, str(cwd))
    # A stale/mismatched live record for the same uuid should lose to the
    # authoritative on-disk transcript.
    _write_live_state(live_dir, UUID_A, "/somewhere/else", None)

    res = client.get(f"/sessions/resolve/{UUID_A[:8]}")
    assert res.status_code == 200
    assert res.json()["project_encoded_name"] == "-Users-test-project"


def test_resolve_unknown_returns_404(env):
    client, _, _ = env
    assert client.get("/sessions/resolve/deadbeef").status_code == 404


def test_resolve_invalid_id_returns_400(env):
    client, _, _ = env
    assert client.get("/sessions/resolve/not..valid").status_code == 400
    assert client.get("/sessions/resolve/abc").status_code == 400  # too short


def test_resolve_ignores_agent_files(env):
    client, projects_dir, _ = env
    project_dir = projects_dir / "-Users-test-project"
    project_dir.mkdir(parents=True)
    (project_dir / f"agent-{UUID_A}.jsonl").write_text("{}\n")

    assert client.get(f"/sessions/resolve/{UUID_A[:8]}").status_code == 404


# ---------------------------------------------------------------------------
# POST /sessions/{uuid}/resume-in-terminal
# ---------------------------------------------------------------------------


def test_resume_invalid_uuid_returns_400(env):
    client, _, _ = env
    assert client.post("/sessions/not-a-uuid/resume-in-terminal").status_code == 400


def test_resume_unknown_session_returns_404(env):
    client, _, _ = env
    assert client.post(f"/sessions/{UUID_A}/resume-in-terminal").status_code == 404


def test_resume_cross_origin_rejected(env):
    client, _, _ = env
    res = client.post(
        f"/sessions/{UUID_A}/resume-in-terminal",
        headers={"Origin": "https://evil.example"},
    )
    assert res.status_code == 403


def test_resume_live_session_focuses_instead(env, monkeypatch):
    client, projects_dir, live_dir = env
    cwd = "/Users/test/project"
    _write_jsonl(projects_dir, "-Users-test-project", UUID_A, cwd)
    _write_live_state(
        live_dir,
        UUID_A,
        cwd,
        {"term_program": "Apple_Terminal", "pid": 4242, "tty": "/dev/ttys009"},
    )

    import services.terminal_focus as tf

    focused_with = {}
    monkeypatch.setattr(tf, "pid_is_live_claude", lambda pid: pid == 4242)
    monkeypatch.setattr(
        tf,
        "focus_terminal",
        lambda terminal: focused_with.update(terminal)
        or {"focused": True, "method": "osascript-tab", "detail": "raised"},
    )

    res = client.post(f"/sessions/{UUID_A}/resume-in-terminal")
    assert res.status_code == 200
    body = res.json()
    assert body["action"] == "focused"
    assert body["ok"] is True
    assert focused_with["tty"] == "/dev/ttys009"


def test_resume_ended_session_launches_terminal(env, monkeypatch, tmp_path):
    client, projects_dir, live_dir = env
    cwd = tmp_path / "repo"
    cwd.mkdir()
    _write_jsonl(projects_dir, "-Users-test-project", UUID_A, str(cwd))
    _write_live_state(
        live_dir,
        UUID_A,
        str(cwd),
        {"term_program": "iTerm.app", "pid": 4242, "tty": "/dev/ttys009"},
    )

    import services.terminal_focus as tf
    import services.terminal_launch as tl

    monkeypatch.setattr(tf, "pid_is_live_claude", lambda pid: False)
    calls = {}

    def fake_launch(project_path, session_uuid, term_program=None):
        calls.update(path=project_path, uuid=session_uuid, term=term_program)
        return {"launched": True, "method": "iterm-tab", "detail": "opened"}

    monkeypatch.setattr(tl, "launch_resume_in_terminal", fake_launch)

    res = client.post(f"/sessions/{UUID_A}/resume-in-terminal")
    assert res.status_code == 200
    body = res.json()
    assert body["action"] == "launched"
    assert body["ok"] is True
    assert calls == {"path": str(cwd), "uuid": UUID_A, "term": "iTerm.app"}


def test_resume_without_live_state_uses_jsonl_cwd(env, monkeypatch, tmp_path):
    client, projects_dir, _ = env
    cwd = tmp_path / "repo"
    cwd.mkdir()
    _write_jsonl(projects_dir, "-Users-test-project", UUID_A, str(cwd))

    import services.terminal_launch as tl

    calls = {}
    monkeypatch.setattr(
        tl,
        "launch_resume_in_terminal",
        lambda project_path, session_uuid, term_program=None: calls.update(
            path=project_path, term=term_program
        )
        or {"launched": True, "method": "terminal-window", "detail": "opened"},
    )

    res = client.post(f"/sessions/{UUID_A}/resume-in-terminal")
    assert res.status_code == 200
    assert calls == {"path": str(cwd), "term": None}


def test_resume_missing_project_dir_returns_409(env):
    client, projects_dir, _ = env
    _write_jsonl(projects_dir, "-Users-test-project", UUID_A, "/nonexistent/path/xyz")

    res = client.post(f"/sessions/{UUID_A}/resume-in-terminal")
    assert res.status_code == 409


def test_resume_launch_failure_reports_failed(env, monkeypatch, tmp_path):
    client, projects_dir, _ = env
    cwd = tmp_path / "repo"
    cwd.mkdir()
    _write_jsonl(projects_dir, "-Users-test-project", UUID_A, str(cwd))

    import services.terminal_launch as tl

    monkeypatch.setattr(
        tl,
        "launch_resume_in_terminal",
        lambda *a, **k: {"launched": False, "method": "terminal-window", "detail": "no osascript"},
    )

    res = client.post(f"/sessions/{UUID_A}/resume-in-terminal")
    assert res.status_code == 200
    body = res.json()
    assert body["action"] == "failed"
    assert body["ok"] is False
    assert "osascript" in body["detail"]

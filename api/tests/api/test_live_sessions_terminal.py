"""Endpoint tests for the terminal-focus feature on the live-sessions router.

Covers:
- ``state_to_summary`` surfacing ``terminal`` + ``can_focus_terminal``
- ``POST /live-sessions/{id}/focus-terminal`` (success, no-terminal 400,
  missing-session 404)

The actual OS focus is mocked; ``services.terminal_focus`` has its own unit
tests. The live-sessions directory is redirected to a tmp path.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

_tests_dir = Path(__file__).resolve().parent.parent
_api_dir = _tests_dir.parent
if str(_api_dir) not in sys.path:
    sys.path.insert(0, str(_api_dir))

from fastapi import FastAPI
from fastapi.testclient import TestClient


def _write_session(live_dir: Path, session_id: str, terminal: dict | None) -> None:
    now = datetime.now(timezone.utc).isoformat()
    data = {
        "session_id": session_id,
        "state": "LIVE",
        "cwd": "/Users/test/project",
        "transcript_path": f"/Users/test/.claude/projects/-Users-test-project/{session_id}.jsonl",
        "permission_mode": "default",
        "last_hook": "PostToolUse",
        "updated_at": now,
        "started_at": now,
        "session_ids": [session_id],
    }
    if terminal is not None:
        data["terminal"] = terminal
    (live_dir / f"{session_id}.json").write_text(json.dumps(data))


@pytest.fixture
def client(tmp_path, monkeypatch):
    live_dir = tmp_path / "live-sessions"
    live_dir.mkdir()

    import models.live_session as live_model

    monkeypatch.setattr(live_model, "get_live_sessions_dir", lambda: live_dir)

    from routers import live_sessions

    app = FastAPI()
    app.include_router(live_sessions.router, prefix="/live-sessions")

    client = TestClient(app)
    client.live_dir = live_dir  # type: ignore[attr-defined]
    return client


# ---------------------------------------------------------------------------
# state_to_summary / GET
# ---------------------------------------------------------------------------


def test_get_live_session_includes_terminal(client, monkeypatch):
    import services.terminal_focus as tf

    monkeypatch.setattr(tf.sys, "platform", "darwin")
    _write_session(
        client.live_dir,
        "sess-term",
        {"tmux": False, "term_program": "iTerm.app", "term_session_id": "abc"},
    )

    res = client.get("/live-sessions/sess-term")
    assert res.status_code == 200
    body = res.json()
    assert body["terminal"]["term_program"] == "iTerm.app"
    assert body["can_focus_terminal"] is True


def test_get_live_session_without_terminal(client):
    _write_session(client.live_dir, "sess-noterm", None)
    res = client.get("/live-sessions/sess-noterm")
    assert res.status_code == 200
    body = res.json()
    assert body["terminal"] is None
    assert body["can_focus_terminal"] is False


# ---------------------------------------------------------------------------
# POST focus-terminal
# ---------------------------------------------------------------------------


def test_focus_terminal_success(client, monkeypatch):
    _write_session(client.live_dir, "sess-focus", {"tmux_pane": "%2"})

    from routers import live_sessions

    captured = {}

    def fake_focus(terminal):
        captured["terminal"] = terminal
        return {"focused": True, "method": "tmux", "detail": "selected tmux pane %2"}

    monkeypatch.setattr(live_sessions, "focus_terminal", fake_focus)

    res = client.post("/live-sessions/sess-focus/focus-terminal")
    assert res.status_code == 200
    body = res.json()
    assert body["focused"] is True
    assert body["method"] == "tmux"
    assert captured["terminal"]["tmux_pane"] == "%2"


def test_focus_terminal_reports_failure_as_200(client, monkeypatch):
    """A known-but-failed method is a 200 with focused=false, not an error."""
    _write_session(client.live_dir, "sess-fail", {"tmux_pane": "%2"})

    from routers import live_sessions

    monkeypatch.setattr(
        live_sessions,
        "focus_terminal",
        lambda terminal: {"focused": False, "method": "tmux", "detail": "tmux not found on PATH"},
    )

    res = client.post("/live-sessions/sess-fail/focus-terminal")
    assert res.status_code == 200
    assert res.json()["focused"] is False


def test_focus_terminal_no_terminal_info_400(client):
    _write_session(client.live_dir, "sess-noterm", None)
    res = client.post("/live-sessions/sess-noterm/focus-terminal")
    assert res.status_code == 400


def test_focus_terminal_missing_session_404(client):
    res = client.post("/live-sessions/does-not-exist/focus-terminal")
    assert res.status_code == 404

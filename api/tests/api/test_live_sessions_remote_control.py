"""Tests for the Remote Control toggle — service unit tests + endpoint tests.

Endpoint tests mock the keystroke senders and the transcript reader; the
service unit tests exercise the real `read_remote_control_state`,
`can_send_remote_control`, and the tmux/`_run` argv building.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

_tests_dir = Path(__file__).resolve().parent.parent
_api_dir = _tests_dir.parent
if str(_api_dir) not in sys.path:
    sys.path.insert(0, str(_api_dir))

from fastapi import FastAPI
from fastapi.testclient import TestClient

TRUSTED_ORIGIN = "http://localhost:5180"
RC_HEADERS = {"origin": TRUSTED_ORIGIN, "x-karma-rc": "1"}


# ===========================================================================
# Unit: read_remote_control_state
# ===========================================================================


def _jsonl(path: Path, *objs: dict) -> None:
    path.write_text("\n".join(json.dumps(o) for o in objs) + "\n")


def _bridge(content: str, url: str | None, ts: str) -> dict:
    o = {"type": "system", "subtype": "bridge_status", "content": content, "timestamp": ts}
    if url is not None:
        o["url"] = url
    return o


@pytest.fixture
def projects_dir(tmp_path):
    d = tmp_path / "projects" / "-proj"
    d.mkdir(parents=True)
    return tmp_path / "projects", d


def test_read_state_on(projects_dir):
    base, proj = projects_dir
    p = proj / "s1.jsonl"
    _jsonl(
        p,
        {"type": "user", "message": {}},
        _bridge(
            "/remote-control is active · Continue on your phone, or at https://claude.ai/code/session_x",
            "https://claude.ai/code/session_x",
            "2026-08-29T07:00:00.000Z",
        ),
    )
    from services.remote_control import read_remote_control_state

    got = read_remote_control_state(str(p), ["s1"], base)
    assert got["state"] == "on"
    assert got["url"] == "https://claude.ai/code/session_x"


def test_read_state_off(projects_dir):
    base, proj = projects_dir
    p = proj / "s1.jsonl"
    _jsonl(
        p,
        _bridge(
            "/remote-control is active", "https://claude.ai/code/session_x", "2026-08-29T07:00:00Z"
        ),
        _bridge(
            "/remote-control is no longer active. Run /remote-control to start a new session.",
            None,
            "2026-08-29T07:05:00Z",
        ),
    )
    from services.remote_control import read_remote_control_state

    assert read_remote_control_state(str(p), ["s1"], base)["state"] == "off"


def test_read_state_no_line_is_off(projects_dir):
    # A session that never touched Remote Control has no bridge_status line.
    base, proj = projects_dir
    p = proj / "s1.jsonl"
    _jsonl(p, {"type": "user", "message": {}}, {"type": "assistant", "message": {}})
    from services.remote_control import read_remote_control_state

    assert read_remote_control_state(str(p), ["s1"], base)["state"] == "off"


def test_read_state_missing_file_is_off(projects_dir):
    base, proj = projects_dir
    from services.remote_control import read_remote_control_state

    assert read_remote_control_state(str(proj / "gone.jsonl"), [], base)["state"] == "off"


def test_read_state_unparseable_line_is_unknown(projects_dir):
    base, proj = projects_dir
    p = proj / "s1.jsonl"
    _jsonl(p, _bridge("remote control did a thing", None, "2026-08-29T07:00:00Z"))
    from services.remote_control import read_remote_control_state

    assert read_remote_control_state(str(p), ["s1"], base)["state"] == "unknown"


def test_read_state_falls_back_to_chain_file(projects_dir):
    base, proj = projects_dir
    old = proj / "old.jsonl"
    new = proj / "new.jsonl"
    _jsonl(
        old,
        _bridge(
            "/remote-control is active", "https://claude.ai/code/session_x", "2026-08-29T06:00:00Z"
        ),
    )
    _jsonl(new, {"type": "user", "message": {}})  # current file has no bridge line
    from services.remote_control import read_remote_control_state

    got = read_remote_control_state(str(new), ["new", "old"], base)
    assert got["state"] == "on"


def test_read_state_primary_wins_over_chain(projects_dir):
    base, proj = projects_dir
    old = proj / "old.jsonl"
    new = proj / "new.jsonl"
    _jsonl(
        old,
        _bridge("/remote-control is active", "https://claude.ai/code/x", "2026-08-29T06:00:00Z"),
    )
    _jsonl(new, _bridge("/remote-control is no longer active", None, "2026-08-29T08:00:00Z"))
    from services.remote_control import read_remote_control_state

    assert read_remote_control_state(str(new), ["new", "old"], base)["state"] == "off"


def test_read_state_finds_event_buried_deep_under_noise(projects_dir):
    # The real bridge_status "is active" event, then ~1 MB of tool output —
    # including lines that merely contain the string "bridge_status" (this
    # repo's own code / review notes). Only the real system event counts.
    base, proj = projects_dir
    p = proj / "s1.jsonl"
    lines = [
        json.dumps({"type": "user", "message": {}}),
        json.dumps(
            _bridge("/remote-control is active", "https://claude.ai/code/x", "2026-08-29T07:00:00Z")
        ),
    ]
    noise = json.dumps(
        {
            "type": "user",
            "message": {
                "content": 'grep found "subtype":"bridge_status" ... is no longer active '
                + "x" * 400
            },
        }
    )
    lines += [noise] * 3000  # ~1.2 MB of post-event noise
    p.write_text("\n".join(lines) + "\n")
    from services.remote_control import read_remote_control_state

    assert read_remote_control_state(str(p), ["s1"], base)["state"] == "on"


def test_read_state_drops_non_claude_url(projects_dir):
    base, proj = projects_dir
    p = proj / "s1.jsonl"
    _jsonl(p, _bridge("/remote-control is active", "javascript:alert(1)", "2026-08-29T07:00:00Z"))
    from services.remote_control import read_remote_control_state

    got = read_remote_control_state(str(p), ["s1"], base)
    assert got["state"] == "on"
    assert got["url"] is None


def test_read_state_refuses_path_outside_projects(tmp_path, projects_dir):
    # A transcript_path outside ~/.claude/projects is not read at all — the
    # "is active" line in it must not leak through; safe fallback is "off".
    base, _ = projects_dir
    outside = tmp_path / "secret.jsonl"
    _jsonl(
        outside,
        _bridge("/remote-control is active", "https://claude.ai/code/x", "2026-08-29T07:00:00Z"),
    )
    from services.remote_control import read_remote_control_state

    got = read_remote_control_state(str(outside), [], base)
    assert got["state"] == "off" and got["url"] is None


# ===========================================================================
# Unit: can_send_remote_control + keystroke senders
# ===========================================================================


def test_can_send_requires_live_pid(monkeypatch):
    import services.remote_control as rc

    monkeypatch.setattr(rc, "pid_is_live_claude", lambda _pid: True)
    assert rc.can_send_remote_control({"tmux_pane": "%2", "pid": 111}) is True
    assert rc.can_send_remote_control({"tmux_pane": "%2"}) is False  # no pid
    assert rc.can_send_remote_control({"term_program": "vscode", "pid": 111}) is False
    assert rc.can_send_remote_control({"term_program": "iTerm.app", "pid": 111}) is True

    monkeypatch.setattr(rc, "pid_is_live_claude", lambda _pid: False)
    assert rc.can_send_remote_control({"tmux_pane": "%2", "pid": 111}) is False


def test_type_command_tmux_argv(monkeypatch):
    import services.remote_control as rc

    calls = []
    monkeypatch.setattr(rc, "pid_is_live_claude", lambda _pid: True)
    monkeypatch.setattr(
        rc,
        "_run",
        lambda cmd: calls.append(cmd) or type("R", (), {"returncode": 0, "stdout": ""})(),
    )
    out = rc.type_remote_control_command({"tmux_pane": "%3", "pid": 1})
    assert out["sent"] is True
    assert calls[0] == ["tmux", "send-keys", "-t", "%3", "-l", "--", "/remote-control"]
    assert calls[1] == ["tmux", "send-keys", "-t", "%3", "Enter"]


def test_type_command_refuses_without_terminal(monkeypatch):
    import services.remote_control as rc

    monkeypatch.setattr(rc, "pid_is_live_claude", lambda _pid: True)
    out = rc.type_remote_control_command({"pid": 1})  # no pane, no term_program
    assert out["sent"] is False


# ===========================================================================
# Endpoint
# ===========================================================================


def _write_session(
    live_dir: Path,
    session_id: str,
    terminal: dict | None,
    *,
    state: str = "STOPPED",
    updated_ago_s: int = 0,
) -> None:
    now = datetime.now(timezone.utc)
    upd = (now - timedelta(seconds=updated_ago_s)).isoformat()
    data = {
        "session_id": session_id,
        "state": state,
        "cwd": "/Users/test/project",
        "transcript_path": f"/Users/test/.claude/projects/-Users-test-project/{session_id}.jsonl",
        "permission_mode": "default",
        "last_hook": "Stop",
        "updated_at": upd,
        "started_at": now.isoformat(),
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

    async def _nosleep(_s):
        return None

    monkeypatch.setattr(live_sessions.asyncio, "sleep", _nosleep)
    # Default: terminal is reachable unless a test overrides.
    monkeypatch.setattr(live_sessions, "can_send_remote_control", lambda _t: True)

    from config import Settings

    app = FastAPI()
    app.include_router(live_sessions.router, prefix="/live-sessions")
    app.dependency_overrides[live_sessions.get_settings] = lambda: Settings(
        rc_trusted_origins=[TRUSTED_ORIGIN]
    )

    c = TestClient(app)
    c.live_dir = live_dir  # type: ignore[attr-defined]
    return c


def _post(client, sid, desired="on", headers=RC_HEADERS):
    return client.post(
        f"/live-sessions/{sid}/remote-control", json={"desired": desired}, headers=headers
    )


def test_missing_karma_header_403(client):
    _write_session(client.live_dir, "s", {"tmux_pane": "%2", "pid": 1})
    r = _post(client, "s", headers={"origin": TRUSTED_ORIGIN})
    assert r.status_code == 403


def test_untrusted_origin_403(client):
    _write_session(client.live_dir, "s", {"tmux_pane": "%2", "pid": 1})
    r = _post(client, "s", headers={"origin": "http://localhost:5173", "x-karma-rc": "1"})
    assert r.status_code == 403


def test_no_origin_allowed(client, monkeypatch):
    from routers import live_sessions

    monkeypatch.setattr(
        live_sessions,
        "read_remote_control_state",
        lambda *a: {"state": "off", "url": None, "at": None},
    )
    monkeypatch.setattr(
        live_sessions,
        "type_remote_control_command",
        lambda _t: {"sent": True, "method": "tmux", "detail": "x"},
    )
    _write_session(client.live_dir, "s", {"tmux_pane": "%2", "pid": 1})
    r = _post(client, "s", headers={"x-karma-rc": "1"})
    assert r.status_code == 200


def test_invalid_session_id_400(client):
    r = _post(client, "..%2fetc", headers=RC_HEADERS)
    assert r.status_code in (400, 404)  # routing may 404 the traversal first


def test_unknown_session_404(client):
    r = _post(client, "nope")
    assert r.status_code == 404


def test_unsupported_terminal_400(client, monkeypatch):
    from routers import live_sessions

    monkeypatch.setattr(live_sessions, "can_send_remote_control", lambda _t: False)
    _write_session(client.live_dir, "s", {"term_program": "vscode", "pid": 1})
    assert _post(client, "s").status_code == 400


def test_ended_session_409_resume_hint(client):
    _write_session(client.live_dir, "s", {"tmux_pane": "%2", "pid": 1}, state="ENDED")
    r = _post(client, "s")
    assert r.status_code == 409
    assert "--remote-control" in r.json()["detail"]


def test_mid_turn_active_is_allowed(client, monkeypatch):
    # ACTIVE (a tool ran in the last 30s) is sendable now — Claude Code queues
    # the slash command if a tool is genuinely still running.
    from routers import live_sessions

    monkeypatch.setattr(
        live_sessions,
        "read_remote_control_state",
        lambda *a: {"state": "off", "url": None, "at": None},
    )
    monkeypatch.setattr(
        live_sessions,
        "type_remote_control_command",
        lambda _t: {"sent": True, "method": "tmux", "detail": "typed"},
    )
    _write_session(
        client.live_dir, "s", {"tmux_pane": "%2", "pid": 1}, state="LIVE", updated_ago_s=1
    )
    assert _post(client, "s").status_code == 200


def test_starting_session_409(client):
    # No REPL yet — the keystrokes would be lost. Blocked.
    _write_session(client.live_dir, "s", {"tmux_pane": "%2", "pid": 1}, state="STARTING")
    r = _post(client, "s")
    assert r.status_code == 409
    assert "starting up" in r.json()["detail"]


def test_idle_live_is_allowed(client, monkeypatch):
    # LIVE + >30s idle => determine_status IDLE, which IS sendable: an
    # actively-used session is almost always LIVE/IDLE, never STOPPED.
    from routers import live_sessions

    monkeypatch.setattr(
        live_sessions,
        "read_remote_control_state",
        lambda *a: {"state": "off", "url": None, "at": None},
    )
    monkeypatch.setattr(
        live_sessions,
        "type_remote_control_command",
        lambda _t: {"sent": True, "method": "tmux", "detail": "typed"},
    )
    _write_session(
        client.live_dir, "s", {"tmux_pane": "%2", "pid": 1}, state="LIVE", updated_ago_s=45
    )
    assert _post(client, "s").status_code == 200


def test_waiting_input_409(client):
    # A permission / question dialog is open — a stray /remote-control could
    # answer it. Blocked.
    _write_session(client.live_dir, "s", {"tmux_pane": "%2", "pid": 1}, state="WAITING")
    r = _post(client, "s")
    assert r.status_code == 409
    assert "waiting for your answer" in r.json()["detail"]


def test_unknown_state_409(client, monkeypatch):
    from routers import live_sessions

    monkeypatch.setattr(
        live_sessions,
        "read_remote_control_state",
        lambda *a: {"state": "unknown", "url": None, "at": None},
    )
    _write_session(client.live_dir, "s", {"tmux_pane": "%2", "pid": 1})
    r = _post(client, "s")
    assert r.status_code == 409
    assert "blind-toggle" in r.json()["detail"]


def test_noop_when_already_desired(client, monkeypatch):
    from routers import live_sessions

    monkeypatch.setattr(
        live_sessions,
        "read_remote_control_state",
        lambda *a: {"state": "on", "url": "https://claude.ai/code/x", "at": "t"},
    )

    def boom(*a):
        raise AssertionError("must not type when already in desired state")

    monkeypatch.setattr(live_sessions, "type_remote_control_command", boom)
    _write_session(client.live_dir, "s", {"tmux_pane": "%2", "pid": 1})
    r = _post(client, "s", desired="on")
    assert r.status_code == 200
    b = r.json()
    assert b["sent"] is False and b["confirmed"] is True and b["state"] == "on"


def test_enable_success_confirmed(client, monkeypatch):
    from routers import live_sessions

    seq = iter([{"state": "off", "url": None, "at": "t0"}])
    later = {"state": "on", "url": "https://claude.ai/code/x", "at": "t1"}
    monkeypatch.setattr(live_sessions, "read_remote_control_state", lambda *a: next(seq, later))
    monkeypatch.setattr(
        live_sessions,
        "type_remote_control_command",
        lambda _t: {"sent": True, "method": "tmux", "detail": "typed"},
    )
    _write_session(client.live_dir, "s", {"tmux_pane": "%2", "pid": 1})
    r = _post(client, "s", desired="on")
    assert r.status_code == 200
    b = r.json()
    assert (
        b["sent"]
        and b["confirmed"]
        and b["state"] == "on"
        and b["url"].startswith("https://claude.ai/")
    )


def test_enable_sent_but_unconfirmed(client, monkeypatch):
    from routers import live_sessions

    monkeypatch.setattr(
        live_sessions,
        "read_remote_control_state",
        lambda *a: {"state": "off", "url": None, "at": "t0"},
    )
    monkeypatch.setattr(
        live_sessions,
        "type_remote_control_command",
        lambda _t: {"sent": True, "method": "tmux", "detail": "typed"},
    )
    _write_session(client.live_dir, "s", {"tmux_pane": "%2", "pid": 1})
    r = _post(client, "s", desired="on")
    assert r.status_code == 200
    b = r.json()
    assert b["sent"] is True and b["confirmed"] is False and b["state"] == "off"


def test_disable_opens_menu_and_raises_terminal(client, monkeypatch):
    # "off" click: type /remote-control (opens the disconnect menu), raise the
    # terminal, hand it to the user. Karma never navigates the menu.
    from routers import live_sessions

    monkeypatch.setattr(
        live_sessions,
        "read_remote_control_state",
        lambda *a: {"state": "on", "url": "https://claude.ai/code/x", "at": "t0"},
    )
    monkeypatch.setattr(
        live_sessions,
        "type_remote_control_command",
        lambda _t: {"sent": True, "method": "osascript-tab", "detail": "typed"},
    )
    focus_called = {"n": 0}
    monkeypatch.setattr(
        live_sessions,
        "focus_terminal",
        lambda _t: focus_called.update(n=focus_called["n"] + 1)
        or {"focused": True, "method": "osascript-tab", "detail": "raised"},
    )
    _write_session(
        client.live_dir, "s", {"term_program": "Apple_Terminal", "tty": "/dev/t9", "pid": 1}
    )
    r = _post(client, "s", desired="off")
    assert r.status_code == 200
    b = r.json()
    assert focus_called["n"] == 1
    assert b["sent"] is True and b["confirmed"] is False and b["state"] == "on"
    assert b["method"] == "menu-open"
    assert "Disconnect this session" in b["detail"] and "front" in b["detail"]


def test_disable_race_already_off(client, monkeypatch):
    from routers import live_sessions

    states = iter(
        [
            {"state": "on", "url": "https://claude.ai/code/x", "at": "t0"},  # pre-check
            {"state": "off", "url": None, "at": "t2"},  # after the wait — already gone
        ]
    )
    monkeypatch.setattr(live_sessions, "read_remote_control_state", lambda *a: next(states))
    monkeypatch.setattr(
        live_sessions,
        "type_remote_control_command",
        lambda _t: {"sent": True, "method": "tmux", "detail": "typed"},
    )
    _write_session(client.live_dir, "s", {"tmux_pane": "%2", "pid": 1})
    r = _post(client, "s", desired="off")
    assert r.status_code == 200
    assert r.json()["state"] == "off"


def test_disable_turned_on_instead_when_transcript_was_stale(client, monkeypatch):
    from routers import live_sessions

    # Pre-check says "on" @ t0, but after typing a NEW "is active" line @ t9
    # appears => it was actually off and the command just turned it on.
    states = iter(
        [
            {"state": "on", "url": None, "at": "2026-08-29T07:00:00Z"},
            {"state": "on", "url": "https://claude.ai/code/x", "at": "2026-08-29T09:00:00Z"},
        ]
    )
    monkeypatch.setattr(live_sessions, "read_remote_control_state", lambda *a: next(states))
    monkeypatch.setattr(
        live_sessions,
        "type_remote_control_command",
        lambda _t: {"sent": True, "method": "tmux", "detail": "typed"},
    )

    def no_focus(*a, **k):
        raise AssertionError("must not raise the terminal — no menu opened, RC just turned on")

    monkeypatch.setattr(live_sessions, "focus_terminal", no_focus)
    _write_session(client.live_dir, "s", {"tmux_pane": "%2", "pid": 1})
    r = _post(client, "s", desired="off")
    assert r.status_code == 200
    b = r.json()
    assert b["state"] == "on" and "turned it on instead" in b["detail"]


def test_concurrent_toggle_locked_409(client, monkeypatch):
    from routers import live_sessions

    _write_session(client.live_dir, "s", {"tmux_pane": "%2", "pid": 1})

    class _Locked:
        def locked(self):
            return True

    monkeypatch.setattr(live_sessions, "_rc_lock", _Locked())
    assert _post(client, "s").status_code == 409


def test_confirm_loop_is_bounded(client, monkeypatch):
    from routers import live_sessions

    reads = {"n": 0}

    def read(*a):
        reads["n"] += 1
        return {"state": "off", "url": None, "at": "t0"}  # never reaches "on"

    monkeypatch.setattr(live_sessions, "read_remote_control_state", read)
    monkeypatch.setattr(
        live_sessions,
        "type_remote_control_command",
        lambda _t: {"sent": True, "method": "tmux", "detail": "x"},
    )
    _write_session(client.live_dir, "s", {"tmux_pane": "%2", "pid": 1})
    _post(client, "s", desired="on")
    # 1 pre-check + (1 initial + up to _RC_CONFIRM_ATTEMPTS) in the poll.
    assert reads["n"] <= 2 + live_sessions._RC_CONFIRM_ATTEMPTS

"""Tests for hooks/live_session_tracker.py terminal capture and state logic.

Direct-import unit tests (unlike the subprocess-driven ticket detector
tests): the interesting logic here is pure functions plus locked file
writes, and LIVE_SESSIONS_DIR is a module global we can point at tmp.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

_hooks_dir = Path(__file__).resolve().parent.parent
if str(_hooks_dir) not in sys.path:
    sys.path.insert(0, str(_hooks_dir))

import live_session_tracker as tracker


class _FakeCompleted:
    def __init__(self, returncode=0, stdout="", stderr=""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


@pytest.fixture
def live_dir(tmp_path, monkeypatch) -> Path:
    """Redirect state files (and the error log) to a tmp dir."""
    d = tmp_path / "live-sessions"
    monkeypatch.setattr(tracker, "LIVE_SESSIONS_DIR", d)
    monkeypatch.setattr(tracker, "ERROR_LOG", d / ".errors.log")
    return d


def _read_state(live_dir: Path, session_id: str) -> dict:
    return json.loads((live_dir / f"{session_id}.json").read_text())


# ---------------------------------------------------------------------------
# resolve_terminal
# ---------------------------------------------------------------------------


def test_resolve_terminal_captures_identity(monkeypatch):
    env = {
        "TERM_PROGRAM": "Apple_Terminal",
        "TERM_SESSION_ID": "UUID-1",
        "ITERM_SESSION_ID": "w0t2p0:UUID-2",
        "__CFBundleIdentifier": "com.apple.Terminal",
    }
    monkeypatch.setattr(tracker.os, "environ", env)
    monkeypatch.setattr(tracker.os, "getppid", lambda: 4242)
    monkeypatch.setattr(
        tracker.subprocess, "run", lambda *a, **k: _FakeCompleted(stdout="ttys004\n")
    )

    t = tracker.resolve_terminal()
    assert t["term_program"] == "Apple_Terminal"
    assert t["term_session_id"] == "UUID-1"
    assert t["iterm_session_id"] == "w0t2p0:UUID-2"
    assert t["bundle_id"] == "com.apple.Terminal"
    assert t["pid"] == 4242
    assert t["tty"] == "/dev/ttys004"
    assert t["tmux"] is False


def test_resolve_terminal_headless_stores_nones(monkeypatch):
    monkeypatch.setattr(tracker.os, "environ", {})
    monkeypatch.setattr(tracker.os, "getppid", lambda: 4242)
    monkeypatch.setattr(
        tracker.subprocess, "run", lambda *a, **k: _FakeCompleted(stdout="??\n")
    )

    t = tracker.resolve_terminal()
    assert t["term_program"] is None
    assert t["bundle_id"] is None
    assert t["tty"] is None  # "??" means no controlling tty
    assert "tty" in t  # key presence marks current-format capture


def test_tty_of_pid_survives_ps_failure(monkeypatch):
    def boom(*a, **k):
        raise OSError("ps unavailable")

    monkeypatch.setattr(tracker.subprocess, "run", boom)
    assert tracker._tty_of_pid(4242) is None
    assert tracker._tty_of_pid(None) is None


# ---------------------------------------------------------------------------
# terminal backfill / upgrade
# ---------------------------------------------------------------------------


def test_terminal_for_keeps_current_format(monkeypatch):
    def boom():
        raise AssertionError("must not re-resolve a current-format capture")

    monkeypatch.setattr(tracker, "resolve_terminal", boom)
    current = {"term_program": "Apple_Terminal", "pid": 1, "tty": None}
    assert tracker._terminal_for(current) is current


def test_terminal_for_upgrades_legacy_and_missing(monkeypatch):
    fresh = {"term_program": "X", "pid": 2, "tty": "/dev/ttys009"}
    monkeypatch.setattr(tracker, "resolve_terminal", lambda: fresh)
    legacy = {"term_program": "Apple_Terminal", "pid": 1}  # predates tty capture
    assert tracker._terminal_for(legacy) is fresh
    assert tracker._terminal_for(None) is fresh


def test_write_state_upgrades_legacy_terminal_once(live_dir, monkeypatch):
    fresh = {"term_program": "Apple_Terminal", "pid": 7, "tty": "/dev/ttys001"}
    monkeypatch.setattr(tracker, "resolve_terminal", lambda: fresh)

    tracker.write_state("s1", "LIVE", {}, terminal={"term_program": "Apple_Terminal", "pid": 7})
    tracker.write_state("s1", "LIVE", {})  # legacy dict on disk → upgraded
    assert _read_state(live_dir, "s1")["terminal"] == fresh


# ---------------------------------------------------------------------------
# Stop semantics
# ---------------------------------------------------------------------------


def test_stop_without_flag_marks_stopped(live_dir, monkeypatch):
    monkeypatch.setattr(tracker, "resolve_terminal", lambda: {"tty": None})
    tracker._handle_event({"hook_event_name": "Stop", "session_id": "s2"})
    assert _read_state(live_dir, "s2")["state"] == "STOPPED"


def test_stop_with_active_stop_hook_is_ignored(live_dir, monkeypatch):
    monkeypatch.setattr(tracker, "resolve_terminal", lambda: {"tty": None})
    tracker._handle_event(
        {"hook_event_name": "Stop", "session_id": "s3", "stop_hook_active": True}
    )
    assert not (live_dir / "s3.json").exists()


# ---------------------------------------------------------------------------
# idle_prompt vs WAITING (locked, no TOCTOU)
# ---------------------------------------------------------------------------


def _notification(session_id: str, notification_type: str) -> dict:
    return {
        "hook_event_name": "Notification",
        "session_id": session_id,
        "notification_type": notification_type,
        "message": "msg",
    }


def test_idle_prompt_does_not_demote_waiting(live_dir, monkeypatch):
    monkeypatch.setattr(tracker, "resolve_terminal", lambda: {"tty": None})
    tracker._handle_event(_notification("s4", "permission_prompt"))
    before = _read_state(live_dir, "s4")
    assert before["state"] == "WAITING"

    tracker._handle_event(_notification("s4", "idle_prompt"))
    after = _read_state(live_dir, "s4")
    assert after["state"] == "WAITING"
    assert after["updated_at"] == before["updated_at"]  # true no-op skip


def test_idle_prompt_marks_live_session_stale(live_dir, monkeypatch):
    monkeypatch.setattr(tracker, "resolve_terminal", lambda: {"tty": None})
    tracker._handle_event(
        {"hook_event_name": "UserPromptSubmit", "session_id": "s5", "prompt": "hi"}
    )
    tracker._handle_event(_notification("s5", "idle_prompt"))
    assert _read_state(live_dir, "s5")["state"] == "STALE"

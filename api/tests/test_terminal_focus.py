"""Tests for ``services.terminal_focus``.

The service shells out to OS window managers, so every test mocks
``shutil.which`` / ``subprocess.run`` / ``sys.platform`` — nothing real is
executed. Covers method selection, best-effort fallbacks, and the never-raise
contract.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

_api_dir = Path(__file__).resolve().parent.parent
if str(_api_dir) not in sys.path:
    sys.path.insert(0, str(_api_dir))

from services import terminal_focus


class _FakeCompleted:
    def __init__(self, returncode=0, stdout="", stderr=""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


# ---------------------------------------------------------------------------
# can_focus
# ---------------------------------------------------------------------------


def test_can_focus_none_and_empty():
    assert terminal_focus.can_focus(None) is False
    assert terminal_focus.can_focus({}) is False


def test_can_focus_tmux_any_platform(monkeypatch):
    monkeypatch.setattr(terminal_focus.sys, "platform", "win32")
    assert terminal_focus.can_focus({"tmux_pane": "%3"}) is True


def test_can_focus_macos_needs_term_program(monkeypatch):
    monkeypatch.setattr(terminal_focus.sys, "platform", "darwin")
    assert terminal_focus.can_focus({"term_program": "iTerm.app"}) is True
    assert terminal_focus.can_focus({"window_id": "123"}) is False


def test_can_focus_linux_needs_window_id(monkeypatch):
    monkeypatch.setattr(terminal_focus.sys, "platform", "linux")
    assert terminal_focus.can_focus({"window_id": "123"}) is True
    assert terminal_focus.can_focus({"term_program": "iTerm.app"}) is False


# ---------------------------------------------------------------------------
# focus_terminal — no info / never raises
# ---------------------------------------------------------------------------


def test_focus_terminal_none_returns_unfocused():
    result = terminal_focus.focus_terminal(None)
    assert result["focused"] is False
    assert result["method"] == "none"


def test_focus_terminal_no_method_available(monkeypatch):
    # Platform with no window_id/term_program and no tmux pane → nothing to do.
    monkeypatch.setattr(terminal_focus.sys, "platform", "linux")
    result = terminal_focus.focus_terminal({"term_program": "iTerm.app"})
    assert result["focused"] is False
    assert result["method"] == "none"


# ---------------------------------------------------------------------------
# tmux
# ---------------------------------------------------------------------------


def test_focus_tmux_success(monkeypatch):
    monkeypatch.setattr(terminal_focus.sys, "platform", "win32")
    monkeypatch.setattr(terminal_focus.shutil, "which", lambda name: "/usr/bin/tmux")

    calls = []

    def fake_run(cmd):
        calls.append(cmd)
        if "display-message" in cmd:
            return _FakeCompleted(stdout="main\n")
        return _FakeCompleted(returncode=0)

    monkeypatch.setattr(terminal_focus, "_run", fake_run)

    result = terminal_focus.focus_terminal({"tmux_pane": "%3"})
    assert result["focused"] is True
    assert result["method"] == "tmux"
    # select-window, select-pane, display-message, switch-client
    assert any("select-pane" in c for c in calls)
    assert any("switch-client" in c for c in calls)


def test_focus_tmux_missing_binary(monkeypatch):
    monkeypatch.setattr(terminal_focus.sys, "platform", "win32")
    monkeypatch.setattr(terminal_focus.shutil, "which", lambda name: None)
    result = terminal_focus.focus_terminal({"tmux_pane": "%3"})
    assert result["focused"] is False
    assert "not found" in result["detail"]


def test_focus_tmux_subprocess_error_is_caught(monkeypatch):
    monkeypatch.setattr(terminal_focus.sys, "platform", "win32")
    monkeypatch.setattr(terminal_focus.shutil, "which", lambda name: "/usr/bin/tmux")

    def boom(cmd):
        raise subprocess.TimeoutExpired(cmd, 5)

    monkeypatch.setattr(terminal_focus, "_run", boom)
    result = terminal_focus.focus_terminal({"tmux_pane": "%3"})
    assert result["focused"] is False  # never raises


# ---------------------------------------------------------------------------
# macOS
# ---------------------------------------------------------------------------


def test_focus_macos_maps_app_name(monkeypatch):
    monkeypatch.setattr(terminal_focus.sys, "platform", "darwin")
    monkeypatch.setattr(terminal_focus.shutil, "which", lambda name: "/usr/bin/osascript")

    captured = {}

    def fake_run(cmd):
        captured["cmd"] = cmd
        return _FakeCompleted(returncode=0)

    monkeypatch.setattr(terminal_focus, "_run", fake_run)
    result = terminal_focus.focus_terminal({"term_program": "iTerm.app"})
    assert result["focused"] is True
    assert result["method"] == "osascript"
    # iTerm.app maps to "iTerm"
    assert 'tell application "iTerm" to activate' in captured["cmd"][-1]


def test_focus_macos_unknown_program_uses_raw_name(monkeypatch):
    monkeypatch.setattr(terminal_focus.sys, "platform", "darwin")
    monkeypatch.setattr(terminal_focus.shutil, "which", lambda name: "/usr/bin/osascript")

    captured = {}

    def fake_run(cmd):
        captured["cmd"] = cmd
        return _FakeCompleted(returncode=0)

    monkeypatch.setattr(terminal_focus, "_run", fake_run)
    terminal_focus.focus_terminal({"term_program": "SomeNewTerm"})
    assert 'tell application "SomeNewTerm" to activate' in captured["cmd"][-1]


# ---------------------------------------------------------------------------
# Linux
# ---------------------------------------------------------------------------


def test_focus_linux_prefers_xdotool(monkeypatch):
    monkeypatch.setattr(terminal_focus.sys, "platform", "linux")
    monkeypatch.setattr(
        terminal_focus.shutil, "which", lambda name: "/usr/bin/xdotool" if name == "xdotool" else None
    )

    captured = {}

    def fake_run(cmd):
        captured["cmd"] = cmd
        return _FakeCompleted(returncode=0)

    monkeypatch.setattr(terminal_focus, "_run", fake_run)
    result = terminal_focus.focus_terminal({"window_id": "44040199"})
    assert result["focused"] is True
    assert result["method"] == "xdotool"
    assert captured["cmd"] == ["xdotool", "windowactivate", "44040199"]


def test_focus_linux_falls_back_to_wmctrl_with_hex(monkeypatch):
    monkeypatch.setattr(terminal_focus.sys, "platform", "linux")
    monkeypatch.setattr(
        terminal_focus.shutil, "which", lambda name: "/usr/bin/wmctrl" if name == "wmctrl" else None
    )

    captured = {}

    def fake_run(cmd):
        captured["cmd"] = cmd
        return _FakeCompleted(returncode=0)

    monkeypatch.setattr(terminal_focus, "_run", fake_run)
    result = terminal_focus.focus_terminal({"window_id": "44040199"})
    assert result["focused"] is True
    assert result["method"] == "wmctrl"
    # decimal converted to hex
    assert captured["cmd"] == ["wmctrl", "-i", "-a", hex(44040199)]


def test_focus_linux_no_tools(monkeypatch):
    monkeypatch.setattr(terminal_focus.sys, "platform", "linux")
    monkeypatch.setattr(terminal_focus.shutil, "which", lambda name: None)
    result = terminal_focus.focus_terminal({"window_id": "123"})
    assert result["focused"] is False

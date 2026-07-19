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


def test_focus_macos_escapes_applescript_injection(monkeypatch):
    # A quote in TERM_PROGRAM must not break out of the AppleScript string.
    monkeypatch.setattr(terminal_focus.sys, "platform", "darwin")
    monkeypatch.setattr(terminal_focus.shutil, "which", lambda name: "/usr/bin/osascript")

    captured = {}

    def fake_run(cmd):
        captured["cmd"] = cmd
        return _FakeCompleted(returncode=0)

    monkeypatch.setattr(terminal_focus, "_run", fake_run)
    terminal_focus.focus_terminal({"term_program": 'Evil" \n do shell script "id'})
    script = captured["cmd"][-1]
    assert script == 'tell application "Evil\\" \n do shell script \\"id" to activate'


# ---------------------------------------------------------------------------
# Linux
# ---------------------------------------------------------------------------


def test_focus_linux_prefers_xdotool(monkeypatch):
    monkeypatch.setattr(terminal_focus.sys, "platform", "linux")
    monkeypatch.setattr(
        terminal_focus.shutil,
        "which",
        lambda name: "/usr/bin/xdotool" if name == "xdotool" else None,
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


# ---------------------------------------------------------------------------
# macOS exact-tab focus (pid → tty → AppleScript tab match)
# ---------------------------------------------------------------------------


def _fake_run_factory(tty="ttys006", comm="claude", tab_stdout="13387", record=None):
    """_run stub routing ps / tab-script / activate calls."""

    def fake_run(cmd):
        if record is not None:
            record.append(cmd)
        if cmd[0] == "ps":
            return _FakeCompleted(stdout=f"{tty} {comm}\n")
        if cmd[0] == "osascript" and "tty of" in cmd[-1]:
            return _FakeCompleted(stdout=f"{tab_stdout}\n")
        return _FakeCompleted(returncode=0)

    return fake_run


def test_tty_for_pid_parses_ps(monkeypatch):
    monkeypatch.setattr(terminal_focus, "_run", _fake_run_factory())
    assert terminal_focus._tty_for_pid(91314) == "/dev/ttys006"


def test_tty_for_pid_no_controlling_tty(monkeypatch):
    monkeypatch.setattr(terminal_focus, "_run", _fake_run_factory(tty="??"))
    assert terminal_focus._tty_for_pid(91314) is None


def test_tty_for_pid_dead_process(monkeypatch):
    def boom(cmd):
        raise subprocess.SubprocessError("no such process")

    monkeypatch.setattr(terminal_focus, "_run", boom)
    assert terminal_focus._tty_for_pid(99999) is None


def test_tty_for_pid_recycled_pid_rejected(monkeypatch):
    # The pid now belongs to some other process → its tty must not be trusted.
    monkeypatch.setattr(terminal_focus, "_run", _fake_run_factory(comm="vim"))
    assert terminal_focus._tty_for_pid(91314) is None


def test_tty_for_pid_accepts_full_claude_path(monkeypatch):
    monkeypatch.setattr(
        terminal_focus, "_run", _fake_run_factory(comm="/usr/local/bin/claude")
    )
    assert terminal_focus._tty_for_pid(91314) == "/dev/ttys006"


def test_focus_macos_exact_tab(monkeypatch):
    monkeypatch.setattr(terminal_focus.sys, "platform", "darwin")
    monkeypatch.setattr(terminal_focus.shutil, "which", lambda name: "/usr/bin/osascript")
    calls = []
    monkeypatch.setattr(terminal_focus, "_run", _fake_run_factory(record=calls))

    result = terminal_focus.focus_terminal({"term_program": "Apple_Terminal", "pid": 91314})
    assert result["focused"] is True
    assert result["method"] == "osascript-tab"
    assert "/dev/ttys006" in result["detail"]
    assert "13387" in result["detail"]
    tab_script = next(c[-1] for c in calls if c[0] == "osascript")
    assert '"Terminal"' in tab_script
    assert '"/dev/ttys006"' in tab_script


def test_focus_macos_iterm_targets_iterm2(monkeypatch):
    monkeypatch.setattr(terminal_focus.sys, "platform", "darwin")
    monkeypatch.setattr(terminal_focus.shutil, "which", lambda name: "/usr/bin/osascript")
    calls = []
    monkeypatch.setattr(terminal_focus, "_run", _fake_run_factory(record=calls))

    result = terminal_focus.focus_terminal({"term_program": "iTerm.app", "pid": 91314})
    assert result["method"] == "osascript-tab"
    tab_script = next(c[-1] for c in calls if c[0] == "osascript")
    assert '"iTerm2"' in tab_script
    assert "sessions of t" in tab_script


def test_focus_macos_tab_not_found_falls_back_to_activate(monkeypatch):
    monkeypatch.setattr(terminal_focus.sys, "platform", "darwin")
    monkeypatch.setattr(terminal_focus.shutil, "which", lambda name: "/usr/bin/osascript")
    calls = []
    monkeypatch.setattr(terminal_focus, "_run", _fake_run_factory(tab_stdout="", record=calls))

    result = terminal_focus.focus_terminal({"term_program": "Apple_Terminal", "pid": 91314})
    assert result["focused"] is True
    assert result["method"] == "osascript"
    activate = [
        c for c in calls if c[0] == "osascript" and "activate" in c[-1] and "tty" not in c[-1]
    ]
    assert activate, "expected fallback to plain app activation"


def test_focus_macos_unsupported_app_skips_tab_script(monkeypatch):
    monkeypatch.setattr(terminal_focus.sys, "platform", "darwin")
    monkeypatch.setattr(terminal_focus.shutil, "which", lambda name: "/usr/bin/osascript")
    calls = []
    monkeypatch.setattr(terminal_focus, "_run", _fake_run_factory(record=calls))

    result = terminal_focus.focus_terminal({"term_program": "WezTerm", "pid": 91314})
    assert result["method"] == "osascript"
    assert not any("tty of" in c[-1] for c in calls if c[0] == "osascript")


def test_focus_macos_no_pid_keeps_activate_behavior(monkeypatch):
    monkeypatch.setattr(terminal_focus.sys, "platform", "darwin")
    monkeypatch.setattr(terminal_focus.shutil, "which", lambda name: "/usr/bin/osascript")
    calls = []
    monkeypatch.setattr(terminal_focus, "_run", _fake_run_factory(record=calls))

    result = terminal_focus.focus_terminal({"term_program": "Apple_Terminal"})
    assert result["method"] == "osascript"
    assert not any(c[0] == "ps" for c in calls)

"""Tests for ``services.terminal_focus``.

The service shells out to OS window managers, so every test mocks
``shutil.which`` / ``subprocess.run`` / ``sys.platform`` — nothing real is
executed. Covers method selection, durable-identifier preference, honest
success reporting, best-effort fallbacks, and the never-raise contract.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

_api_dir = Path(__file__).resolve().parent.parent
if str(_api_dir) not in sys.path:
    sys.path.insert(0, str(_api_dir))

from services import terminal_focus


class _FakeCompleted:
    def __init__(self, returncode=0, stdout="", stderr=""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


@pytest.fixture(autouse=True)
def _clear_probe_cache():
    terminal_focus._probe_cache.clear()
    yield
    terminal_focus._probe_cache.clear()


def _fake_run_factory(
    tty="ttys006",
    comm="claude",
    tab_stdout="13387 raised",
    record=None,
    app_running=True,
):
    """_run stub routing ps / is-running probes / tab scripts / activation."""

    def fake_run(cmd):
        if record is not None:
            record.append(cmd)
        if cmd[0] == "ps":
            if "tty=,comm=" in cmd:
                return _FakeCompleted(stdout=f"{tty} {comm}\n")
            return _FakeCompleted(stdout=f"{comm}\n")
        if cmd[0] == "osascript":
            script = cmd[-1]
            if script.endswith("is running"):
                return _FakeCompleted(stdout="true\n" if app_running else "false\n")
            if "tty of" in script or "id of s is" in script:
                return _FakeCompleted(stdout=f"{tab_stdout}\n")
        return _FakeCompleted(returncode=0)

    return fake_run


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


def test_can_focus_dead_pid_hides_button_everywhere(monkeypatch):
    # A dead (or recycled) pid means the session is over — the button is
    # withheld on every platform, tmux panes included.
    monkeypatch.setattr(terminal_focus, "pid_is_live_claude", lambda pid: False)
    monkeypatch.setattr(terminal_focus.sys, "platform", "darwin")
    assert terminal_focus.can_focus({"term_program": "Apple_Terminal", "pid": 1234}) is False
    assert terminal_focus.can_focus({"tmux_pane": "%1", "pid": 1234}) is False
    monkeypatch.setattr(terminal_focus.sys, "platform", "linux")
    assert terminal_focus.can_focus({"window_id": "123", "pid": 1234}) is False


def test_can_focus_alive_pid(monkeypatch):
    monkeypatch.setattr(terminal_focus.sys, "platform", "darwin")
    monkeypatch.setattr(terminal_focus, "pid_is_live_claude", lambda pid: True)
    assert terminal_focus.can_focus({"term_program": "Apple_Terminal", "pid": 1234}) is True


def test_can_focus_legacy_no_pid_keeps_button(monkeypatch):
    def boom(pid):
        raise AssertionError("pid probe must not run without a pid")

    monkeypatch.setattr(terminal_focus, "pid_is_live_claude", boom)
    monkeypatch.setattr(terminal_focus.sys, "platform", "linux")
    assert terminal_focus.can_focus({"window_id": "123"}) is True


# ---------------------------------------------------------------------------
# pid liveness probes
# ---------------------------------------------------------------------------


def test_pid_alive_windows_fallback_without_ctypes_windll(monkeypatch):
    # On non-Windows hosts the ctypes probe is unavailable; never os.kill.
    def boom(pid, sig):
        raise AssertionError("os.kill must not run off POSIX")

    monkeypatch.setattr(terminal_focus.os, "kill", boom)
    monkeypatch.setattr(terminal_focus.os, "name", "nt")
    assert terminal_focus._pid_alive(1234) is True


def test_pid_is_live_claude_rejects_recycled_comm(monkeypatch):
    monkeypatch.setattr(terminal_focus, "_pid_alive", lambda pid: True)
    monkeypatch.setattr(terminal_focus, "_run", _fake_run_factory(comm="vim"))
    monkeypatch.setattr(terminal_focus.os, "name", "posix")
    assert terminal_focus.pid_is_live_claude(4242) is False


def test_pid_is_live_claude_accepts_claude_comm(monkeypatch):
    monkeypatch.setattr(terminal_focus, "_pid_alive", lambda pid: True)
    monkeypatch.setattr(terminal_focus, "_run", _fake_run_factory(comm="/usr/local/bin/claude"))
    monkeypatch.setattr(terminal_focus.os, "name", "posix")
    assert terminal_focus.pid_is_live_claude(4242) is True


def test_pid_is_live_claude_caches_probe(monkeypatch):
    calls = []

    def fake_alive(pid):
        calls.append(pid)
        return False

    monkeypatch.setattr(terminal_focus, "_pid_alive", fake_alive)
    assert terminal_focus.pid_is_live_claude(7) is False
    assert terminal_focus.pid_is_live_claude(7) is False
    assert calls == [7]  # second call served from the TTL cache


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


def _tmux_run_factory(
    record,
    session_name="main",
    attached=None,
    all_clients=None,
    pane_ok=True,
    switch_ok=True,
    gui_tab_stdout="42 raised",
):
    def fake_run(cmd):
        record.append(cmd)
        if cmd[0] == "osascript":
            script = cmd[-1]
            if script.endswith("is running"):
                return _FakeCompleted(stdout="true\n")
            if "tty of" in script:
                return _FakeCompleted(stdout=f"{gui_tab_stdout}\n")
            return _FakeCompleted()
        if cmd[0] != "tmux":
            return _FakeCompleted()
        sub = cmd[1]
        if sub in ("select-window", "select-pane"):
            return _FakeCompleted(
                returncode=0 if pane_ok else 1,
                stderr="" if pane_ok else "can't find pane",
            )
        if sub == "display-message":
            return _FakeCompleted(stdout=f"{session_name}\n")
        if sub == "list-clients":
            rows = (attached or []) if "-t" in cmd else (all_clients or [])
            return _FakeCompleted(stdout="".join(f"{t}\t{a}\n" for t, a in rows))
        if sub == "switch-client":
            return _FakeCompleted(returncode=0 if switch_ok else 1)
        return _FakeCompleted()

    return fake_run


def test_focus_tmux_attached_client_success(monkeypatch):
    monkeypatch.setattr(terminal_focus.sys, "platform", "win32")
    monkeypatch.setattr(terminal_focus.shutil, "which", lambda name: "/usr/bin/tmux")
    calls = []
    monkeypatch.setattr(
        terminal_focus, "_run", _tmux_run_factory(calls, attached=[("/dev/ttys009", 100)])
    )

    result = terminal_focus.focus_terminal({"tmux_pane": "%3"})
    assert result["focused"] is True
    assert result["method"] == "tmux"
    assert "client_tty" not in result  # internal key must not leak to the API
    # A client already shows the session — no client stealing.
    assert not any(c[0] == "tmux" and c[1] == "switch-client" for c in calls)


def test_focus_tmux_switches_client_from_other_session(monkeypatch):
    monkeypatch.setattr(terminal_focus.sys, "platform", "win32")
    monkeypatch.setattr(terminal_focus.shutil, "which", lambda name: "/usr/bin/tmux")
    calls = []
    monkeypatch.setattr(
        terminal_focus,
        "_run",
        _tmux_run_factory(calls, attached=[], all_clients=[("/dev/ttys009", 100)]),
    )

    result = terminal_focus.focus_terminal({"tmux_pane": "%3"})
    assert result["focused"] is True
    switch = next(c for c in calls if c[0] == "tmux" and c[1] == "switch-client")
    # The target client is named explicitly — from the API process there is
    # no "current client" for tmux to infer.
    assert "-c" in switch and "/dev/ttys009" in switch


def test_focus_tmux_detached_is_honest(monkeypatch):
    monkeypatch.setattr(terminal_focus.sys, "platform", "win32")
    monkeypatch.setattr(terminal_focus.shutil, "which", lambda name: "/usr/bin/tmux")
    calls = []
    monkeypatch.setattr(terminal_focus, "_run", _tmux_run_factory(calls))

    result = terminal_focus.focus_terminal({"tmux_pane": "%3"})
    assert result["focused"] is False
    assert "tmux attach -t main" in result["detail"]


def test_focus_tmux_dead_pane_is_honest(monkeypatch):
    monkeypatch.setattr(terminal_focus.sys, "platform", "win32")
    monkeypatch.setattr(terminal_focus.shutil, "which", lambda name: "/usr/bin/tmux")
    calls = []
    monkeypatch.setattr(terminal_focus, "_run", _tmux_run_factory(calls, pane_ok=False))

    result = terminal_focus.focus_terminal({"tmux_pane": "%3"})
    assert result["focused"] is False
    assert "can't find pane" in result["detail"]


def test_focus_tmux_raises_hosting_gui_window_on_macos(monkeypatch):
    monkeypatch.setattr(terminal_focus.sys, "platform", "darwin")
    monkeypatch.setattr(terminal_focus.shutil, "which", lambda name: f"/usr/bin/{name}")
    calls = []
    monkeypatch.setattr(
        terminal_focus, "_run", _tmux_run_factory(calls, attached=[("/dev/ttys009", 100)])
    )

    result = terminal_focus.focus_terminal({"tmux_pane": "%3"})
    assert result["focused"] is True
    assert result["method"] == "tmux+gui"
    # The GUI raise matches the CLIENT's tty, not the pane's pty.
    gui_scripts = [c[-1] for c in calls if c[0] == "osascript" and "tty of" in c[-1]]
    assert any("/dev/ttys009" in s for s in gui_scripts)


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
# macOS — app activation fallback (guarded)
# ---------------------------------------------------------------------------


def test_focus_macos_maps_app_name(monkeypatch):
    monkeypatch.setattr(terminal_focus.sys, "platform", "darwin")
    monkeypatch.setattr(terminal_focus.shutil, "which", lambda name: "/usr/bin/osascript")
    calls = []
    monkeypatch.setattr(terminal_focus, "_run", _fake_run_factory(record=calls))

    result = terminal_focus.focus_terminal({"term_program": "iTerm.app"})
    assert result["focused"] is True
    assert result["method"] == "osascript"
    # iTerm.app maps to "iTerm"
    assert any('tell application "iTerm" to activate' in c[-1] for c in calls)


def test_focus_macos_unknown_program_uses_raw_name(monkeypatch):
    monkeypatch.setattr(terminal_focus.sys, "platform", "darwin")
    monkeypatch.setattr(terminal_focus.shutil, "which", lambda name: "/usr/bin/osascript")
    calls = []
    monkeypatch.setattr(terminal_focus, "_run", _fake_run_factory(record=calls))

    terminal_focus.focus_terminal({"term_program": "SomeNewTerm"})
    assert any('tell application "SomeNewTerm" to activate' in c[-1] for c in calls)


def test_focus_macos_prefers_bundle_id(monkeypatch):
    monkeypatch.setattr(terminal_focus.sys, "platform", "darwin")
    monkeypatch.setattr(terminal_focus.shutil, "which", lambda name: "/usr/bin/osascript")
    calls = []
    monkeypatch.setattr(terminal_focus, "_run", _fake_run_factory(record=calls))

    # Cursor sets TERM_PROGRAM=vscode; the bundle id must win so real VS Code
    # is never targeted.
    result = terminal_focus.focus_terminal(
        {"term_program": "vscode", "bundle_id": "com.todesktop.cursor"}
    )
    assert result["focused"] is True
    assert any('tell application id "com.todesktop.cursor" to activate' in c[-1] for c in calls)
    assert not any('application "Code"' in c[-1] for c in calls)


def test_focus_macos_never_launches_a_quit_app(monkeypatch):
    monkeypatch.setattr(terminal_focus.sys, "platform", "darwin")
    monkeypatch.setattr(terminal_focus.shutil, "which", lambda name: "/usr/bin/osascript")
    calls = []
    monkeypatch.setattr(terminal_focus, "_run", _fake_run_factory(record=calls, app_running=False))

    result = terminal_focus.focus_terminal({"term_program": "WezTerm"})
    assert result["focused"] is False
    assert "not running" in result["detail"]
    # `tell ... to activate` launches non-running apps; it must never be sent.
    assert not any("to activate" in c[-1] for c in calls if c[0] == "osascript")


def test_focus_macos_escapes_applescript_injection(monkeypatch):
    # A quote in TERM_PROGRAM must not break out of the AppleScript string.
    monkeypatch.setattr(terminal_focus.sys, "platform", "darwin")
    monkeypatch.setattr(terminal_focus.shutil, "which", lambda name: "/usr/bin/osascript")
    calls = []
    monkeypatch.setattr(terminal_focus, "_run", _fake_run_factory(record=calls))

    terminal_focus.focus_terminal({"term_program": 'Evil" \n do shell script "id'})
    activate = [c[-1] for c in calls if c[0] == "osascript" and "to activate" in c[-1]]
    assert activate == ['tell application "Evil\\" \\n do shell script \\"id" to activate']


def test_applescript_str_escapes_control_characters():
    assert terminal_focus._applescript_str('a"b\\c\nd\re') == 'a\\"b\\\\c\\nd\\re'


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


def test_focus_linux_dead_pid_refuses_recycled_window_id(monkeypatch):
    monkeypatch.setattr(terminal_focus.sys, "platform", "linux")
    monkeypatch.setattr(terminal_focus, "pid_is_live_claude", lambda pid: False)

    def boom(cmd):
        raise AssertionError("no window manager tool may run for a dead session")

    monkeypatch.setattr(terminal_focus, "_run", boom)
    result = terminal_focus.focus_terminal({"window_id": "123", "pid": 4242})
    assert result["focused"] is False
    assert "recycled" in result["detail"]


# ---------------------------------------------------------------------------
# macOS exact-tab focus (stored identifiers > pid → tty)
# ---------------------------------------------------------------------------


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


def test_focus_macos_exact_tab_via_stored_tty(monkeypatch):
    monkeypatch.setattr(terminal_focus.sys, "platform", "darwin")
    monkeypatch.setattr(terminal_focus.shutil, "which", lambda name: "/usr/bin/osascript")
    monkeypatch.setattr(terminal_focus, "pid_is_live_claude", lambda pid: True)
    calls = []
    monkeypatch.setattr(terminal_focus, "_run", _fake_run_factory(record=calls))

    result = terminal_focus.focus_terminal(
        {"term_program": "Apple_Terminal", "pid": 91314, "tty": "/dev/ttys006"}
    )
    assert result["focused"] is True
    assert result["method"] == "osascript-tab"
    assert "/dev/ttys006" in result["detail"]
    assert "13387" in result["detail"]
    tab_script = next(c[-1] for c in calls if c[0] == "osascript" and "tty of" in c[-1])
    assert '"Terminal"' in tab_script
    assert '"/dev/ttys006"' in tab_script
    # Stored tty wins — no click-time pid → tty lookup at all.
    assert not any(c[0] == "ps" for c in calls)


def test_focus_macos_stored_tty_beats_recycled_pids_tty(monkeypatch):
    # Pid recycled onto another claude on ttys999: the stored tty from
    # capture time must be matched, not the impostor's.
    monkeypatch.setattr(terminal_focus.sys, "platform", "darwin")
    monkeypatch.setattr(terminal_focus.shutil, "which", lambda name: "/usr/bin/osascript")
    monkeypatch.setattr(terminal_focus, "pid_is_live_claude", lambda pid: True)
    calls = []
    monkeypatch.setattr(terminal_focus, "_run", _fake_run_factory(tty="ttys999", record=calls))

    terminal_focus.focus_terminal(
        {"term_program": "Apple_Terminal", "pid": 91314, "tty": "/dev/ttys006"}
    )
    tab_script = next(c[-1] for c in calls if c[0] == "osascript" and "tty of" in c[-1])
    assert '"/dev/ttys006"' in tab_script
    assert "ttys999" not in tab_script


def test_focus_macos_legacy_state_falls_back_to_pid_tty(monkeypatch):
    monkeypatch.setattr(terminal_focus.sys, "platform", "darwin")
    monkeypatch.setattr(terminal_focus.shutil, "which", lambda name: "/usr/bin/osascript")
    monkeypatch.setattr(terminal_focus, "pid_is_live_claude", lambda pid: True)
    calls = []
    monkeypatch.setattr(terminal_focus, "_run", _fake_run_factory(record=calls))

    result = terminal_focus.focus_terminal({"term_program": "Apple_Terminal", "pid": 91314})
    assert result["focused"] is True
    assert result["method"] == "osascript-tab"
    assert any(c[0] == "ps" for c in calls)


def test_focus_macos_iterm_by_session_id_first(monkeypatch):
    monkeypatch.setattr(terminal_focus.sys, "platform", "darwin")
    monkeypatch.setattr(terminal_focus.shutil, "which", lambda name: "/usr/bin/osascript")
    calls = []
    monkeypatch.setattr(terminal_focus, "_run", _fake_run_factory(record=calls))

    result = terminal_focus.focus_terminal(
        {
            "term_program": "iTerm.app",
            "pid": 91314,
            "tty": "/dev/ttys006",
            "iterm_session_id": "w0t2p0:44BF03B0-AAAA-BBBB-CCCC-DDDDEEEEFFFF",
        }
    )
    assert result["focused"] is True
    assert result["method"] == "osascript-tab"
    id_script = next(c[-1] for c in calls if c[0] == "osascript" and "id of s is" in c[-1])
    # The UUID part after the colon is matched against the session's id.
    assert '"44BF03B0-AAAA-BBBB-CCCC-DDDDEEEEFFFF"' in id_script
    # The durable id matched — the tty script never runs.
    assert not any("tty of" in c[-1] for c in calls if c[0] == "osascript")


def test_focus_macos_iterm_id_miss_falls_back_to_tty(monkeypatch):
    monkeypatch.setattr(terminal_focus.sys, "platform", "darwin")
    monkeypatch.setattr(terminal_focus.shutil, "which", lambda name: "/usr/bin/osascript")
    calls = []

    def fake_run(cmd):
        calls.append(cmd)
        script = cmd[-1]
        if cmd[0] == "osascript":
            if script.endswith("is running"):
                return _FakeCompleted(stdout="true\n")
            if "id of s is" in script:
                return _FakeCompleted(stdout="\n")  # tab was closed / id unknown
            if "tty of" in script:
                return _FakeCompleted(stdout="7 raised\n")
        return _FakeCompleted()

    monkeypatch.setattr(terminal_focus, "_run", fake_run)
    result = terminal_focus.focus_terminal(
        {
            "term_program": "iTerm.app",
            "tty": "/dev/ttys006",
            "iterm_session_id": "w0t2p0:DEAD",
        }
    )
    assert result["focused"] is True
    assert any("tty of" in c[-1] for c in calls if c[0] == "osascript")


def test_focus_macos_iterm_tty_script_targets_iterm2(monkeypatch):
    monkeypatch.setattr(terminal_focus.sys, "platform", "darwin")
    monkeypatch.setattr(terminal_focus.shutil, "which", lambda name: "/usr/bin/osascript")
    monkeypatch.setattr(terminal_focus, "pid_is_live_claude", lambda pid: True)
    calls = []
    monkeypatch.setattr(terminal_focus, "_run", _fake_run_factory(record=calls))

    result = terminal_focus.focus_terminal({"term_program": "iTerm.app", "pid": 91314})
    assert result["method"] == "osascript-tab"
    tab_script = next(c[-1] for c in calls if c[0] == "osascript" and "tty of" in c[-1])
    assert '"iTerm2"' in tab_script
    assert "sessions of t" in tab_script


def test_focus_macos_tab_not_found_alive_pid_falls_back_to_activate(monkeypatch):
    monkeypatch.setattr(terminal_focus.sys, "platform", "darwin")
    monkeypatch.setattr(terminal_focus.shutil, "which", lambda name: "/usr/bin/osascript")
    monkeypatch.setattr(terminal_focus, "pid_is_live_claude", lambda pid: True)
    calls = []
    monkeypatch.setattr(terminal_focus, "_run", _fake_run_factory(tab_stdout="", record=calls))

    result = terminal_focus.focus_terminal({"term_program": "Apple_Terminal", "pid": 91314})
    assert result["focused"] is True
    assert result["method"] == "osascript"
    assert any("to activate" in c[-1] for c in calls if c[0] == "osascript")


def test_focus_macos_unsupported_app_skips_tab_script(monkeypatch):
    monkeypatch.setattr(terminal_focus.sys, "platform", "darwin")
    monkeypatch.setattr(terminal_focus.shutil, "which", lambda name: "/usr/bin/osascript")
    monkeypatch.setattr(terminal_focus, "pid_is_live_claude", lambda pid: True)
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


# ---------------------------------------------------------------------------
# Window raise truthfulness + dead-session lifecycle
# ---------------------------------------------------------------------------


def test_terminal_app_script_raises_index_first_with_verified_fallback():
    # `set index to 1` is the raise that works (windows on other Spaces
    # ignore `set miniaturized`); the cycle stays as fallback, and the
    # script must VERIFY the outcome instead of assuming it.
    script = terminal_focus._MAC_TAB_SCRIPTS["Apple_Terminal"]
    assert "set index of window id matchedId to 1" in script
    assert script.index("set index") < script.index("activate")
    assert "set miniaturized" in script
    assert "if id of front window is not matchedId" in script
    assert '" raised"' in script
    assert '" selected"' in script


def test_focus_macos_fullscreen_selected_not_raised_is_honest(monkeypatch):
    # Fullscreen windows can't be miniaturized: the tab gets selected but the
    # window stays buried. The result must say focused=false, and must NOT
    # fall through to app activation (which would raise a different window).
    monkeypatch.setattr(terminal_focus.sys, "platform", "darwin")
    monkeypatch.setattr(terminal_focus.shutil, "which", lambda name: "/usr/bin/osascript")
    monkeypatch.setattr(terminal_focus, "pid_is_live_claude", lambda pid: True)
    calls = []
    monkeypatch.setattr(
        terminal_focus, "_run", _fake_run_factory(tab_stdout="13387 selected", record=calls)
    )

    result = terminal_focus.focus_terminal(
        {"term_program": "Apple_Terminal", "tty": "/dev/ttys006", "pid": 91314}
    )
    assert result["focused"] is False
    assert result["method"] == "osascript-tab"
    assert "full screen" in result["detail"]
    assert not any("to activate" in c[-1] for c in calls if c[0] == "osascript")


def test_focus_macos_dead_pid_fails_instead_of_wrong_window(monkeypatch):
    monkeypatch.setattr(terminal_focus.sys, "platform", "darwin")
    monkeypatch.setattr(terminal_focus.shutil, "which", lambda name: "/usr/bin/osascript")
    monkeypatch.setattr(terminal_focus, "pid_is_live_claude", lambda pid: False)
    calls = []
    monkeypatch.setattr(terminal_focus, "_run", _fake_run_factory(record=calls))

    result = terminal_focus.focus_terminal({"term_program": "Apple_Terminal", "pid": 424242})
    assert result["focused"] is False
    assert "Could not locate" in result["detail"]
    # No blind app activation of an arbitrary window.
    assert not any("to activate" in c[-1] for c in calls if c[0] == "osascript")


def test_focus_macos_dead_pid_refuses_stored_tty_match(monkeypatch):
    # tty devices are recycled once their tab closes — after the process
    # dies, a stored tty may already belong to a stranger's tab, so it must
    # not be matched (honest failure beats raising the wrong window).
    monkeypatch.setattr(terminal_focus.sys, "platform", "darwin")
    monkeypatch.setattr(terminal_focus.shutil, "which", lambda name: "/usr/bin/osascript")
    monkeypatch.setattr(terminal_focus, "pid_is_live_claude", lambda pid: False)
    calls = []
    monkeypatch.setattr(terminal_focus, "_run", _fake_run_factory(record=calls))

    result = terminal_focus.focus_terminal(
        {"term_program": "Apple_Terminal", "pid": 424242, "tty": "/dev/ttys006"}
    )
    assert result["focused"] is False
    assert not any("tty of" in c[-1] for c in calls if c[0] == "osascript")


def test_focus_macos_dead_pid_still_matches_iterm_session_id(monkeypatch):
    # iTerm session UUIDs are never recycled — unlike a tty, the id match
    # stays safe after the process dies (click racing the session's death).
    monkeypatch.setattr(terminal_focus.sys, "platform", "darwin")
    monkeypatch.setattr(terminal_focus.shutil, "which", lambda name: "/usr/bin/osascript")
    monkeypatch.setattr(terminal_focus, "pid_is_live_claude", lambda pid: False)
    calls = []
    monkeypatch.setattr(terminal_focus, "_run", _fake_run_factory(record=calls))

    result = terminal_focus.focus_terminal(
        {
            "term_program": "iTerm.app",
            "pid": 424242,
            "tty": "/dev/ttys006",
            "iterm_session_id": "w0t2p0:44BF03B0-AAAA-BBBB-CCCC-DDDDEEEEFFFF",
        }
    )
    assert result["focused"] is True
    assert result["method"] == "osascript-tab"
    assert any("id of s is" in c[-1] for c in calls if c[0] == "osascript")

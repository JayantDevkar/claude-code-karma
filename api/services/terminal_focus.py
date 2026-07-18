"""Focus (raise) the terminal window/pane a live session runs in.

Claude Code Karma runs locally on the same machine as the terminals it
tracks, so the API can shell out to OS-level window managers to bring the
right terminal to the foreground. Supported focus methods:

- **tmux**  : select the window/pane the session lives in (any host OS, when
  the session was started inside tmux).
- **macOS** : activate the terminal application via AppleScript (``osascript``),
  mapped from ``TERM_PROGRAM``.
- **Linux** : activate the X11 window via ``xdotool`` / ``wmctrl`` using
  ``WINDOWID``.

Everything is best-effort: if the required tool isn't installed or the
identifier wasn't captured, we report what was attempted instead of raising.
The terminal identifiers come from
:func:`hooks.live_session_tracker.resolve_terminal`.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from typing import Any, Dict, Optional

# TERM_PROGRAM -> macOS application name for `tell application "<name>" to activate`.
# Falls back to the raw TERM_PROGRAM value when unmapped.
_MAC_APP_NAMES: Dict[str, str] = {
    "iTerm.app": "iTerm",
    "Apple_Terminal": "Terminal",
    "WezTerm": "WezTerm",
    "Hyper": "Hyper",
    "vscode": "Code",
    "ghostty": "Ghostty",
    "Tabby": "Tabby",
    "kitty": "kitty",
    "alacritty": "Alacritty",
    "Warp": "Warp",
}

_TIMEOUT_SECONDS = 5


def _run(cmd: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, timeout=_TIMEOUT_SECONDS)


def can_focus(terminal: Optional[Dict[str, Any]]) -> bool:
    """Whether we have an identifier we could plausibly focus on this host.

    tmux panes are focusable on any OS; GUI-window focus depends on the host
    the API is running on (which is the same machine as the terminal).
    """
    if not terminal:
        return False
    if terminal.get("tmux_pane"):
        return True
    if sys.platform == "darwin" and terminal.get("term_program"):
        return True
    if sys.platform.startswith("linux") and terminal.get("window_id"):
        return True
    return False


def _focus_tmux(pane: str) -> Dict[str, Any]:
    """Make ``pane`` the active pane in its tmux window/session."""
    if not shutil.which("tmux"):
        return {"focused": False, "method": "tmux", "detail": "tmux not found on PATH"}
    try:
        _run(["tmux", "select-window", "-t", pane])
        res = _run(["tmux", "select-pane", "-t", pane])
        # If a client is attached to the pane's session, switch it to that window.
        sess = _run(["tmux", "display-message", "-p", "-t", pane, "#{session_name}"])
        session_name = sess.stdout.strip()
        if session_name:
            _run(["tmux", "switch-client", "-t", session_name])
        ok = res.returncode == 0
        return {
            "focused": ok,
            "method": "tmux",
            "detail": (res.stderr.strip() or f"selected tmux pane {pane}"),
        }
    except (subprocess.SubprocessError, OSError) as exc:
        return {"focused": False, "method": "tmux", "detail": str(exc)}


# Per-app AppleScript to select the exact tab owning a tty. Keyed by
# TERM_PROGRAM so we never `tell` (and thereby launch) an app the session
# isn't actually running in. `{tty}` is substituted with e.g. /dev/ttys006.
_MAC_TAB_SCRIPTS: Dict[str, str] = {
    "Apple_Terminal": (
        'tell application "Terminal"\n'
        "    repeat with w in windows\n"
        "        repeat with t in tabs of w\n"
        '            if tty of t is "{tty}" then\n'
        "                set selected of t to true\n"
        "                set index of w to 1\n"
        "                activate\n"
        "                return id of w\n"
        "            end if\n"
        "        end repeat\n"
        "    end repeat\n"
        '    return ""\n'
        "end tell"
    ),
    "iTerm.app": (
        'tell application "iTerm2"\n'
        "    repeat with w in windows\n"
        "        repeat with t in tabs of w\n"
        "            repeat with s in sessions of t\n"
        '                if tty of s is "{tty}" then\n'
        "                    select s\n"
        "                    select t\n"
        "                    select w\n"
        "                    activate\n"
        "                    return id of w\n"
        "                end if\n"
        "            end repeat\n"
        "        end repeat\n"
        "    end repeat\n"
        '    return ""\n'
        "end tell"
    ),
}


def _tty_for_pid(pid: int) -> Optional[str]:
    """Resolve the tty a live process is attached to, e.g. '/dev/ttys006'."""
    try:
        res = _run(["ps", "-o", "tty=", "-p", str(pid)])
        tty = res.stdout.strip()
        if res.returncode == 0 and tty and tty not in ("??", "-"):
            return tty if tty.startswith("/dev/") else f"/dev/{tty}"
    except (subprocess.SubprocessError, OSError):
        pass
    return None


def _focus_macos_tab(term_program: str, tty: str) -> Optional[Dict[str, Any]]:
    """Select the exact window/tab owning ``tty``; None means fall back."""
    script = _MAC_TAB_SCRIPTS.get(term_program)
    if not script:
        return None
    try:
        res = _run(["osascript", "-e", script.format(tty=tty)])
        window_id = res.stdout.strip()
        if res.returncode == 0 and window_id:
            return {
                "focused": True,
                "method": "osascript-tab",
                "detail": f"selected {term_program} tab on {tty} (window id {window_id})",
            }
    except (subprocess.SubprocessError, OSError):
        pass
    return None


def _focus_macos(term_program: str, pid: Optional[int] = None) -> Dict[str, Any]:
    """Bring the macOS terminal to the foreground, exact tab when possible.

    The session's captured pid is the live ``claude`` process; while the
    session is running its tty identifies the exact tab, which the supported
    apps can select via AppleScript. Anything else falls back to activating
    the application.
    """
    if not shutil.which("osascript"):
        return {"focused": False, "method": "osascript", "detail": "osascript not found"}
    tty = _tty_for_pid(pid) if pid else None
    if tty:
        exact = _focus_macos_tab(term_program, tty)
        if exact:
            return exact
    app = _MAC_APP_NAMES.get(term_program, term_program)
    try:
        res = _run(["osascript", "-e", f'tell application "{app}" to activate'])
        return {
            "focused": res.returncode == 0,
            "method": "osascript",
            "detail": (res.stderr.strip() or f"activated {app}"),
        }
    except (subprocess.SubprocessError, OSError) as exc:
        return {"focused": False, "method": "osascript", "detail": str(exc)}


def _focus_linux(window_id: str) -> Dict[str, Any]:
    """Activate an X11 window by id via xdotool (preferred) or wmctrl."""
    last_detail = ""
    try:
        if shutil.which("xdotool"):
            # xdotool accepts a decimal window id directly.
            res = _run(["xdotool", "windowactivate", str(window_id)])
            if res.returncode == 0:
                return {
                    "focused": True,
                    "method": "xdotool",
                    "detail": f"activated window {window_id}",
                }
            last_detail = res.stderr.strip()
        else:
            last_detail = "xdotool not found"

        if shutil.which("wmctrl"):
            # wmctrl expects a hex window id like 0x01234567.
            try:
                hex_id = window_id if str(window_id).startswith("0x") else hex(int(window_id))
            except (ValueError, TypeError):
                hex_id = str(window_id)
            res = _run(["wmctrl", "-i", "-a", hex_id])
            return {
                "focused": res.returncode == 0,
                "method": "wmctrl",
                "detail": (res.stderr.strip() or f"activated window {hex_id}"),
            }
    except (subprocess.SubprocessError, OSError) as exc:
        return {"focused": False, "method": "linux", "detail": str(exc)}

    return {
        "focused": False,
        "method": "none",
        "detail": last_detail or "no window manager tool (xdotool/wmctrl) found",
    }


def focus_terminal(terminal: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Attempt to raise the terminal for a session.

    Returns a dict ``{focused: bool, method: str, detail: str}``. Never
    raises — a missing tool or identifier is reported via ``focused=False``.

    Strategy: bring the GUI terminal window forward for the host OS *and*,
    when the session runs in tmux, select the correct pane inside it. The
    most informative successful result is returned (GUI focus preferred).
    """
    if not terminal:
        return {
            "focused": False,
            "method": "none",
            "detail": "No terminal information was captured for this session.",
        }

    tmux_pane = terminal.get("tmux_pane")
    tmux_result = _focus_tmux(tmux_pane) if tmux_pane else None

    if sys.platform == "darwin" and terminal.get("term_program"):
        gui_result: Optional[Dict[str, Any]] = _focus_macos(
            terminal["term_program"], pid=terminal.get("pid")
        )
    elif sys.platform.startswith("linux") and terminal.get("window_id"):
        gui_result = _focus_linux(str(terminal["window_id"]))
    else:
        gui_result = None

    # Prefer a successful GUI focus, then a successful tmux focus, then any
    # attempted result so the caller sees a useful detail message.
    if gui_result and gui_result.get("focused"):
        return gui_result
    if tmux_result and tmux_result.get("focused"):
        return tmux_result
    if gui_result:
        return gui_result
    if tmux_result:
        return tmux_result
    return {
        "focused": False,
        "method": "none",
        "detail": "No supported terminal focus method is available for this session.",
    }

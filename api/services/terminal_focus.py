"""Focus (raise) the terminal window/pane a live session runs in.

Claude Code Karma runs locally on the same machine as the terminals it
tracks, so the API can shell out to OS-level window managers to bring the
right terminal to the foreground. Supported focus methods:

- **tmux**  : select the window/pane, put it on an attached client, and (on
  macOS) raise the GUI terminal window hosting that client.
- **macOS** : exact tab via stored identifiers — iTerm2 session UUID or the
  captured tty — with a guarded app activation fallback (``osascript``).
- **Linux** : activate the X11 window via ``xdotool`` / ``wmctrl`` using
  ``WINDOWID``.

Identity comes from :func:`hooks.live_session_tracker.resolve_terminal`,
which stores the claude process's tty (and iTerm session id / app bundle id)
*while the process is alive*. Focus prefers those stored identifiers over a
click-time pid lookup, so tab matching survives pid death and recycling.

Everything is best-effort and honest: if a window genuinely could not be
raised, the result says ``focused=False`` with a human-readable reason
instead of raising — or worse, raising the wrong window.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import time
from typing import Any, Dict, List, Optional, Tuple

# TERM_PROGRAM -> macOS application name for `tell application "<name>"`.
# Only used when no bundle id was captured; falls back to the raw value.
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

# Process names the captured pid may legitimately resolve to (the claude CLI,
# or a JS runtime when the CLI runs under one). Anything else means the pid
# was recycled by the OS after the session died. A recycled pid landing on
# another claude/node/bun process can still slip through the name check, but
# tab matching no longer trusts the pid's tty — the tty stored at capture
# time wins — so a recycled pid can't redirect focus to the wrong tab.
_CLAUDE_PROCESS_NAMES = ("claude", "node", "bun", "deno")

# Cache pid liveness probes (they shell out to ps) — can_focus runs per
# session on a 1s polling endpoint.
_PROBE_TTL_SECONDS = 5.0
_probe_cache: Dict[int, Tuple[float, bool]] = {}


def _run(cmd: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, timeout=_TIMEOUT_SECONDS)


def _applescript_str(value: str) -> str:
    """Escape a value for safe embedding inside a double-quoted AppleScript string."""
    return value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n").replace("\r", "\\r")


# ---------------------------------------------------------------------------
# Process liveness
# ---------------------------------------------------------------------------


def _pid_alive(pid: int) -> bool:
    """Whether a process with this pid still exists."""
    if os.name == "posix":
        try:
            os.kill(pid, 0)
            return True
        except ProcessLookupError:
            return False
        except OSError:
            return True  # exists but owned by someone else
    if os.name == "nt":
        # os.kill(pid, 0) TERMINATES processes on Windows — probe via ctypes.
        return _pid_alive_windows(pid)
    return True


def _pid_alive_windows(pid: int) -> bool:  # pragma: no cover - Windows only
    try:
        import ctypes

        kernel32 = ctypes.windll.kernel32
    except (ImportError, AttributeError):
        return True  # no probe available; behave like the pre-probe era
    PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
    ERROR_ACCESS_DENIED = 5
    STILL_ACTIVE = 259
    handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, int(pid))
    if not handle:
        return kernel32.GetLastError() == ERROR_ACCESS_DENIED
    try:
        code = ctypes.c_ulong()
        if kernel32.GetExitCodeProcess(handle, ctypes.byref(code)):
            return code.value == STILL_ACTIVE
        return True
    finally:
        kernel32.CloseHandle(handle)


def _comm_is_claude(pid: int) -> bool:
    """Whether the pid's process name still looks like the claude CLI."""
    try:
        res = _run(["ps", "-o", "comm=", "-p", str(pid)])
        comm = res.stdout.strip()
        if res.returncode != 0 or not comm:
            return False
        return comm.rsplit("/", 1)[-1] in _CLAUDE_PROCESS_NAMES
    except (subprocess.SubprocessError, OSError):
        return True  # flaky ps must not hide a live session's button


def pid_is_live_claude(pid: int) -> bool:
    """Cached check: the pid is alive AND still the claude-ish process captured.

    Detects both plain death and pid recycling onto an unrelated process.
    Shared by ``can_focus`` (button visibility) and the dead-session reaper.
    """
    now = time.monotonic()
    hit = _probe_cache.get(pid)
    if hit is not None and now - hit[0] < _PROBE_TTL_SECONDS:
        return hit[1]
    ok = _pid_alive(pid)
    if ok and os.name == "posix":
        ok = _comm_is_claude(pid)
    if len(_probe_cache) > 512:
        _probe_cache.clear()
    _probe_cache[pid] = (now, ok)
    return ok


# ---------------------------------------------------------------------------
# Button visibility
# ---------------------------------------------------------------------------


def can_focus(terminal: Optional[Dict[str, Any]]) -> bool:
    """Whether we have an identifier we could plausibly focus on this host.

    tmux panes are focusable on any OS; GUI-window focus depends on the host
    the API is running on (which is the same machine as the terminal). When a
    pid was captured, the button is withheld once that process is dead or
    recycled — on every platform: a dead claude means the session is over,
    and on Linux the X11 window id may itself have been recycled.
    """
    if not terminal:
        return False
    has_identifier = (
        bool(terminal.get("tmux_pane"))
        or (sys.platform == "darwin" and bool(terminal.get("term_program")))
        or (sys.platform.startswith("linux") and bool(terminal.get("window_id")))
    )
    if not has_identifier:
        return False
    pid = terminal.get("pid")
    if not pid:
        return True  # legacy capture without pid — keep the button, fail honestly on click
    return pid_is_live_claude(pid)


# ---------------------------------------------------------------------------
# tmux
# ---------------------------------------------------------------------------


def _tmux_clients(target_args: List[str]) -> List[Tuple[str, int]]:
    """List tmux clients as (client_tty, last_activity), most recent first."""
    res = _run(["tmux", "list-clients", *target_args, "-F", "#{client_tty}\t#{client_activity}"])
    clients: List[Tuple[str, int]] = []
    if res.returncode != 0:
        return clients
    for line in res.stdout.splitlines():
        parts = line.split("\t")
        if not parts or not parts[0]:
            continue
        try:
            activity = int(parts[1]) if len(parts) > 1 and parts[1] else 0
        except ValueError:
            activity = 0
        clients.append((parts[0], activity))
    clients.sort(key=lambda c: c[1], reverse=True)
    return clients


def _focus_tmux(pane: str) -> Dict[str, Any]:
    """Select ``pane`` and make sure some attached client is showing it.

    Honest by construction: ``focused=True`` only when a client actually
    displays the pane's session (already attached, or switched via
    ``switch-client -c``). A detached server reports False with the attach
    command. On success the result carries ``client_tty`` (internal key,
    popped by the caller) so the GUI window hosting that client can be raised.
    """
    if not shutil.which("tmux"):
        return {"focused": False, "method": "tmux", "detail": "tmux not found on PATH"}
    try:
        win = _run(["tmux", "select-window", "-t", pane])
        res = _run(["tmux", "select-pane", "-t", pane])
        if win.returncode != 0 or res.returncode != 0:
            detail = (
                res.stderr.strip() or win.stderr.strip() or f"tmux pane {pane} no longer exists"
            )
            return {"focused": False, "method": "tmux", "detail": detail}

        sess = _run(["tmux", "display-message", "-p", "-t", pane, "#{session_name}"])
        session_name = sess.stdout.strip()

        client_tty: Optional[str] = None
        attached = _tmux_clients(["-t", session_name]) if session_name else []
        if attached:
            client_tty = attached[0][0]
        else:
            other = _tmux_clients([])
            if other and session_name:
                candidate = other[0][0]
                sw = _run(["tmux", "switch-client", "-c", candidate, "-t", session_name])
                if sw.returncode == 0:
                    client_tty = candidate

        if client_tty:
            return {
                "focused": True,
                "method": "tmux",
                "detail": f"selected tmux pane {pane} in session '{session_name}'",
                "client_tty": client_tty,
            }
        return {
            "focused": False,
            "method": "tmux",
            "detail": (
                f"selected tmux pane {pane}, but no tmux client is attached — "
                f"run: tmux attach -t {session_name or '<session>'}"
            ),
        }
    except (subprocess.SubprocessError, OSError) as exc:
        return {"focused": False, "method": "tmux", "detail": str(exc)}


# ---------------------------------------------------------------------------
# macOS
# ---------------------------------------------------------------------------

# App owning each supported tab script — probed with `is running` before any
# `tell`, because telling a non-running app launches it.
_TAB_SCRIPT_APPS: Dict[str, str] = {
    "Apple_Terminal": "Terminal",
    "iTerm.app": "iTerm2",
}

# Per-app AppleScript to select the exact tab owning a tty. `{tty}` is
# substituted with e.g. /dev/ttys006. Terminal.app ignores `set frontmost`,
# but `set index to 1` reorders reliably (windows parked on other Spaces
# silently ignore `set miniaturized`, which is why index comes first and the
# miniaturize cycle is only a fallback). The outcome is VERIFIED: the script
# reports "raised" only when the matched window really is frontmost after
# the attempts; anything else reports "selected" so the API stays honest.
_MAC_TAB_SCRIPTS: Dict[str, str] = {
    "Apple_Terminal": (
        'tell application "Terminal"\n'
        "    set matchedId to 0\n"
        "    repeat with w in windows\n"
        "        repeat with t in tabs of w\n"
        '            if tty of t is "{tty}" then\n'
        "                set selected of t to true\n"
        "                set matchedId to id of w\n"
        "                exit repeat\n"
        "            end if\n"
        "        end repeat\n"
        "        if matchedId is not 0 then exit repeat\n"
        "    end repeat\n"
        '    if matchedId is 0 then return ""\n'
        "    try\n"
        "        set index of window id matchedId to 1\n"
        "    end try\n"
        "    activate\n"
        "    if id of front window is not matchedId then\n"
        "        try\n"
        "            set miniaturized of window id matchedId to true\n"
        "            delay 0.4\n"
        "            set miniaturized of window id matchedId to false\n"
        "            delay 0.2\n"
        "        end try\n"
        "    end if\n"
        "    if id of front window is matchedId then\n"
        '        return (matchedId as text) & " raised"\n'
        "    else\n"
        '        return (matchedId as text) & " selected"\n'
        "    end if\n"
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
        '                    return (id of w as text) & " raised"\n'
        "                end if\n"
        "            end repeat\n"
        "        end repeat\n"
        "    end repeat\n"
        '    return ""\n'
        "end tell"
    ),
}

# Same shape, but matches an iTerm2 session by its unique id (the UUID from
# ITERM_SESSION_ID). Survives pid death and recycling entirely.
_ITERM_ID_SCRIPT = (
    'tell application "iTerm2"\n'
    "    repeat with w in windows\n"
    "        repeat with t in tabs of w\n"
    "            repeat with s in sessions of t\n"
    '                if id of s is "{value}" then\n'
    "                    select s\n"
    "                    select t\n"
    "                    select w\n"
    "                    activate\n"
    '                    return (id of w as text) & " raised"\n'
    "                end if\n"
    "            end repeat\n"
    "        end repeat\n"
    "    end repeat\n"
    '    return ""\n'
    "end tell"
)


def _app_is_running(target: str) -> bool:
    """Whether ``target`` (an AppleScript app specifier) is running.

    The standalone ``application X is running`` form never launches the app;
    an unknown bundle id errors out, which also reads as not running.
    """
    try:
        res = _run(["osascript", "-e", f"{target} is running"])
        return res.returncode == 0 and res.stdout.strip() == "true"
    except (subprocess.SubprocessError, OSError):
        return False


def _macos_app_target(term_program: str, bundle_id: Optional[str]) -> str:
    """AppleScript specifier for the session's terminal app, exact when possible."""
    if bundle_id:
        return f'application id "{_applescript_str(bundle_id)}"'
    app = _MAC_APP_NAMES.get(term_program, term_program)
    return f'application "{_applescript_str(app)}"'


def _tty_for_pid(pid: int) -> Optional[str]:
    """Resolve the tty the claude process is attached to, e.g. '/dev/ttys006'.

    Click-time fallback for state files that predate stored-tty capture. The
    process name is verified so a recycled pid's tty is never trusted.
    """
    try:
        res = _run(["ps", "-o", "tty=,comm=", "-p", str(pid)])
        # comm is a full path on macOS and may contain spaces; tty never does.
        parts = res.stdout.strip().split(None, 1)
        if res.returncode != 0 or len(parts) < 2:
            return None
        tty, comm = parts
        if comm.rsplit("/", 1)[-1] not in _CLAUDE_PROCESS_NAMES:
            return None
        if tty and tty not in ("??", "-"):
            return tty if tty.startswith("/dev/") else f"/dev/{tty}"
    except (subprocess.SubprocessError, OSError):
        pass
    return None


def _parse_tab_result(
    res: subprocess.CompletedProcess, term_program: str, matched: str
) -> Optional[Dict[str, Any]]:
    """Interpret a tab script's "<window-id> raised|selected" output."""
    out = res.stdout.strip()
    if res.returncode != 0 or not out:
        return None
    parts = out.split()
    window_id = parts[0]
    if len(parts) > 1 and parts[1] == "selected":
        return {
            "focused": False,
            "method": "osascript-tab",
            "detail": (
                f"selected the {term_program} tab on {matched} (window id {window_id}), "
                "but its window could not be raised — it may be full screen; "
                "click it in the Dock or Mission Control"
            ),
        }
    return {
        "focused": True,
        "method": "osascript-tab",
        "detail": f"selected {term_program} tab on {matched} (window id {window_id})",
    }


def _focus_macos_tab(term_program: str, tty: str) -> Optional[Dict[str, Any]]:
    """Select the exact window/tab owning ``tty``; None means fall back."""
    script = _MAC_TAB_SCRIPTS.get(term_program)
    if not script:
        return None
    app = _TAB_SCRIPT_APPS[term_program]
    if not _app_is_running(f'application "{_applescript_str(app)}"'):
        return None
    try:
        res = _run(["osascript", "-e", script.format(tty=_applescript_str(tty))])
        return _parse_tab_result(res, term_program, tty)
    except (subprocess.SubprocessError, OSError):
        pass
    return None


def _focus_iterm_by_session_id(iterm_session_id: str) -> Optional[Dict[str, Any]]:
    """Select the iTerm2 session whose unique id matches ITERM_SESSION_ID."""
    uuid = iterm_session_id.rsplit(":", 1)[-1].strip()
    if not uuid:
        return None
    if not _app_is_running('application "iTerm2"'):
        return None
    try:
        res = _run(["osascript", "-e", _ITERM_ID_SCRIPT.format(value=_applescript_str(uuid))])
        return _parse_tab_result(res, "iTerm.app", f"session {uuid}")
    except (subprocess.SubprocessError, OSError):
        pass
    return None


def _raise_gui_for_tty(tty: str) -> Optional[Dict[str, Any]]:
    """Raise the GUI window of whichever *running* terminal app owns ``tty``.

    Used for tmux: the pane's client tty belongs to some GUI terminal tab,
    but nothing recorded which app — so every supported app is tried, gated
    on being running (never launches anything).
    """
    if not shutil.which("osascript"):
        return None
    for term_program in _MAC_TAB_SCRIPTS:
        result = _focus_macos_tab(term_program, tty)
        if result is not None:
            return result
    return None


def _activate_app(term_program: str, bundle_id: Optional[str]) -> Dict[str, Any]:
    """App-level activation, guarded so a non-running app is never launched."""
    target = _macos_app_target(term_program, bundle_id)
    label = bundle_id or _MAC_APP_NAMES.get(term_program, term_program)
    if not _app_is_running(target):
        return {
            "focused": False,
            "method": "osascript",
            "detail": f"{label} is not running — the session's terminal app appears to have quit.",
        }
    try:
        res = _run(["osascript", "-e", f"tell {target} to activate"])
        return {
            "focused": res.returncode == 0,
            "method": "osascript",
            "detail": (res.stderr.strip() or f"activated {label}"),
        }
    except (subprocess.SubprocessError, OSError) as exc:
        return {"focused": False, "method": "osascript", "detail": str(exc)}


def _focus_macos(term_program: str, terminal: Dict[str, Any]) -> Dict[str, Any]:
    """Bring the macOS terminal to the foreground, exact tab when possible.

    Identifier preference: iTerm2 session UUID (fully durable, never
    recycled — usable even after the process dies) → tty stored at capture
    time (immune to pid recycling) → live pid→tty lookup (legacy state
    files). tty devices ARE recycled once their tab closes, so tty matching
    and app activation require the session's process to still be alive; a
    dead session fails honestly rather than risk raising a stranger's tab.
    """
    if not shutil.which("osascript"):
        return {"focused": False, "method": "osascript", "detail": "osascript not found"}

    pid = terminal.get("pid")

    if term_program == "iTerm.app" and terminal.get("iterm_session_id"):
        exact = _focus_iterm_by_session_id(terminal["iterm_session_id"])
        if exact:
            return exact

    if pid and not pid_is_live_claude(pid):
        return {
            "focused": False,
            "method": "osascript-tab",
            "detail": (
                "Could not locate the session's terminal window (its process is "
                "gone, and its tty may have been reassigned to an unrelated tab)."
            ),
        }

    tty = terminal.get("tty") or (_tty_for_pid(pid) if pid else None)
    if tty:
        exact = _focus_macos_tab(term_program, tty)
        if exact:
            return exact  # includes the honest "selected but not raised" case

    return _activate_app(term_program, terminal.get("bundle_id"))


# ---------------------------------------------------------------------------
# Linux
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def focus_terminal(terminal: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Attempt to raise the terminal for a session.

    Returns a dict ``{focused: bool, method: str, detail: str}``. Never
    raises — a missing tool or identifier is reported via ``focused=False``.

    tmux sessions route entirely through the tmux path (their captured
    tty/TERM_PROGRAM describe the tmux server, not a GUI tab): select the
    pane, ensure a client displays it, then raise that client's GUI window.
    Everything else goes through the host OS window manager directly.
    """
    if not terminal:
        return {
            "focused": False,
            "method": "none",
            "detail": "No terminal information was captured for this session.",
        }

    tmux_pane = terminal.get("tmux_pane")
    if tmux_pane:
        result = _focus_tmux(tmux_pane)
        client_tty = result.pop("client_tty", None)
        if client_tty and sys.platform == "darwin":
            gui = _raise_gui_for_tty(client_tty)
            if gui and gui.get("focused"):
                result["method"] = "tmux+gui"
                result["detail"] += f"; {gui['detail']}"
            elif result.get("focused"):
                result["detail"] += (
                    "; the hosting terminal window could not be raised automatically"
                )
        return result

    if sys.platform == "darwin" and terminal.get("term_program"):
        return _focus_macos(terminal["term_program"], terminal)

    if sys.platform.startswith("linux") and terminal.get("window_id"):
        pid = terminal.get("pid")
        if pid and not pid_is_live_claude(pid):
            return {
                "focused": False,
                "method": "linux",
                "detail": (
                    "The session's process is gone; refusing to raise a window id "
                    "that may have been recycled."
                ),
            }
        return _focus_linux(str(terminal["window_id"]))

    return {
        "focused": False,
        "method": "none",
        "detail": "No supported terminal focus method is available for this session.",
    }

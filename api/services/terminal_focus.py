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

Terminal.app raising is racy: ``set index to 1`` genuinely fails ~40% of the
time right after other window reordering (the window server needs ~0.3–0.5s
to settle), and window-order reads *inside the mutating script* return stale
values in both directions. The raise is therefore retried with settle
delays and verified from a separate ``osascript`` process. ``activate`` also
never switches macOS Spaces when the app already has a window on the current
Space — a cross-Space window can top the z-order while staying invisible, so
Space visibility is probed via System Events and reported honestly.

Everything is best-effort and honest: if a window genuinely could not be
raised, the result says ``focused=False`` with a human-readable reason
instead of raising — or worse, raising the wrong window.
"""

from __future__ import annotations

import os
import re
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
# substituted with e.g. /dev/ttys006. Terminal.app's script only selects and
# raises (`set index to 1` + activate) and returns the matched window id —
# NO in-script verification (order reads are stale within the mutating
# script) and NO miniaturize fallback (programmatic un-miniaturize restores
# the window to the BACK of the z-order, burying what was just raised).
# Verification happens in Python via a separate osascript process.
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
        "    return matchedId as text\n"
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

# Raise verification, run as a SEPARATE osascript process — reads from the
# script that mutated the order are stale (measured both false negatives and
# false positives live). Returns "<front id>\n<x1,y1,x2,y2>\n<target name>";
# the name goes last so a pathological linefeed in a title can't shift the
# machine-parsed fields.
_TERMINAL_VERIFY_SCRIPT = (
    'tell application "Terminal"\n'
    "    set b to bounds of window id {window_id}\n"
    "    return (id of front window as text) & linefeed & "
    '(item 1 of b as text) & "," & (item 2 of b as text) & "," & '
    '(item 3 of b as text) & "," & (item 4 of b as text) & linefeed & '
    "(name of window id {window_id})\n"
    "end tell"
)

# System Events only enumerates windows on the CURRENT Space — exactly the
# probe needed to tell "raised where the user can see it" from "topped the
# z-order on another desktop". Emits "<x>,<y>,<w>,<h>|<name>" per window:
# titles are not unique (every idle tab is "-zsh — 80×24"), so visibility
# requires the geometry to match too. Requires Accessibility permission;
# failure is treated as unknown and z-order is trusted.
_SE_WINDOW_NAMES_SCRIPT = (
    'tell application "System Events" to tell process "Terminal"\n'
    '    set out to ""\n'
    "    repeat with w in windows\n"
    "        set p to position of w\n"
    "        set s to size of w\n"
    '        set out to out & (item 1 of p as text) & "," & (item 2 of p as text) & "," & '
    '(item 1 of s as text) & "," & (item 2 of s as text) & "|" & (name of w) & linefeed\n'
    "    end repeat\n"
    "    return out\n"
    "end tell"
)

# Post-churn, the first raise reliably fails; ~0.45s of settle almost always
# lands it (measured 9/10, nearly all on the third attempt).
_RAISE_ATTEMPTS = 3
_RAISE_SETTLE_SECONDS = 0.15

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


def _sanitize_title(title: str) -> str:
    """Reduce a window title to stable ASCII (spinner glyphs animate between reads)."""
    return re.sub(r"\s+", " ", re.sub(r"[^ -~]", "", title)).strip()


def _window_on_current_space(
    target_name: str, target_bounds: Optional[Tuple[int, int, int, int]]
) -> Optional[bool]:
    """Whether THIS window (title + exact geometry) is on the current Space; None = unknown.

    Titles alone are ambiguous — two idle tabs share "-zsh — 80×24" — so a
    match also requires the System Events position/size to equal the bounds
    Terminal reported for the exact window id (coordinate systems agree:
    verified live, SE position = x1,y1 and size = x2-x1,y2-y1).
    """
    target = _sanitize_title(target_name)
    if not target or target_bounds is None:
        return None
    x1, y1, x2, y2 = target_bounds
    target_geo = (x1, y1, x2 - x1, y2 - y1)
    try:
        res = _run(["osascript", "-e", _SE_WINDOW_NAMES_SCRIPT])
    except (subprocess.SubprocessError, OSError):
        return None
    if res.returncode != 0:
        return None  # likely no Accessibility permission
    for line in res.stdout.splitlines():
        geo_part, sep, name_part = line.partition("|")
        if not sep or _sanitize_title(name_part) != target:
            continue
        try:
            geo = tuple(int(v) for v in geo_part.split(","))
        except ValueError:
            continue
        if geo == target_geo:
            return True
    return False


def _parse_bounds(csv: str) -> Optional[Tuple[int, int, int, int]]:
    """Parse the verify script's "x1,y1,x2,y2" line; None when malformed."""
    parts = csv.split(",")
    if len(parts) != 4:
        return None
    try:
        x1, y1, x2, y2 = (int(v) for v in parts)
    except ValueError:
        return None
    return x1, y1, x2, y2


def _terminal_verify_state(
    window_id: str,
) -> Tuple[Optional[str], Optional[Tuple[int, int, int, int]], str]:
    """Fresh-process read of Terminal's front id plus the target's bounds and title."""
    try:
        res = _run(["osascript", "-e", _TERMINAL_VERIFY_SCRIPT.format(window_id=window_id)])
    except (subprocess.SubprocessError, OSError):
        return None, None, ""
    if res.returncode != 0:
        return None, None, ""
    lines = res.stdout.splitlines()
    front = lines[0].strip() if lines else None
    bounds = _parse_bounds(lines[1]) if len(lines) > 1 else None
    name = "\n".join(lines[2:]) if len(lines) > 2 else ""
    return front, bounds, name


def _focus_terminal_app_tab(tty: str) -> Optional[Dict[str, Any]]:
    """Raise the Terminal.app window owning ``tty``: retry, verify, report honestly."""
    script = _MAC_TAB_SCRIPTS["Apple_Terminal"]
    window_id = ""
    for _ in range(_RAISE_ATTEMPTS):
        try:
            res = _run(["osascript", "-e", script.format(tty=_applescript_str(tty))])
        except (subprocess.SubprocessError, OSError):
            return None
        window_id = res.stdout.strip()
        if res.returncode != 0 or not window_id:
            return None  # no tab owns this tty — let the caller fall back
        time.sleep(_RAISE_SETTLE_SECONDS)
        front, bounds, name = _terminal_verify_state(window_id)
        if front != window_id:
            continue  # settle race — reorder didn't take yet; try again
        if _window_on_current_space(name, bounds) is False:
            return {
                "focused": False,
                "method": "osascript-tab",
                "detail": (
                    f"selected the Apple_Terminal tab on {tty} (window id {window_id}), "
                    "but the window is on another desktop or full screen — macOS won't "
                    "switch Spaces automatically; find it via Mission Control"
                ),
            }
        return {
            "focused": True,
            "method": "osascript-tab",
            "detail": f"selected Apple_Terminal tab on {tty} (window id {window_id})",
        }
    return {
        "focused": False,
        "method": "osascript-tab",
        "detail": (
            f"selected the Apple_Terminal tab on {tty} (window id {window_id}), "
            f"but its window could not be raised after {_RAISE_ATTEMPTS} attempts — "
            "try clicking again"
        ),
    }


def _focus_macos_tab(term_program: str, tty: str) -> Optional[Dict[str, Any]]:
    """Select the exact window/tab owning ``tty``; None means fall back."""
    script = _MAC_TAB_SCRIPTS.get(term_program)
    if not script:
        return None
    app = _TAB_SCRIPT_APPS[term_program]
    if not _app_is_running(f'application "{_applescript_str(app)}"'):
        return None
    if term_program == "Apple_Terminal":
        return _focus_terminal_app_tab(tty)
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

"""Toggle a live session's Claude Code Remote Control from the Karma dashboard.

Claude Code exposes exactly one lever for Remote Control: the ``/remote-control``
slash command typed *inside* the running session. There is no local API. Karma
runs on the same machine as the tracked terminal, so it drives Remote Control by
**typing into the session's terminal tab** — reusing the tty / iTerm2-session-id
targeting from :mod:`services.terminal_focus`.

``/remote-control`` is **not** a symmetric toggle, so only turning it **on** is
fully automated:

- **off → on**: the bare command turns it on. Karma types it and confirms via
  the transcript.
- **on → off**: the command opens an interactive "Disconnect Remote Control"
  menu. Nothing drives that menu reliably from outside the process (``do
  script`` can't deliver arrow keys; System Events needs a machine-wide
  Accessibility grant that misfires). So Karma types the command to *open* the
  menu and raises the terminal (``services.terminal_focus.focus_terminal``);
  the user picks "Disconnect this session" themselves.

Supported terminals: tmux, macOS Terminal.app, macOS iTerm2 — and only for a
session whose ``pid`` is still alive (a reused tty / tmux pane must never be
typed into blind).

State is read back from the session JSONL transcript chain, where Claude Code
writes ``{"type":"system","subtype":"bridge_status", ...}`` lines on connect
("...is active...") and disconnect ("...is no longer active..."), carrying the
``claude.ai/code`` URL. No such line anywhere → ``"off"`` (Remote Control is
opt-in and writes a line when enabled); a line we can't classify → ``"unknown"``
(callers 409 rather than blind-toggle).
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from services.terminal_focus import (
    _app_is_running,
    _applescript_str,
    _run,
    _tty_for_pid,
    pid_is_live_claude,
)

# The slash command that controls Remote Control from inside a session.
RC_COMMAND = "/remote-control"

# The connect/disconnect line can be anywhere — a 20h session buries it under
# megabytes of tool output — so the whole transcript is scanned, capped at
# _MAX_SCAN_BYTES (beyond that, best-effort tail of _TAIL_BYTES). The strict
# JSON match means conversation text that merely contains "bridge_status"
# (this repo's own code, review notes) is ignored (review #1, #14).
_MAX_SCAN_BYTES = 48 * 1024 * 1024
_TAIL_BYTES = 2 * 1024 * 1024

# Terminal hosts we can actually type into.
_SUPPORTED_TERM_PROGRAMS = {"Apple_Terminal", "iTerm.app"}
_TAB_SCRIPT_APPS: Dict[str, str] = {"Apple_Terminal": "Terminal", "iTerm.app": "iTerm2"}

# Only a claude.ai https URL is ever handed to the frontend <a href>.
SAFE_RC_URL_RE = re.compile(r"^https://claude\.ai/", re.IGNORECASE)

# bridge_status.content wording (lower-cased). OFF is matched first so a future
# rephrasing that happens to contain "active" can't be misread as ON.
_OFF_MARKERS = (
    "no longer active",
    "no longer",
    "disconnected",
    "not active",
    "is off",
    "turned off",
    "inactive",
)
_ON_MARKERS = ("is active", "session is active", "remote control is on")


# ---------------------------------------------------------------------------
# Capability gate
# ---------------------------------------------------------------------------


def can_send_remote_control(terminal: Optional[Dict[str, Any]]) -> bool:
    """Whether Karma can type ``/remote-control`` into this session's terminal.

    Stricter than ``terminal_focus.can_focus``: keystroke injection requires a
    still-alive captured ``pid`` (so a recycled tty / tmux pane is never typed
    into) and one of the three terminal hosts we implement.
    """
    if not terminal:
        return False
    pid = terminal.get("pid")
    if not pid or not pid_is_live_claude(pid):
        return False
    if terminal.get("tmux_pane"):
        return True
    return terminal.get("term_program") in _SUPPORTED_TERM_PROGRAMS


# ---------------------------------------------------------------------------
# State read-back (from the transcript chain)
# ---------------------------------------------------------------------------


def _chain_transcript_paths(
    transcript_path: Optional[str], chain_ids: Optional[Sequence[str]]
) -> List[Path]:
    """Primary transcript first, then sibling JSONLs for the other chain UUIDs."""
    if not transcript_path:
        return []
    primary = Path(transcript_path)
    paths = [primary]
    parent = primary.parent
    for sid in chain_ids or []:
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", str(sid)):
            continue
        cand = parent / f"{sid}.jsonl"
        if cand != primary:
            paths.append(cand)
    return paths


def _within_projects(path: Path, projects_dir: Optional[Path]) -> bool:
    """True only if ``path`` really resolves under ``~/.claude/projects``.

    Guards against a state file whose ``transcript_path`` points elsewhere or
    through a symlink (review #15).
    """
    try:
        real = Path(os.path.realpath(path))
    except OSError:
        return False
    base = projects_dir or (Path.home() / ".claude" / "projects")
    try:
        base_real = Path(os.path.realpath(base))
    except OSError:
        base_real = Path(base)
    return real == base_real or base_real in real.parents


def _last_bridge_status_in(path: Path) -> Optional[Dict[str, Any]]:
    """The last real ``system/bridge_status`` event in ``path``, or None.

    Scans the whole file (capped at _MAX_SCAN_BYTES) — the event can be far
    from the end of an active session. Lines that only *contain* the string
    "bridge_status" but don't parse to a ``type==system`` event are ignored.
    """
    try:
        if not path.is_file():
            return None
        size = path.stat().st_size
        with path.open("rb") as fh:
            if size > _MAX_SCAN_BYTES:
                fh.seek(size - _TAIL_BYTES)
            chunk = fh.read().decode("utf-8", "replace")
    except OSError:
        return None
    latest: Optional[Dict[str, Any]] = None
    for line in chunk.splitlines():
        if "bridge_status" not in line:
            continue
        try:
            obj = json.loads(line)
        except ValueError:
            continue  # a truncated tail line, or non-JSON
        if obj.get("type") == "system" and obj.get("subtype") == "bridge_status":
            latest = obj
    return latest


def read_remote_control_state(
    transcript_path: Optional[str],
    chain_ids: Optional[Sequence[str]] = None,
    projects_dir: Optional[Path] = None,
) -> Dict[str, Any]:
    """Current Remote Control state for a session.

    Returns ``{state: "on"|"off"|"unknown", url: str|None, at: str|None}``.

    - **No** ``bridge_status`` line anywhere in the chain → ``"off"``. Remote
      Control has to be turned on explicitly and writes a line when it does, so
      "never seen one" means off. (The rare case where it was on via
      ``--remote-control`` and the line has scrolled past the tail degrades
      safely: turning "on" again just opens — and Esc-dismisses — the menu; we
      only ever *disable* from a positive "is active" reading.)
    - A line we found but can't classify → ``"unknown"`` (callers 409 rather
      than blind-toggle — this needs Claude Code to have changed its wording).

    The primary transcript is the newest file in the chain, so a line there
    wins; older chain files are consulted only when it has none.
    """
    best: Optional[Dict[str, Any]] = None
    for i, path in enumerate(_chain_transcript_paths(transcript_path, chain_ids)):
        if not _within_projects(path, projects_dir):
            continue
        obj = _last_bridge_status_in(path)
        if obj is not None:
            best = obj
            if i == 0:
                break  # newest file had a line — trust it
    if best is None:
        return {"state": "off", "url": None, "at": None}

    content = str(best.get("content") or "").lower()
    if any(m in content for m in _OFF_MARKERS):
        state = "off"
    elif any(m in content for m in _ON_MARKERS):
        state = "on"
    else:
        state = "unknown"

    url = best.get("url")
    if not (isinstance(url, str) and SAFE_RC_URL_RE.match(url)):
        url = None
    return {"state": state, "url": url, "at": best.get("timestamp")}


# ---------------------------------------------------------------------------
# Typing /remote-control into the session's terminal
# ---------------------------------------------------------------------------
#
# Only the *type the command* direction is automated. Turning RC OFF means
# navigating Claude Code's interactive "Disconnect Remote Control" menu, and
# nothing can drive that menu reliably from outside the process without the
# macOS Accessibility grant (System Events) — which is a machine-wide
# "any AppleScript may type" switch and fires stray keystrokes at the worst
# times. So OFF just opens the menu and raises the terminal for the user.


def _err(method: str, detail: str) -> Dict[str, Any]:
    return {"sent": False, "method": method, "detail": detail}


def _ok(method: str, detail: str) -> Dict[str, Any]:
    return {"sent": True, "method": method, "detail": detail}


def _iterm_target_script(terminal: Dict[str, Any], body: str) -> Optional[str]:
    """Wrap ``body`` (an iTerm ``tell s to ...`` fragment) in a session lookup."""
    sid = terminal.get("iterm_session_id")
    tty = terminal.get("tty") or (_tty_for_pid(terminal["pid"]) if terminal.get("pid") else None)
    if sid:
        uuid = str(sid).rsplit(":", 1)[-1].strip()
        if uuid:
            match = f'id of s is "{_applescript_str(uuid)}"'
        else:
            match = None
    else:
        match = None
    if match is None and tty:
        match = f'tty of s is "{_applescript_str(tty)}"'
    if match is None:
        return None
    return (
        'tell application "iTerm2"\n'
        "  repeat with w in windows\n"
        "    repeat with t in tabs of w\n"
        "      repeat with s in sessions of t\n"
        f"        if {match} then\n"
        f"          {body}\n"
        '          return "sent"\n'
        "        end if\n"
        "      end repeat\n"
        "    end repeat\n"
        "  end repeat\n"
        '  return ""\n'
        "end tell"
    )


def _run_osascript(script: str) -> bool:
    try:
        res = _run(["osascript", "-e", script])
    except Exception:  # noqa: BLE001 — this helper must never raise
        return False
    return res.returncode == 0 and res.stdout.strip() == "sent"


# ---- tmux --------------------------------------------------------------------


def _tmux(pane: str, args: List[str]) -> bool:
    try:
        res = _run(["tmux", "send-keys", "-t", pane, *args])
    except Exception:  # noqa: BLE001
        return False
    return res.returncode == 0


def _tmux_type_command(pane: str) -> Dict[str, Any]:
    # -l => literal text (no key-name lookup), then a separate Enter key.
    if _tmux(pane, ["-l", "--", RC_COMMAND]) and _tmux(pane, ["Enter"]):
        return _ok("tmux", f"typed {RC_COMMAND} into tmux pane {pane}")
    return _err("tmux", f"tmux send-keys failed for pane {pane}")


# ---- Terminal.app ----------------------------------------------------------


def _terminal_app_type_command(tty: str) -> Dict[str, Any]:
    script = (
        'tell application "Terminal"\n'
        "  repeat with w in windows\n"
        "    repeat with t in tabs of w\n"
        f'      if tty of t is "{_applescript_str(tty)}" then\n'
        f'        do script "{_applescript_str(RC_COMMAND)}" in t\n'
        '        return "sent"\n'
        "      end if\n"
        "    end repeat\n"
        "  end repeat\n"
        '  return ""\n'
        "end tell"
    )
    if _run_osascript(script):
        return _ok("osascript-tab", f"typed {RC_COMMAND} into the Terminal.app tab on {tty}")
    return _err("osascript-tab", f"could not find a Terminal.app tab on {tty}")


# ---- iTerm2 --------------------------------------------------------------------


def _iterm_type_command(terminal: Dict[str, Any]) -> Dict[str, Any]:
    script = _iterm_target_script(
        terminal, f'tell s to write text "{_applescript_str(RC_COMMAND)}"'
    )
    if script and _app_is_running('application "iTerm2"') and _run_osascript(script):
        return _ok("osascript-tab", f"typed {RC_COMMAND} into the iTerm2 session")
    return _err("osascript-tab", "could not find the iTerm2 session")


# ---- dispatch ---------------------------------------------------------------


def _resolve_tty(terminal: Dict[str, Any]) -> Optional[str]:
    return terminal.get("tty") or (_tty_for_pid(terminal["pid"]) if terminal.get("pid") else None)


def type_remote_control_command(terminal: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Type ``/remote-control`` + Enter into the session's terminal.

    Turns Remote Control **on** when it is off; opens the "Disconnect Remote
    Control" menu when it is on (the caller then raises the terminal so the
    user can finish it). Returns ``{sent: bool, method: str, detail: str}`` and
    never raises.
    """
    if not can_send_remote_control(terminal):
        return _err(
            "none",
            "This session has no live tmux / Terminal.app / iTerm2 terminal on "
            "the machine running Karma.",
        )
    assert terminal is not None
    pane = terminal.get("tmux_pane")
    if pane:
        return _tmux_type_command(str(pane))
    term_program = terminal.get("term_program")
    if term_program == "iTerm.app":
        return _iterm_type_command(terminal)
    tty = _resolve_tty(terminal)
    if term_program == "Apple_Terminal" and tty:
        return _terminal_app_type_command(tty)
    return _err("none", "Unsupported terminal for Remote Control toggling.")

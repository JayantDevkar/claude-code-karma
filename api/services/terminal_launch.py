"""Launch a new terminal tab/window and run `claude --resume` in it.

Counterpart to :mod:`services.terminal_focus`: focus raises the terminal of a
session that is still running; launch spawns a fresh terminal for a session
that has ended, cd's into the project, and starts ``claude --resume <uuid>``.
Once claude starts, its SessionStart hook re-captures the new tab's identity,
so the live dashboard (and the focus button) pick the session up on their own.

macOS only for now, mirroring the focus service's platform support:

- **iTerm2**       : clean scripting API — a new tab in the current window
  (or a new window when none exist), then ``write text``.
- **Terminal.app** : ``do script`` runs the command in a NEW WINDOW natively.
  A new *tab* would require a System Events Cmd+T keystroke, which is racy
  and needs extra Accessibility trust — deliberately not done.

SECURITY: the shell command is built entirely server-side. ``project_path``
must come from Karma's own project resolution and ``session_uuid`` must be a
validated UUID (the router enforces both); everything is still shell-quoted
and AppleScript-escaped here as defense in depth. No caller-provided text
may ever reach ``_build_command`` unvalidated.

Everything is best-effort and honest: ``launched=False`` plus a
human-readable reason, never an exception.
"""

from __future__ import annotations

import shlex
import subprocess
import sys
from typing import Any, Dict, Optional

from services.terminal_focus import _app_is_running, _applescript_str, _run

# Launching runs a command in a brand-new shell; the safe default is the
# terminal every macOS install has. iTerm2 is used only when the session's
# recorded TERM_PROGRAM says it lived there AND iTerm2 is running.
_ITERM_LAUNCH_SCRIPT = (
    'tell application "iTerm2"\n'
    "    activate\n"
    "    if (count of windows) is 0 then\n"
    "        create window with default profile\n"
    "    else\n"
    "        tell current window to create tab with default profile\n"
    "    end if\n"
    '    tell current session of current window to write text "{command}"\n'
    "end tell"
)

_TERMINAL_LAUNCH_SCRIPT = (
    'tell application "Terminal"\n    do script "{command}"\n    activate\nend tell'
)


def _build_command(project_path: str, session_uuid: str) -> str:
    """The shell line typed into the new terminal, fully quoted."""
    return f"cd {shlex.quote(project_path)} && claude --resume {shlex.quote(session_uuid)}"


def _osascript(script: str) -> Optional[str]:
    """Run an AppleScript; stderr text on failure, None on success."""
    try:
        res = _run(["osascript", "-e", script])
    except (subprocess.SubprocessError, OSError) as exc:
        return str(exc)
    if res.returncode != 0:
        return res.stderr.strip() or "osascript failed"
    return None


def launch_resume_in_terminal(
    project_path: str,
    session_uuid: str,
    term_program: Optional[str] = None,
) -> Dict[str, Any]:
    """Open a terminal at ``project_path`` and run ``claude --resume``.

    ``term_program`` is the TERM_PROGRAM recorded when the session last ran,
    used as a hint to resume in the same terminal app. Returns
    ``{launched: bool, method: str, detail: str}``.
    """
    if sys.platform != "darwin":
        return {
            "launched": False,
            "method": "none",
            "detail": "Resuming in a terminal is currently supported on macOS only.",
        }

    command = _build_command(project_path, session_uuid)
    escaped = _applescript_str(command)

    if term_program == "iTerm.app" and _app_is_running('application "iTerm2"'):
        err = _osascript(_ITERM_LAUNCH_SCRIPT.format(command=escaped))
        if err is None:
            return {
                "launched": True,
                "method": "iterm-tab",
                "detail": f"opened an iTerm2 tab and ran: {command}",
            }
        return {"launched": False, "method": "iterm-tab", "detail": err}

    err = _osascript(_TERMINAL_LAUNCH_SCRIPT.format(command=escaped))
    if err is None:
        return {
            "launched": True,
            "method": "terminal-window",
            "detail": f"opened a Terminal window and ran: {command}",
        }
    return {"launched": False, "method": "terminal-window", "detail": err}

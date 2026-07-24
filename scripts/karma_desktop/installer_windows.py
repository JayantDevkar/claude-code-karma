"""Windows side of the desktop installer: a Desktop shortcut, optionally
copied into the Startup folder to run at logon.

A Desktop shortcut is used rather than a taskbar pin on purpose — Windows
deliberately offers no supported API for programmatic taskbar pinning, and the
registry hacks that fake it break between releases. Desktop icons are also
where Windows users generally expect app shortcuts to live.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

from . import core

SHORTCUT_NAME = f"{core.APP_NAME}.lnk"

# Creating a .lnk needs the Windows shell COM object. PowerShell can reach it
# without any third-party package, which keeps the installer dependency-free.
_PS_CREATE = r"""
$ErrorActionPreference = 'Stop'
$shell = New-Object -ComObject WScript.Shell
$sc = $shell.CreateShortcut("{lnk}")
$sc.TargetPath = "{target}"
$sc.Arguments = '{arguments}'
$sc.WorkingDirectory = "{workdir}"
$sc.Description = 'Start Claude Code Karma and open the dashboard'
{icon}
$sc.Save()
"""


def desktop_dir() -> Path:
    """The user's Desktop, honouring a redirected (OneDrive) profile."""
    userprofile = os.environ.get("USERPROFILE")
    if userprofile:
        for candidate in (
            Path(userprofile) / "Desktop",
            Path(userprofile) / "OneDrive" / "Desktop",
        ):
            if candidate.is_dir():
                return candidate
    return Path.home() / "Desktop"


def startup_dir() -> Path:
    """The per-user Startup folder, whose contents run at logon."""
    appdata = os.environ.get("APPDATA")
    base = Path(appdata) if appdata else Path.home() / "AppData" / "Roaming"
    return base / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"


def pythonw_for(python: Path) -> Path:
    """``pythonw.exe`` beside ``python.exe`` when it exists.

    pythonw runs without allocating a console, which is what stops a black cmd
    window flashing up every time the shortcut is double-clicked. No .vbs
    wrapper needed.
    """
    candidate = python.with_name("pythonw.exe")
    return candidate if candidate.is_file() else python


def create_shortcut(
    lnk: Path,
    target: Path,
    arguments: str,
    workdir: Path,
    icon: Path | None = None,
) -> Path:
    """Write a .lnk via the WScript.Shell COM object."""
    lnk.parent.mkdir(parents=True, exist_ok=True)
    icon_line = ""
    if icon is not None and icon.is_file():
        icon_line = f'$sc.IconLocation = "{icon}"'

    script = _PS_CREATE.format(
        lnk=str(lnk),
        target=str(target),
        # Single-quoted in PowerShell, so escape embedded single quotes only;
        # this keeps paths containing spaces intact.
        arguments=arguments.replace("'", "''"),
        workdir=str(workdir),
        icon=icon_line,
    )
    subprocess.run(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script],
        check=True,
        capture_output=True,
    )
    return lnk


def _launch_arguments(repo: Path, web_port: int, api_port: int, extra: str = "") -> str:
    launcher = repo / "scripts" / "karma_desktop" / "launcher.py"
    # Quote the script path so profiles like C:\Users\First Last survive.
    args = f'"{launcher}" --web-port {web_port} --api-port {api_port}'
    return f"{args} {extra}".strip()


def install_app(repo: Path, python: Path, web_port: int, api_port: int) -> Path:
    """Create the Desktop shortcut and return its path."""
    icon = repo / "frontend" / "static" / "icons" / "karma.ico"
    return create_shortcut(
        lnk=desktop_dir() / SHORTCUT_NAME,
        target=pythonw_for(python),
        arguments=_launch_arguments(repo, web_port, api_port),
        workdir=repo,
        icon=icon if icon.is_file() else None,
    )


def autostart_enabled() -> bool:
    """Whether Karma is registered to start at logon.

    Read from disk rather than from a stored preference: Task Manager's Startup
    tab can disable the entry independently of us, so the filesystem is the only
    answer that cannot go stale.
    """
    return (startup_dir() / SHORTCUT_NAME).exists()


def uninstall_autostart() -> bool:
    """Stop Karma starting at logon. True if an entry was actually removed."""
    entry = startup_dir() / SHORTCUT_NAME
    if not entry.exists():
        return False
    entry.unlink()
    return True


def install_autostart(repo: Path, python: Path, web_port: int, api_port: int) -> Path:
    """Put a headless copy of the launcher in the Startup folder."""
    icon = repo / "frontend" / "static" / "icons" / "karma.ico"
    return create_shortcut(
        lnk=startup_dir() / SHORTCUT_NAME,
        target=pythonw_for(python),
        arguments=_launch_arguments(
            repo, web_port, api_port, extra="--no-open --quiet"
        ),
        workdir=repo,
        icon=icon if icon.is_file() else None,
    )


def uninstall() -> list[str]:
    removed = []
    for path in (desktop_dir() / SHORTCUT_NAME, startup_dir() / SHORTCUT_NAME):
        if path.exists():
            path.unlink()
            removed.append(str(path))
    return removed

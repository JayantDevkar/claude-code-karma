"""Windows side of the desktop installer: a Desktop shortcut, optionally
copied into the Startup folder to run at logon.

A Desktop shortcut is used rather than a taskbar pin on purpose — Windows
deliberately offers no supported API for programmatic taskbar pinning, and the
registry hacks that fake it break between releases. Desktop icons are also
where Windows users generally expect app shortcuts to live.

Both shortcuts point at a small *boot script* kept outside the repo (under
``%LOCALAPPDATA%\\Karma``) rather than directly at the launcher inside the repo.
That boot script is the Windows equivalent of the macOS ``.app`` stub's
repo-gone guard: if the repo has been moved, deleted, or its git worktree
pruned, the Desktop icon shows an explanatory alert and the Startup entry
removes itself, instead of a bare ``pythonw missing_script.py`` that exits
silently at every logon with no window, no console and no log.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

from . import core

SHORTCUT_NAME = f"{core.APP_NAME}.lnk"

# Written into every shortcut we create and checked before deleting one, so
# uninstall never removes an unrelated Karma.lnk a user or another app placed
# on the Desktop -- the Windows counterpart of installer_macos._is_our_bundle.
_SHORTCUT_DESCRIPTION = "Start Claude Code Karma and open the dashboard"

# Boot script that survives the repo being moved/deleted. Values are embedded
# with ``repr`` so Windows paths (backslashes, spaces) are inert Python
# literals and can never be misread as escapes. MODE is "desktop" (show an
# alert) or "startup" (silently delete our own Startup shortcut so it stops
# firing every logon). On success it just forwards its own arguments to the
# real launcher.
_BOOT_TEMPLATE = """import os, sys, subprocess
LAUNCHER = {launcher!r}
MODE = {mode!r}
STARTUP_LNK = {startup_lnk!r}
if not os.path.isfile(LAUNCHER):
    if MODE == "startup":
        try:
            if STARTUP_LNK and os.path.isfile(STARTUP_LNK):
                os.remove(STARTUP_LNK)
        except OSError:
            pass
    else:
        try:
            import ctypes
            ctypes.windll.user32.MessageBoxW(
                0,
                "Karma cannot find its files - the project folder was moved or "
                "removed. Reinstall the desktop app from the dashboard "
                "(Settings > Desktop App).",
                "Karma",
                0x10,
            )
        except Exception:
            pass
    sys.exit(1)
# sys.executable is the interpreter running this boot script -- pythonw.exe when
# launched from the shortcut, so re-using it (rather than a baked python.exe
# path) keeps the launch windowless AND can never point at an interpreter that
# was removed by an upgrade. CREATE_NO_WINDOW belts-and-braces the no-console
# guarantee even if the shortcut somehow resolved to console python.
sys.exit(subprocess.call(
    [sys.executable, LAUNCHER] + sys.argv[1:],
    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
))
"""


def _ps_quote(value: object) -> str:
    """Quote a value as a PowerShell single-quoted literal.

    Single-quoted PowerShell strings do not expand ``$var`` or ``$(...)``, so a
    path containing ``$`` or ``()`` is inert and cannot execute; only an
    embedded single quote needs doubling. The previous template substituted
    paths into *double*-quoted strings, where ``$(...)`` runs and ``"`` breaks
    out -- an injection through any repo/profile path.
    """
    return "'" + str(value).replace("'", "''") + "'"


def _known_folder(reg_name: str, fallback: Path) -> Path:
    """Resolve a Windows shell folder from the registry, OneDrive-aware.

    ``HKCU\\...\\Explorer\\Shell Folders`` holds the *current, expanded* path for
    'Desktop', 'Startup', etc. With OneDrive Known Folder Move (the default on
    most consumer Windows) this points at the OneDrive location, while the
    legacy ``%USERPROFILE%\\Desktop`` often lingers as a stale folder or
    junction -- so probing the profile path first drops shortcuts where the
    user never sees them. The registry is the authoritative source.
    """
    try:
        import winreg  # noqa: PLC0415 - Windows-only stdlib

        key = r"Software\Microsoft\Windows\CurrentVersion\Explorer\Shell Folders"
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key) as handle:
            value, _ = winreg.QueryValueEx(handle, reg_name)
        resolved = Path(os.path.expandvars(value))
        if resolved.is_dir():
            return resolved
    except (OSError, ImportError, ValueError):
        pass
    return fallback


def desktop_dir() -> Path:
    """The user's real Desktop, honouring OneDrive Known Folder Move."""
    userprofile = os.environ.get("USERPROFILE", str(Path.home()))
    return _known_folder("Desktop", Path(userprofile) / "Desktop")


def startup_dir() -> Path:
    """The per-user Startup folder, whose contents run at logon."""
    appdata = os.environ.get("APPDATA", str(Path.home() / "AppData" / "Roaming"))
    fallback = (
        Path(appdata) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"
    )
    return _known_folder("Startup", fallback)


def stub_dir() -> Path:
    """A stable, outside-the-repo home for the boot scripts.

    ``%LOCALAPPDATA%\\Karma``, created on demand. It must not live in the repo:
    the whole point of the boot script is to still exist (and explain itself)
    after the repo is gone.
    """
    local = os.environ.get("LOCALAPPDATA")
    base = Path(local) if local else Path.home() / ".karma"
    d = base / "Karma"
    d.mkdir(parents=True, exist_ok=True)
    return d


def pythonw_for(python: Path) -> Path:
    """``pythonw.exe`` beside ``python.exe`` when it exists.

    pythonw runs without allocating a console, which is what stops a black cmd
    window flashing up every time the shortcut is double-clicked. No .vbs
    wrapper needed.
    """
    candidate = python.with_name("pythonw.exe")
    return candidate if candidate.is_file() else python


def _write_boot_script(
    name: str, mode: str, launcher: Path, python: Path, startup_lnk: Path | None
) -> Path:
    """Write a boot script into ``stub_dir()`` and return its path."""
    path = stub_dir() / name
    path.write_text(
        _BOOT_TEMPLATE.format(
            launcher=str(launcher),
            python=str(python),
            mode=mode,
            startup_lnk=str(startup_lnk) if startup_lnk else "",
        ),
        encoding="utf-8",
    )
    return path


def _build_script(
    lnk: Path, target: Path, arguments: str, workdir: Path, icon: Path | None
) -> str:
    """Build the .lnk-creating PowerShell, every value single-quoted.

    One line with ``;`` separators rather than embedded newlines, so it is not
    at the mercy of how ``-Command`` handles multi-line input.
    """
    lines = [
        "$ErrorActionPreference = 'Stop'",
        "$shell = New-Object -ComObject WScript.Shell",
        f"$sc = $shell.CreateShortcut({_ps_quote(lnk)})",
        f"$sc.TargetPath = {_ps_quote(target)}",
        f"$sc.Arguments = {_ps_quote(arguments)}",
        f"$sc.WorkingDirectory = {_ps_quote(workdir)}",
        f"$sc.Description = {_ps_quote(_SHORTCUT_DESCRIPTION)}",
    ]
    if icon is not None and icon.is_file():
        lines.append(f"$sc.IconLocation = {_ps_quote(icon)}")
    lines.append("$sc.Save()")
    return "; ".join(lines)


def create_shortcut(
    lnk: Path,
    target: Path,
    arguments: str,
    workdir: Path,
    icon: Path | None = None,
) -> Path:
    """Write a .lnk via the WScript.Shell COM object."""
    lnk.parent.mkdir(parents=True, exist_ok=True)
    script = _build_script(lnk, target, arguments, workdir, icon)
    subprocess.run(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script],
        check=True,
        capture_output=True,
    )
    return lnk


def _flag_arguments(boot: Path, web_port: int, api_port: int, extra: str = "") -> str:
    """Shortcut arguments: the boot script path plus launcher flags.

    The launcher path is baked into the boot script, so only the flags are
    passed here; the boot script forwards them on. The boot path is quoted so a
    profile like ``C:\\Users\\First Last`` survives.
    """
    args = f'"{boot}" --web-port {web_port} --api-port {api_port}'
    return f"{args} {extra}".strip()


def install_app(repo: Path, python: Path, web_port: int, api_port: int) -> Path:
    """Create the Desktop shortcut (via the repo-gone-aware boot script).

    Refuses to overwrite a same-named .lnk that is not ours, mirroring the macOS
    install_app's FileExistsError on a foreign bundle; the endpoint turns that
    into a 409 rather than silently clobbering an unrelated shortcut.
    """
    lnk = desktop_dir() / SHORTCUT_NAME
    if lnk.exists() and not _is_our_shortcut(lnk):
        raise FileExistsError(
            f"{lnk} already exists and was not created by Karma. "
            f"Refusing to overwrite it."
        )
    launcher = repo / "scripts" / "karma_desktop" / "launcher.py"
    boot = _write_boot_script("boot_desktop.py", "desktop", launcher, python, None)
    icon = repo / "frontend" / "static" / "icons" / "karma.ico"
    return create_shortcut(
        lnk=lnk,
        target=pythonw_for(python),
        arguments=_flag_arguments(boot, web_port, api_port),
        workdir=repo,
        icon=icon if icon.is_file() else None,
    )


def autostart_enabled() -> bool:
    """Whether the Startup entry is *installed*.

    This reports the presence of the shortcut, not whether Windows will
    actually run it: Task Manager's Startup tab can disable the entry (a flag
    under ``StartupApproved`` in the registry) while the ``.lnk`` stays on disk,
    and that disabled flag is not read here. So a True result means "we put it
    there", not "it is guaranteed to run at logon".
    """
    return (startup_dir() / SHORTCUT_NAME).exists()


def uninstall_autostart() -> bool:
    """Stop Karma starting at logon. True if an entry was actually removed.

    Only removes a Startup entry we created -- the toggle must be no less careful
    than the Remove button (uninstall), which already checks ownership, so a
    same-named foreign Startup shortcut is never deleted out from under the user.
    """
    entry = startup_dir() / SHORTCUT_NAME
    if not entry.exists() or not _is_our_shortcut(entry):
        return False
    entry.unlink()
    return True


def install_autostart(repo: Path, python: Path, web_port: int, api_port: int) -> Path:
    """Put a headless copy of the launcher in the Startup folder.

    The Startup boot script is told its own shortcut path so that, if the repo
    is later gone, it deletes that shortcut and stops firing at every logon --
    the Windows counterpart of the launchd agent's self-unload on macOS.
    """
    launcher = repo / "scripts" / "karma_desktop" / "launcher.py"
    startup_lnk = startup_dir() / SHORTCUT_NAME
    boot = _write_boot_script(
        "boot_startup.py", "startup", launcher, python, startup_lnk
    )
    icon = repo / "frontend" / "static" / "icons" / "karma.ico"
    return create_shortcut(
        lnk=startup_lnk,
        target=pythonw_for(python),
        arguments=_flag_arguments(boot, web_port, api_port, extra="--no-open --quiet"),
        workdir=repo,
        icon=icon if icon.is_file() else None,
    )


def _read_shortcut(lnk: Path) -> dict:
    """Read a .lnk's Description and Arguments. Empty dict on any failure."""
    script = (
        f"$s=(New-Object -ComObject WScript.Shell).CreateShortcut({_ps_quote(lnk)});"
        '"$($s.Description)|$($s.Arguments)"'
    )
    try:
        out = subprocess.run(
            ["powershell", "-NoProfile", "-Command", script],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
    except (subprocess.SubprocessError, OSError):
        return {}
    description, _, arguments = out.partition("|")
    return {"description": description, "arguments": arguments}


def _is_our_shortcut(lnk: Path) -> bool:
    """True only for a shortcut this installer created.

    Identified by our fixed Description string, or by arguments that reference
    one of our boot scripts -- both are set only by ``create_shortcut`` here. If
    the shortcut can't be read we treat it as *not* ours and leave it, the same
    conservative stance ``_is_our_bundle`` takes on macOS.
    """
    fields = _read_shortcut(lnk)
    if not fields:
        return False
    if fields.get("description") == _SHORTCUT_DESCRIPTION:
        return True
    args = fields.get("arguments", "")
    return "boot_desktop.py" in args or "boot_startup.py" in args


def uninstall() -> list[str]:
    removed = []
    # Each shortcut is paired with the boot script it runs. Only remove a .lnk we
    # actually created, and -- crucially -- keep a boot script alive whenever its
    # shortcut survives (foreign, or unreadable so ownership is uncertain).
    # Deleting the boot script out from under a surviving shortcut would turn it
    # into a silent dead icon whose own repo-gone alert we'd just removed.
    pairs = (
        (desktop_dir() / SHORTCUT_NAME, stub_dir() / "boot_desktop.py"),
        (startup_dir() / SHORTCUT_NAME, stub_dir() / "boot_startup.py"),
    )
    for lnk, boot in pairs:
        if lnk.exists() and not _is_our_shortcut(lnk):
            continue  # foreign or unreadable: leave the shortcut and its boot
        if lnk.exists():
            lnk.unlink()
            removed.append(str(lnk))
        if boot.exists():
            boot.unlink()
            removed.append(str(boot))
    return removed

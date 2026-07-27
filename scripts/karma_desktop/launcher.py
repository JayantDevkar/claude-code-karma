"""Runtime entry point for the Karma desktop icon.

Invoked by the generated macOS ``.app`` or Windows Desktop shortcut. Starts
whichever karma servers are not already running, posts a "starting" desktop
notification so a cold start never looks like a dead click, then opens the
dashboard once the servers answer.

Run directly for a headless check::

    python3 scripts/karma_desktop/launcher.py --no-open
"""

from __future__ import annotations

import argparse
import contextlib
import os
import shutil
import subprocess
import sys
import webbrowser
from pathlib import Path

if __package__ in (None, ""):  # invoked as a plain script by the .app / .lnk
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from karma_desktop import core
else:
    from . import core

# A cold vite build on this repo is slow; the API is comparatively instant.
API_TIMEOUT = 90
WEB_TIMEOUT = 240


def _log(message: str) -> None:
    """Append a line to the launcher log. Never raises.

    The autostart path runs under ``pythonw`` (Windows) or a launchd job with
    no terminal, where ``sys.stdout``/``sys.stderr`` are None and ``print`` is
    a silent no-op. Without this, a failed autostart leaves nothing at all to
    inspect -- the user just finds Karma missing after login. The macOS agent
    additionally redirects to autostart.log, but this covers every platform.
    """
    try:
        from datetime import datetime

        with open(core.log_dir() / "launcher.log", "a", encoding="utf-8") as fh:
            fh.write(f"{datetime.now().isoformat(timespec='seconds')} {message}\n")
    except OSError:
        pass


def _fail(message: str, quiet: bool) -> int:
    """Report a startup failure, using a GUI alert when there is no terminal."""
    _log(f"FAIL: {message}")
    if quiet or sys.platform not in ("darwin", "win32"):
        print(f"FAIL: {message}", file=sys.stderr)
        return 1
    if sys.platform == "darwin":
        # message can contain a path read from a third-party process (lsof), so
        # it must be quoted as an AppleScript literal, never spliced into source.
        subprocess.run(
            [
                "/usr/bin/osascript",
                "-e",
                f'display alert "Karma" message {_osa_quote(message)} as critical',
            ],
            capture_output=True,
        )
    else:
        # Same for PowerShell: a single-quoted literal so $ and $(...) in the
        # message cannot expand or execute. CREATE_NO_WINDOW keeps the error
        # path from flashing a console under pythonw.
        script = (
            "Add-Type -AssemblyName PresentationFramework;"
            f"[System.Windows.MessageBox]::Show({_ps_quote(message)}, 'Karma')"
        )
        subprocess.run(
            ["powershell", "-NoProfile", "-Command", script],
            capture_output=True,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    return 1


# --------------------------------------------------------------------------
# Browsers
# --------------------------------------------------------------------------


_MACOS_BROWSERS = ("Google Chrome", "Microsoft Edge", "Brave Browser", "Chromium")


def _chrome_command() -> list[str] | None:
    """Command prefix for a Chromium app-mode window, or None if none is found.

    On macOS the previous version returned a Chrome command unconditionally,
    with no check that Chrome exists. On a Safari/Firefox/Edge-only Mac that
    ``open -na "Google Chrome"`` fails, the error is swallowed, and nothing
    opens. Now every branch confirms the browser is actually installed, so
    ``open_window`` can fall back to the default browser when there is no
    Chromium family browser at all.
    """
    if sys.platform == "darwin":
        for name in _MACOS_BROWSERS:
            if (Path("/Applications") / f"{name}.app").is_dir() or (
                Path.home() / "Applications" / f"{name}.app"
            ).is_dir():
                return ["open", "-na", name, "--args"]
        return None
    candidates = (
        ["google-chrome", "chrome", "chromium", "microsoft-edge", "msedge"]
        if sys.platform != "win32"
        else []
    )
    for name in candidates:
        found = shutil.which(name)
        if found:
            return [found]
    if sys.platform == "win32":
        # Edge ships on every stock Windows install; searching only for Chrome
        # meant the common case silently fell through to a plain browser tab
        # instead of the advertised app-mode window.
        relative = (
            ("Google", "Chrome", "Application", "chrome.exe"),
            ("Microsoft", "Edge", "Application", "msedge.exe"),
            ("BraveSoftware", "Brave-Browser", "Application", "brave.exe"),
        )
        bases = (
            os.environ.get("PROGRAMFILES", r"C:\Program Files"),
            os.environ.get("PROGRAMFILES(X86)", r"C:\Program Files (x86)"),
            os.environ.get("LOCALAPPDATA", ""),
        )
        for base in bases:
            if not base:
                continue
            for parts in relative:
                exe = Path(base).joinpath(*parts)
                if exe.is_file():
                    return [str(exe)]
    return None


def _installed_pwa() -> Path | None:
    """The Chrome-installed Karma PWA bundle on macOS, if the user added it.

    Preferred when present: it carries Karma's own Dock icon and has the
    back/refresh title-bar controls that a bare app-mode window lacks.
    """
    if sys.platform != "darwin":
        return None
    # macOS localises this folder name, so match on the prefix.
    apps = Path.home() / "Applications"
    if not apps.is_dir():
        return None
    for child in apps.iterdir():
        if child.name.startswith("Chrome Apps"):
            for app in child.glob("*Karma*.app"):
                return app
    return None


def open_window(url: str) -> None:
    """Open the dashboard, preferring an app-style window, then any browser.

    Order: an installed Karma PWA (its own icon + title-bar controls), then a
    Chromium app-mode window, then the OS default browser. Every branch is
    guarded by an existence check so a machine without Chrome still gets a
    window rather than a silently-swallowed failure.
    """
    pwa = _installed_pwa()
    if pwa is not None:
        subprocess.run(["open", str(pwa)], capture_output=True)
        return
    chrome = _chrome_command()
    if chrome:
        subprocess.Popen(
            chrome + [f"--app={url}"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return
    # No Chromium browser: hand the URL to whatever the OS default is.
    if sys.platform == "darwin":
        subprocess.Popen(
            ["open", url], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )
        return
    webbrowser.open(url)


def notify(message: str) -> None:
    """Best-effort "Karma is starting" desktop notification. Never raises.

    Replaces the old splash window: it tells the user a slow cold start is
    under way without standing up an HTTP server, a throwaway port, and an
    AppleScript teardown just to show one line of text.
    """
    try:
        if sys.platform == "darwin":
            subprocess.Popen(
                [
                    "/usr/bin/osascript",
                    "-e",
                    f'display notification {_osa_quote(message)} with title "Karma"',
                ],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        elif sys.platform == "win32":
            # A NotifyIcon balloon needs no third-party module. Run it detached
            # so the launcher does not block on the balloon's dwell time.
            ps = (
                "Add-Type -AssemblyName System.Windows.Forms;"
                "$n=New-Object System.Windows.Forms.NotifyIcon;"
                "$n.Icon=[System.Drawing.SystemIcons]::Information;"
                "$n.Visible=$true;"
                f"$n.ShowBalloonTip(4000,'Karma',{_ps_quote(message)},"
                "[System.Windows.Forms.ToolTipIcon]::Info);"
                "Start-Sleep -Seconds 5;$n.Dispose()"
            )
            subprocess.Popen(
                ["powershell", "-NoProfile", "-WindowStyle", "Hidden", "-Command", ps],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
    except OSError:
        pass


def _osa_quote(text: str) -> str:
    """Quote a string as an AppleScript literal."""
    return '"' + text.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _ps_quote(text: str) -> str:
    """Quote a string as a PowerShell single-quoted literal."""
    return "'" + text.replace("'", "''") + "'"


# --------------------------------------------------------------------------
# Servers
# --------------------------------------------------------------------------


def start_api(root: Path, port: int) -> None:
    """Start uvicorn, preferring a karma virtualenv over the ambient PATH.

    No ``--reload``: this launcher runs Karma to *use* it, often as a login
    item. Dev-mode reload doubles the process count (reloader parent + worker)
    and, without watchfiles, falls back to StatReload, which polls the tree
    continuously -- steady CPU and disk for no benefit here. Developers run
    ``uvicorn --reload`` themselves.
    """
    venv_uvicorn = core.find_venv_bin(root, "uvicorn")
    if venv_uvicorn:
        # A venv binary already points at its own interpreter, so no login
        # shell is needed to find it.
        core.spawn_detached(
            [str(venv_uvicorn), "main:app", "--port", str(port)],
            cwd=root / "api",
            log_path=core.log_dir() / "api.log",
            use_login_shell=False,
        )
        return
    core.spawn_detached(
        ["uvicorn", "main:app", "--port", str(port)],
        cwd=root / "api",
        log_path=core.log_dir() / "api.log",
    )


def start_web(root: Path, port: int) -> None:
    """Start the vite dev server on karma's fixed port."""
    core.spawn_detached(
        ["npm", "run", "dev", "--", "--port", str(port), "--strictPort"],
        cwd=root / "frontend",
        log_path=core.log_dir() / "web.log",
    )


def _has_command(name: str) -> bool:
    """Whether ``name`` resolves in the same environment the servers run in.

    Servers are launched through a login shell (GUI processes get a minimal
    PATH), so a plain ``shutil.which`` here would false-negative on a tool that
    is really on the user's PATH. Probe through the login shell to match.
    """
    shell = core.login_shell()
    if shell:
        result = subprocess.run(
            [shell, "-lc", f"command -v {name}"],
            capture_output=True,
        )
        return result.returncode == 0
    return shutil.which(name) is not None


def _preflight(root: Path, need_api: bool, need_web: bool) -> str | None:
    """Fast, accurate error for a missing toolchain, instead of a 4-minute wait.

    ``start_web`` runs ``npm run dev`` and ``start_api`` runs uvicorn; with no
    check, a missing npm/node/node_modules or uvicorn just prints
    "command not found" into a log nobody reads while the launcher waits out the
    full ~4-minute port timeout.
    """
    if need_api:
        if core.find_venv_bin(root, "uvicorn") is None and not _has_command("uvicorn"):
            return (
                "uvicorn is not installed. In the repo's api/ folder run:\n"
                "  pip install -e '.[dev]' && pip install -r requirements.txt"
            )
    if need_web:
        if not (root / "frontend" / "node_modules").is_dir():
            return (
                "The frontend's dependencies are not installed. Run:\n"
                "  cd frontend && npm install"
            )
        if not _has_command("npm"):
            return (
                "npm was not found. Install Node.js (which includes npm) and try again."
            )
    return None


@contextlib.contextmanager
def _spawn_lock():
    """Best-effort cross-launch lock around the server-spawn critical section.

    Uses an exclusively-created lock file; a stale one (from a crashed launch)
    is taken over after a minute. On any error the lock is skipped rather than
    blocking the launch -- correctness of the servers doesn't depend on it, it
    only avoids a double-spawn race.
    """
    lock = core.log_dir() / "launch.lock"
    acquired = False
    try:
        try:
            fd = os.open(str(lock), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
            os.close(fd)
            acquired = True
        except FileExistsError:
            import time

            if lock.exists() and time.time() - lock.stat().st_mtime > 60:
                acquired = True  # stale; proceed and let the winner-by-bind sort it out
    except OSError:
        pass
    try:
        yield
    finally:
        if acquired:
            try:
                lock.unlink(missing_ok=True)
            except OSError:
                pass


def _claim_port(root: Path, port: int, label: str) -> str | None:
    """Check whether ``port`` is free, ours, or held by an unrelated project.

    Returns an error message when another project owns it, else None.
    """
    if not core.port_is_up(port):
        return None
    cwd = core.port_owner_cwd(port)
    if cwd is None:
        # Not inspectable (or Windows): a live port is assumed to be karma's.
        return None
    try:
        owned_by_karma = Path(cwd).resolve().is_relative_to(root.resolve())
    except (OSError, ValueError):
        return None
    if owned_by_karma:
        return None
    return (
        f"Port {port} ({label}) is in use by another project at {cwd}. "
        f"Free it and try again."
    )


# --------------------------------------------------------------------------
# Main
# --------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Start Karma and open the dashboard.")
    parser.add_argument("--web-port", type=int, default=core.WEB_PORT)
    parser.add_argument("--api-port", type=int, default=core.API_PORT)
    parser.add_argument(
        "--no-open",
        action="store_true",
        help="Start the servers but do not open a window (for scripts and CI).",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Report failures on stderr instead of a GUI alert.",
    )
    args = parser.parse_args(argv)

    root = core.repo_root()
    url = f"http://localhost:{args.web_port}"
    headless = args.no_open

    api_up = core.port_is_up(args.api_port)
    web_up = core.port_is_up(args.web_port)

    for port, label in ((args.api_port, "API"), (args.web_port, "frontend")):
        problem = _claim_port(root, port, label)
        if problem:
            return _fail(problem, headless or args.quiet)

    # Fail fast on a missing toolchain rather than waiting out the port timeout.
    problem = _preflight(root, need_api=not api_up, need_web=not web_up)
    if problem:
        return _fail(problem, headless or args.quiet)

    # Serialise the spawn so two near-simultaneous launches (an impatient
    # double-click, or a Dock click while launchd's RunAtLoad is still working)
    # don't both start servers and race for the port. Whoever loses the lock
    # skips spawning and falls through to wait for the winner's servers.
    with _spawn_lock():
        api_up = core.port_is_up(args.api_port)
        web_up = core.port_is_up(args.web_port)
        if not api_up:
            start_api(root, args.api_port)
        if not web_up:
            start_web(root, args.web_port)

    # A cold start compiles the frontend (~1-2 min); tell the user so the click
    # does not look dead. Only when something actually has to boot, and only
    # when we are the interactive launcher (headless autostart stays silent).
    cold = not (api_up and web_up)
    if cold and not headless:
        notify("Starting servers — the dashboard will open in a moment.")

    if not core.wait_for_port(args.api_port, API_TIMEOUT):
        return _fail(
            f"The API did not start on port {args.api_port}. "
            f"Check {core.log_dir() / 'api.log'}",
            headless or args.quiet,
        )
    if not core.wait_for_port(args.web_port, WEB_TIMEOUT):
        return _fail(
            f"The frontend did not start on port {args.web_port}. "
            f"Check {core.log_dir() / 'web.log'}",
            headless or args.quiet,
        )

    _log(f"OK: servers ready at {url} (headless={headless})")
    if headless:
        print(f"OK: Karma is ready at {url}")
        return 0

    open_window(url)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Runtime entry point for the Karma desktop icon.

Invoked by the generated macOS ``.app`` or Windows Desktop shortcut. Starts
whichever karma servers are not already running, shows a splash window while
the frontend compiles, then opens the dashboard.

Run directly for a headless check::

    python3 scripts/karma_desktop/launcher.py --no-open
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import tempfile
import webbrowser
from pathlib import Path

if __package__ in (None, ""):  # invoked as a plain script by the .app / .lnk
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from karma_desktop import core, splash
else:
    from . import core, splash

# A cold vite build on this repo is slow; the API is comparatively instant.
API_TIMEOUT = 90
WEB_TIMEOUT = 240


def _fail(message: str, quiet: bool) -> int:
    """Report a startup failure, using a GUI alert when there is no terminal."""
    if quiet or sys.platform not in ("darwin", "win32"):
        print(f"FAIL: {message}", file=sys.stderr)
        return 1
    if sys.platform == "darwin":
        subprocess.run(
            [
                "/usr/bin/osascript",
                "-e",
                f'display alert "Karma" message "{message}" as critical',
            ],
            capture_output=True,
        )
    else:
        subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-Command",
                "Add-Type -AssemblyName PresentationFramework;"
                f'[System.Windows.MessageBox]::Show("{message}", "Karma")',
            ],
            capture_output=True,
        )
    return 1


# --------------------------------------------------------------------------
# Browsers
# --------------------------------------------------------------------------


def _chrome_command() -> list[str] | None:
    """Command to open a Chrome/Edge app-mode window, if one is installed."""
    if sys.platform == "darwin":
        return ["open", "-na", "Google Chrome", "--args"]
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
        import os

        for base in (
            os.environ.get("PROGRAMFILES", r"C:\Program Files"),
            os.environ.get("PROGRAMFILES(X86)", r"C:\Program Files (x86)"),
            os.environ.get("LOCALAPPDATA", ""),
        ):
            if not base:
                continue
            exe = Path(base) / "Google" / "Chrome" / "Application" / "chrome.exe"
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
    """Open the dashboard, preferring an app-style window over a browser tab."""
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
    webbrowser.open(url)


def close_splash_window(port: int) -> None:
    """Close the macOS splash window, matched by URL so only ours is touched."""
    if sys.platform != "darwin":
        return
    script = f"""
tell application "Google Chrome"
  repeat with w in (every window)
    try
      if (URL of active tab of w) contains ":{port}" then close w
    end try
  end repeat
end tell
"""
    subprocess.run(["/usr/bin/osascript", "-e", script], capture_output=True)


# --------------------------------------------------------------------------
# Servers
# --------------------------------------------------------------------------


def start_api(root: Path, port: int) -> None:
    """Start uvicorn, preferring a karma virtualenv over the ambient PATH."""
    venv_uvicorn = core.find_venv_bin(root, "uvicorn")
    if venv_uvicorn:
        # A venv binary already points at its own interpreter, so no login
        # shell is needed to find it.
        core.spawn_detached(
            [str(venv_uvicorn), "main:app", "--reload", "--port", str(port)],
            cwd=root / "api",
            log_path=core.log_dir() / "api.log",
            use_login_shell=False,
        )
        return
    core.spawn_detached(
        ["uvicorn", "main:app", "--reload", "--port", str(port)],
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

    if not api_up:
        start_api(root, args.api_port)
    if not web_up:
        start_web(root, args.web_port)

    # Only worth a splash when something actually has to boot.
    httpd = None
    cold = not (api_up and web_up)
    if cold and not headless:
        httpd = _start_splash(args.api_port, args.web_port)

    try:
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

        if headless:
            print(f"OK: Karma is ready at {url}")
            return 0

        if httpd is not None and sys.platform == "win32":
            # The splash redirected itself; give it a moment to load the
            # dashboard before the splash server goes away.
            import time

            time.sleep(3)
        else:
            open_window(url)
            if httpd is not None:
                import time

                time.sleep(2)
                close_splash_window(httpd.server_address[1])
        return 0
    finally:
        if httpd is not None:
            httpd.shutdown()
            httpd.server_close()


def _start_splash(api_port: int, web_port: int):
    """Serve and open the splash page; returns the server, or None on failure."""
    try:
        tmp = Path(tempfile.mkdtemp(prefix="karma-splash-"))
        (tmp / "index.html").write_text(
            splash.render(api_port, web_port, redirect=sys.platform == "win32"),
            encoding="utf-8",
        )
        httpd = splash.serve(tmp, core.SPLASH_PORT)
    except OSError:
        # The splash is a nicety; never let it block the actual launch.
        return None
    # SPLASH_PORT is 0, so read back the port the OS actually assigned.
    open_window(f"http://localhost:{httpd.server_address[1]}/")
    return httpd


if __name__ == "__main__":
    raise SystemExit(main())

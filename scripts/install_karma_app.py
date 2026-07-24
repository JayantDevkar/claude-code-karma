#!/usr/bin/env python3
"""Install a desktop entry that starts Karma and opens the dashboard.

    python3 scripts/install_karma_app.py              # install
    python3 scripts/install_karma_app.py --dock       # macOS: also pin to Dock
    python3 scripts/install_karma_app.py --autostart  # also start at login
    python3 scripts/install_karma_app.py --uninstall

By default the desktop icon starts the servers on demand, so nothing runs
until you click it. ``--autostart`` additionally brings the servers up at
login, which is what makes a browser-installed PWA icon work on its own.

No paths are baked into the repository: the repo location comes from this
file's position on disk, and the Python interpreter is discovered on the
machine running the install.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from karma_desktop import core  # noqa: E402


def stable_python() -> Path:
    """A Python interpreter the shortcut can rely on long-term.

    The launcher only uses the standard library, so any Python 3 works. What
    matters is picking one that will still exist later — so if the installer
    is being run from inside a virtualenv, resolve to the interpreter that
    venv was built from rather than the venv itself, which may be deleted.
    """
    if sys.prefix != sys.base_prefix:
        base = Path(sys.base_prefix) / (
            "python.exe" if sys.platform == "win32" else "bin/python3"
        )
        if base.is_file():
            return base
    return Path(sys.executable).resolve()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Install the Karma desktop launcher.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--web-port", type=int, default=core.WEB_PORT)
    parser.add_argument("--api-port", type=int, default=core.API_PORT)
    parser.add_argument(
        "--dock",
        action="store_true",
        help="macOS only: pin the app to the Dock (restarts the Dock).",
    )
    parser.add_argument(
        "--autostart",
        action="store_true",
        help="Also start the servers at login (launchd / Startup folder).",
    )
    parser.add_argument(
        "--no-autostart",
        action="store_true",
        help="Stop starting the servers at login, leaving the icon in place.",
    )
    parser.add_argument(
        "--user",
        action="store_true",
        help="macOS only: install to ~/Applications instead of /Applications.",
    )
    parser.add_argument("--uninstall", action="store_true")
    args = parser.parse_args(argv)

    repo = core.repo_root()
    python = stable_python()

    if sys.platform == "darwin":
        from karma_desktop import installer_macos as backend

        if args.uninstall:
            removed = backend.uninstall(
                [Path("/Applications"), Path.home() / "Applications"]
            )
            print("Removed:" if removed else "Nothing to remove.")
            for item in removed:
                print(f"  {item}")
            return 0

        app_dir = Path.home() / "Applications" if args.user else Path("/Applications")
        app_dir.mkdir(parents=True, exist_ok=True)
        try:
            app = backend.install_app(
                repo, python, app_dir, args.web_port, args.api_port
            )
        except PermissionError:
            print(
                f"No permission to write to {app_dir}. "
                f"Re-run with --user to install to ~/Applications.",
                file=sys.stderr,
            )
            return 1
        print(f"Installed {app}")

        if args.dock:
            print(
                "Pinned to the Dock."
                if backend.add_to_dock(app)
                else "Could not update the Dock; drag the app there manually."
            )
        if args.autostart:
            backend.install_autostart(repo, python, args.web_port, args.api_port)
            print(f"Autostart enabled: {backend.agent_path()}")
            print(
                "macOS will notify you a background item was added; you can turn "
                "it off under System Settings > General > Login Items."
            )
        elif args.no_autostart:
            print(
                "Autostart disabled."
                if backend.uninstall_autostart()
                else "Autostart was not enabled."
            )

    elif sys.platform == "win32":
        from karma_desktop import installer_windows as backend

        if args.uninstall:
            removed = backend.uninstall()
            print("Removed:" if removed else "Nothing to remove.")
            for item in removed:
                print(f"  {item}")
            return 0

        lnk = backend.install_app(repo, python, args.web_port, args.api_port)
        print(f"Installed {lnk}")
        if args.autostart:
            entry = backend.install_autostart(
                repo, python, args.web_port, args.api_port
            )
            print(f"Autostart enabled: {entry}")
            print("Windows lists this under Task Manager > Startup.")
        elif args.no_autostart:
            print(
                "Autostart disabled."
                if backend.uninstall_autostart()
                else "Autostart was not enabled."
            )
        if args.dock:
            print(
                "Note: --dock is macOS only. On Windows, right-click the Desktop "
                "icon and choose 'Pin to taskbar' if you want it there."
            )

    else:
        print(
            f"No desktop installer for platform {sys.platform!r} yet "
            f"(macOS and Windows are supported). You can still run the launcher "
            f"directly:\n"
            f"  python3 {repo / 'scripts' / 'karma_desktop' / 'launcher.py'}",
            file=sys.stderr,
        )
        return 1

    print(
        f"\nRepo:   {repo}\nPython: {python}\nPorts:  web {args.web_port}, api {args.api_port}"
    )
    print(
        "\nClick the icon to start Karma. First launch compiles the frontend "
        "and can take a minute or two; a splash window shows progress."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

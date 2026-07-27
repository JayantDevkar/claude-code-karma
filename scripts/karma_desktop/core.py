"""Shared, platform-neutral pieces of the karma desktop launcher.

Everything here must work identically on macOS, Windows and Linux. Anything
that needs a platform branch lives in ``installer_macos`` / ``installer_windows``.
"""

from __future__ import annotations

import os
import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path
from typing import Optional, Sequence

# Karma's declared ports. These are deliberately fixed rather than taken from
# vite/uvicorn defaults so that karma always lives at the same address on every
# machine — the same way Jupyter owns 8888 or Ollama owns 11434. Both servers
# bind with strict-port semantics, so a clash is a loud failure, never a silent
# move to another port.
WEB_PORT = 5180
API_PORT = 8020

APP_NAME = "Karma"


def repo_root() -> Path:
    """Absolute path to the repository this package was installed from.

    Derived from this file's own location (``<repo>/scripts/karma_desktop/core.py``)
    so a clone at any path works with no configuration.
    """
    return Path(__file__).resolve().parents[2]


def log_dir() -> Path:
    """Where launcher and server logs are written, created on demand."""
    d = Path.home() / ".claude_karma" / "launcher"
    d.mkdir(parents=True, exist_ok=True)
    return d


# --------------------------------------------------------------------------
# Port probing
# --------------------------------------------------------------------------


def port_is_up(port: int, host: str = "localhost", timeout: float = 1.0) -> bool:
    """True when something is accepting TCP connections on ``port``.

    A plain socket connect is used rather than an HTTP request: it is faster,
    dependency-free, and identical across platforms. It also correctly reports
    a server that is listening but not yet answering HTTP.

    The host defaults to ``localhost`` rather than ``127.0.0.1`` on purpose.
    Vite frequently binds the IPv6 loopback (``[::1]``) only, so an IPv4-only
    probe reports a perfectly healthy dev server as down and the launcher waits
    forever. ``create_connection`` walks every address ``getaddrinfo`` returns,
    so both families are covered.
    """
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def wait_for_port(port: int, seconds: float, interval: float = 0.5) -> bool:
    """Poll ``port`` until it accepts connections or ``seconds`` elapses."""
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if port_is_up(port):
            return True
        time.sleep(interval)
    return False


def port_owner_cwd(port: int) -> Optional[str]:
    """Working directory of the process listening on ``port``, if discoverable.

    Used to tell "karma is already running" apart from "another project has
    taken karma's port". Best effort by design — on platforms where the owning
    process cannot be inspected without extra dependencies this returns None,
    and callers fall back to treating a live port as usable.
    """
    if sys.platform == "win32":
        # Resolving a PID's cwd on Windows needs psutil or WMI; not worth a
        # dependency for a diagnostic. Callers handle None.
        return None

    lsof = shutil.which("lsof")
    if not lsof:
        return None
    try:
        pids = subprocess.run(
            [lsof, "-ti", f"tcp:{port}", "-sTCP:LISTEN"],
            capture_output=True,
            text=True,
            timeout=5,
        ).stdout.split()
        if not pids:
            return None
        out = subprocess.run(
            [lsof, "-a", "-p", pids[0], "-d", "cwd", "-Fn"],
            capture_output=True,
            text=True,
            timeout=5,
        ).stdout
    except (OSError, subprocess.SubprocessError):
        return None

    for line in out.splitlines():
        if line.startswith("n"):
            return line[1:]
    return None


# --------------------------------------------------------------------------
# Interpreter / toolchain discovery
# --------------------------------------------------------------------------

_VENV_DIRS = (".karma-venv", ".venv", "venv", "env")


def find_venv_bin(root: Path, exe: str) -> Optional[Path]:
    """Locate ``exe`` inside a virtualenv at the repo root or under ``api/``.

    Checked before the ambient PATH so the API runs against the dependencies
    the user actually installed for karma rather than whatever happens to be
    global.
    """
    bindir = "Scripts" if sys.platform == "win32" else "bin"
    suffixes = (".exe", "") if sys.platform == "win32" else ("",)
    for base in (root, root / "api"):
        for venv in _VENV_DIRS:
            for suffix in suffixes:
                candidate = base / venv / bindir / (exe + suffix)
                if candidate.is_file():
                    return candidate
    return None


def login_shell() -> Optional[str]:
    """The user's interactive shell, used to recover their real PATH.

    GUI-launched processes on macOS inherit a minimal PATH that omits homebrew,
    nvm, pyenv and friends, so commands are run through a login shell to pick
    up the profile the user actually configured. Returns None on Windows, where
    the environment block already carries the user's PATH.
    """
    if sys.platform == "win32":
        return None
    shell = os.environ.get("SHELL")
    if shell and Path(shell).exists():
        return shell
    for candidate in ("/bin/zsh", "/bin/bash", "/bin/sh"):
        if Path(candidate).exists():
            return candidate
    return None


def _quote(args: Sequence[str]) -> str:
    import shlex

    return " ".join(shlex.quote(a) for a in args)


def spawn_detached(
    args: Sequence[str],
    cwd: Path,
    log_path: Path,
    use_login_shell: bool = True,
) -> subprocess.Popen:
    """Start a long-running server, detached, with output appended to a log.

    The process must outlive this launcher: the launcher exits as soon as the
    dashboard is open, but the servers keep running.
    """
    log_path.parent.mkdir(parents=True, exist_ok=True)
    handle = open(log_path, "ab")

    popen_kwargs = {
        "cwd": str(cwd),
        "stdout": handle,
        "stderr": subprocess.STDOUT,
        "stdin": subprocess.DEVNULL,
    }

    if sys.platform == "win32":
        # Detach from this console and never flash a window.
        popen_kwargs["creationflags"] = (
            subprocess.CREATE_NO_WINDOW | subprocess.DETACHED_PROCESS  # type: ignore[attr-defined]
        )
        return subprocess.Popen(list(args), **popen_kwargs)

    popen_kwargs["start_new_session"] = True
    shell = login_shell() if use_login_shell else None
    if shell:
        return subprocess.Popen([shell, "-lc", _quote(args)], **popen_kwargs)
    return subprocess.Popen(list(args), **popen_kwargs)

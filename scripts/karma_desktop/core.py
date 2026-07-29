"""Shared, platform-neutral pieces of the karma desktop launcher.

Everything here must work identically on macOS, Windows and Linux. Anything
that needs a platform branch lives in ``installer_macos`` / ``installer_windows``.
"""

from __future__ import annotations

import os
import re
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
        # A port can have several matching pids (a reloader parent + worker, or
        # IPv4/IPv6 sockets); return the first cwd we can resolve.
        for pid in pids:
            out = subprocess.run(
                [lsof, "-a", "-p", pid, "-d", "cwd", "-Fn"],
                capture_output=True,
                text=True,
                timeout=5,
            ).stdout
            for line in out.splitlines():
                if line.startswith("n"):
                    return line[1:]
    except (OSError, subprocess.SubprocessError):
        return None
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


# A path is "version-pinned" if it names a specific minor version anywhere:
# .../Versions/3.12/..., python@3.12, python3.12. Such a path stops existing
# the moment that minor version is removed on upgrade.
_VERSIONED_INTERPRETER = re.compile(r"Versions/3\.\d+|python@3\.\d+|python3\.\d+")


def _is_versioned_interpreter(path: Path) -> bool:
    # as_posix() so the ``Versions/3.N`` pattern matches regardless of the host's
    # path separator (str(Path(...)) yields backslashes on Windows).
    return bool(_VERSIONED_INTERPRETER.search(path.as_posix()))


def stable_python() -> Path:
    """A Python interpreter the generated shortcut can rely on long-term.

    The launcher only uses the standard library, so *any* Python 3 works -- what
    matters is picking one that still exists after an interpreter upgrade. The
    trap is ``Path(sys.executable).resolve()``: on python.org and Homebrew that
    follows the ``python3`` symlink straight into ``.../Versions/3.12/...``,
    which the stub then bakes in and which breaks the day 3.12 is removed.

    So prefer an *unversioned* interpreter -- ``/usr/local/bin/python3``,
    ``/opt/homebrew/bin/python3``, ``py``/``python.exe`` -- whose symlink the
    distribution repoints across upgrades. Candidates, best first: the venv's
    base interpreter, then ``python3``/``python`` on PATH, then this very
    interpreter; the first one that both exists and is not version-pinned wins,
    falling back to whatever exists if all of them are pinned.
    """
    candidates: list[Path] = []
    if sys.prefix != sys.base_prefix:
        candidates.append(
            Path(sys.base_prefix)
            / ("python.exe" if sys.platform == "win32" else "bin/python3")
        )
    names = (
        ("python.exe", "python") if sys.platform == "win32" else ("python3", "python")
    )
    for name in names:
        found = shutil.which(name)
        if found:
            candidates.append(Path(found))
    candidates.append(Path(sys.executable))

    existing = [c for c in candidates if c.is_file()]
    for candidate in existing:
        if not _is_versioned_interpreter(candidate):
            return candidate
    return existing[0] if existing else Path(sys.executable)


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


_LOG_CAP_BYTES = 10 * 1024 * 1024  # keep launcher-managed logs from growing forever


def _cap_log(log_path: Path) -> None:
    """Truncate a server log that has grown past the cap.

    api.log / web.log have no rotation; over many launches they grow without
    bound. A hard truncate keeps the newest run's output and drops history --
    fine for a diagnostic log.
    """
    try:
        if log_path.is_file() and log_path.stat().st_size > _LOG_CAP_BYTES:
            with open(log_path, "wb") as fh:
                fh.write(b"[log truncated: exceeded size cap]\n")
    except OSError:
        pass


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
    _cap_log(log_path)
    # The child inherits a dup of this fd, so the parent closes its own copy
    # once Popen has taken it -- leaving it open leaks a handle per call.
    handle = open(log_path, "ab")
    try:
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
            # CreateProcess only appends ".exe" to a bare name; it does NOT walk
            # PATHEXT. Node ships "npm" as npm.cmd (no npm.exe), so Popen(["npm",
            # ...]) raises WinError 2. Resolve through shutil.which (which does
            # honour PATHEXT) so the real npm.cmd / npx.cmd is launched. Without
            # this the frontend never starts and, under pythonw, does so with no
            # error anywhere.
            resolved = shutil.which(args[0])
            win_args = [resolved, *args[1:]] if resolved else list(args)
            return subprocess.Popen(win_args, **popen_kwargs)

        popen_kwargs["start_new_session"] = True
        shell = login_shell() if use_login_shell else None
        if shell:
            # Force the working directory *after* the login shell's profile
            # runs: a .zprofile/.bash_profile with `cd ~` would otherwise move
            # the process out of <repo>/api before uvicorn's `main:app` import.
            command = f"cd {_quote([str(cwd)])} && {_quote(args)}"
            return subprocess.Popen([shell, "-lc", command], **popen_kwargs)
        return subprocess.Popen(list(args), **popen_kwargs)
    finally:
        handle.close()

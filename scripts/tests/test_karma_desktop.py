"""Tests for the desktop launcher and installer.

Runs on Linux, macOS and Windows. Platform-specific behaviour is exercised
where the host allows it and skipped otherwise, so the same file is meaningful
on every runner in the CI matrix.
"""

from __future__ import annotations

import re
import socket
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1]
REPO = SCRIPTS.parent
sys.path.insert(0, str(SCRIPTS))

from karma_desktop import core, splash  # noqa: E402
from karma_desktop import installer_windows as win  # noqa: E402


# --------------------------------------------------------------------------
# No machine-specific values may reach the repository
# --------------------------------------------------------------------------

# The launcher was originally a hand-written script full of one developer's
# absolute paths. These patterns are what that looked like; none of them may
# ever appear in the shipped sources again.
FORBIDDEN = [
    re.compile(r"/Users/[a-zA-Z0-9._-]+"),  # a macOS home directory
    re.compile(r"C:\\\\Users\\\\(?!First )"),  # a Windows profile
    re.compile(r"/home/[a-zA-Z0-9._-]+"),  # a Linux home directory
    re.compile(r"Python\.framework/Versions/3\.\d+"),  # a pinned interpreter
    re.compile(r"My-Github"),  # a personal repo folder
]

SHIPPED = sorted(p for p in (SCRIPTS / "karma_desktop").glob("*.py")) + [
    SCRIPTS / "install_karma_app.py"
]


@pytest.mark.parametrize("path", SHIPPED, ids=lambda p: p.name)
def test_no_machine_specific_paths(path: Path):
    """Shipped sources must contain no absolute user or interpreter paths.

    Everything is derived at runtime, so a clone at any location works for any
    user. This guard exists because the opposite is easy to reintroduce by
    accident while debugging on one machine.
    """
    text = path.read_text(encoding="utf-8")
    for line_no, line in enumerate(text.splitlines(), 1):
        for pattern in FORBIDDEN:
            assert not pattern.search(line), (
                f"{path.name}:{line_no} contains a machine-specific path "
                f"matching {pattern.pattern!r}: {line.strip()}"
            )


def test_repo_root_resolves_to_this_checkout():
    """Repo root comes from the package location, not configuration."""
    assert core.repo_root() == REPO
    assert (core.repo_root() / "scripts" / "karma_desktop").is_dir()


# --------------------------------------------------------------------------
# Ports
# --------------------------------------------------------------------------


def test_brand_ports_are_fixed():
    assert core.WEB_PORT == 5180
    assert core.API_PORT == 8020


def test_splash_port_is_os_assigned():
    """The splash must not squat a fixed port.

    A fixed splash port would sit in vite's auto-increment path (5174, 5175,
    ...), making it the most collision-prone port of the three for anyone
    running several projects at once.
    """
    assert core.SPLASH_PORT == 0


def test_port_is_up_detects_a_live_listener():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        s.listen(1)
        port = s.getsockname()[1]
        assert core.port_is_up(port) is True
    # Closed again; the same port must now read as down.
    assert core.port_is_up(port, timeout=0.3) is False


@pytest.mark.skipif(not socket.has_ipv6, reason="host has no IPv6")
def test_port_is_up_detects_an_ipv6_only_listener():
    """Vite often binds [::1] only; an IPv4-only probe would miss it entirely.

    Regression test: probing 127.0.0.1 made the launcher wait the full frontend
    timeout while a perfectly healthy dev server was already serving on [::1].
    """
    try:
        s = socket.socket(socket.AF_INET6, socket.SOCK_STREAM)
        s.bind(("::1", 0))
        s.listen(1)
    except OSError:
        pytest.skip("IPv6 loopback unavailable on this host")
    try:
        port = s.getsockname()[1]
        assert core.port_is_up(port) is True
    finally:
        s.close()


def test_wait_for_port_times_out_without_a_listener():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        free_port = s.getsockname()[1]
    assert core.wait_for_port(free_port, seconds=1, interval=0.2) is False


# --------------------------------------------------------------------------
# Splash
# --------------------------------------------------------------------------


def test_splash_substitutes_every_placeholder():
    html = splash.render(1234, 5678)
    assert "__API_PORT__" not in html
    assert "__WEB_PORT__" not in html
    assert "__HANDOFF__" not in html
    assert "const API = 1234, WEB = 5678;" in html


def test_splash_handoff_modes_differ():
    """Redirect mode navigates itself; close mode waits to be closed."""
    redirecting = splash.render(1, 2, redirect=True)
    closing = splash.render(1, 2, redirect=False)
    assert "location.replace" in redirecting
    assert "location.replace" not in closing
    assert "Ready" in closing


def test_splash_server_serves_the_page_on_an_assigned_port(tmp_path):
    """Serving with port=0 must yield a real, reachable port."""
    import urllib.request

    (tmp_path / "index.html").write_text(splash.render(1, 2), encoding="utf-8")
    httpd = splash.serve(tmp_path)
    try:
        port = httpd.server_address[1]
        assert port > 0, "OS must assign a concrete port"
        assert port not in (core.WEB_PORT, core.API_PORT)
        assert core.wait_for_port(port, seconds=5)
        body = urllib.request.urlopen(f"http://127.0.0.1:{port}/", timeout=5).read()
        assert b"Starting Karma" in body
    finally:
        httpd.shutdown()
        httpd.server_close()


def test_two_splash_servers_do_not_collide(tmp_path):
    """Concurrent launches must not fight over one fixed splash port."""
    (tmp_path / "index.html").write_text(splash.render(1, 2), encoding="utf-8")
    first = splash.serve(tmp_path)
    second = splash.serve(tmp_path)
    try:
        assert first.server_address[1] != second.server_address[1]
    finally:
        for httpd in (first, second):
            httpd.shutdown()
            httpd.server_close()


# --------------------------------------------------------------------------
# Toolchain discovery
# --------------------------------------------------------------------------


def test_find_venv_bin_finds_a_venv_layout(tmp_path):
    """A karma venv is preferred over whatever happens to be on PATH."""
    bindir = "Scripts" if sys.platform == "win32" else "bin"
    exe = "uvicorn.exe" if sys.platform == "win32" else "uvicorn"
    target = tmp_path / ".karma-venv" / bindir / exe
    target.parent.mkdir(parents=True)
    target.write_text("#!/bin/sh\n")
    assert core.find_venv_bin(tmp_path, "uvicorn") == target


def test_find_venv_bin_returns_none_when_absent(tmp_path):
    assert core.find_venv_bin(tmp_path, "uvicorn") is None


# --------------------------------------------------------------------------
# Windows shortcut creation
# --------------------------------------------------------------------------


@pytest.mark.skipif(sys.platform != "win32", reason="Windows shortcut API")
def test_creates_desktop_shortcut_and_resolves_back(tmp_path):
    """A generated .lnk must point where we said, including with spaces."""
    spaced = tmp_path / "Repo With Spaces"
    (spaced / "scripts" / "karma_desktop").mkdir(parents=True)
    lnk = tmp_path / "Karma.lnk"

    win.create_shortcut(
        lnk=lnk,
        target=Path(sys.executable),
        arguments=f'"{spaced / "scripts" / "karma_desktop" / "launcher.py"}" --web-port 5180',
        workdir=spaced,
    )
    assert lnk.is_file()

    read_back = subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-Command",
            f'$s=(New-Object -ComObject WScript.Shell).CreateShortcut("{lnk}");'
            '"$($s.TargetPath)|$($s.Arguments)|$($s.WorkingDirectory)"',
        ],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    target, arguments, workdir = read_back.split("|")
    assert Path(target) == Path(sys.executable)
    assert "Repo With Spaces" in arguments
    assert "--web-port 5180" in arguments
    assert Path(workdir) == spaced


@pytest.mark.skipif(sys.platform != "win32", reason="Windows path conventions")
def test_desktop_and_startup_dirs_are_absolute():
    assert win.desktop_dir().is_absolute()
    assert win.startup_dir().is_absolute()
    assert win.startup_dir().name == "Startup"


@pytest.mark.skipif(sys.platform != "win32", reason="pythonw is Windows-only")
def test_pythonw_preferred_when_present():
    """pythonw avoids a console window flashing on every launch."""
    chosen = win.pythonw_for(Path(sys.executable))
    assert chosen.name in ("pythonw.exe", Path(sys.executable).name)


# --------------------------------------------------------------------------
# macOS bundle generation
# --------------------------------------------------------------------------


@pytest.mark.skipif(sys.platform != "darwin", reason="macOS bundle layout")
def test_builds_app_bundle_with_correct_stub(tmp_path):
    import plistlib

    from karma_desktop import installer_macos as mac

    app = mac.install_app(
        repo=REPO,
        python=Path(sys.executable),
        app_dir=tmp_path,
        web_port=5180,
        api_port=8020,
    )
    assert app.is_dir()

    stub = app / "Contents" / "MacOS" / "Karma"
    assert stub.is_file()
    assert stub.stat().st_mode & 0o111, "stub must be executable"

    body = stub.read_text()
    assert "--web-port 5180" in body
    assert "--api-port 8020" in body
    assert "launcher.py" in body
    assert "proc_translated" in body, "Rosetta guard must survive"

    info = plistlib.loads((app / "Contents" / "Info.plist").read_bytes())
    assert info["CFBundleIdentifier"] == mac.BUNDLE_ID
    assert info["CFBundleExecutable"] == "Karma"
    assert info["LSUIElement"] is True


@pytest.mark.skipif(sys.platform != "darwin", reason="macOS bundle layout")
def test_app_bundle_handles_repo_paths_with_spaces(tmp_path):
    """Quoting in the stub must survive a repo path containing spaces."""
    from karma_desktop import installer_macos as mac

    spaced = tmp_path / "my repo"
    (spaced / "scripts" / "karma_desktop").mkdir(parents=True)
    app = mac.install_app(
        repo=spaced,
        python=Path(sys.executable),
        app_dir=tmp_path,
        web_port=5180,
        api_port=8020,
    )
    body = (app / "Contents" / "MacOS" / "Karma").read_text()
    # shlex.quote wraps the path so bash sees one argument, not two.
    assert "'" in body and "my repo" in body
    assert (
        subprocess.run(
            ["bash", "-n", str(app / "Contents" / "MacOS" / "Karma")]
        ).returncode
        == 0
    )

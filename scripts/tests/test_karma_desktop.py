"""Tests for the desktop launcher and installer.

Runs on Linux, macOS and Windows. Platform-specific behaviour is exercised
where the host allows it and skipped otherwise, so the same file is meaningful
on every runner in the CI matrix.
"""

from __future__ import annotations

import plistlib
import re
import socket
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1]
REPO = SCRIPTS.parent
sys.path.insert(0, str(SCRIPTS))

from karma_desktop import core  # noqa: E402
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
# Window opening: prefer PWA, then Chromium app-mode, then default browser
# --------------------------------------------------------------------------


def test_open_window_prefers_the_installed_pwa(monkeypatch):
    from karma_desktop import launcher

    monkeypatch.setattr(launcher, "_installed_pwa", lambda: Path("/fake/Karma.app"))
    calls = {}
    monkeypatch.setattr(
        launcher.subprocess, "run", lambda *a, **k: calls.__setitem__("run", a[0])
    )
    launcher.open_window("http://localhost:5180/")
    assert calls.get("run") == ["open", "/fake/Karma.app"]


def test_open_window_uses_chromium_app_mode_when_no_pwa(monkeypatch):
    from karma_desktop import launcher

    monkeypatch.setattr(launcher, "_installed_pwa", lambda: None)
    monkeypatch.setattr(launcher, "_chrome_command", lambda: ["chrome-bin"])
    calls = {}
    monkeypatch.setattr(
        launcher.subprocess, "Popen", lambda cmd, **k: calls.__setitem__("popen", cmd)
    )
    launcher.open_window("http://localhost:5180/")
    assert calls["popen"] == ["chrome-bin", "--app=http://localhost:5180/"]


def test_open_window_falls_back_when_no_chromium_browser(monkeypatch):
    """A Mac with no Chromium browser must still open *something*.

    Regression: the darwin branch always returned a Chrome command, so on a
    Chrome-less Mac it failed silently and no window opened at all.
    """
    from karma_desktop import launcher

    monkeypatch.setattr(launcher, "_installed_pwa", lambda: None)
    monkeypatch.setattr(launcher, "_chrome_command", lambda: None)
    calls = {}
    monkeypatch.setattr(
        launcher.subprocess, "Popen", lambda cmd, **k: calls.__setitem__("popen", cmd)
    )
    monkeypatch.setattr(
        launcher.webbrowser, "open", lambda u: calls.__setitem__("web", u)
    )

    launcher.open_window("http://localhost:5180/")
    if sys.platform == "darwin":
        assert calls["popen"] == ["open", "http://localhost:5180/"]
    else:
        assert calls.get("web") == "http://localhost:5180/"


@pytest.mark.skipif(sys.platform != "darwin", reason="Chromium detection is per-OS")
def test_chrome_command_none_without_a_browser(monkeypatch):
    """With no Chromium browser bundle present, _chrome_command returns None."""
    from karma_desktop import launcher

    # Ask for a browser name that cannot exist, so neither /Applications nor
    # ~/Applications resolves it.
    monkeypatch.setattr(launcher, "_MACOS_BROWSERS", ("No Such Browser 4b2c",))
    assert launcher._chrome_command() is None


def test_notify_never_raises(monkeypatch):
    """notify() is best-effort; a missing tool must not crash the launch."""
    from karma_desktop import launcher

    def boom(*a, **k):
        raise OSError("no such tool")

    monkeypatch.setattr(launcher.subprocess, "Popen", boom)
    launcher.notify("hello")  # must not raise


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
# Destructive-operation safety (macOS)
# --------------------------------------------------------------------------


@pytest.mark.skipif(sys.platform != "darwin", reason="macOS bundle layout")
def test_install_app_refuses_to_overwrite_a_foreign_bundle(tmp_path):
    """A same-named app from another vendor must never be rmtree'd."""
    from karma_desktop import installer_macos as mac

    contents = tmp_path / "Karma.app" / "Contents"
    contents.mkdir(parents=True)
    with open(contents / "Info.plist", "wb") as fh:
        plistlib.dump({"CFBundleIdentifier": "com.someoneelse.karma"}, fh)
    marker = contents / "keep-me.txt"
    marker.write_text("not ours")

    with pytest.raises(FileExistsError):
        mac.install_app(REPO, Path(sys.executable), tmp_path, 5180, 8020)
    assert marker.exists(), "foreign bundle must be left completely intact"


def test_dock_matcher_ignores_apps_whose_path_merely_contains_karma():
    """The Dock matcher must not sweep up unrelated apps by path substring.

    Regression: matching "karma" anywhere in the tile's file URL deleted any
    app living under a directory containing "karma" — e.g. a checkout of this
    very repo, or ~/Projects/karma-tools/SomeApp.app.
    """
    from karma_desktop import installer_macos as mac

    unrelated = {
        "tile-data": {
            "file-label": "SomeApp",
            "bundle-identifier": "com.vendor.someapp",
            "file-data": {"_CFURLString": "file:///Users/me/karma-tools/SomeApp.app/"},
        }
    }
    launcher_tile = {"tile-data": {"bundle-identifier": mac.BUNDLE_ID}}
    pwa_tile = {
        "tile-data": {
            "file-label": "Claude Code Karma",
            "bundle-identifier": "com.google.Chrome.app.ncciflbl",
        }
    }
    assert mac._is_replaceable_karma_tile(unrelated) is False
    assert mac._is_replaceable_karma_tile(launcher_tile) is True
    assert mac._is_replaceable_karma_tile(pwa_tile) is True


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


# --------------------------------------------------------------------------
# Autostart must be symmetric
# --------------------------------------------------------------------------


@pytest.mark.skipif(sys.platform != "darwin", reason="launchd is macOS-only")
def test_autostart_round_trips(tmp_path, monkeypatch):
    """Enabling then disabling must leave no login item behind.

    Regression test: the first version only ever *added* the agent, so turning
    the toggle off silently did nothing and Karma still started at login.
    """
    from karma_desktop import installer_macos as mac

    fake_agent = tmp_path / "com.claudecodekarma.servers.plist"
    monkeypatch.setattr(mac, "agent_path", lambda: fake_agent)
    # Never talk to the real launchd from a test.
    monkeypatch.setattr(mac.subprocess, "run", lambda *a, **k: None)

    assert mac.autostart_enabled() is False

    mac.install_autostart(REPO, Path(sys.executable), 5180, 8020)
    assert fake_agent.exists()
    assert mac.autostart_enabled() is True

    assert mac.uninstall_autostart() is True
    assert not fake_agent.exists()
    assert mac.autostart_enabled() is False

    # Disabling twice is not an error, it is simply a no-op.
    assert mac.uninstall_autostart() is False


@pytest.mark.skipif(sys.platform != "darwin", reason="Dock is macOS-only")
def test_unpin_only_removes_the_launcher_bundle(monkeypatch):
    """Unpinning must target the launcher by bundle id, never a user's PWA tile.

    Autostart enables unpin; if it matched on the word "Karma" it would also
    strip a browser-installed PWA tile the user pinned on purpose.
    """
    import types

    from karma_desktop import installer_macos as mac

    dock = {
        "persistent-apps": [
            {
                "tile-data": {
                    "file-label": "Safari",
                    "bundle-identifier": "com.apple.Safari",
                }
            },
            {"tile-data": {"file-label": "Karma", "bundle-identifier": mac.BUNDLE_ID}},
            {
                "tile-data": {
                    "file-label": "Claude Code Karma",
                    "bundle-identifier": "com.google.Chrome.app.abc",
                }
            },
        ]
    }

    monkeypatch.setattr(
        mac.subprocess,
        "run",
        lambda *a, **k: types.SimpleNamespace(stdout=plistlib.dumps(dock)),
    )
    written = {}

    def capture(plist):
        written["p"] = plist
        return True

    monkeypatch.setattr(mac, "_write_dock", capture)

    assert mac.unpin_from_dock() is True
    labels = [a["tile-data"]["file-label"] for a in written["p"]["persistent-apps"]]
    # Launcher gone; Safari and the user's browser PWA tile untouched.
    assert labels == ["Safari", "Claude Code Karma"]


@pytest.mark.skipif(sys.platform != "darwin", reason="launchd is macOS-only")
def test_autostart_plist_runs_the_launcher_headless(tmp_path, monkeypatch):
    """The login item must not try to open a window at login."""
    import plistlib

    from karma_desktop import installer_macos as mac

    fake_agent = tmp_path / "agent.plist"
    monkeypatch.setattr(mac, "agent_path", lambda: fake_agent)
    monkeypatch.setattr(mac.subprocess, "run", lambda *a, **k: None)

    mac.install_autostart(REPO, Path(sys.executable), 5180, 8020)
    payload = plistlib.loads(fake_agent.read_bytes())

    assert payload["Label"] == mac.AGENT_LABEL
    assert payload["RunAtLoad"] is True
    # KeepAlive must stay off: the launcher exits once the servers are up, so
    # relaunching it forever would be a restart loop.
    assert payload["KeepAlive"] is False
    assert "--no-open" in payload["ProgramArguments"]
    assert "--quiet" in payload["ProgramArguments"]


@pytest.mark.skipif(sys.platform != "win32", reason="Startup folder is Windows-only")
def test_windows_autostart_round_trips(tmp_path, monkeypatch):
    monkeypatch.setattr(win, "startup_dir", lambda: tmp_path)

    assert win.autostart_enabled() is False
    win.install_autostart(REPO, Path(sys.executable), 5180, 8020)
    assert win.autostart_enabled() is True
    assert win.uninstall_autostart() is True
    assert win.autostart_enabled() is False
    assert win.uninstall_autostart() is False


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

"""Tests for the production frontend build the launcher serves.

No npm runs here: the build step is replaced by a fake that writes what a real
``vite build`` with adapter-node would leave in the output directory.
"""

from __future__ import annotations

import os
import sys
import types
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1]
REPO = SCRIPTS.parent
sys.path.insert(0, str(SCRIPTS))

from karma_desktop import core, frontend  # noqa: E402


@pytest.fixture
def fe(tmp_path: Path) -> Path:
    root = tmp_path / "frontend"
    (root / "src" / "routes").mkdir(parents=True)
    (root / "static").mkdir()
    (root / "node_modules" / "pkg").mkdir(parents=True)
    (root / "src" / "routes" / "+page.svelte").write_text("<h1>hi</h1>")
    (root / "static" / "favicon.svg").write_text("<svg/>")
    for name in (
        "package.json",
        "package-lock.json",
        "svelte.config.js",
        "vite.config.ts",
    ):
        (root / name).write_text("{}")
    return root


def _touch_later(path: Path, text: str | None = None) -> None:
    if text is not None:
        path.write_text(text)
    stat = path.stat()
    os.utime(path, ns=(stat.st_atime_ns, stat.st_mtime_ns + 5_000_000_000))


@pytest.fixture
def fake_build(monkeypatch):
    """Replace the npm build; returns a dict of what it was asked to do."""
    calls: dict = {"runs": 0}

    def run(args, cwd, log_path, timeout, env=None):
        calls["runs"] += 1
        calls.update(args=list(args), cwd=Path(cwd), env=env or {}, timeout=timeout)
        out = Path(cwd) / (env or {}).get("KARMA_BUILD_OUT", "build")
        if calls.get("fail"):
            out.mkdir(parents=True, exist_ok=True)  # a half-written output
            return 1
        (out / "client").mkdir(parents=True, exist_ok=True)
        (out / "index.js").write_text(f"// build {calls['runs']}")
        return 0

    monkeypatch.setattr(core, "run_logged", run)
    return calls


# --------------------------------------------------------------------------
# Fingerprint: what invalidates a build
# --------------------------------------------------------------------------


def test_fingerprint_is_stable(fe):
    assert frontend.fingerprint(fe) == frontend.fingerprint(fe)


@pytest.mark.parametrize(
    "relpath",
    [
        "src/routes/+page.svelte",
        "static/favicon.svg",
        "package-lock.json",
        "svelte.config.js",
    ],
)
def test_fingerprint_changes_with_any_build_input(fe, relpath):
    before = frontend.fingerprint(fe)
    _touch_later(fe / relpath)
    assert frontend.fingerprint(fe) != before


def test_fingerprint_sees_new_source_files(fe):
    before = frontend.fingerprint(fe)
    (fe / "src" / "routes" / "about").mkdir()
    (fe / "src" / "routes" / "about" / "+page.svelte").write_text("x")
    assert frontend.fingerprint(fe) != before


def test_fingerprint_ignores_outputs_and_dependencies(fe):
    before = frontend.fingerprint(fe)
    (fe / "build").mkdir()
    (fe / "build" / "index.js").write_text("x")
    (fe / "node_modules" / "pkg" / "index.js").write_text("x")
    (fe / ".svelte-kit").mkdir()
    assert frontend.fingerprint(fe) == before


# --------------------------------------------------------------------------
# Building and swapping
# --------------------------------------------------------------------------


def test_no_build_is_not_current(fe):
    assert frontend.build_is_current(fe) is False


def test_successful_build_is_current_until_a_source_changes(fe, fake_build, tmp_path):
    assert frontend.build(fe, tmp_path / "build.log", timeout=60) is True

    assert frontend.build_is_current(fe) is True
    assert fake_build["args"] == ["npm", "run", "build"]
    assert fake_build["cwd"] == fe
    # Built aside, never into the directory a running server reads from
    assert fake_build["env"]["KARMA_BUILD_OUT"] != "build"
    assert not (fe / fake_build["env"]["KARMA_BUILD_OUT"]).exists()

    _touch_later(fe / "src" / "routes" / "+page.svelte", "<h1>changed</h1>")
    assert frontend.build_is_current(fe) is False


def test_rebuild_replaces_the_previous_build(fe, fake_build, tmp_path):
    frontend.build(fe, tmp_path / "build.log", timeout=60)
    (fe / "build" / "leftover.js").write_text("old chunk")
    _touch_later(fe / "src" / "routes" / "+page.svelte", "v2")

    assert frontend.build(fe, tmp_path / "build.log", timeout=60) is True

    assert (fe / "build" / "index.js").read_text() == "// build 2"
    assert not (fe / "build" / "leftover.js").exists()
    assert frontend.build_is_current(fe) is True


def test_failed_build_keeps_the_previous_build(fe, fake_build, tmp_path):
    frontend.build(fe, tmp_path / "build.log", timeout=60)
    _touch_later(fe / "src" / "routes" / "+page.svelte", "broken")
    fake_build["fail"] = True

    assert frontend.build(fe, tmp_path / "build.log", timeout=60) is False

    assert (fe / "build" / "index.js").read_text() == "// build 1"
    assert not (fe / fake_build["env"]["KARMA_BUILD_OUT"]).exists()
    assert frontend.build_is_current(fe) is False


def test_build_without_an_entry_point_is_a_failure(fe, monkeypatch, tmp_path):
    def run(args, cwd, log_path, timeout, env=None):
        (Path(cwd) / env["KARMA_BUILD_OUT"]).mkdir()
        return 0

    monkeypatch.setattr(core, "run_logged", run)

    assert frontend.build(fe, tmp_path / "build.log", timeout=60) is False
    assert not (fe / "build").exists()


def test_build_timeout_is_a_failure(fe, monkeypatch, tmp_path):
    monkeypatch.setattr(core, "run_logged", lambda *a, **k: None)

    assert frontend.build(fe, tmp_path / "build.log", timeout=1) is False


# --------------------------------------------------------------------------
# Launcher: serving the build
# --------------------------------------------------------------------------


def test_start_web_serves_the_build_on_localhost(monkeypatch, tmp_path):
    from karma_desktop import launcher

    captured = {}
    monkeypatch.setattr(
        core, "spawn_detached", lambda args, **k: captured.update(args=args, **k)
    )

    launcher.start_web(tmp_path, 5180)

    assert captured["args"] == ["node", "build"]
    assert captured["cwd"] == tmp_path / "frontend"
    # Never node's default 0.0.0.0: the dashboard must not be reachable off-machine
    assert captured["env"] == {"PORT": "5180", "HOST": "localhost"}


def test_start_web_dev_mode_runs_vite(monkeypatch, tmp_path):
    from karma_desktop import launcher

    captured = {}
    monkeypatch.setattr(
        core, "spawn_detached", lambda args, **k: captured.update(args=args)
    )

    launcher.start_web(tmp_path, 5180, dev=True)

    assert captured["args"] == [
        "npm",
        "run",
        "dev",
        "--",
        "--port",
        "5180",
        "--strictPort",
    ]


def test_spawn_lock_outlives_a_build():
    from karma_desktop import launcher

    assert launcher._STALE_LOCK_SECONDS > (
        launcher.API_TIMEOUT + launcher.BUILD_TIMEOUT + launcher.WEB_TIMEOUT
    )


class FakeWeb:
    """Records what _ensure_web did to the frontend server."""

    def __init__(self, monkeypatch, *, up, current, ours=None, build_ok=True):
        from karma_desktop import launcher

        self.events: list = []
        self.current = current
        monkeypatch.setattr(launcher.core, "port_is_up", lambda port, *a, **k: up)
        monkeypatch.setattr(
            launcher.frontend, "build_is_current", lambda fe: self.current
        )
        monkeypatch.setattr(launcher, "_running_build_server", lambda port: ours)
        monkeypatch.setattr(launcher.core, "wait_for_port_closed", lambda *a, **k: True)
        monkeypatch.setattr(launcher, "notify", lambda message: None)

        def fake_build(fe, log_path, timeout):
            self.events.append("build")
            self.current = build_ok
            return build_ok

        def fake_start(root, port, dev=False):
            self.events.append("start dev" if dev else "start build")
            return types.SimpleNamespace(pid=4242)

        monkeypatch.setattr(launcher.frontend, "build", fake_build)
        monkeypatch.setattr(launcher, "start_web", fake_start)
        monkeypatch.setattr(
            launcher.core,
            "stop_process_tree",
            lambda pid: self.events.append(f"stop {pid}"),
        )
        monkeypatch.setattr(
            launcher, "_record_web_server", lambda *a: self.events.append("record")
        )


def _ensure(dev=False):
    from karma_desktop import launcher

    return launcher._ensure_web(REPO, 5180, dev=dev, headless=True)


@pytest.mark.parametrize(
    "case, expected",
    [
        ({"up": False, "current": True}, ["start build", "record"]),
        ({"up": False, "current": False}, ["build", "start build", "record"]),
        (
            {"up": False, "current": False, "build_ok": False},
            ["build", "start dev", "record"],
        ),
        ({"up": True, "current": True, "ours": 99}, []),
        (
            {"up": True, "current": False, "ours": 99},
            ["build", "stop 99", "start build", "record"],
        ),
        ({"up": True, "current": False, "ours": 99, "build_ok": False}, ["build"]),
        ({"up": True, "current": False, "ours": None}, []),
    ],
    ids=[
        "cold-current",
        "cold-stale",
        "cold-build-fails-falls-back-to-dev",
        "running-current",
        "running-stale-ours-restarts",
        "running-stale-build-fails-keeps-old",
        "running-not-ours-untouched",
    ],
)
def test_ensure_web(monkeypatch, case, expected):
    fake = FakeWeb(monkeypatch, **case)
    _ensure()
    assert fake.events == expected


def test_ensure_web_dev_flag_never_builds(monkeypatch):
    fake = FakeWeb(monkeypatch, up=False, current=False)
    _ensure(dev=True)
    assert fake.events == ["start dev", "record"]


def test_running_build_server_requires_a_matching_record(monkeypatch, tmp_path):
    from karma_desktop import launcher

    monkeypatch.setattr(core, "log_dir", lambda: tmp_path)
    monkeypatch.setattr(sys, "platform", "darwin")
    monkeypatch.setattr(core, "port_listener_pids", lambda port: [501, 502])
    monkeypatch.setattr(launcher.os, "getpgid", lambda pid: {501: 1, 502: 77}[pid])

    assert launcher._running_build_server(5180) is None  # no record yet

    launcher._record_web_server(77, "build", 5180)
    assert launcher._running_build_server(5180) == 77

    launcher._record_web_server(77, "dev", 5180)
    assert launcher._running_build_server(5180) is None  # never restart a dev server

    launcher._record_web_server(12, "build", 5180)
    assert (
        launcher._running_build_server(5180) is None
    )  # recorded pid no longer serves the port


def test_running_build_server_is_unknowable_on_windows(monkeypatch, tmp_path):
    from karma_desktop import launcher

    monkeypatch.setattr(core, "log_dir", lambda: tmp_path)
    launcher._record_web_server(77, "build", 5180)
    monkeypatch.setattr(sys, "platform", "win32")

    assert launcher._running_build_server(5180) is None

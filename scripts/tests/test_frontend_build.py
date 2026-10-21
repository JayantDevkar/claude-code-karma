"""Tests for the production frontend build the launcher serves.

No npm runs here: the build step is replaced by a fake that writes what a real
``vite build`` with adapter-node would leave in the output directory.
"""

from __future__ import annotations

import os
import sys
import time
import types
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1]
REPO = SCRIPTS.parent
sys.path.insert(0, str(SCRIPTS))

from karma_desktop import core, frontend  # noqa: E402


@pytest.fixture(autouse=True)
def _private_log_dir(monkeypatch, tmp_path_factory):
    """Keep launcher logs, locks and the web-server record out of the real ~/.claude_karma."""
    logs = tmp_path_factory.mktemp("launcher-logs")
    monkeypatch.setattr(core, "log_dir", lambda: logs)


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

    def __init__(
        self,
        monkeypatch,
        *,
        up,
        current,
        owned=None,
        build_ok=True,
        stops=True,
        swap_ok=True,
        has_build=True,
    ):
        from karma_desktop import launcher

        self.events: list = []
        monkeypatch.setattr(launcher.core, "port_is_up", lambda port, *a, **k: up)
        monkeypatch.setattr(launcher.frontend, "build_is_current", lambda fe: current)
        monkeypatch.setattr(launcher.frontend, "has_build", lambda fe: has_build)
        monkeypatch.setattr(launcher, "_owned_web_server", lambda port: owned)
        monkeypatch.setattr(
            launcher.core, "wait_for_port_closed", lambda *a, **k: stops
        )
        monkeypatch.setattr(launcher, "notify", lambda message: None)

        def step(name, result):
            def run(*a, **k):
                self.events.append(name)
                return result

            return run

        monkeypatch.setattr(launcher.frontend, "prepare", step("prepare", build_ok))
        monkeypatch.setattr(launcher.frontend, "activate", step("activate", swap_ok))
        monkeypatch.setattr(launcher.frontend, "discard", step("discard", None))
        monkeypatch.setattr(
            launcher,
            "_start_and_record",
            lambda root, port, mode: self.events.append(f"start {mode}"),
        )
        monkeypatch.setattr(
            launcher.core,
            "stop_process_tree",
            lambda pid, **k: self.events.append(f"stop {pid}"),
        )


def _ensure(dev=False):
    from karma_desktop import launcher

    return launcher._ensure_web(REPO, 5180, dev=dev, headless=True)


@pytest.mark.parametrize(
    "case, expected",
    [
        ({"up": False, "current": True}, ["start build"]),
        ({"up": False, "current": False}, ["prepare", "activate", "start build"]),
        ({"up": False, "current": False, "build_ok": False}, ["prepare", "start dev"]),
        ({"up": True, "current": True, "owned": (99, "build")}, []),
        (
            {"up": True, "current": False, "owned": (99, "build")},
            ["prepare", "stop 99", "activate", "start build"],
        ),
        (
            {"up": True, "current": False, "owned": (99, "build"), "build_ok": False},
            ["prepare"],
        ),
        (
            {"up": True, "current": False, "owned": (99, "build"), "stops": False},
            ["prepare", "stop 99", "discard"],
        ),
        (
            {"up": True, "current": False, "owned": (99, "build"), "swap_ok": False},
            ["prepare", "stop 99", "activate", "start build"],
        ),
        (
            {"up": False, "current": False, "swap_ok": False, "has_build": False},
            ["prepare", "activate", "start dev"],
        ),
        (
            {"up": True, "current": True, "owned": (99, "dev")},
            ["stop 99", "start build"],
        ),
        (
            {"up": True, "current": False, "owned": (99, "dev")},
            ["prepare", "stop 99", "activate", "start build"],
        ),
        ({"up": True, "current": False, "owned": None}, []),
    ],
    ids=[
        "cold-current",
        "cold-stale",
        "cold-build-fails-falls-back-to-dev",
        "running-current",
        "running-stale-restarts-after-build",
        "running-stale-build-fails-keeps-old",
        "running-stale-old-server-wont-stop",
        "running-stale-swap-fails-serves-old-build",
        "cold-swap-fails-no-build-falls-back-to-dev",
        "running-dev-fallback-replaced-by-build",
        "running-dev-fallback-stale-rebuilt",
        "running-not-ours-untouched",
    ],
)
def test_ensure_web(monkeypatch, case, expected):
    fake = FakeWeb(monkeypatch, **case)
    _ensure()
    assert fake.events == expected


@pytest.mark.parametrize("up, expected", [(False, ["start dev"]), (True, [])])
def test_ensure_web_dev_flag_never_builds(monkeypatch, up, expected):
    fake = FakeWeb(monkeypatch, up=up, current=False, owned=(99, "build"))
    _ensure(dev=True)
    assert fake.events == expected


@pytest.mark.skipif(sys.platform == "win32", reason="process groups are POSIX-only")
def test_owned_web_server_requires_a_matching_record(monkeypatch, tmp_path):
    from karma_desktop import launcher

    monkeypatch.setattr(core, "log_dir", lambda: tmp_path)
    monkeypatch.setattr(core, "port_listener_pids", lambda port: [501, 502])
    monkeypatch.setattr(launcher.os, "getpgid", lambda pid: {501: 1, 502: 77}[pid])

    assert launcher._owned_web_server(5180) is None  # no record yet

    launcher._record_web_server(77, "build", 5180)
    assert launcher._owned_web_server(5180) == (77, "build")

    launcher._record_web_server(77, "dev", 5180)
    assert launcher._owned_web_server(5180) == (77, "dev")

    launcher._record_web_server(77, "build", 5181)
    assert launcher._owned_web_server(5180) is None  # recorded for another port

    launcher._record_web_server(12, "build", 5180)
    assert (
        launcher._owned_web_server(5180) is None
    )  # recorded pid no longer serves the port


def test_owned_web_server_is_unknowable_on_windows(monkeypatch, tmp_path):
    from karma_desktop import launcher

    monkeypatch.setattr(core, "log_dir", lambda: tmp_path)
    launcher._record_web_server(77, "build", 5180)
    monkeypatch.setattr(sys, "platform", "win32")

    assert launcher._owned_web_server(5180) is None


def test_start_and_record_writes_what_was_started(monkeypatch, tmp_path):
    import json

    from karma_desktop import launcher

    monkeypatch.setattr(core, "log_dir", lambda: tmp_path)
    monkeypatch.setattr(
        launcher,
        "start_web",
        lambda root, port, dev=False: types.SimpleNamespace(pid=4242),
    )

    launcher._start_and_record(REPO, 5180, "dev")

    record = json.loads((tmp_path / launcher._WEB_RECORD).read_text())
    assert record == {"pid": 4242, "mode": "dev", "port": 5180}


def test_a_running_frontend_does_not_need_the_build_toolchain(monkeypatch, tmp_path):
    """Preflight must not block opening a dashboard that is already being served."""
    from karma_desktop import launcher

    seen = {}
    monkeypatch.setattr(launcher, "_repair_autostart", lambda: None)
    monkeypatch.setattr(core, "port_is_up", lambda port, *a, **k: True)
    monkeypatch.setattr(launcher, "_claim_port", lambda *a: None)
    monkeypatch.setattr(launcher.frontend, "build_is_current", lambda fe: False)

    def preflight(root, need_api, need_web):
        seen.update(need_api=need_api, need_web=need_web)
        return "stop here"

    monkeypatch.setattr(launcher, "_preflight", preflight)
    monkeypatch.setattr(launcher, "_fail", lambda message, quiet: 1)

    launcher.main(["--no-open", "--quiet"])

    assert seen == {"need_api": False, "need_web": False}


def test_a_launch_waiting_on_another_launch_allows_for_its_build():
    from karma_desktop import launcher

    assert launcher._web_wait_seconds(own_spawn=True) == launcher.WEB_TIMEOUT
    assert launcher._web_wait_seconds(own_spawn=False) >= (
        launcher.BUILD_TIMEOUT + launcher.WEB_TIMEOUT
    )


# --------------------------------------------------------------------------
# Build process lifecycle
# --------------------------------------------------------------------------


@pytest.mark.skipif(sys.platform == "win32", reason="SIGTERM semantics are POSIX-only")
def test_timed_out_build_is_killed_even_if_it_ignores_sigterm(tmp_path):
    pid_file = tmp_path / "child.pid"
    script = (
        "import os, signal, time; signal.signal(signal.SIGTERM, signal.SIG_IGN); "
        f"open({str(pid_file)!r}, 'w').write(str(os.getpid())); time.sleep(60)"
    )

    started = time.monotonic()
    code = core.run_logged(
        [sys.executable, "-c", script],
        cwd=tmp_path,
        log_path=tmp_path / "log",
        timeout=2,
    )

    assert code is None
    assert time.monotonic() - started < 15  # killed, not waited out
    child = int(pid_file.read_text())
    with pytest.raises(ProcessLookupError):
        os.kill(child, 0)


def test_a_stamp_write_failure_is_a_failed_build(fe, fake_build, monkeypatch, tmp_path):
    real_write = Path.write_text

    def failing_write(self, *a, **k):
        if self.name == frontend.STAMP_NAME:
            raise OSError("disk full")
        return real_write(self, *a, **k)

    monkeypatch.setattr(Path, "write_text", failing_write)

    assert frontend.build(fe, tmp_path / "build.log", timeout=60) is False
    assert not (fe / frontend.STAGING_DIR).exists()

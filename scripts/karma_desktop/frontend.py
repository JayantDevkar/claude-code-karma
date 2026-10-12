"""The production frontend build the launcher serves.

``vite dev`` compiles every page on first request and keeps the compiler
running; ``node build`` serves precompiled output. The build is redone only
when an input changed, is written beside the live one, and is swapped in only
once it is complete, so a failed or interrupted build never replaces a good one.
"""

from __future__ import annotations

import hashlib
import os
import shutil
from pathlib import Path

if __package__ in (None, ""):
    from karma_desktop import core
else:
    from . import core

BUILD_DIR = "build"
STAGING_DIR = ".karma-build-next"
RETIRED_DIR = ".karma-build-old"
STAMP_NAME = ".karma-build-stamp"

# Everything vite build reads that a user or git pull can change.
_INPUT_DIRS = ("src", "static")
_INPUT_FILES = (
    "package.json",
    "package-lock.json",
    "svelte.config.js",
    "vite.config.ts",
    "tsconfig.json",
)


def fingerprint(frontend: Path) -> str:
    """Hash of every build input's path, size and mtime."""
    entries = []
    for name in _INPUT_DIRS:
        top = frontend / name
        for dirpath, dirnames, filenames in os.walk(top):
            dirnames.sort()
            for filename in sorted(filenames):
                entries.append(_entry(frontend, Path(dirpath) / filename))
    for name in _INPUT_FILES:
        entries.append(_entry(frontend, frontend / name))
    for env_file in sorted(frontend.glob(".env*")):
        entries.append(_entry(frontend, env_file))
    return hashlib.sha256("\n".join(entries).encode()).hexdigest()


def _entry(frontend: Path, path: Path) -> str:
    rel = path.relative_to(frontend).as_posix()
    try:
        stat = path.stat()
    except OSError:
        return f"{rel}|missing"
    return f"{rel}|{stat.st_size}|{stat.st_mtime_ns}"


def build_is_current(frontend: Path) -> bool:
    """True when ``build/`` exists and was made from the current inputs."""
    build_dir = frontend / BUILD_DIR
    if not (build_dir / "index.js").is_file():
        return False
    try:
        stamp = (build_dir / STAMP_NAME).read_text().strip()
    except OSError:
        return False
    return stamp == fingerprint(frontend)


def build(frontend: Path, log_path: Path, timeout: float) -> bool:
    """Build into a staging directory and swap it in. True on success."""
    stamp = fingerprint(frontend)
    staging = frontend / STAGING_DIR
    shutil.rmtree(staging, ignore_errors=True)

    code = core.run_logged(
        ["npm", "run", "build"],
        cwd=frontend,
        log_path=log_path,
        timeout=timeout,
        env={"KARMA_BUILD_OUT": STAGING_DIR},
    )
    if code != 0 or not (staging / "index.js").is_file():
        shutil.rmtree(staging, ignore_errors=True)
        return False

    (staging / STAMP_NAME).write_text(stamp)
    return _swap_in(frontend, staging)


def _swap_in(frontend: Path, staging: Path) -> bool:
    live = frontend / BUILD_DIR
    retired = frontend / RETIRED_DIR
    shutil.rmtree(retired, ignore_errors=True)
    try:
        if live.exists():
            os.rename(live, retired)
        os.rename(staging, live)
    except OSError:
        # Put the previous build back if it was moved; never leave no build at all.
        if retired.exists() and not live.exists():
            os.rename(retired, live)
        shutil.rmtree(staging, ignore_errors=True)
        return False
    shutil.rmtree(retired, ignore_errors=True)
    return True

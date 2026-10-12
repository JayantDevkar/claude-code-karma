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


def has_build(frontend: Path) -> bool:
    return (frontend / BUILD_DIR / "index.js").is_file()


def build_is_current(frontend: Path) -> bool:
    """True when ``build/`` exists and was made from the current inputs."""
    if not has_build(frontend):
        return False
    try:
        stamp = (frontend / BUILD_DIR / STAMP_NAME).read_text().strip()
    except OSError:
        return False
    return stamp == fingerprint(frontend)


def build(frontend: Path, log_path: Path, timeout: float) -> bool:
    """Build and swap the result in. True on success."""
    return prepare(frontend, log_path, timeout) and activate(frontend)


def prepare(frontend: Path, log_path: Path, timeout: float) -> bool:
    """Build into the staging directory, leaving the live build untouched. True on success."""
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
        discard(frontend)
        return False
    try:
        (staging / STAMP_NAME).write_text(stamp)
    except OSError:
        discard(frontend)
        return False
    return True


def discard(frontend: Path) -> None:
    """Drop a staged build that will not be used."""
    shutil.rmtree(frontend / STAGING_DIR, ignore_errors=True)


def activate(frontend: Path) -> bool:
    """Swap the staged build in. On failure the previous build is kept."""
    staging = frontend / STAGING_DIR
    live = frontend / BUILD_DIR
    retired = frontend / RETIRED_DIR
    if not (staging / "index.js").is_file():
        return False
    shutil.rmtree(retired, ignore_errors=True)
    try:
        if live.exists():
            os.rename(live, retired)
        os.rename(staging, live)
    except OSError:
        # Put the previous build back if it was moved; never leave no build at all.
        if retired.exists() and not live.exists():
            os.rename(retired, live)
        discard(frontend)
        return False
    shutil.rmtree(retired, ignore_errors=True)
    return True

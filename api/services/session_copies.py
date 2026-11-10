"""Resolve a session spread over a repo's project dir and its worktree dirs."""

from __future__ import annotations

import json
import os
import threading
import time
from functools import lru_cache
from pathlib import Path
from typing import Iterable, Optional

_SIBLING_TTL = 30.0  # seconds a projects dir's sibling index is reused

_sibling_cache: dict[str, tuple[float, int, dict[str, list[tuple[str, str]]]]] = {}
_sibling_lock = threading.Lock()


@lru_cache(maxsize=512)
def _message_count(path: str, mtime_ns: int, size: int) -> int:
    uuids: set[str] = set()
    with open(path, "rb") as f:
        for line in f:
            if b'"uuid"' not in line:
                continue
            try:
                entry = json.loads(line)
            except ValueError:
                continue
            if isinstance(entry, dict) and isinstance(entry.get("uuid"), str):
                uuids.add(entry["uuid"])
    return len(uuids)


def _completeness(path: Path) -> int:
    try:
        st = path.stat()
        return _message_count(str(path), st.st_mtime_ns, st.st_size)
    except OSError:
        return -1


def most_complete(paths: Iterable[Path]) -> Optional[Path]:
    """The existing copy with the most messages; the earliest one wins a tie. None if none exist."""
    existing = [p for p in paths if p.is_file()]
    if len(existing) <= 1:
        return existing[0] if existing else None
    return max(existing, key=_completeness)  # max keeps the first of equal keys


def _build_sibling_index(projects_dir: Path) -> dict[str, list[tuple[str, str]]]:
    from services.desktop_sessions import _extract_project_prefix_from_worktree

    names = {d.name for d in projects_dir.iterdir() if d.is_dir()}
    repo_of: dict[str, str] = {}
    for name in names:
        repo = _extract_project_prefix_from_worktree(name)
        if repo:
            repo_of[name] = repo
            if repo in names:
                repo_of[repo] = repo
    index: dict[str, list[tuple[str, str]]] = {}
    for name, repo in repo_of.items():
        try:
            with os.scandir(projects_dir / name) as entries:
                for entry in entries:
                    if entry.is_dir():
                        index.setdefault(entry.name, []).append((name, repo))
        except OSError:
            continue
    return index


def _sibling_index(projects_dir: Path) -> dict[str, list[tuple[str, str]]]:
    """Session UUID -> (dir, repo) for every repo or worktree dir holding a ``{uuid}/`` folder."""
    key = str(projects_dir)
    try:
        mtime = projects_dir.stat().st_mtime_ns
    except OSError:
        return {}
    now = time.monotonic()
    hit = _sibling_cache.get(key)
    if hit and hit[1] == mtime and now - hit[0] < _SIBLING_TTL:
        return hit[2]
    try:
        index = _build_sibling_index(projects_dir)
    except OSError:
        return hit[2] if hit else {}
    with _sibling_lock:
        _sibling_cache[key] = (now, mtime, index)
    return index


def subagent_files(jsonl_path: Path) -> list[Path]:
    """Subagent JSONLs from the session's dir plus its repo and worktree dirs; best copy per agent."""
    from services.desktop_sessions import _extract_project_prefix_from_worktree

    own, uuid = jsonl_path.parent, jsonl_path.stem
    repo = _extract_project_prefix_from_worktree(own.name) or own.name
    dirs = [own] + [
        own.parent / name
        for name, r in _sibling_index(own.parent).get(uuid, ())
        if r == repo and name != own.name
    ]
    copies: dict[str, list[Path]] = {}
    for d in dirs:
        try:
            agent_paths = list((d / uuid / "subagents").glob("agent-*.jsonl"))
        except OSError:
            continue
        for p in agent_paths:
            copies.setdefault(p.name, []).append(p)
    picked = [ps[0] if len(ps) == 1 else most_complete(ps) for ps in copies.values()]
    return sorted((p for p in picked if p is not None), key=lambda p: p.name)


def superseded_copies(dirs: Iterable[Path]) -> dict[Path, set[str]]:
    """Per dir, the session UUIDs whose more complete copy lives in another of these dirs."""
    copies: dict[str, list[Path]] = {}
    for d in dirs:
        try:
            for p in d.glob("*.jsonl"):
                if not p.name.startswith("agent-"):
                    copies.setdefault(p.stem, []).append(p)
        except OSError:
            continue  # a dir that cannot be listed holds no copies we can compare
    skips: dict[Path, set[str]] = {}
    for uuid, paths in copies.items():
        if len(paths) < 2:
            continue
        best = most_complete(paths)
        for p in paths:
            if p != best:
                skips.setdefault(p.parent, set()).add(uuid)
    return skips

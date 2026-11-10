"""Pick one file when a session UUID has a JSONL in several project dirs.

Claude Code copies a session's transcript when the session moves into a
worktree: the repo dir keeps the history up to the move, the worktree dir
holds that same history plus everything after it. Reading the first copy
found undercounts tokens and cost, so every UUID-to-file lookup picks the
copy holding the most messages. Copies seen so far are always prefixes of
each other, so that copy is also the union of both.

Subagent JSONLs can land under the other dir than the session's own JSONL,
so a session's subagents are the union over the repo dir and its worktree dirs.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Iterable, Optional


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


@lru_cache(maxsize=32)
def _worktree_dirs_by_repo(projects_dir: str, mtime_ns: int) -> dict[str, tuple[str, ...]]:
    """Worktree dir names per repo dir name in one projects dir (keyed on its mtime)."""
    from services.desktop_sessions import _extract_project_prefix_from_worktree

    by_repo: dict[str, list[str]] = {}
    for d in Path(projects_dir).iterdir():
        repo = _extract_project_prefix_from_worktree(d.name)
        if repo and d.is_dir():
            by_repo.setdefault(repo, []).append(d.name)
    return {repo: tuple(sorted(names)) for repo, names in by_repo.items()}


def _sibling_dirs(project_dir: Path) -> list[Path]:
    """project_dir, then its repo dir and that repo's worktree dirs in the same projects dir."""
    from services.desktop_sessions import _extract_project_prefix_from_worktree

    parent = project_dir.parent
    try:
        worktrees = _worktree_dirs_by_repo(str(parent), parent.stat().st_mtime_ns)
    except OSError:
        return [project_dir]
    repo = _extract_project_prefix_from_worktree(project_dir.name) or project_dir.name
    names = [project_dir.name, repo, *worktrees.get(repo, ())]
    return [parent / n for n in dict.fromkeys(names)]


def subagent_files(jsonl_path: Path) -> list[Path]:
    """A session's subagent JSONLs, sorted by name.

    A session that moves into a worktree keeps its JSONL in one dir while its
    subagents may be written under the other, so this takes the union over the
    repo dir and its worktree dirs. An agent found in several dirs uses its
    most complete copy; the session's own dir wins a tie.
    """
    uuid = jsonl_path.stem
    copies: dict[str, list[Path]] = {}
    for d in _sibling_dirs(jsonl_path.parent):
        subagents = d / uuid / "subagents"
        try:
            agent_paths = list(subagents.glob("agent-*.jsonl"))
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

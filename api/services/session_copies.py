"""Pick one file when a session UUID has a JSONL in several project dirs.

Claude Code copies a session's transcript when the session moves into a
worktree: the repo dir keeps the history up to the move, the worktree dir
holds that same history plus everything after it. Reading the first copy
found undercounts tokens and cost, so every UUID-to-file lookup picks the
copy holding the most messages. Copies seen so far are always prefixes of
each other, so that copy is also the union of both.
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

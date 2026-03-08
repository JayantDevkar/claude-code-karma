"""Atomic read/write/merge for titles.json sidecar files.

Used by both the session packager (bulk dump of cached titles) and the
POST /sessions/{uuid}/title handler (single title write on generation).

File format:
{
  "version": 1,
  "updated_at": "2026-03-08T14:30:00Z",
  "titles": {
    "uuid": {"title": "...", "source": "git|haiku|fallback", "generated_at": "..."}
  }
}
"""

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


_VERSION = 1


def read_titles(path: Path) -> dict[str, dict]:
    """Read titles.json. Returns {uuid: {title, source, generated_at}} or empty dict."""
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if data.get("version") != _VERSION:
            return {}
        return data.get("titles", {})
    except (json.JSONDecodeError, OSError, TypeError):
        return {}


def write_title(
    path: Path,
    uuid: str,
    title: str,
    source: str,
    generated_at: Optional[str] = None,
) -> None:
    """Write or merge a single title into titles.json. Atomic (tmp+rename)."""
    existing = read_titles(path)
    existing[uuid] = {
        "title": title,
        "source": source,
        "generated_at": generated_at or datetime.now(timezone.utc).isoformat(),
    }
    _write_file(path, existing)


def write_titles_bulk(path: Path, entries: dict[str, dict]) -> None:
    """Bulk write/merge titles into titles.json. Atomic (tmp+rename).

    Args:
        path: Path to titles.json
        entries: {uuid: {"title": str, "source": str}} — generated_at added if missing
    """
    existing = read_titles(path)
    now = datetime.now(timezone.utc).isoformat()
    for uuid, entry in entries.items():
        existing[uuid] = {
            "title": entry["title"],
            "source": entry.get("source", "unknown"),
            "generated_at": entry.get("generated_at", now),
        }
    _write_file(path, existing)


def _write_file(path: Path, titles: dict[str, dict]) -> None:
    """Atomically write titles dict to path."""
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "version": _VERSION,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "titles": titles,
    }
    tmp_path = path.with_name(f".titles-{os.getpid()}.tmp")
    tmp_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    tmp_path.replace(path)

"""
List Cursor skill definitions (no usage tracking — Cursor doesn't log it).

Cursor 2.5.26 emits zero per-conversation skill-invocation telemetry to
local disk (verified via exhaustive 10-signal adversarial check). We
expose skill DEFINITIONS so users can browse what's available, with a
`tracking_unavailable=True` flag so the UI can render the limitation
clearly.

Locations:
- `~/.cursor/skills-cursor/<name>/SKILL.md` — bundled skills (5 ship)
- `~/.cursor/skills/<name>/SKILL.md` — user skills (often absent)
- `<project>/.cursor/skills/<name>/SKILL.md` — project skills (not v1)
"""

import logging
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

from cursor.paths import cursor_builtin_skills_dir, cursor_skills_dir

logger = logging.getLogger(__name__)

_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---", re.DOTALL)


@dataclass(frozen=True)
class CursorSkill:
    name: str
    description: str | None
    file_path: str
    modified_at: datetime
    is_builtin: bool


def iter_cursor_skills() -> Iterator[CursorSkill]:
    """Yield every Cursor skill (bundled + user) currently on disk."""
    for root, is_builtin in (
        (cursor_builtin_skills_dir(), True),
        (cursor_skills_dir(), False),
    ):
        if not root.is_dir():
            continue
        for entry in root.iterdir():
            if not entry.is_dir():
                continue
            skill_md = entry / "SKILL.md"
            if not skill_md.is_file():
                continue
            try:
                yield _parse_skill(skill_md, is_builtin=is_builtin)
            except (OSError, UnicodeDecodeError) as e:
                logger.debug("Skipping malformed Cursor skill %s: %s", skill_md, e)


def _parse_skill(skill_md: Path, is_builtin: bool) -> CursorSkill:
    text = skill_md.read_text(encoding="utf-8")
    description = None
    match = _FRONTMATTER_RE.match(text)
    if match:
        for line in match.group(1).splitlines():
            if line.startswith("description:"):
                description = line.partition(":")[2].strip().strip("\"'")
                break
    stat = skill_md.stat()
    modified_at = datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc)
    return CursorSkill(
        name=skill_md.parent.name,
        description=description,
        file_path=str(skill_md),
        modified_at=modified_at,
        is_builtin=is_builtin,
    )

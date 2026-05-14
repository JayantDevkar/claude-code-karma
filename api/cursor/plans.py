"""
Parse Cursor plans at `~/.cursor/plans/<slug>_<8hex>.plan.md`.

Schema: YAML front-matter + Markdown body. Front-matter contains `name`,
`overview`, and an optional `todos` list with id/content/status/dependencies.
"""

import json
import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

from cursor.paths import cursor_plans_dir

logger = logging.getLogger(__name__)

_PLAN_FILE_RE = re.compile(r"^(?P<slug>.+)_(?P<plan_id>[0-9a-f]{8})\.plan\.md$")
_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n(.*)$", re.DOTALL)


@dataclass(frozen=True)
class CursorPlan:
    slug: str
    plan_id: str | None
    name: str | None
    overview: str | None
    todos_json: str | None
    body_md: str
    file_path: str
    file_mtime_ms: int


def iter_plans() -> Iterator[CursorPlan]:
    """Yield every Cursor plan file on disk, parsed."""
    root = cursor_plans_dir()
    if not root.is_dir():
        return
    for path in root.iterdir():
        if not path.is_file() or not path.name.endswith(".plan.md"):
            continue
        try:
            plan = _parse_plan(path)
        except (OSError, UnicodeDecodeError) as e:
            logger.debug("Skipping malformed plan %s: %s", path, e)
            continue
        if plan is not None:
            yield plan


def _parse_plan(path: Path) -> CursorPlan | None:
    text = path.read_text(encoding="utf-8")
    match = _PLAN_FILE_RE.match(path.name)
    plan_id = match.group("plan_id") if match else None
    slug = match.group("slug") if match else path.name[: -len(".plan.md")]

    name = None
    overview = None
    todos_json = None
    body_md = text

    fm_match = _FRONTMATTER_RE.match(text)
    if fm_match:
        frontmatter_text = fm_match.group(1)
        body_md = fm_match.group(2).strip()
        parsed = _parse_frontmatter(frontmatter_text)
        name = parsed.get("name")
        overview = parsed.get("overview")
        todos = parsed.get("todos")
        if isinstance(todos, list) and todos:
            try:
                todos_json = json.dumps(todos)
            except (TypeError, ValueError):
                todos_json = None

    mtime_ms = int(path.stat().st_mtime * 1000)
    return CursorPlan(
        slug=slug,
        plan_id=plan_id,
        name=name,
        overview=overview,
        todos_json=todos_json,
        body_md=body_md,
        file_path=str(path),
        file_mtime_ms=mtime_ms,
    )


def _parse_frontmatter(text: str) -> dict:
    """
    Lightweight YAML-subset parser for plan front-matter.

    We avoid a PyYAML dependency by handling only the shapes Cursor uses:
    - `key: value` scalars (strings, multi-word values)
    - `key:` followed by indented list of `- item` or `- key: value` dicts
    """
    try:
        import yaml  # type: ignore[import-not-found]

        return yaml.safe_load(text) or {}
    except ImportError:
        pass

    # Minimal fallback parser if PyYAML isn't installed
    result: dict = {}
    lines = text.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            i += 1
            continue
        if ":" not in line:
            i += 1
            continue
        key, _, value = line.partition(":")
        key = key.strip()
        value = value.strip()
        if value:
            result[key] = value.strip("\"'")
            i += 1
            continue
        # Block — collect indented list items
        items: list = []
        i += 1
        while i < len(lines):
            next_line = lines[i]
            if not next_line.strip():
                i += 1
                continue
            if not next_line.startswith((" ", "\t")):
                break
            if next_line.lstrip().startswith("- "):
                item_text = next_line.lstrip()[2:].rstrip()
                if ":" in item_text:
                    item_dict: dict = {}
                    sub_key, _, sub_val = item_text.partition(":")
                    item_dict[sub_key.strip()] = sub_val.strip().strip("\"'")
                    j = i + 1
                    while j < len(lines):
                        sub_line = lines[j]
                        if not sub_line.strip():
                            j += 1
                            continue
                        if not sub_line.startswith((" ", "\t")):
                            break
                        if sub_line.lstrip().startswith("- "):
                            break
                        if ":" not in sub_line:
                            j += 1
                            continue
                        sk, _, sv = sub_line.lstrip().partition(":")
                        item_dict[sk.strip()] = sv.strip().strip("\"'")
                        j += 1
                    items.append(item_dict)
                    i = j
                else:
                    items.append(item_text)
                    i += 1
            else:
                i += 1
        if items:
            result[key] = items
    return result

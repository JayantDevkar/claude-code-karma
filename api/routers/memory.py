"""
Global memory index.

GET /memory   — projects that own a memory/ dir, with note counts.
               Ordered by note count desc. Deliberately light: only counts
               files, does not re-parse content (that stays the job of
               GET /projects/{encoded}/memory).
"""

from __future__ import annotations

import logging
from pathlib import Path

from fastapi import APIRouter

from config import settings
from models.project import Project

logger = logging.getLogger(__name__)

router = APIRouter(tags=["memory"])


def _decoded_path(encoded: str) -> str:
    return Project.decode_path(encoded) or encoded.lstrip("-").replace("-", "/")


def _project_label(encoded: str) -> str:
    name = Path(_decoded_path(encoded)).name
    return name or encoded.lstrip("-")


@router.get("/memory")
def memory_index() -> dict:
    """
    One row per project that owns a memory/ directory: encoded name, label,
    decoded path, note count (*.md excluding MEMORY.md index) and whether an
    index exists. Ordered by note count desc.
    """
    projects: list[dict] = []
    pdir = settings.projects_dir

    if pdir.is_dir():
        for enc_dir in sorted(pdir.iterdir()):
            if not enc_dir.is_dir():
                continue
            mem_dir = enc_dir / "memory"
            if not mem_dir.is_dir():
                continue

            try:
                md_files = [f for f in mem_dir.iterdir() if f.is_file() and f.suffix == ".md"]
            except OSError:
                continue
            if not md_files:
                continue

            note_count = sum(1 for f in md_files if f.name != "MEMORY.md")
            has_index = any(f.name == "MEMORY.md" for f in md_files)

            projects.append(
                {
                    "encoded": enc_dir.name,
                    "label": _project_label(enc_dir.name),
                    "path": _decoded_path(enc_dir.name),
                    "note_count": note_count,
                    "has_index": has_index,
                }
            )

    projects.sort(key=lambda p: (-p["note_count"], p["label"].lower()))

    return {
        "projects": projects,
        "total_projects": len(projects),
        "total_notes": sum(p["note_count"] for p in projects),
    }

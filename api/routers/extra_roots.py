"""
Extra session roots status.

GET  /extra-roots         — configured synced roots (other machines' ~/.claude copies)
                            and how each of their project dirs was matched to a project.
POST /extra-roots/refresh — re-read the config and rescan now, then return the same.

Both are localhost-only: the response lists absolute paths on this host. Roots
are configured via CLAUDE_KARMA_EXTRA_ROOTS or ~/.claude_karma/extra-roots.json.
"""

from __future__ import annotations

from fastapi import APIRouter, Request

from routers.desktop_app import _require_local
from services import session_roots

router = APIRouter(tags=["extra-roots"])


def _status() -> dict:
    dirs_by_root: dict[str, list[dict]] = {}
    for rd in session_roots.get_remote_dirs():
        dirs_by_root.setdefault(rd.root.name, []).append(
            {
                "dir": rd.path.name,
                "project_encoded_name": rd.canonical,
                "matched_by": rd.matched_by,
                "remote_project_path": rd.remote_project_path,
                "has_sidecar": session_roots.read_sidecar(rd.path) is not None,
            }
        )
    return {
        "config_file": str(session_roots.roots_file()),
        "config_ok": session_roots.roots_config_ok(),
        "roots": [
            {
                "name": root.name,
                "path": str(root.claude_base),
                "exists": root.projects_dir.is_dir(),
                "project_dirs": dirs_by_root.get(root.name, []),
            }
            for root in session_roots.get_extra_roots()
        ],
    }


@router.get("/extra-roots")
def list_extra_roots(request: Request) -> dict:
    _require_local(request, subject="Extra roots status")
    return _status()


@router.post("/extra-roots/refresh")
def refresh_extra_roots(request: Request) -> dict:
    _require_local(request, subject="Extra roots refresh")
    session_roots.invalidate()
    return _status()

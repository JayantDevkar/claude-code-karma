"""
Extra session roots status.

GET /extra-roots — configured synced roots (other machines' ~/.claude copies)
                   and how each of their project dirs was matched to a project.
                   Read-only; roots are configured via CLAUDE_KARMA_EXTRA_ROOTS
                   or ~/.claude_karma/extra-roots.json.
"""

from __future__ import annotations

from fastapi import APIRouter

from services import session_roots

router = APIRouter(tags=["extra-roots"])


@router.get("/extra-roots")
def list_extra_roots(refresh: bool = False) -> dict:
    if refresh:  # re-read config and rescan now instead of waiting for the cache
        session_roots.clear_cache()
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

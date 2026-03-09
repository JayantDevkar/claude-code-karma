"""Remote sessions API — serves sessions synced via Syncthing."""

import json
import logging
import re
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ValidationError

from config import settings
from services.remote_sessions import _get_local_user_id

logger = logging.getLogger(__name__)

router = APIRouter()

REMOTE_SESSIONS_DIR = settings.karma_base / "remote-sessions"

_SAFE_NAME = re.compile(r"^[a-zA-Z0-9_.\-]+$")


class RemoteUser(BaseModel):
    user_id: str
    project_count: int
    total_sessions: int


class RemoteProject(BaseModel):
    encoded_name: str
    session_count: int
    synced_at: Optional[str] = None
    machine_id: Optional[str] = None


class RemoteSessionSummary(BaseModel):
    uuid: str
    mtime: str
    size_bytes: int
    worktree_name: Optional[str] = None


class RemoteManifest(BaseModel):
    version: int
    user_id: str
    machine_id: str
    project_path: str
    project_encoded: str
    synced_at: str
    session_count: int
    sessions: list[RemoteSessionSummary]


def _validate_path_segment(value: str, label: str) -> None:
    """Reject path segments that could escape the remote-sessions directory."""
    if not _SAFE_NAME.match(value) or value in (".", ".."):
        raise HTTPException(
            status_code=400,
            detail=f"Invalid {label}: must be alphanumeric, dash, underscore, or dot",
        )


def _is_safe_dirname(name: str) -> bool:
    """Check if a directory name is safe for path construction."""
    return bool(_SAFE_NAME.match(name)) and name not in (".", "..")


def _load_manifest_safe(user_id: str, project: str) -> Optional[dict]:
    """Load a manifest.json from filesystem-sourced names. Returns None on any error."""
    if not _is_safe_dirname(user_id) or not _is_safe_dirname(project):
        return None
    manifest_path = REMOTE_SESSIONS_DIR / user_id / project / "manifest.json"
    if not manifest_path.exists():
        return None
    try:
        return json.loads(manifest_path.read_text())
    except (json.JSONDecodeError, OSError):
        return None


def _load_manifest(user_id: str, project: str) -> Optional[dict]:
    """Load a manifest.json for a remote user's project (URL param sourced)."""
    _validate_path_segment(user_id, "user_id")
    _validate_path_segment(project, "project")
    manifest_path = REMOTE_SESSIONS_DIR / user_id / project / "manifest.json"
    if not manifest_path.exists():
        return None
    try:
        return json.loads(manifest_path.read_text())
    except (json.JSONDecodeError, OSError):
        return None


@router.get("/users", response_model=list[RemoteUser])
def list_remote_users() -> list[RemoteUser]:
    """List all remote users who have synced sessions."""
    if not REMOTE_SESSIONS_DIR.is_dir():
        return []

    local_user = _get_local_user_id()
    users = []
    for user_dir in sorted(REMOTE_SESSIONS_DIR.iterdir()):
        if not user_dir.is_dir() or not _is_safe_dirname(user_dir.name):
            continue
        if user_dir.name == local_user:
            continue
        project_count = 0
        total_sessions = 0
        for proj_dir in user_dir.iterdir():
            if not proj_dir.is_dir():
                continue
            project_count += 1
            manifest = _load_manifest_safe(user_dir.name, proj_dir.name)
            if manifest:
                total_sessions += manifest.get("session_count", 0)
        users.append(
            RemoteUser(
                user_id=user_dir.name,
                project_count=project_count,
                total_sessions=total_sessions,
            )
        )
    return users


@router.get("/users/{user_id}/projects", response_model=list[RemoteProject])
def list_user_projects(user_id: str) -> list[RemoteProject]:
    """List projects synced by a remote user."""
    _validate_path_segment(user_id, "user_id")
    user_dir = REMOTE_SESSIONS_DIR / user_id
    if not user_dir.is_dir():
        raise HTTPException(status_code=404, detail=f"User '{user_id}' not found")

    projects = []
    for proj_dir in sorted(user_dir.iterdir()):
        if not proj_dir.is_dir():
            continue
        manifest = _load_manifest_safe(user_id, proj_dir.name)
        projects.append(
            RemoteProject(
                encoded_name=proj_dir.name,
                session_count=manifest.get("session_count", 0) if manifest else 0,
                synced_at=manifest.get("synced_at") if manifest else None,
                machine_id=manifest.get("machine_id") if manifest else None,
            )
        )
    return projects


@router.get(
    "/users/{user_id}/projects/{project}/sessions", response_model=list[RemoteSessionSummary]
)
def list_user_sessions(user_id: str, project: str) -> list[RemoteSessionSummary]:
    """List sessions for a remote user's project."""
    manifest = _load_manifest(user_id, project)
    if not manifest:
        raise HTTPException(status_code=404, detail="Manifest not found")

    try:
        return [RemoteSessionSummary(**s) for s in manifest.get("sessions", [])]
    except ValidationError:
        raise HTTPException(status_code=422, detail="Malformed session data in manifest") from None


@router.get("/users/{user_id}/projects/{project}/manifest", response_model=RemoteManifest)
def get_manifest(user_id: str, project: str) -> RemoteManifest:
    """Get the full manifest for a remote user's project."""
    manifest = _load_manifest(user_id, project)
    if not manifest:
        raise HTTPException(status_code=404, detail="Manifest not found")
    try:
        return RemoteManifest(**manifest)
    except ValidationError:
        raise HTTPException(status_code=422, detail="Malformed manifest data") from None

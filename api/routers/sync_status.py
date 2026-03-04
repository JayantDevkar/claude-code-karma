"""Sync status API endpoints."""

import json
from pathlib import Path
from typing import Optional

from fastapi import APIRouter

SYNC_CONFIG_PATH = Path.home() / ".claude_karma" / "sync-config.json"

router = APIRouter(prefix="/sync", tags=["sync"])


def _load_config() -> Optional[dict]:
    if not SYNC_CONFIG_PATH.exists():
        return None
    try:
        return json.loads(SYNC_CONFIG_PATH.read_text())
    except (json.JSONDecodeError, OSError):
        return None


@router.get("/status")
async def sync_status():
    """Get sync configuration and status."""
    config = _load_config()
    if config is None:
        return {"configured": False}

    teams = {}
    for name, team in config.get("teams", {}).items():
        teams[name] = {
            "backend": team["backend"],
            "project_count": len(team.get("projects", {})),
            "member_count": len(team.get("ipfs_members", {})) + len(team.get("syncthing_members", {})),
        }

    return {
        "configured": True,
        "user_id": config.get("user_id"),
        "machine_id": config.get("machine_id"),
        "teams": teams,
    }


@router.get("/teams")
async def sync_teams():
    """List all teams with their backend and members."""
    config = _load_config()
    if config is None:
        return {"teams": []}

    teams = []
    for name, team in config.get("teams", {}).items():
        teams.append({
            "name": name,
            "backend": team["backend"],
            "projects": list(team.get("projects", {}).keys()),
            "members": list(team.get("ipfs_members", {}).keys()) + list(team.get("syncthing_members", {}).keys()),
        })

    return {"teams": teams}

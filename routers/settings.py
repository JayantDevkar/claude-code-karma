import json
import logging
from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from config import settings
from parallel import run_in_thread

router = APIRouter()
logger = logging.getLogger(__name__)


def _read_settings_sync(settings_path: Path) -> dict:
    """Synchronous helper to read settings file."""
    if not settings_path.exists():
        return {}
    with open(settings_path, "r", encoding="utf-8") as f:
        return json.load(f)


def _write_settings_sync(settings_path: Path, data: dict) -> None:
    """Synchronous helper to write settings file."""
    settings_path.parent.mkdir(parents=True, exist_ok=True)
    with open(settings_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


class ClaudeSettingsUpdate(BaseModel):
    cleanupPeriodDays: Optional[int] = Field(
        None,
        description="Days to keep sessions before cleanup. Default is 30. Set to 99999 to disable.",
    )

    model_config = {"extra": "allow"}


@router.get("/", response_model=Dict[str, Any])
async def get_settings():
    """Get the current global Claude Code settings."""
    settings_path = settings.claude_base / "settings.json"

    try:
        return await run_in_thread(_read_settings_sync, settings_path)
    except Exception as e:
        logger.error(f"Error reading settings.json: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to read settings file: {str(e)}",
        ) from e


@router.put("/", response_model=Dict[str, Any])
async def update_settings(updates: ClaudeSettingsUpdate):
    """Update Claude Code settings. Merges with existing settings."""
    settings_path = settings.claude_base / "settings.json"

    try:
        current_settings = await run_in_thread(_read_settings_sync, settings_path)
    except Exception as e:
        logger.error(f"Error reading existing settings: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to read existing settings: {str(e)}",
        ) from e

    # Update settings with new values
    # We only update fields that were explicitly provided in the request
    # Since we are using extra="allow", all fields in the payload will be in model_dump()
    new_values = updates.model_dump(exclude_unset=True)
    current_settings.update(new_values)

    try:
        await run_in_thread(_write_settings_sync, settings_path, current_settings)
        return current_settings
    except Exception as e:
        logger.error(f"Error writing settings: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to save settings: {str(e)}",
        ) from e

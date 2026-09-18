import asyncio
import json
import logging
import os
import shutil
import stat
import tempfile
from copy import deepcopy
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import JSONResponse
from jsonschema import Draft7Validator
from pydantic import BaseModel, Field

from config import settings
from parallel import run_in_thread

router = APIRouter()
logger = logging.getLogger(__name__)

# Serializes the whole read -> merge -> validate -> write sequence in
# update_settings() so two concurrent PUTs (two browser tabs, a debounced
# text-field save racing a toggle click) queue instead of racing on
# current_settings. Scoped to this single process/event loop, which is the
# only topology this local, single-user, single-worker tool runs under.
_settings_write_lock = asyncio.Lock()

# Vendored snapshot of https://www.schemastore.org/claude-code-settings.json,
# kept in sync by .github/workflows/schema-drift.yml. Its top-level
# `additionalProperties: true` already lets unknown keys like `spellcheck`
# (missing from this snapshot as of 2026-08-25, but real and documented)
# pass through untouched.
SETTINGS_SCHEMA_PATH = (
    Path(__file__).resolve().parents[2] / "schema" / "claude-code-settings.schema.json"
)

SPELLCHECKER_BINARIES = ["aspell", "hunspell", "ispell"]


async def handle_recursion_error(request: Request, exc: RecursionError) -> JSONResponse:
    """App-wide handler for a `RecursionError` bubbling out of request handling.

    A JSON body nested deep enough (thousands of levels, not necessarily many
    bytes) blows Python's recursion limit while Starlette parses it, before
    any router code runs. Without this handler that surfaces as an opaque,
    unhandled 500. Registered globally in main.py (this can happen on any
    route, not just this one) since FastAPI only supports exception handlers
    at the app level -- but this router turning `/settings/` into a write
    endpoint is what makes guarding it worth doing.
    """
    logger.warning(f"RecursionError handling {request.method} {request.url.path}: {exc}")
    return JSONResponse(
        status_code=status.HTTP_400_BAD_REQUEST,
        content={"detail": "Request body is too deeply nested to process."},
    )


def _load_settings_schema() -> Optional[dict]:
    try:
        with open(SETTINGS_SCHEMA_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.warning(f"Could not load vendored settings schema ({SETTINGS_SCHEMA_PATH}): {e}")
        return None


_SETTINGS_SCHEMA = _load_settings_schema()
_SETTINGS_VALIDATOR = Draft7Validator(_SETTINGS_SCHEMA) if _SETTINGS_SCHEMA else None


def _read_settings_sync(settings_path: Path) -> dict:
    """Synchronous helper to read settings file."""
    if not settings_path.exists():
        return {}
    with open(settings_path, "r", encoding="utf-8") as f:
        return json.load(f)


def _write_settings_sync(settings_path: Path, data: dict) -> None:
    """Write settings atomically, preserving permissions and a rolling backup.

    Writes to a per-call-unique sibling temp file (never a fixed name — two
    concurrent writers on a fixed temp filename can interleave their writes
    into the same inode before either `os.replace()` fires, corrupting the
    result) and `os.replace()`s it over the real file so a crash mid-write
    can never leave settings.json truncated or corrupt. Callers are also
    expected to hold `_settings_write_lock` for the whole read-merge-write
    sequence; the unique temp file alone only prevents interleaved writes,
    not a stale read racing a concurrent write.

    If `settings_path` is itself a symlink (e.g. a user syncs settings.json
    into a dotfiles repo), every operation below targets the symlink's real
    target instead: `os.replace()` on the symlink path would silently swap
    the symlink itself out for a plain file, breaking that setup. Resolving
    once up front means the symlink is never touched -- only the content it
    points at changes.
    """
    write_path = (
        Path(os.path.realpath(settings_path)) if settings_path.is_symlink() else settings_path
    )
    write_path.parent.mkdir(parents=True, exist_ok=True)

    original_mode: Optional[int] = None
    if write_path.exists():
        original_mode = stat.S_IMODE(os.stat(write_path).st_mode)
        backup_path = write_path.parent / f"{write_path.name}.karma-bak"
        shutil.copy2(write_path, backup_path)

    fd, tmp_name = tempfile.mkstemp(
        dir=write_path.parent, prefix=f"{write_path.name}.", suffix=".tmp"
    )
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
            f.write("\n")

        if original_mode is not None:
            # On Windows, os.chmod only toggles the read-only attribute, so
            # "preserve original permissions" is a partial no-op there --
            # harmless (doesn't raise), just not the full POSIX guarantee.
            os.chmod(tmp_path, original_mode)

        os.replace(tmp_path, write_path)
    except BaseException:
        tmp_path.unlink(missing_ok=True)
        raise


def _strip_none_leaves(value: Any) -> Any:
    """Recursively remove `None` leaves from a dict, per _deep_merge's null-deletes-key
    contract, for the case where there's no existing dict on `base` to merge into (so
    _deep_merge's own recursion never runs over these values). Returns `None` itself
    if everything under `value` collapses away, so the caller can drop the key entirely
    instead of writing an empty `{}`.
    """
    if not isinstance(value, dict):
        return value
    cleaned = {}
    for key, sub_value in value.items():
        if sub_value is None:
            continue
        stripped = _strip_none_leaves(sub_value)
        if stripped is None and isinstance(sub_value, dict):
            continue
        cleaned[key] = stripped
    return cleaned or None


def _deep_merge(base: dict, updates: dict) -> dict:
    """Recursively merge `updates` into `base`.

    A `None` value deletes the corresponding key (this is how "reset to
    default" works from the UI) instead of writing a literal null. Nested
    dicts are merged key-by-key rather than replacing the whole sub-object,
    so a partial nested payload (e.g. `{"spellcheck": {"enabled": true}}`)
    never clobbers sibling keys already on disk (e.g. `spellcheck.language`).

    This null-deletes-key contract holds even when `base` doesn't already
    have a dict at `key` to recurse into (e.g. resetting `spellcheck.enabled`
    when `spellcheck` was never set on disk) -- the nested nulls are stripped
    before assignment instead of being written as literal `null`s, and the
    key is dropped entirely if everything under it collapses away.
    """
    for key, value in updates.items():
        if value is None:
            base.pop(key, None)
        elif isinstance(value, dict) and isinstance(base.get(key), dict):
            _deep_merge(base[key], value)
            if base[key] == {}:
                base.pop(key, None)
        elif isinstance(value, dict):
            stripped = _strip_none_leaves(value)
            if stripped is None:
                base.pop(key, None)
            else:
                base[key] = stripped
        else:
            base[key] = value
    return base


def _validate_and_normalize(merged: dict) -> dict:
    """Round-trip through JSON and schema-validate before anything is written.

    Returns the JSON-normalized dict to write on success. Raises HTTP 422
    (leaving the on-disk file untouched) on a hard validation failure.
    Values for keys the vendored schema doesn't know about are passed
    through untouched — Claude Code itself tolerates unknown keys, and the
    vendored schema can lag behind real settings.json keys.
    """
    try:
        normalized = json.loads(json.dumps(merged))
    except (TypeError, ValueError) as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Settings payload could not be serialized to JSON: {e}",
        ) from e

    if _SETTINGS_VALIDATOR is not None:
        # Only an *unknown top-level key* is tolerated (e.g. `spellcheck`,
        # missing from this vendored snapshot but real) -- that's an
        # additionalProperties error at the schema root (empty err.path).
        # The same validator code fires for a typo'd/extra key inside a
        # nested object that explicitly declares `additionalProperties:
        # false` (e.g. a hook matcher), several levels down; suppressing
        # those too would silently accept exactly the "quietly no-ops"
        # failure this validation layer exists to catch.
        hard_errors = [
            err
            for err in _SETTINGS_VALIDATOR.iter_errors(normalized)
            if not (err.validator == "additionalProperties" and len(err.path) == 0)
        ]
        if hard_errors:
            hard_errors.sort(key=lambda err: list(err.path))
            first = hard_errors[0]
            location = ".".join(str(p) for p in first.path) or "(root)"
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Invalid value for '{location}': {first.message}",
            )

    return normalized


class PermissionModeEnum(str, Enum):
    default = "default"
    acceptEdits = "acceptEdits"
    plan = "plan"
    bypassPermissions = "bypassPermissions"
    dontAsk = "dontAsk"


class NotifChannelEnum(str, Enum):
    auto = "auto"
    iterm2 = "iterm2"
    terminal_bell = "terminal_bell"
    iterm2_with_bell = "iterm2_with_bell"
    kitty = "kitty"
    ghostty = "ghostty"
    notifications_disabled = "notifications_disabled"


class EditorModeEnum(str, Enum):
    normal = "normal"
    vim = "vim"


class AutoUpdatesChannelEnum(str, Enum):
    latest = "latest"
    stable = "stable"


class PermissionsUpdate(BaseModel):
    allow: Optional[List[str]] = None
    deny: Optional[List[str]] = None
    defaultMode: Optional[PermissionModeEnum] = None

    model_config = {"extra": "allow"}


class StatusLineUpdate(BaseModel):
    type: Optional[str] = Field(None, pattern=r"^(command|disabled)$")
    command: Optional[str] = None
    padding: Optional[int] = Field(None, ge=0)

    model_config = {"extra": "allow"}


class SpellcheckUpdate(BaseModel):
    enabled: Optional[bool] = None
    checker: Optional[str] = None
    language: Optional[str] = None
    color: Optional[str] = None

    model_config = {"extra": "allow"}


class ClaudeSettingsUpdate(BaseModel):
    cleanupPeriodDays: Optional[int] = Field(
        None,
        description="Days to keep sessions before cleanup. Default is 30. Set to 99999 to disable.",
        ge=1,
    )
    permissions: Optional[PermissionsUpdate] = None
    statusLine: Optional[StatusLineUpdate] = None
    enabledPlugins: Optional[Dict[str, bool]] = None
    alwaysThinkingEnabled: Optional[bool] = None
    env: Optional[Dict[str, str]] = None
    model: Optional[str] = None

    # Seven new settings (see docs/settings-page-v2-plan.md)
    spellcheck: Optional[SpellcheckUpdate] = None
    preferredNotifChannel: Optional[NotifChannelEnum] = None
    editorMode: Optional[EditorModeEnum] = None
    includeCoAuthoredBy: Optional[bool] = None
    autoUpdatesChannel: Optional[AutoUpdatesChannelEnum] = None
    verbose: Optional[bool] = None

    model_config = {"extra": "allow"}


@router.get("/", response_model=Dict[str, Any])
async def get_settings():
    """Get the current global Claude Code settings."""
    settings_path = settings.claude_base / "settings.json"

    try:
        return await run_in_thread(_read_settings_sync, settings_path)
    except json.JSONDecodeError as e:
        logger.error(f"settings.json is not valid JSON: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"{settings_path} contains invalid JSON and could not be read: {e}",
        ) from e
    except Exception as e:
        logger.error(f"Error reading settings.json: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to read settings file: {str(e)}",
        ) from e


@router.get("/environment", response_model=Dict[str, Any])
async def get_settings_environment():
    """Detect optional external tools/paths some settings depend on.

    Used by the UI to gate the spell-check toggle on a spell checker actually
    being on PATH, and to show which settings.json karma is editing.
    """
    settings_path = settings.claude_base / "settings.json"
    found_spellcheckers = [name for name in SPELLCHECKER_BINARIES if shutil.which(name)]
    return {
        "spellcheckers": found_spellcheckers,
        "settingsPath": str(settings_path),
    }


@router.put("/", response_model=Dict[str, Any])
async def update_settings(updates: ClaudeSettingsUpdate):
    """Update Claude Code settings. Deep-merges with existing settings.

    A field explicitly set to `null` deletes that key (or nested key) rather
    than writing a literal null, so the UI's "reset to default" leaves the
    user on Claude Code's own future default instead of pinning today's.
    """
    settings_path = settings.claude_base / "settings.json"

    async with _settings_write_lock:
        try:
            current_settings = await run_in_thread(_read_settings_sync, settings_path)
        except json.JSONDecodeError as e:
            logger.error(f"settings.json is not valid JSON: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"{settings_path} contains invalid JSON and could not be read. "
                f"Fix or remove it before saving from karma: {e}",
            ) from e
        except Exception as e:
            logger.error(f"Error reading existing settings: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to read existing settings: {str(e)}",
            ) from e

        # We only merge fields that were explicitly provided in the request.
        # Since we are using extra="allow", all fields in the payload will be
        # in model_dump(), including ones explicitly set to null (deletions).
        new_values = updates.model_dump(exclude_unset=True)
        merged = _deep_merge(deepcopy(current_settings), new_values)
        merged = _validate_and_normalize(merged)

        try:
            await run_in_thread(_write_settings_sync, settings_path, merged)
            return merged
        except Exception as e:
            logger.error(f"Error writing settings: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to save settings: {str(e)}",
            ) from e

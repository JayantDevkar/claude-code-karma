"""File validation for received sync files.

Validates extension, size, content format, and paths before indexing.
Quarantines rejected files with audit logging.
"""

import json
import logging
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, field_validator

logger = logging.getLogger(__name__)

# ── Size limits ──────────────────────────────────────────────────────

ALLOWED_EXTENSIONS = {".jsonl", ".json", ".txt"}
MAX_JSONL_SIZE = 200 * 1024 * 1024   # 200 MB per session file
MAX_JSON_SIZE  = 10 * 1024 * 1024    # 10 MB per manifest/todo
MAX_TXT_SIZE   = 50 * 1024 * 1024    # 50 MB per tool result
MAX_FILES_PER_SESSION = 500          # subagents + tool results
MAX_TOTAL_SIZE_PER_PROJECT = 2 * 1024 * 1024 * 1024  # 2 GB

_SIZE_LIMITS = {
    ".jsonl": MAX_JSONL_SIZE,
    ".json": MAX_JSON_SIZE,
    ".txt": MAX_TXT_SIZE,
}

SAFE_PATH_PART = re.compile(r'^[a-zA-Z0-9_\-\.]+$')

# ── Manifest validation ──────────────────────────────────────────────

# Same pattern as SAFE_PATH_PART — reuse for identifiers
SAFE_IDENTIFIER = SAFE_PATH_PART
from command_helpers.categories import InvocationCategory
import typing as _typing

# Derive valid categories from the canonical type, excluding "agent" (not a manifest category)
VALID_SKILL_CATEGORIES: frozenset[str] = frozenset(_typing.get_args(InvocationCategory)) - {"agent"}


class ManifestSession(BaseModel):
    uuid: str
    mtime: str
    size_bytes: int = 0
    worktree_name: Optional[str] = None
    git_branch: Optional[str] = None


class SyncManifest(BaseModel):
    """Validated manifest for remote session packages."""
    version: int = 1
    user_id: str
    machine_id: str
    project_path: str = ""
    project_encoded: str = ""
    synced_at: str = ""
    session_count: int = 0
    sessions: list[ManifestSession] = []
    sync_backend: str = "syncthing"
    skill_classifications: dict[str, str] = {}
    # Allow extra fields from older/newer manifests
    model_config = {"extra": "ignore"}

    @field_validator("user_id", "machine_id")
    @classmethod
    def validate_identifiers(cls, v: str) -> str:
        if not SAFE_IDENTIFIER.match(v):
            raise ValueError(f"Unsafe identifier: {v!r}")
        if len(v) > 128:
            raise ValueError(f"Identifier too long: {len(v)} chars")
        return v

    @field_validator("skill_classifications")
    @classmethod
    def validate_classifications(cls, v: dict) -> dict:
        return {k: cat for k, cat in v.items() if isinstance(cat, str) and cat in VALID_SKILL_CATEGORIES}


# ── Path validation ──────────────────────────────────────────────────


def validate_remote_path(base_dir: Path, relative_parts: list[str]) -> Path:
    """Construct and validate a path from remote-derived components.

    Ensures the resolved path is strictly under base_dir.
    Rejects: .., symlinks, non-alphanumeric chars (except - _ .).
    """
    for part in relative_parts:
        if not SAFE_PATH_PART.match(part):
            raise ValueError(f"Unsafe path component: {part!r}")
        if part in (".", ".."):
            raise ValueError(f"Path traversal attempt: {part!r}")

    constructed = base_dir.joinpath(*relative_parts).resolve()
    base_resolved = base_dir.resolve()

    if not str(constructed).startswith(str(base_resolved) + "/") and constructed != base_resolved:
        raise ValueError(f"Path escapes base directory: {constructed}")

    return constructed


# ── File validation ──────────────────────────────────────────────────


def validate_received_file(path: Path) -> tuple[bool, str]:
    """Validate a received file. Returns (valid, reason)."""
    if not path.is_file():
        return False, "Not a file"

    ext = path.suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        return False, f"Disallowed extension: {ext}"

    size = path.stat().st_size
    max_size = _SIZE_LIMITS.get(ext, MAX_TXT_SIZE)
    if size > max_size:
        return False, f"File too large: {size} bytes (max {max_size})"

    if size == 0:
        return True, "ok"  # Empty files are valid (new sessions)

    # Content validation for JSONL
    if ext == ".jsonl":
        return validate_jsonl_file(path)

    # Content validation for JSON
    if ext == ".json":
        return validate_json_file(path)

    return True, "ok"


def validate_jsonl_file(path: Path) -> tuple[bool, str]:
    """Validate JSONL: check first line is valid JSON with expected keys."""
    try:
        with open(path) as f:
            first_line = f.readline(2_000_000)  # Cap line read to 2MB
            if not first_line.strip():
                return False, "Empty JSONL file"
            obj = json.loads(first_line)
            if not isinstance(obj, dict):
                return False, "First line is not a JSON object"
            # Claude Code JSONL lines have 'type' or 'role' at top level
            if "type" not in obj and "role" not in obj:
                return False, "Missing 'type' or 'role' key in first line"
    except json.JSONDecodeError as e:
        return False, f"Invalid JSON on first line: {e}"
    except Exception as e:
        return False, f"Read error: {e}"

    return True, "ok"


def validate_json_file(path: Path) -> tuple[bool, str]:
    """Validate JSON file: must be parseable.

    Size is already checked by validate_received_file() via stat().
    """
    try:
        with open(path) as f:
            json.load(f)
    except json.JSONDecodeError as e:
        return False, f"Invalid JSON: {e}"
    except Exception as e:
        return False, f"Read error: {e}"

    return True, "ok"


def validate_manifest(path: Path) -> tuple[Optional[SyncManifest], str]:
    """Parse and validate a manifest.json file. Returns (manifest, reason)."""
    try:
        if path.stat().st_size > MAX_JSON_SIZE:
            return None, "Manifest too large"
        data = json.loads(path.read_text())
        manifest = SyncManifest.model_validate(data)
        return manifest, "ok"
    except json.JSONDecodeError as e:
        return None, f"Invalid JSON: {e}"
    except Exception as e:
        return None, f"Validation failed: {e}"


# ── Quarantine ───────────────────────────────────────────────────────

QUARANTINE_DIR = Path.home() / ".claude_karma" / "quarantine"


def quarantine_file(path: Path, reason: str, member_name: str = "unknown") -> Path:
    """Move a rejected file to quarantine directory.

    Returns the quarantine path.
    """
    QUARANTINE_DIR.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H%M%S")
    quarantine_name = f"{timestamp}_{member_name}_{path.name}"
    dest = QUARANTINE_DIR / quarantine_name

    try:
        shutil.move(str(path), str(dest))
        logger.warning("Quarantined %s → %s (reason: %s)", path.name, dest, reason)
    except Exception as e:
        logger.error("Failed to quarantine %s: %s", path, e)
        dest = path  # Return original path if move fails

    return dest

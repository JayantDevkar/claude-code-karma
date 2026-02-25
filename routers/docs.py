"""
Docs router - serve About page documentation markdown files.

Provides endpoints for browsing and reading documentation files
stored in docs/about/ directory at project root.

Phase 3: HTTP caching with Cache-Control headers.
"""

import logging
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request

# Add api to path
api_path = Path(__file__).parent.parent
sys.path.insert(0, str(api_path))

from config import Settings, settings
from http_caching import cacheable
from parallel import run_in_thread
from schemas import DocContent, DocItem, DocsListResponse
from utils_io import safe_read_file as _safe_read_file

logger = logging.getLogger(__name__)

router = APIRouter()

# Constants
# Allow only alphanumeric, hyphens, underscores, dots (no slashes for docs)
ALLOWED_PATH_PATTERN = re.compile(r"^[a-zA-Z0-9_.\-]+$")

# Predefined order for docs
DOC_ORDER = ["overview", "quick-start", "features", "architecture", "hooks-guide", "api-reference"]


# =============================================================================
# Dependencies
# =============================================================================


def get_settings() -> Settings:
    """
    Dependency to get application settings.

    Returns:
        Settings instance
    """
    return settings


def get_docs_dir(config: Annotated[Settings, Depends(get_settings)]) -> Path:
    """
    Dependency to get the docs directory.

    Args:
        config: Application settings (injected)

    Returns:
        Path to docs/about directory (project root)
    """
    # api/routers/docs.py -> api/ -> claude-karma/ -> docs/about/
    return Path(__file__).parent.parent.parent / "docs" / "about"


def validate_doc_path(path: str, docs_dir: Path, max_length: int = 500) -> Path:
    """
    Validate and sanitize documentation path for security.

    Args:
        path: Relative path from docs directory
        docs_dir: Base docs directory
        max_length: Maximum path length (default: 500)

    Returns:
        Resolved absolute path within docs directory

    Raises:
        HTTPException: If path is invalid or attempts directory traversal
    """
    if not path or len(path) > max_length:
        raise HTTPException(
            status_code=400, detail=f"Path must be between 1 and {max_length} characters"
        )

    # Remove leading/trailing slashes and normalize
    clean_path = path.strip("/").strip()

    if not clean_path:
        raise HTTPException(status_code=400, detail="Invalid path")

    # Basic pattern check (no slashes allowed for flat structure)
    if not ALLOWED_PATH_PATTERN.match(clean_path):
        raise HTTPException(
            status_code=400,
            detail="Path must contain only alphanumeric characters, hyphens, underscores, and dots",
        )

    # Prevent directory traversal
    if ".." in clean_path:
        raise HTTPException(status_code=400, detail="Path traversal not allowed")

    # Resolve to absolute path
    target_path = (docs_dir / clean_path).resolve()

    # Ensure the resolved path is still within docs directory
    try:
        resolved_docs_dir = docs_dir.resolve()
        target_path.relative_to(resolved_docs_dir)
    except ValueError as e:
        logger.warning(f"Path traversal attempt detected: {path}")
        raise HTTPException(status_code=400, detail="Invalid path: outside docs directory") from e

    return target_path


def safe_read_file(file_path: Path, max_size: int) -> str:
    """Read file with UTF-8 encoding (docs are always text)."""
    return _safe_read_file(file_path, max_size, binary_placeholder="(Binary content)")


def derive_title(filename: str) -> str:
    """
    Derive human-readable title from filename.

    Args:
        filename: Name of the file (e.g., 'quick-start.md')

    Returns:
        Title (e.g., 'Quick Start')
    """
    # Remove .md extension
    name = filename.rsplit(".", 1)[0] if "." in filename else filename
    # Replace hyphens and underscores with spaces
    name = name.replace("-", " ").replace("_", " ")
    # Capitalize words
    return name.title()


def get_sort_key(filename: str) -> tuple:
    """
    Get sort key for documentation files.

    Args:
        filename: Name of the file (e.g., 'overview.md')

    Returns:
        Tuple (order_index, filename) for sorting
    """
    # Remove .md extension for matching
    name = filename.rsplit(".", 1)[0] if "." in filename else filename

    # Try to find in predefined order
    try:
        order_index = DOC_ORDER.index(name)
    except ValueError:
        # Not in predefined order, put at end alphabetically
        order_index = len(DOC_ORDER)

    return (order_index, filename.lower())


@router.get("/about", response_model=DocsListResponse)
@cacheable(max_age=120, stale_while_revalidate=300, private=True)
def list_docs(
    request: Request,
    docs_dir: Annotated[Path, Depends(get_docs_dir)],
) -> DocsListResponse:
    """
    List all available markdown files in docs/about/.

    Returns files sorted by predefined order (overview, quick-start, etc.)
    with derived titles from filenames.

    Phase 3: Moderate cache (120s) - documentation changes infrequently.

    Args:
        request: FastAPI request object (for caching support)
        docs_dir: Docs directory path (injected)

    Returns:
        List of documentation file metadata sorted by predefined order
    """
    if not docs_dir.exists():
        return DocsListResponse(docs=[])

    if not docs_dir.is_dir():
        raise HTTPException(status_code=500, detail="Docs path is not a directory")

    items: list[DocItem] = []

    try:
        for entry in docs_dir.iterdir():
            # Skip hidden files and directories
            if entry.name.startswith("."):
                continue

            # Only include markdown files
            if not entry.is_file() or not entry.name.endswith(".md"):
                continue

            try:
                stat = entry.stat()
                title = derive_title(entry.name)

                items.append(
                    DocItem(
                        name=entry.name,
                        title=title,
                        path=entry.name,
                        size_bytes=stat.st_size,
                        modified_at=datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc),
                    )
                )
            except OSError as e:
                logger.warning(f"Failed to process doc file {entry}: {e}")
                continue
    except OSError as e:
        logger.error(f"Failed to list docs directory {docs_dir}: {e}")
        raise HTTPException(status_code=500, detail="Failed to list docs directory") from e

    # Sort by predefined order
    items.sort(key=lambda x: get_sort_key(x.name))

    return DocsListResponse(docs=items)


@router.get("/about/content", response_model=DocContent)
@cacheable(max_age=120, stale_while_revalidate=300, private=True)
async def get_doc_content(
    path: str,
    request: Request,
    docs_dir: Annotated[Path, Depends(get_docs_dir)],
    config: Annotated[Settings, Depends(get_settings)],
) -> DocContent:
    """
    Get content of a specific documentation file.

    Phase 3: Moderate cache (120s) - documentation content changes infrequently.
    Phase 4: Async file I/O via run_in_thread() for consistency.

    Args:
        path: Relative path to the doc file from docs/about/ (e.g., 'overview.md')
        request: FastAPI request object (for caching support)
        docs_dir: Docs directory path (injected)
        config: Application settings (injected)

    Returns:
        Documentation file content and metadata

    Raises:
        HTTPException: 400 if path is invalid, 404 if file not found
    """
    target_file = validate_doc_path(path, docs_dir)

    if not target_file.exists():
        raise HTTPException(status_code=404, detail="File not found")

    if not target_file.is_file():
        raise HTTPException(status_code=400, detail="Path is not a file")

    # Use max_skill_size from config (500KB limit)
    max_size = getattr(config, "max_doc_size", 500_000)
    content = await run_in_thread(safe_read_file, target_file, max_size)
    stat = target_file.stat()

    return DocContent(
        name=target_file.name,
        path=path,
        content=content,
        size_bytes=stat.st_size,
        modified_at=datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc),
    )

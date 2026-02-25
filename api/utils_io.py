"""
Shared file I/O utilities for safe reading, writing, and deleting files.

Used by agents and skills routers to avoid code duplication.
"""

import logging
from pathlib import Path

from fastapi import HTTPException

logger = logging.getLogger(__name__)


def safe_read_file(
    file_path: Path,
    max_size: int,
    *,
    binary_placeholder: str | None = None,
) -> str:
    """
    Safely read a file with size limits.

    Args:
        file_path: Path to file to read
        max_size: Maximum file size in bytes
        binary_placeholder: If set, return this string on UnicodeDecodeError
                           instead of raising HTTPException 400.

    Returns:
        File content as string

    Raises:
        HTTPException: If file is too large or cannot be read
    """
    try:
        size = file_path.stat().st_size
        if size > max_size:
            raise HTTPException(
                status_code=413,
                detail=f"File too large ({size} bytes). Maximum size is {max_size} bytes",
            )

        try:
            with file_path.open("r", encoding="utf-8") as f:
                return f.read()
        except UnicodeDecodeError as e:
            if binary_placeholder is not None:
                return binary_placeholder
            logger.error("Failed to decode file %s: %s", file_path, e)
            raise HTTPException(status_code=400, detail="File is not valid UTF-8 text") from e
    except HTTPException:
        raise
    except OSError as e:
        logger.error("Failed to read file %s: %s", file_path, e)
        raise HTTPException(status_code=500, detail="Failed to read file") from e


def safe_write_file(file_path: Path, content: str) -> None:
    """
    Safely write content to a file using atomic rename.

    Args:
        file_path: Path to file to write
        content: Content to write

    Raises:
        HTTPException: If write fails
    """
    try:
        file_path.parent.mkdir(parents=True, exist_ok=True)

        # Write atomically using a temp file
        temp_path = file_path.with_suffix(file_path.suffix + ".tmp")
        with temp_path.open("w", encoding="utf-8") as f:
            f.write(content)

        # Atomic rename
        temp_path.replace(file_path)
        logger.info("Successfully wrote file: %s", file_path.name)
    except OSError as e:
        logger.error("Failed to write file %s: %s", file_path, e)
        raise HTTPException(status_code=500, detail="Failed to write file") from e


def delete_file_sync(file_path: Path) -> None:
    """Synchronous helper to delete a file."""
    file_path.unlink()

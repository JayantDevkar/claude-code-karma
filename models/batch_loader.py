"""
Batch session loading utilities.

Phase 4 optimization: Load metadata from multiple sessions efficiently
by only reading first and last lines of JSONL files.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


class BatchSessionLoader:
    """
    Load multiple sessions efficiently with optimized I/O.

    Instead of parsing entire JSONL files, this loader reads only
    the first and last lines to extract timestamps and slug.
    """

    def __init__(self, session_paths: List[Path]):
        """
        Initialize the batch loader.

        Args:
            session_paths: List of paths to session JSONL files
        """
        self.paths = session_paths

    def load_all_metadata(self) -> List[Dict[str, Any]]:
        """
        Load metadata from all sessions using optimized I/O.

        Only reads first and last lines of each file instead of
        parsing the entire JSONL.

        Returns:
            List of metadata dicts with path, start_time, end_time, slug
        """
        results = []

        for path in self.paths:
            try:
                metadata = self._load_single_metadata(path)
                if metadata:
                    results.append(metadata)
            except Exception:
                continue

        return results

    def _load_single_metadata(self, path: Path) -> Optional[Dict[str, Any]]:
        """
        Load metadata from a single session file.

        Uses optimized reading of first and last lines only.

        Args:
            path: Path to session JSONL file

        Returns:
            Dict with path, start_time, end_time, slug or None on error
        """
        if not path.exists():
            return None

        try:
            first_line, last_line = self._read_first_last_lines(path)
        except Exception:
            return None

        start_time = None
        end_time = None
        slug = None

        # Parse first line for start_time and slug
        if first_line:
            try:
                data = json.loads(first_line)
                ts = data.get("timestamp")
                if ts:
                    start_time = self._parse_timestamp(ts)
                slug = data.get("slug")
            except json.JSONDecodeError:
                pass

        # Parse last line for end_time
        if last_line and last_line != first_line:
            try:
                data = json.loads(last_line)
                ts = data.get("timestamp")
                if ts:
                    end_time = self._parse_timestamp(ts)
                # Try slug from last line if not found in first
                if not slug:
                    slug = data.get("slug")
            except json.JSONDecodeError:
                pass
        elif first_line:
            end_time = start_time

        return {
            "path": path,
            "uuid": path.stem,
            "start_time": start_time,
            "end_time": end_time,
            "slug": slug,
        }

    def _read_first_last_lines(self, path: Path) -> tuple:
        """
        Efficiently read only first and last lines of a file.

        Uses seek for large files to avoid reading middle content.

        Args:
            path: Path to file

        Returns:
            Tuple of (first_line, last_line)
        """
        # Check file size
        file_size = path.stat().st_size

        if file_size == 0:
            return None, None

        if file_size < 8192:
            # Small file: read entire content
            with open(path, "r", encoding="utf-8") as f:
                lines = [line.strip() for line in f if line.strip()]
                if not lines:
                    return None, None
                return lines[0], lines[-1]

        # Large file: read first line normally, seek for last line
        with open(path, "rb") as f:
            # Read first line
            first_line_bytes = f.readline()
            first_line = first_line_bytes.decode("utf-8", errors="ignore").strip()

            # Seek to end and scan backwards for last line
            f.seek(0, 2)  # End of file
            actual_size = f.tell()

            # Read last chunk (up to 8KB)
            chunk_size = min(8192, actual_size)
            f.seek(max(0, actual_size - chunk_size))
            chunk = f.read().decode("utf-8", errors="ignore")

            # Find last non-empty line in chunk
            lines = [line.strip() for line in chunk.split("\n") if line.strip()]
            last_line = lines[-1] if lines else first_line

        return first_line, last_line

    def _parse_timestamp(self, ts: Any) -> Optional[datetime]:
        """
        Parse timestamp from various formats.

        Args:
            ts: Timestamp value (string or already datetime)

        Returns:
            datetime object or None
        """
        if ts is None:
            return None

        if isinstance(ts, datetime):
            return ts

        if isinstance(ts, str):
            try:
                # ISO format with optional timezone
                if "Z" in ts:
                    ts = ts.replace("Z", "+00:00")
                return datetime.fromisoformat(ts)
            except ValueError:
                pass

            try:
                # Try parsing without timezone
                dt = datetime.fromisoformat(ts.replace("Z", ""))
                return dt.replace(tzinfo=timezone.utc)
            except ValueError:
                pass

        return None


def load_sessions_metadata_batch(session_paths: List[Path]) -> List[Dict[str, Any]]:
    """
    Convenience function to batch load session metadata.

    Args:
        session_paths: List of session JSONL file paths

    Returns:
        List of metadata dicts
    """
    loader = BatchSessionLoader(session_paths)
    return loader.load_all_metadata()

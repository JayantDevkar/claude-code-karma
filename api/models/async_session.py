"""
Async session reader for high-throughput scenarios.

Phase 4 optimization: Non-blocking file I/O using aiofiles.
Use when processing many sessions concurrently.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, AsyncIterator, Dict, List, Optional, Set

try:
    import aiofiles

    AIOFILES_AVAILABLE = True
except ImportError:
    AIOFILES_AVAILABLE = False


class AsyncSession:
    """
    Async version of Session for high-throughput scenarios.

    Use when processing many sessions concurrently to avoid
    blocking the event loop with synchronous file I/O.
    """

    def __init__(self, jsonl_path: Path):
        """
        Initialize async session reader.

        Args:
            jsonl_path: Path to session JSONL file
        """
        if not AIOFILES_AVAILABLE:
            raise ImportError(
                "aiofiles is required for AsyncSession. Install with: pip install aiofiles"
            )
        self.jsonl_path = jsonl_path
        self.uuid = jsonl_path.stem

    async def iter_lines(self) -> AsyncIterator[str]:
        """
        Async iteration over lines in the JSONL file.

        Yields:
            Stripped non-empty lines
        """
        if not self.jsonl_path.exists():
            return

        async with aiofiles.open(self.jsonl_path, "r", encoding="utf-8") as f:
            async for line in f:
                line = line.strip()
                if line:
                    yield line

    async def iter_messages_raw(self) -> AsyncIterator[Dict[str, Any]]:
        """
        Async iteration over raw message dicts.

        Yields:
            Parsed JSON dicts from each line
        """
        async for line in self.iter_lines():
            try:
                yield json.loads(line)
            except json.JSONDecodeError:
                continue

    async def get_metadata(self) -> Dict[str, Any]:
        """
        Get all metadata in single async pass.

        Returns:
            Dict with start_time, end_time, slug, message_count
        """
        first_ts: Optional[datetime] = None
        last_ts: Optional[datetime] = None
        slug: Optional[str] = None
        message_count = 0
        models_used: Set[str] = set()

        async for data in self.iter_messages_raw():
            message_count += 1

            # Timestamp extraction
            ts_str = data.get("timestamp")
            if ts_str:
                try:
                    ts = self._parse_timestamp(ts_str)
                    if ts:
                        if first_ts is None:
                            first_ts = ts
                        last_ts = ts
                except (ValueError, TypeError):
                    pass

            # Slug (from any message)
            if not slug:
                slug = data.get("slug")

            # Model tracking (from assistant messages)
            msg_data = data.get("message", {})
            if isinstance(msg_data, dict):
                model = msg_data.get("model")
                if model:
                    models_used.add(model)

        return {
            "uuid": self.uuid,
            "start_time": first_ts,
            "end_time": last_ts,
            "slug": slug,
            "message_count": message_count,
            "models_used": list(models_used),
        }

    async def get_first_user_prompt(self) -> Optional[str]:
        """
        Get the first user prompt from the session.

        Returns:
            First user message content or None
        """
        async for data in self.iter_messages_raw():
            msg_type = data.get("type")
            if msg_type == "user":
                msg_data = data.get("message", {})
                if isinstance(msg_data, dict):
                    content = msg_data.get("content", "")
                    if isinstance(content, str) and content:
                        return content[:500]
        return None

    def _parse_timestamp(self, ts: Any) -> Optional[datetime]:
        """Parse timestamp from string."""
        if ts is None:
            return None

        if isinstance(ts, datetime):
            return ts

        if isinstance(ts, str):
            try:
                if "Z" in ts:
                    ts = ts.replace("Z", "+00:00")
                return datetime.fromisoformat(ts)
            except ValueError:
                pass

        return None


async def get_sessions_metadata_async(session_paths: List[Path]) -> List[Dict[str, Any]]:
    """
    Get metadata from multiple sessions concurrently.

    Phase 4 optimization: Uses async I/O to process all sessions
    in parallel without blocking.

    Args:
        session_paths: List of session JSONL file paths

    Returns:
        List of metadata dicts
    """
    import asyncio

    async def process_session(path: Path) -> Optional[Dict[str, Any]]:
        try:
            session = AsyncSession(path)
            return await session.get_metadata()
        except Exception:
            return None

    tasks = [process_session(p) for p in session_paths]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    # Filter out None and exceptions
    return [r for r in results if isinstance(r, dict)]


async def calculate_analytics_async(session_paths: List[Path]) -> Dict[str, Any]:
    """
    Calculate analytics using async I/O.

    Args:
        session_paths: List of session JSONL file paths

    Returns:
        Aggregated analytics dict
    """
    metadata_list = await get_sessions_metadata_async(session_paths)

    total_messages = 0
    all_models: Set[str] = set()

    for metadata in metadata_list:
        total_messages += metadata.get("message_count", 0)
        models = metadata.get("models_used", [])
        all_models.update(models)

    return {
        "total_sessions": len(metadata_list),
        "total_messages": total_messages,
        "models_used": list(all_models),
    }

"""
FastAPI lifecycle wrapper for the Cursor indexer.

Mirrors the existing Claude Code indexer pattern in `main.py` lines 64-94:
- Background thread runs the initial full scan on startup
- Asyncio task runs incremental scans on a fixed interval thereafter

If Cursor isn't installed, both are no-ops.
"""

import asyncio
import logging
import threading

from cursor.indexer import run_cursor_full_index
from cursor.paths import detect_cursor_install

logger = logging.getLogger(__name__)


def start_cursor_background_index() -> threading.Thread | None:
    """Kick off the initial full scan in a daemon thread. Returns the thread."""
    if not detect_cursor_install():
        logger.info("Cursor not detected; cursor indexer disabled")
        return None

    thread = threading.Thread(
        target=_run_initial_scan,
        name="cursor-indexer",
        daemon=True,
    )
    thread.start()
    logger.info("Cursor background indexing started")
    return thread


def _run_initial_scan() -> None:
    """Run the first full scan against the writer DB."""
    try:
        from db.connection import get_writer_db

        conn = get_writer_db()
        stats = run_cursor_full_index(conn)
        logger.info("Cursor initial scan: %s", stats)
    except Exception as e:
        logger.warning("Cursor initial scan failed: %s", e)


async def run_periodic_cursor_sync(interval_seconds: int = 60) -> None:
    """Re-scan Cursor data every N seconds. Mirrors run_periodic_sync()."""
    if not detect_cursor_install():
        return

    from cursor.indexer import is_cursor_index_ready

    # Wait for the initial scan to complete before starting the periodic loop
    while not is_cursor_index_ready():
        await asyncio.sleep(1)

    logger.info("Cursor periodic reindex started (interval=%ds)", interval_seconds)

    while True:
        await asyncio.sleep(interval_seconds)
        try:
            from db.connection import get_writer_db

            conn = get_writer_db()
            stats = await asyncio.to_thread(run_cursor_full_index, conn)
            logger.debug("Cursor periodic reindex: %s", stats)
        except Exception as e:
            logger.warning("Cursor periodic reindex failed: %s", e)

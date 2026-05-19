"""
Background task that periodically removes orphan session_tickets rows.

An orphan is a link whose `session_uuid` never appears in the sessions
index — for example, the branch-detect hook fired at SessionStart for a
session that was killed before its JSONL was written.

Loop interval defaults to 6 hours; TTL before deletion defaults to 7 days
(both match the spec). Uses the same FastAPI lifespan + asyncio.create_task
pattern as session_reconciler.
"""

from __future__ import annotations

import asyncio
import logging

logger = logging.getLogger(__name__)

_DEFAULT_INTERVAL_SECONDS = 6 * 60 * 60  # 6 hours
_DEFAULT_TTL_DAYS = 7


async def run_ticket_orphan_cleanup(
    interval_seconds: int = _DEFAULT_INTERVAL_SECONDS,
    ttl_days: int = _DEFAULT_TTL_DAYS,
) -> None:
    """Long-running coroutine: sleep, sweep, repeat.

    Cancellable via task.cancel() from the lifespan shutdown hook.
    """
    logger.info(
        "Ticket orphan cleanup loop starting (interval=%ds, ttl=%d days)",
        interval_seconds,
        ttl_days,
    )
    while True:
        try:
            await asyncio.sleep(interval_seconds)
        except asyncio.CancelledError:
            logger.info("Ticket orphan cleanup loop cancelled")
            raise

        try:
            await asyncio.to_thread(_run_one_sweep, ttl_days)
        except Exception as e:  # never let the loop die
            logger.warning("Ticket orphan cleanup sweep failed: %s", e)


def _run_one_sweep(ttl_days: int) -> None:
    """Sync helper executed in a worker thread to avoid blocking the loop.

    Imported lazily so module-level import order doesn't drag the DB
    into hook-side use of this file (none today, but defensive).
    """
    from db.connection import get_writer_db
    from db.ticket_queries import cleanup_orphan_session_tickets

    conn = get_writer_db()
    try:
        removed = cleanup_orphan_session_tickets(conn, ttl_days=ttl_days)
        conn.commit()
    except Exception:
        conn.rollback()
        raise

    if removed:
        logger.info("Ticket orphan cleanup removed %d row(s)", removed)
    else:
        logger.debug("Ticket orphan cleanup: nothing to remove")

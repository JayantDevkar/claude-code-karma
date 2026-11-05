"""Store a session title in the title cache and SQLite."""

from __future__ import annotations

import json
import logging
import sqlite3
from typing import Optional

from config import settings
from services.session_title_cache import title_cache

logger = logging.getLogger(__name__)


def store_session_title(
    encoded_name: str,
    uuid: str,
    title: str,
    conn: Optional[sqlite3.Connection] = None,
) -> None:
    """Prepend a title to a session's titles in the cache and, if enabled, SQLite."""
    title_cache.set_title(encoded_name, uuid, title)

    if not settings.use_sqlite:
        return
    try:
        if conn is None:
            from db.connection import get_writer_db

            conn = get_writer_db()
        # Get existing titles, prepend new one
        row = conn.execute("SELECT session_titles FROM sessions WHERE uuid = ?", (uuid,)).fetchone()

        if row:
            existing_titles = []
            if row["session_titles"]:
                try:
                    existing_titles = json.loads(row["session_titles"])
                except json.JSONDecodeError:
                    pass

            # Prepend new title if not already present
            if title not in existing_titles:
                new_titles = [title] + existing_titles
            else:
                new_titles = existing_titles

            conn.execute(
                "UPDATE sessions SET session_titles = ? WHERE uuid = ?",
                (json.dumps(new_titles), uuid),
            )
            conn.commit()
    except Exception as e:
        # Don't fail the caller if the SQLite update fails
        logger.warning("Failed to update SQLite for session %s: %s", uuid, e)

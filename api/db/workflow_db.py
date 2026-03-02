"""
SQLite connection management for workflow.db.

Mirrors the reader/writer pattern from connection.py but for the
separate workflow database. Single writer connection, per-request readers.
"""

import logging
import sqlite3
import threading
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# Writer singleton state
_wf_writer: Optional[sqlite3.Connection] = None
_wf_writer_lock = threading.Lock()


def get_workflow_db_path() -> Path:
    """Get the workflow database file path."""
    from config import settings

    return settings.workflow_db_path


def get_wf_writer() -> sqlite3.Connection:
    """
    Get or create the singleton writer connection for workflow.db.

    Initializes schema and runs migration from metadata.db on first call.
    """
    global _wf_writer

    if _wf_writer is not None:
        return _wf_writer

    with _wf_writer_lock:
        if _wf_writer is not None:
            return _wf_writer

        db_path = get_workflow_db_path()
        db_path.parent.mkdir(parents=True, exist_ok=True)

        logger.info("Opening workflow DB writer connection at %s", db_path)

        conn = sqlite3.connect(
            str(db_path),
            check_same_thread=False,
            timeout=10.0,
        )
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("PRAGMA busy_timeout=5000")

        from .workflow_schema import ensure_workflow_schema, migrate_from_metadata_db

        ensure_workflow_schema(conn)
        migrate_from_metadata_db(conn)

        _wf_writer = conn
        logger.info("Workflow DB writer connection ready")
        return _wf_writer


def create_wf_read_conn() -> sqlite3.Connection:
    """
    Create a new read-only connection for workflow.db.

    Caller is responsible for closing the connection.
    """
    db_path = get_workflow_db_path()

    conn = sqlite3.connect(
        f"file:{db_path}?mode=ro",
        uri=True,
        timeout=5.0,
    )
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout=5000")
    return conn


def close_wf_db() -> None:
    """Close the singleton writer. Called during app shutdown."""
    global _wf_writer

    with _wf_writer_lock:
        if _wf_writer is not None:
            logger.info("Closing workflow DB writer connection")
            _wf_writer.close()
            _wf_writer = None

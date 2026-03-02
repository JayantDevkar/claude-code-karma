"""
SQLite connection management — Reader/Writer separation.

Writer: Singleton connection used exclusively by the background indexer thread.
Reader: Per-request connections via create_read_connection() for FastAPI handlers.

This separation enables true concurrent reads during writes under WAL mode,
instead of serializing all access through a single shared connection.
"""

import logging
import sqlite3
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Generator, Optional

logger = logging.getLogger(__name__)

# Writer singleton state
_writer: Optional[sqlite3.Connection] = None
_writer_lock = threading.Lock()


def get_db_path() -> Path:
    """Get the SQLite database file path."""
    from config import settings

    return settings.sqlite_db_path


def _apply_pragmas(conn: sqlite3.Connection, *, readonly: bool = False) -> None:
    """Apply performance pragmas to a connection."""
    if not readonly:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA cache_size=-64000")  # 64MB cache
    conn.execute("PRAGMA mmap_size=268435456")  # 256MB mmap
    if not readonly:
        conn.execute("PRAGMA journal_size_limit=67108864")  # 64MB WAL limit
    conn.execute("PRAGMA busy_timeout=5000")


def get_writer_db() -> sqlite3.Connection:
    """
    Get or create the singleton writer connection.

    Used exclusively by the background indexer thread.
    Creates the database file and schema on first call.
    """
    global _writer

    if _writer is not None:
        return _writer

    with _writer_lock:
        # Double-check after acquiring lock
        if _writer is not None:
            return _writer

        db_path = get_db_path()
        db_path.parent.mkdir(parents=True, exist_ok=True)

        logger.info("Opening SQLite writer connection at %s", db_path)

        conn = sqlite3.connect(
            str(db_path),
            check_same_thread=False,
            timeout=10.0,
        )
        conn.row_factory = sqlite3.Row

        _apply_pragmas(conn, readonly=False)

        # Create schema
        from .schema import ensure_schema

        ensure_schema(conn)

        _writer = conn
        logger.info("SQLite writer connection ready (WAL mode)")
        return _writer


def create_read_connection() -> sqlite3.Connection:
    """
    Create a new read-only connection for request handling.

    Each request gets its own connection, enabling true concurrent
    reads under WAL mode while the indexer writes. Caller is
    responsible for closing the connection.

    Raises sqlite3.OperationalError if the database file doesn't exist.
    """
    db_path = get_db_path()

    conn = sqlite3.connect(
        f"file:{db_path}?mode=ro",
        uri=True,
        timeout=5.0,
    )
    conn.row_factory = sqlite3.Row
    _apply_pragmas(conn, readonly=True)
    return conn


def get_read_db() -> Generator[Optional[sqlite3.Connection], None, None]:
    """
    FastAPI dependency that yields a request-scoped read connection.

    Yields None if SQLite is disabled or not ready (triggers JSONL fallback).
    Auto-closes the connection when the request completes.

    Usage:
        @router.get("/endpoint")
        def handler(db: sqlite3.Connection | None = Depends(get_read_db)):
            if db is not None:
                ...

    Note: Most routers currently use the manual pattern (create_read_connection()
    + try/finally) but this dependency is available for new endpoints.
    """
    from config import settings

    from .indexer import is_db_ready

    if not settings.use_sqlite or not is_db_ready():
        yield None
        return

    try:
        conn = create_read_connection()
    except Exception:
        yield None
        return

    try:
        yield conn
    finally:
        conn.close()


@contextmanager
def sqlite_read() -> Generator[Optional[sqlite3.Connection], None, None]:
    """
    Context manager that yields a read connection if SQLite is enabled and ready.

    Yields None if SQLite is disabled or the index isn't built yet,
    letting callers fall back to JSONL. Auto-closes the connection on exit.

    Usage:
        with sqlite_read() as conn:
            if conn is not None:
                # SQLite fast path
                ...
        # JSONL fallback if conn was None
    """
    from config import settings

    from .indexer import is_db_ready

    if not settings.use_sqlite or not is_db_ready():
        yield None
        return

    conn = create_read_connection()
    try:
        yield conn
    finally:
        conn.close()


def close_db() -> None:
    """Close the writer connection. Called during app shutdown."""
    global _writer

    with _writer_lock:
        if _writer is not None:
            logger.info("Closing SQLite writer connection")
            _writer.close()
            _writer = None

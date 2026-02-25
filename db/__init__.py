"""
SQLite metadata index for Claude Karma.

Provides a derived metadata layer over JSONL session files,
enabling fast queries, filtering, pagination, and full-text search
without parsing JSONL on every request.

The JSONL files remain the source of truth. SQLite is a rebuildable cache.
"""

from .connection import close_db, create_read_connection, get_read_db, get_writer_db
from .indexer import is_db_ready, run_periodic_sync, sync_all_projects, sync_project

__all__ = [
    "get_writer_db",
    "get_read_db",
    "create_read_connection",
    "close_db",
    "sync_all_projects",
    "sync_project",
    "is_db_ready",
    "run_periodic_sync",
]

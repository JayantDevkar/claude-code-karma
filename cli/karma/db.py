"""SQLite connection helper for CLI direct DB access."""

import sqlite3
from pathlib import Path

DB_PATH = Path.home() / ".claude_karma" / "metadata.db"


def get_connection() -> sqlite3.Connection:
    """Open a connection to the shared metadata.db."""
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    return conn

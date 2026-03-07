"""SQLite connection helper for CLI direct DB access."""

import sqlite3
import sys
from pathlib import Path

DB_PATH = Path.home() / ".claude_karma" / "metadata.db"

# Add API to path for schema module
_API_PATH = Path(__file__).parent.parent.parent / "api"
if str(_API_PATH) not in sys.path:
    sys.path.insert(0, str(_API_PATH))


def get_connection() -> sqlite3.Connection:
    """Open a connection to the shared metadata.db, ensuring schema."""
    from db.schema import ensure_schema

    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    ensure_schema(conn)
    return conn

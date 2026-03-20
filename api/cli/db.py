"""Read-only SQLite connection for CLI queries."""
import sqlite3
from pathlib import Path

DB_PATH = Path.home() / ".claude_karma" / "metadata.db"


def get_read_connection(db_path: Path | None = None) -> sqlite3.Connection:
    """Open a read-only connection to the Karma metadata database.

    Raises FileNotFoundError if the database file does not exist.
    """
    path = db_path or DB_PATH
    if not path.exists():
        raise FileNotFoundError(
            f"Karma database not found at {path}. "
            "Make sure the API has been started at least once to create the index."
        )

    conn = sqlite3.connect(
        f"file:{path}?mode=ro",
        uri=True,
        timeout=5.0,
    )
    conn.row_factory = sqlite3.Row
    return conn

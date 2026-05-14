"""
WAL-safe, read-only SQLite helpers for Cursor's state.vscdb.

Cursor's master database is **actively written** by the running IDE.
We open with `?mode=ro&immutable=1` which:
  - Forces read-only (no risk of corrupting Cursor's data)
  - Bypasses WAL entirely (no lock contention with the live app)
  - Returns a consistent snapshot of pre-WAL committed state

Trade-off: missed writes go into WAL and are invisible until Cursor's next
checkpoint (~30s under typical usage). Acceptable for our polling indexer.
"""

import sqlite3
from pathlib import Path


def open_state_db_readonly(path: Path) -> sqlite3.Connection:
    """Open a Cursor state.vscdb in read-only WAL-bypass mode."""
    if not path.is_file():
        raise FileNotFoundError(f"Cursor state DB not found: {path}")
    uri = f"file:{path}?mode=ro&immutable=1"
    conn = sqlite3.connect(uri, uri=True, timeout=5.0)
    conn.row_factory = sqlite3.Row
    return conn


def read_kv_value(conn: sqlite3.Connection, key: str) -> str | None:
    """Fetch a single value from cursorDiskKV by exact key. Returns text."""
    row = conn.execute(
        "SELECT value FROM cursorDiskKV WHERE key = ?", (key,)
    ).fetchone()
    if not row:
        return None
    val = row["value"]
    if isinstance(val, bytes):
        try:
            return val.decode("utf-8")
        except UnicodeDecodeError:
            return None
    return val


def iter_kv_keys(conn: sqlite3.Connection, prefix: str):
    """Iterate keys matching a prefix (e.g. 'composerData:')."""
    cursor = conn.execute(
        "SELECT key FROM cursorDiskKV WHERE key LIKE ? || '%'", (prefix,)
    )
    for row in cursor:
        yield row["key"]


def read_item_table(conn: sqlite3.Connection, key: str) -> str | None:
    """Fetch a single value from the per-workspace ItemTable."""
    row = conn.execute(
        "SELECT value FROM ItemTable WHERE key = ?", (key,)
    ).fetchone()
    if not row:
        return None
    val = row["value"]
    if isinstance(val, bytes):
        try:
            return val.decode("utf-8")
        except UnicodeDecodeError:
            return None
    return val

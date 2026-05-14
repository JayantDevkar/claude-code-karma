"""
Cursor IDE session ingestion package.

Parses Cursor 2.x's local storage (`~/Library/Application Support/Cursor/User/
globalStorage/state.vscdb` plus per-project files in `~/.cursor/`) and
materializes sessions, bubbles, tool calls, plans, and MCP descriptors into
claude-karma's existing SQLite metadata.db.

Auto-detected: if `state.vscdb` exists at the expected platform path, the
indexer runs. Otherwise it's a no-op. See `paths.detect_cursor_install()`.

Public re-exports for callers that don't want to import deeply:
"""

from cursor.paths import detect_cursor_install, cursor_global_db_path

__all__ = ["detect_cursor_install", "cursor_global_db_path"]

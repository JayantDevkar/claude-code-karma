"""
Scan Cursor's per-workspace state directories.

`~/Library/Application Support/Cursor/User/workspaceStorage/<16-hex-hash>/`
holds one dir per workspace ever opened. The `workspace.json` file inside
maps the hash to a `file://...` URI — the canonical workspace → real path
lookup. Per-workspace `state.vscdb` carries the composer ID list for that
workspace.
"""

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

from cursor.paths import cursor_workspace_storage_dir
from cursor.state_db import open_state_db_readonly, read_item_table

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class CursorWorkspace:
    workspace_hash: str
    folder_uri: str | None
    real_path: str | None


def _decode_folder_uri(folder_uri: str | None) -> str | None:
    """Convert 'file:///Users/me/repo' to '/Users/me/repo'."""
    if not folder_uri:
        return None
    if folder_uri.startswith("file://"):
        from urllib.parse import unquote

        return unquote(folder_uri[len("file://") :])
    return folder_uri


def iter_workspaces() -> Iterator[CursorWorkspace]:
    """Yield every Cursor workspace registered on this machine."""
    root = cursor_workspace_storage_dir()
    if not root.is_dir():
        return
    for ws_dir in root.iterdir():
        if not ws_dir.is_dir():
            continue
        # Workspace hashes are hex; skip anything else
        if len(ws_dir.name) < 8 or not all(
            c in "0123456789abcdef" for c in ws_dir.name
        ):
            continue
        folder_uri = None
        wj = ws_dir / "workspace.json"
        if wj.is_file():
            try:
                data = json.loads(wj.read_text(encoding="utf-8"))
                folder_uri = data.get("folder")
            except (json.JSONDecodeError, OSError, UnicodeDecodeError) as e:
                logger.debug("Skipping malformed workspace.json at %s: %s", wj, e)
        yield CursorWorkspace(
            workspace_hash=ws_dir.name,
            folder_uri=folder_uri,
            real_path=_decode_folder_uri(folder_uri),
        )


def list_composer_ids_for_workspace(workspace_hash: str) -> list[str]:
    """
    Read the per-workspace state.vscdb and return its composer ID list.

    Returns [] if the workspace dir has no state.vscdb or the composer
    metadata is missing/malformed (drafts, never-used workspaces, etc.).
    """
    import sqlite3

    state_db = cursor_workspace_storage_dir() / workspace_hash / "state.vscdb"
    if not state_db.is_file():
        return []
    try:
        conn = open_state_db_readonly(state_db)
    except (FileNotFoundError, sqlite3.Error):
        return []
    try:
        raw = read_item_table(conn, "composer.composerData")
        if not raw:
            return []
        data = json.loads(raw)
        composers = data.get("allComposers", []) or []
        return [c.get("composerId") for c in composers if c.get("composerId")]
    except (json.JSONDecodeError, sqlite3.Error) as e:
        logger.debug(
            "Could not read composer list for workspace %s: %s", workspace_hash, e
        )
        return []
    finally:
        conn.close()

"""
Walk Cursor's per-project MCP descriptor tree.

Layout (one entry per project ever opened in Cursor):
    ~/.cursor/projects/<encoded>/mcps/<server>/SERVER_METADATA.json
    ~/.cursor/projects/<encoded>/mcps/<server>/tools/<tool_name>.json

The `<encoded>` directory name does NOT round-trip back to a real path
(lossy on Windows; see research doc §3). We surface the workspace_hash
from `workspace.json` instead, which is the canonical workspace identity.
"""

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

from cursor.paths import cursor_projects_dir

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class CursorMcpServer:
    server_identifier: str
    workspace_hash: str
    server_name: str | None
    source: str | None
    file_path: str


@dataclass(frozen=True)
class CursorMcpTool:
    server_identifier: str
    workspace_hash: str
    tool_name: str
    description: str | None
    arguments_json: str | None
    file_path: str


def iter_mcp_descriptors_for_workspace(
    workspace_hash: str, real_path: str | None
) -> tuple[list[CursorMcpServer], list[CursorMcpTool]]:
    """
    Find the `~/.cursor/projects/<encoded>/mcps/` dir for this workspace.

    We try the workspace's real_path encoded via Cursor's convention
    (`Users-...`) and also fall back to scanning the projects dir for any
    entry whose decoded name matches the real_path. Returns empty lists
    if no MCPs are declared.
    """
    project_dir = _resolve_cursor_project_dir(real_path)
    if project_dir is None:
        return [], []
    mcps_dir = project_dir / "mcps"
    if not mcps_dir.is_dir():
        return [], []

    servers: list[CursorMcpServer] = []
    tools: list[CursorMcpTool] = []

    for server_dir in mcps_dir.iterdir():
        if not server_dir.is_dir():
            continue
        meta_path = server_dir / "SERVER_METADATA.json"
        server_identifier = server_dir.name
        server_name = None
        if meta_path.is_file():
            try:
                data = json.loads(meta_path.read_text(encoding="utf-8"))
                server_identifier = data.get("serverIdentifier") or server_identifier
                server_name = data.get("serverName")
            except (json.JSONDecodeError, OSError, UnicodeDecodeError) as e:
                logger.debug("Malformed SERVER_METADATA.json at %s: %s", meta_path, e)

        servers.append(
            CursorMcpServer(
                server_identifier=server_identifier,
                workspace_hash=workspace_hash,
                server_name=server_name,
                source=_classify_server_source(server_identifier),
                file_path=str(meta_path),
            )
        )

        tools_dir = server_dir / "tools"
        if not tools_dir.is_dir():
            continue
        for tool_path in tools_dir.iterdir():
            if not tool_path.is_file() or not tool_path.name.endswith(".json"):
                continue
            try:
                td = json.loads(tool_path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError, UnicodeDecodeError) as e:
                logger.debug("Malformed tool descriptor at %s: %s", tool_path, e)
                continue
            tool_name = td.get("name") or tool_path.stem
            args = td.get("arguments")
            args_json = json.dumps(args) if isinstance(args, dict) else None
            tools.append(
                CursorMcpTool(
                    server_identifier=server_identifier,
                    workspace_hash=workspace_hash,
                    tool_name=tool_name,
                    description=td.get("description"),
                    arguments_json=args_json,
                    file_path=str(tool_path),
                )
            )

    return servers, tools


def _resolve_cursor_project_dir(real_path: str | None) -> Path | None:
    """
    Cursor's per-project dir is `~/.cursor/projects/<encoded>/`, where
    <encoded> = real_path with leading '/' dropped and '/' replaced by '-'.

    Lossy on names containing real '-'; falls back to scanning all
    project dirs and returning any whose mcps/ subdir is non-empty.
    """
    if not real_path:
        return None
    encoded = real_path.lstrip("/").replace("/", "-").replace("\\", "-")
    candidate = cursor_projects_dir() / encoded
    if candidate.is_dir():
        return candidate
    # Best-effort scan: many users have empty project dirs and the encoding
    # collision rate is low, so return None rather than guessing wrong.
    return None


def _classify_server_source(identifier: str) -> str:
    """Heuristic: 'plugin' / 'user' / 'builtin' based on common prefixes."""
    if identifier.startswith("plugin-"):
        return "plugin"
    if identifier.startswith("user-"):
        return "user"
    if identifier.startswith("cursor-"):
        return "builtin"
    return "user"

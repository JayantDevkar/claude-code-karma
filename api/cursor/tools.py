"""
Tool-call extraction from Cursor bubbles.

Per POC validation (Cursor 2.5.26): tool calls live at `bubble.toolFormerData`,
NOT in `bubble.capabilities[]`. The `tool` field is an integer; use the
sibling `name` field for the human-readable tool name. MCP tools are
re-prefixed as `mcp__{server}__{tool}` during indexing so claude-karma's
existing MCP aggregation queries work unchanged.
"""

import json
from typing import Optional

# tool int → canonical name registry built from POC scan of 31,829 tool calls
# across 1,334 composers on Cursor 2.5.26. Unknown ints fall back to the
# bubble's own `name` field, then to `tool_<int>`.
TOOL_INT_NAME_REGISTRY: dict[int, str | None] = {
    3: "codebase_search",
    5: "read_file",            # older shape
    7: None,                   # older edit family — use bubble's name field
    9: None,                   # older grep family — use bubble's name field
    15: "run_terminal_command_v2",
    19: None,                  # MCP — server/tool name in rawArgs
    30: "read_multiple_files",
    35: "todo_write",
    38: None,                  # newer edit family — use bubble's name field
    39: "list_dir",
    40: "read_file_v2",
    41: None,                  # grep family — use bubble's name field
    42: "glob_file_search",
    43: "plan_tool",
}

# Tool names recognized as file operations (for /sessions/{uuid}/file-activity).
FILE_OP_TOOLS_CURSOR: set[str] = {
    "read_file_v2",
    "read_file",
    "read_multiple_files",
    "edit_file",
    "write_file",
    "create_file",
    "search_replace",
    "list_dir",
    "glob_file_search",
    "grep_search",
    "delete_file",
}

# Path-key candidates by tool name. Order matters: first hit wins.
PATH_ARG_KEYS = (
    "path",
    "file_path",
    "target_file",
    "targetFile",
    "relative_workspace_path",
)


def resolve_tool_name(bubble: dict) -> Optional[str]:
    """Return the human-readable tool name from a bubble, or None if no tool call."""
    tfd = bubble.get("toolFormerData")
    if not isinstance(tfd, dict):
        return None
    explicit = tfd.get("name")
    if explicit:
        return str(explicit)
    tool_int = tfd.get("tool")
    if isinstance(tool_int, int):
        mapped = TOOL_INT_NAME_REGISTRY.get(tool_int)
        if mapped:
            return mapped
        return f"tool_{tool_int}"
    return None


def is_mcp_tool_call(bubble: dict) -> bool:
    """True if this bubble's tool call is an MCP invocation."""
    tfd = bubble.get("toolFormerData") or {}
    return tfd.get("tool") == 19


def extract_mcp_server_name(bubble: dict) -> Optional[str]:
    """Pull the MCP server identifier from rawArgs (best-effort)."""
    tfd = bubble.get("toolFormerData") or {}
    raw_args = tfd.get("rawArgs")
    if not raw_args:
        return None
    try:
        args = json.loads(raw_args) if isinstance(raw_args, str) else raw_args
    except (json.JSONDecodeError, TypeError):
        return None
    if not isinstance(args, dict):
        return None
    return (
        args.get("serverName")
        or args.get("server")
        or args.get("providerIdentifier")
        or None
    )


def extract_tool_call_row(
    composer_id: str, bubble_id: str, bubble: dict
) -> dict | None:
    """
    Build a cursor_tool_call row from a bubble, or None if no tool call.

    Re-prefixes MCP tool names as `mcp__{server}__{tool}` so they aggregate
    with claude-karma's existing MCP analytics.
    """
    tfd = bubble.get("toolFormerData")
    if not isinstance(tfd, dict):
        return None

    tool_name = resolve_tool_name(bubble)
    if not tool_name:
        return None

    if is_mcp_tool_call(bubble):
        server = extract_mcp_server_name(bubble) or "unknown"
        tool_name = f"mcp__{server}__{tool_name}"

    raw_args = tfd.get("rawArgs")
    result = tfd.get("result")
    args_json = raw_args if isinstance(raw_args, str) else (
        json.dumps(raw_args) if raw_args is not None else None
    )
    result_text = result if isinstance(result, str) else (
        json.dumps(result) if result is not None else None
    )
    file_path = extract_file_path(tool_name, args_json) if args_json else None

    return {
        "session_uuid": composer_id,
        "bubble_id": bubble_id,
        "tool_call_id": tfd.get("toolCallId"),
        "tool_name": tool_name,
        "tool_int": tfd.get("tool"),
        "status": tfd.get("status"),
        "args_json": args_json,
        "result_text": result_text,
        "file_path": file_path,
        "created_at_ms": None,
    }


def extract_file_path(tool_name: str, args_json: str) -> Optional[str]:
    """Extract a file path from a tool call's rawArgs JSON, if applicable."""
    if not args_json:
        return None
    try:
        args = json.loads(args_json)
    except (json.JSONDecodeError, TypeError):
        return None
    if not isinstance(args, dict):
        return None
    for key in PATH_ARG_KEYS:
        val = args.get(key)
        if isinstance(val, str) and val.strip():
            return val
    return None

"""
Utility functions for API routers.

Consolidated from:
- services/session_utils.py (get_initial_prompt)
- services/tool_results.py (tool result parsing)
- services/tool_summary.py (tool summarization)
- services/projects.py (project listing)
"""

import ast
import hashlib
import re
import subprocess
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Iterator, Optional, Protocol

if TYPE_CHECKING:
    from models.session import Session


def resolve_git_root(path: str) -> Optional[str]:
    """Find the git repository root for a path.

    For submodules, returns the parent (superproject) root.
    Returns None if not in a git repo.
    """
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--show-superproject-working-tree"],
            cwd=path,
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()

        result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            cwd=path,
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        if result.returncode == 0:
            return result.stdout.strip()
        return None
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError, PermissionError):
        return None


def compute_project_slug(encoded_name: str, project_path: str) -> str:
    """Compute a URL-friendly project slug: lowercased name + 4-char md5 hash."""
    name = Path(project_path).name.lower() if project_path else encoded_name.lower()
    name = re.sub(r"[^a-z0-9-]", "-", name).strip("-")
    name = re.sub(r"-+", "-", name)
    short_hash = hashlib.md5(encoded_name.encode()).hexdigest()[:4]
    return f"{name}-{short_hash}"


def parse_timestamp_range(
    start_ts: Optional[int],
    end_ts: Optional[int],
) -> tuple[Optional[datetime], Optional[datetime]]:
    """
    Parse Unix timestamps (milliseconds) to UTC datetime objects.

    This is a simple, timezone-agnostic approach that eliminates all
    timezone conversion complexity. The frontend sends absolute timestamps
    which are parsed directly to UTC datetimes.

    Args:
        start_ts: Start timestamp in milliseconds since epoch
        end_ts: End timestamp in milliseconds since epoch

    Returns:
        Tuple of (start_datetime, end_datetime) in UTC timezone

    Example:
        - Input: start_ts=1736899200000 (2026-01-15T00:00:00Z)
        - Output: start_dt = datetime(2026, 1, 15, 0, 0, 0, tzinfo=timezone.utc)
    """
    start_dt = None
    if start_ts is not None:
        start_dt = datetime.fromtimestamp(start_ts / 1000, tz=timezone.utc)

    end_dt = None
    if end_ts is not None:
        end_dt = datetime.fromtimestamp(end_ts / 1000, tz=timezone.utc)

    return start_dt, end_dt


def normalize_key(text: str) -> str:
    """
    Normalize text for matching: lowercase, strip, collapse whitespace.

    Used for fuzzy matching of task descriptions to subagent types.
    """
    return " ".join(text.lower().strip().split())


def normalize_timezone(dt: Optional[datetime]) -> datetime:
    """
    Normalize a datetime to be timezone-aware (UTC).

    Useful for sorting and comparing datetimes that may or may not have
    timezone info.

    IMPORTANT: Naive datetimes are assumed to be in LOCAL time and are
    converted to UTC. This fixes the timezone mismatch bug where the API
    stores local time but the frontend sends UTC.

    Args:
        dt: A datetime that may be None or timezone-naive

    Returns:
        A timezone-aware datetime (UTC). Returns datetime.min with UTC
        timezone if dt is None.
    """
    if dt is None:
        return datetime.min.replace(tzinfo=timezone.utc)
    if dt.tzinfo is None:
        # Naive datetime is assumed to be LOCAL time - convert to UTC properly
        # Using astimezone() first adds local timezone, then converts to UTC
        return dt.astimezone(timezone.utc)
    # Already timezone-aware - convert to UTC for consistent comparison
    return dt.astimezone(timezone.utc)


# =============================================================================
# File Operation utilities (consolidated from collectors.py and conversation_endpoints.py)
# =============================================================================


@dataclass
class FileOperation:
    """Represents a file read/write operation extracted from tool calls."""

    path: str
    tool_name: str
    operation: str  # "read", "write", "edit", "delete", "search"
    timestamp: datetime
    actor: str  # "session" or agent_id
    actor_type: str  # "session" or "subagent"


def extract_file_operation(
    tool_name: str,
    tool_input: dict,
    timestamp: datetime,
    actor: str,
    actor_type: str,
    file_tool_mappings: dict,
) -> Optional[FileOperation]:
    """
    Extract file operation from tool use data if applicable.

    This is the canonical implementation used by both collectors.py
    and conversation_endpoints.py.

    Args:
        tool_name: Name of the tool (e.g., "Read", "Write")
        tool_input: Tool input dictionary
        timestamp: When the tool was called
        actor: Who called the tool ("session" or agent_id)
        actor_type: Type of actor ("session" or "subagent")
        file_tool_mappings: Mapping of tool names to (operation, path_field) tuples

    Returns:
        FileOperation if this is a file tool, None otherwise
    """
    if tool_name not in file_tool_mappings:
        return None

    operation, path_field = file_tool_mappings[tool_name]

    # Extract path from input
    path_value = tool_input.get(path_field)

    # Fallback for older/different tool versions
    if path_value is None and path_field == "file_path":
        path_value = tool_input.get("path")

    if path_value is None:
        return None

    # Handle list of paths (e.g., SemanticSearch target_directories)
    if isinstance(path_value, list):
        path_value = path_value[0] if path_value else None

    if not path_value:
        return None

    return FileOperation(
        path=str(path_value),
        tool_name=tool_name,
        operation=operation,
        timestamp=timestamp,
        actor=actor,
        actor_type=actor_type,
    )


# =============================================================================
# Session utilities (from services/session_utils.py)
# =============================================================================


def extract_prompt_from_content(content: str) -> str:
    """
    Extract the actual user prompt from command-wrapped content.

    Claude Code's skill invocations wrap user prompts in command tags like:
    <command-message>oh-my-claudecode:analyze</command-message>
    <command-name>/oh-my-claudecode:analyze</command-name>
    <command-args>actual user prompt here</command-args>

    This function extracts the content from <command-args> if present,
    otherwise returns the original content. Handles truncated content from
    sessions-index.json by extracting content after opening tag even if
    closing tag is missing.

    Args:
        content: Raw message content that may contain command tags

    Returns:
        Extracted prompt from <command-args>, or original content if no command tags
    """
    if not content:
        return content

    # Check if content starts with command tags (skill invocation)
    is_command_wrapped = (
        content.startswith("<command-message>") or "<command-name>" in content[:100]
    )

    # If no command-args tag at all, return original or empty for command-wrapped
    if "<command-args>" not in content:
        # If it looks like command-wrapped but no args tag, it's truncated before args
        return "" if is_command_wrapped else content

    # Try to extract content between <command-args>...</command-args>
    # Use DOTALL to handle multiline content
    match = re.search(r"<command-args>(.*?)</command-args>", content, re.DOTALL)

    if match:
        # Extract and clean up the prompt
        extracted = match.group(1).strip()
        return extracted if extracted else ""

    # Has <command-args> but no closing tag - truncated in index
    # Extract everything AFTER the opening tag
    opening_tag = "<command-args>"
    tag_index = content.find(opening_tag)

    if tag_index != -1:
        # Extract content after opening tag
        extracted = content[tag_index + len(opening_tag) :].strip()

        # Strip common truncation markers
        for marker in ["…", "...", "…</command-args"]:
            if extracted.endswith(marker):
                extracted = extracted[: -len(marker)].rstrip()

        return extracted if extracted else ""

    # Edge case: shouldn't reach here, but return empty for safety
    return ""


def get_initial_prompt(session: "Session", max_length: Optional[int] = None) -> Optional[str]:
    """
    Extract the initial user prompt from a session.

    Handles both regular user messages and command-wrapped messages
    (e.g., skill invocations that wrap prompts in <command-args> tags).

    Args:
        session: The session to extract the prompt from
        max_length: Maximum length of the returned prompt.
                   If None, returns the full prompt without truncation.

    Returns:
        The initial prompt (potentially truncated), or None if no user messages exist
    """
    for msg in session.iter_user_messages():
        if msg.content:
            # Extract actual prompt from command-wrapped content
            prompt = extract_prompt_from_content(msg.content)

            if max_length is not None:
                return prompt[:max_length]
            return prompt

    # Fallback: check queue-operation messages for plan-mode sessions
    from models.message import QueueOperationMessage

    for msg in session.iter_messages():
        if isinstance(msg, QueueOperationMessage) and msg.operation == "enqueue" and msg.content:
            prompt = msg.content
            if max_length is not None:
                return prompt[:max_length]
            return prompt

    return None


def get_initial_prompt_from_index(
    first_prompt: Optional[str], max_length: int = 500
) -> Optional[str]:
    """
    Extract initial prompt from session index entry's first_prompt field.

    This is a lightweight version of get_initial_prompt() for use with
    session index entries (from sessions-index.json) that don't require
    full session loading.

    Handles:
    - "No prompt" placeholder → None
    - Command-wrapped content (e.g., skill invocations) → extracts from <command-args>
    - Truncated command content (missing closing tag or empty args) → None
    - Regular prompts → truncated to max_length

    Args:
        first_prompt: The first_prompt value from session index entry
        max_length: Maximum length of returned prompt (default 500)

    Returns:
        Extracted prompt (truncated to max_length), or None if invalid/empty

    Examples:
        >>> get_initial_prompt_from_index("No prompt")
        None
        >>> get_initial_prompt_from_index("<command-args>Fix the bug</command-args>")
        'Fix the bug'
        >>> get_initial_prompt_from_index("<command-args>…")
        None
        >>> get_initial_prompt_from_index("Regular user prompt")
        'Regular user prompt'
    """
    # Filter out placeholder
    if not first_prompt or first_prompt == "No prompt":
        return None

    # Extract actual prompt from command-wrapped content
    extracted = extract_prompt_from_content(first_prompt)

    # Return None if extraction resulted in empty string
    # (happens with truncated command content or missing args)
    if not extracted:
        return None

    # Truncate to max_length
    return extracted[:max_length]


# =============================================================================
# Project utilities (from services/projects.py)
# =============================================================================

# Project list cache
_projects_cache: tuple[float, list] = (0.0, [])
_PROJECTS_CACHE_TTL = 10  # 10 seconds - short TTL since projects can change


def list_all_projects() -> list:
    """
    List all Claude Code projects from ~/.claude/projects/.

    Uses a short-lived cache to avoid redundant filesystem scans.

    Returns:
        List of Project objects sorted by path.
    """
    global _projects_cache
    now = time.time()
    cached_time, cached_projects = _projects_cache

    if cached_projects and (now - cached_time) < _PROJECTS_CACHE_TTL:
        return cached_projects

    # Compute fresh result
    result = _list_all_projects_impl()
    _projects_cache = (now, result)
    return result


def _list_all_projects_impl() -> list:
    """Implementation of list_all_projects without caching."""
    from config import settings
    from models.project import Project
    from services.desktop_sessions import (
        get_real_project_encoded_name,
        is_worktree_project,
    )

    projects_dir = settings.projects_dir
    if not projects_dir.exists():
        return []

    projects = []
    worktree_dirs = []  # Collect worktree dirs for second pass

    # First pass: collect normal projects and identify worktree dirs
    for encoded_dir in projects_dir.iterdir():
        if not encoded_dir.is_dir() or not encoded_dir.name.startswith("-"):
            continue
        if is_worktree_project(encoded_dir.name):
            worktree_dirs.append(encoded_dir)
            continue
        try:
            project = Project.from_encoded_name(encoded_dir.name)
            projects.append(project)
        except Exception:
            continue

    # Second pass: merge worktree sessions into real projects
    project_lookup = {p.encoded_name: p for p in projects}

    for wt_dir in worktree_dirs:
        session_uuids = [f.stem for f in wt_dir.glob("*.jsonl") if not f.name.startswith("agent-")]
        real_encoded = get_real_project_encoded_name(wt_dir.name, session_uuids)
        if real_encoded and real_encoded in project_lookup:
            # Real project exists - store mapping for router to use
            _register_worktree_mapping(wt_dir.name, real_encoded)
        else:
            # Can't resolve - show as standalone project (graceful degradation)
            try:
                project = Project.from_encoded_name(wt_dir.name)
                projects.append(project)
            except Exception:
                continue

    return sorted(projects, key=lambda p: p.path)


# Worktree mapping registry: worktree_encoded -> real_encoded
# Note: in-memory dict assumes single-process uvicorn (no workers)
_worktree_mappings: dict[str, str] = {}


def _register_worktree_mapping(worktree_encoded: str, real_encoded: str):
    """Register a worktree -> real project mapping."""
    _worktree_mappings[worktree_encoded] = real_encoded


def get_worktree_mappings_for_project(real_encoded: str) -> list[str]:
    """Get all worktree encoded_names that map to a real project.

    Self-populates mappings by calling list_all_projects() if needed,
    so mappings are available even if the project list hasn't been fetched yet.
    """
    # Always delegate to list_all_projects() which has its own TTL cache
    # and populates _worktree_mappings as a side effect
    list_all_projects()
    return [wt for wt, real in _worktree_mappings.items() if real == real_encoded]


def clear_project_cache():
    """Clear the projects cache and worktree mappings. Useful for testing."""
    global _projects_cache, _worktree_mappings
    _projects_cache = (0.0, [])
    _worktree_mappings = {}


# =============================================================================
# Tool result parsing (from services/tool_results.py)
# =============================================================================


class MessageSource(Protocol):
    """Protocol for objects that can iterate over messages."""

    def iter_messages(self) -> Iterator: ...


@dataclass
class ToolResultData:
    """Data extracted from a tool result message."""

    timestamp: datetime
    content: str  # Truncated for display
    parsed: dict | None = None
    spawned_agent_id: str | None = None  # Extracted from full content before truncation


def parse_tool_result_content(content: str) -> tuple[bool, str | None, str | None]:
    """
    Parse tool result dict from UserMessage content.

    Tool results appear in user messages as dicts like:
    {'tool_use_id': 'toolu_xxx', 'type': 'tool_result', 'content': '...'}

    Or as lists of such dicts:
    [{'tool_use_id': 'toolu_xxx', 'type': 'tool_result', 'content': '...'}, ...]

    Returns:
        (is_tool_result, tool_use_id, extracted_content)
    """
    if not content:
        return False, None, None

    content_stripped = content.strip()

    # Quick check for tool result patterns
    if not (content_stripped.startswith("{") or content_stripped.startswith("[")):
        return False, None, None

    # Check for tool_result pattern
    if "'tool_use_id':" not in content_stripped and '"tool_use_id":' not in content_stripped:
        return False, None, None

    try:
        # Try to parse as Python literal (handles single quotes)
        parsed = ast.literal_eval(content_stripped)

        # Handle list of tool results
        if isinstance(parsed, list) and len(parsed) > 0:
            parsed = parsed[0]

        if isinstance(parsed, dict):
            if parsed.get("type") == "tool_result":
                tool_use_id = parsed.get("tool_use_id")
                inner_content = parsed.get("content", "")

                # Content might be a string or a list of content blocks
                if isinstance(inner_content, list):
                    # Extract text from content blocks
                    text_parts = []
                    for block in inner_content:
                        if isinstance(block, dict):
                            if block.get("type") == "text":
                                text_parts.append(block.get("text", ""))
                            else:
                                # For other types, just stringify
                                text_parts.append(str(block))
                        else:
                            text_parts.append(str(block))
                    inner_content = "\n".join(text_parts)

                # Clean up line number prefixes (e.g., " 1->", " 2->")
                if isinstance(inner_content, str):
                    # Remove line number prefixes like " 1->", "10->", etc.
                    inner_content = re.sub(r"^\s*\d+→", "", inner_content, flags=re.MULTILINE)
                    # Truncate for summary
                    inner_content = inner_content.strip()

                return True, tool_use_id, inner_content
    except (ValueError, SyntaxError):
        # Not valid Python literal, try regex fallback
        pass

    # Regex fallback for malformed content
    tool_id_match = re.search(r"'tool_use_id':\s*'([^']+)'", content_stripped)
    content_match = re.search(r"'content':\s*'([^']*)'", content_stripped)

    if tool_id_match:
        tool_use_id = tool_id_match.group(1)
        inner_content = content_match.group(1) if content_match else None
        return True, tool_use_id, inner_content

    return False, None, None


def parse_xml_like_content(content: str) -> dict | None:
    """
    Parse simple flat XML-like content into a dict.

    Handles content like:
    <retrieval_status>success</retrieval_status><task_id>a36f681</task_id>...

    NOTE: Only handles flat <tag>value</tag> patterns.
    Does NOT support: nested tags, attributes, namespaces, or CDATA.
    This is sufficient for TaskOutput which uses simple flat XML.

    Returns:
        Dict of tag -> value pairs, or None if no valid XML-like tags found.
    """
    if not content or "<" not in content:
        return None

    # Extract all <tag>value</tag> patterns
    pattern = r"<(\w+)>(.*?)</\1>"
    matches = re.findall(pattern, content, re.DOTALL)

    if not matches:
        return None

    result = {}
    for tag, value in matches:
        # Clean up value - strip whitespace and handle truncation markers
        cleaned_value = value.strip()
        if cleaned_value.startswith("[Truncated"):
            cleaned_value = "[Truncated]"
        result[tag] = cleaned_value

    return result if result else None


def collect_tool_results(
    message_source: MessageSource,
    extract_spawned_agent: bool = False,
    parse_xml: bool = False,
) -> dict[str, ToolResultData]:
    """
    Collect all tool results from user messages.

    Iterates through messages from the source and extracts tool results
    from UserMessage content.

    Args:
        message_source: Object with iter_messages() method (Session or Agent)
        extract_spawned_agent: If True, extract spawned agent IDs from content
        parse_xml: If True, parse XML-like content structure

    Returns:
        Dict mapping tool_use_id -> ToolResultData
    """
    from models import UserMessage

    results: dict[str, ToolResultData] = {}

    for msg in message_source.iter_messages():
        if not isinstance(msg, UserMessage):
            continue

        # Use pre-computed flag from model validator (reliable)
        if not msg.is_tool_result:
            continue

        tool_use_id = msg.tool_result_id
        # Fall back to parse_tool_result_content for edge cases
        if not tool_use_id:
            _, tool_use_id, _ = parse_tool_result_content(msg.content)
        if not tool_use_id:
            continue

        extracted_content = msg.content  # Already extracted by validator

        if extracted_content is not None:
            # Extract spawned agent ID from FULL content before truncation
            spawned_agent_id = None
            if extract_spawned_agent:
                match = re.search(r"agentId:\s*([\w\-]+)", extracted_content)
                if match:
                    agent_id = match.group(1)
                    # Validate agent ID (real ones are 7 hex chars)
                    if agent_id and len(agent_id) >= 6 and agent_id != "xxx":
                        spawned_agent_id = agent_id

            # Parse XML-like content if requested
            parsed_xml = None
            if parse_xml:
                parsed_xml = parse_xml_like_content(extracted_content)

            # Limit stored content size for display
            result_preview = (
                extracted_content[:500] if len(extracted_content) > 500 else extracted_content
            )

            results[tool_use_id] = ToolResultData(
                timestamp=msg.timestamp,
                content=result_preview,
                parsed=parsed_xml,
                spawned_agent_id=spawned_agent_id,
            )

    return results


# =============================================================================
# Tool summary utilities (from services/tool_summary.py)
# =============================================================================


def make_relative_path(absolute_path: str, project_root: str) -> str:
    """Convert absolute path to relative if inside project root."""
    if not absolute_path or not project_root:
        return absolute_path
    try:
        abs_p = Path(absolute_path)
        root_p = Path(project_root)
        if abs_p.is_relative_to(root_p):
            return str(abs_p.relative_to(root_p))
        return absolute_path
    except (ValueError, TypeError):
        return absolute_path


def find_best_root(path: str, working_dirs: list[str]) -> str | None:
    """Find the deepest working directory that contains the given path."""
    if not path or not working_dirs:
        return None
    try:
        abs_p = Path(path)
        matching = [wd for wd in working_dirs if abs_p.is_relative_to(Path(wd))]
        return max(matching, key=len) if matching else None
    except (ValueError, TypeError):
        return None


def get_tool_summary(block, working_dirs: list[str] | None = None) -> tuple[str, str | None, dict]:
    """
    Extract title, summary, and metadata from a tool use block.

    Args:
        block: The ToolUseBlock to summarize
        working_dirs: Optional list of working directories for path relativization

    Returns:
        Tuple of (title, summary, metadata)
    """
    tool_name = block.name
    tool_input = block.input

    # Helper for path conversion
    def to_relative(path: str) -> str:
        if not path or not working_dirs:
            return path
        root = find_best_root(path, working_dirs)
        return make_relative_path(path, root) if root else path

    # Generate human-readable titles and summaries for common tools
    if tool_name == "Read":
        path = tool_input.get("path") or tool_input.get("file_path", "")
        return "Read file", to_relative(path), {"path": path}
    elif tool_name == "Write":
        path = tool_input.get("path") or tool_input.get("file_path", "")
        return "Write file", to_relative(path), {"path": path}
    elif tool_name == "Edit" or tool_name == "StrReplace":
        path = tool_input.get("path") or tool_input.get("file_path", "")
        return "Edit file", to_relative(path), {"path": path}
    elif tool_name == "Delete":
        path = tool_input.get("path") or tool_input.get("file_path", "")
        return "Delete file", to_relative(path), {"path": path}
    elif tool_name == "Shell" or tool_name == "Bash":
        command = tool_input.get("command", "")
        return "Run command", command[:100] if command else None, {"command": command}
    elif tool_name == "Glob":
        pattern = tool_input.get("glob_pattern", "") or tool_input.get("pattern", "")
        return "Search files", pattern, {"pattern": pattern}
    elif tool_name == "Grep":
        pattern = tool_input.get("pattern", "")
        path = tool_input.get("path", "")
        return (
            "Search content",
            pattern[:50] if pattern else None,
            {"pattern": pattern, "path": to_relative(path) if path else None},
        )
    elif tool_name == "LS":
        path = tool_input.get("target_directory", "") or tool_input.get("path", "")
        return "List directory", to_relative(path), {"path": path}
    elif tool_name == "SemanticSearch":
        query = tool_input.get("query", "")
        return "Semantic search", query[:100] if query else None, {"query": query}
    elif tool_name == "Task":
        description = tool_input.get("description", "")
        subagent_type = tool_input.get("subagent_type")  # None if missing
        return (
            "Spawn subagent",
            description[:100] if description else None,
            {
                "description": description,
                "subagent_type": subagent_type,
            },
        )
    elif tool_name == "TodoWrite":
        todos_input = tool_input.get("todos", [])
        count = len(todos_input) if isinstance(todos_input, list) else 0
        merge = tool_input.get("merge", False)
        action = "merge" if merge else "set"
        summary = f"{'Merge' if merge else 'Set'} {count} todo{'s' if count != 1 else ''}"

        # Parse todo items for richer metadata
        parsed_todos = []
        if isinstance(todos_input, list):
            for todo in todos_input:
                if isinstance(todo, dict):
                    parsed_todos.append(
                        {
                            "content": todo.get("content", ""),
                            "status": todo.get("status", "pending"),
                            "activeForm": todo.get("activeForm") or todo.get("active_form"),
                        }
                    )

        return (
            "Update todos",
            summary,
            {
                "action": action,
                "count": count,
                "todos": parsed_todos,
            },
        )
    elif tool_name == "TaskOutput":
        # TaskOutput retrieves results from a completed subagent
        output = tool_input.get("output", "")

        # Parse XML-like structured content
        parsed = parse_xml_like_content(output) if output else None

        if parsed:
            # Extract key fields from parsed XML
            status = parsed.get("status", "unknown")
            task_id = parsed.get("task_id", "")
            task_type = parsed.get("task_type", "")
            retrieval_status = parsed.get("retrieval_status", "")

            # Build human-readable summary
            summary_parts = []
            if retrieval_status:
                summary_parts.append(retrieval_status.capitalize())
            if status and status != retrieval_status:
                summary_parts.append(f"Status: {status}")
            if task_id:
                summary_parts.append(f"Task: {task_id[:8]}")

            summary = " | ".join(summary_parts) if summary_parts else None

            return (
                "Task output",
                summary,
                {
                    "output": output,
                    "parsed_output": parsed,
                    "status": status,
                    "task_id": task_id,
                    "task_type": task_type,
                    "retrieval_status": retrieval_status,
                },
            )
        else:
            # Fallback for non-XML content
            summary = output[:100] if output else None
            return "Task output", summary, {"output": output}
    elif tool_name == "EditNotebook":
        notebook = tool_input.get("target_notebook", "")
        cell_idx = tool_input.get("cell_idx", 0)
        is_new = tool_input.get("is_new_cell", False)
        action = "Create cell" if is_new else "Edit cell"
        summary = f"{action} {cell_idx} in {notebook.split('/')[-1] if notebook else 'notebook'}"
        return (
            "Edit notebook",
            summary,
            {"notebook": notebook, "cell_idx": cell_idx, "is_new_cell": is_new},
        )
    elif tool_name == "WebSearch":
        search_term = tool_input.get("search_term", "")
        return (
            "Web search",
            search_term[:100] if search_term else None,
            {"search_term": search_term},
        )
    elif tool_name == "AskQuestion":
        title = tool_input.get("title", "")
        questions = tool_input.get("questions", [])
        count = len(questions) if isinstance(questions, list) else 0
        summary = title if title else f"{count} question{'s' if count != 1 else ''}"
        return "Ask question", summary, {"title": title, "question_count": count}
    elif tool_name == "SwitchMode":
        target_mode = tool_input.get("target_mode_id", "")
        explanation = tool_input.get("explanation", "")
        summary = f"Switch to {target_mode}" + (f": {explanation[:50]}" if explanation else "")
        return "Switch mode", summary, {"target_mode": target_mode}
    elif tool_name == "CreatePlan":
        name = tool_input.get("name", "")
        return "Create plan", name if name else None, {"name": name}
    elif tool_name == "ReadLints":
        paths = tool_input.get("paths", [])
        count = len(paths) if isinstance(paths, list) else 0
        summary = f"{count} path{'s' if count != 1 else ''}" if count else "workspace"
        return "Read lints", summary, {"paths": paths}
    elif tool_name == "CallMcpTool":
        server = tool_input.get("server", "")
        mcp_tool = tool_input.get("toolName", "")
        summary = f"{server}/{mcp_tool}" if server and mcp_tool else None
        return "MCP tool", summary, {"server": server, "tool": mcp_tool}
    else:
        return tool_name, None, tool_input

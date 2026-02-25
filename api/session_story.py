#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Session Story Generator

Generates a narrative activity story for the last session of a Claude Code project.

Usage:
    python session_story.py /path/to/project
    python session_story.py /path/to/project --session-uuid <uuid>  # specific session
"""

from __future__ import annotations

import argparse
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Tuple

# Add models directory to path
sys.path.insert(0, str(Path(__file__).parent))

from models import (
    Project,
    Session,
    ToolUseBlock,
)


def format_duration(seconds: Optional[float]) -> str:
    """Format duration in human-readable form."""
    if seconds is None:
        return "unknown duration"

    if seconds < 60:
        return f"{int(seconds)} seconds"
    elif seconds < 3600:
        minutes = int(seconds // 60)
        secs = int(seconds % 60)
        return f"{minutes}m {secs}s" if secs else f"{minutes} minutes"
    else:
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        return f"{hours}h {minutes}m"


def format_tokens(count: int) -> str:
    """Format token count with commas."""
    if count >= 1_000_000:
        return f"{count / 1_000_000:.1f}M"
    elif count >= 1_000:
        return f"{count / 1_000:.1f}K"
    return str(count)


def format_timestamp(dt: Optional[datetime]) -> str:
    """Format datetime for display."""
    if dt is None:
        return "unknown time"
    return dt.strftime("%B %d, %Y at %I:%M %p")


def truncate_text(text: str, max_length: int = 100) -> str:
    """Truncate text with ellipsis."""
    if len(text) <= max_length:
        return text
    return text[: max_length - 3].strip() + "..."


def get_tool_description(tool_name: str) -> str:
    """Get a human-readable description for common tools."""
    descriptions = {
        # Current tool names
        "Read": "reading files",
        "Write": "writing files",
        "Shell": "running commands",
        "Grep": "searching code",
        "Glob": "finding files",
        "LS": "listing directories",
        "StrReplace": "editing files",
        "Delete": "deleting files",
        "SemanticSearch": "semantic code search",
        "WebSearch": "searching the web",
        "TodoWrite": "managing tasks",
        "SwitchMode": "switching modes",
        "CallMcpTool": "using MCP tools",
        "ReadLints": "checking linter errors",
        "EditNotebook": "editing notebooks",
        # Legacy/alternative tool names
        "Bash": "running commands",
        "Task": "spawning subagents",
    }
    return descriptions.get(tool_name, f"using {tool_name}")


def categorize_tools(tool_counts: Counter[str]) -> dict[str, List[Tuple[str, int]]]:
    """Categorize tools by their function."""
    categories = {
        "file_read": ["Read", "Grep", "Glob", "LS", "SemanticSearch"],
        "file_write": ["Write", "StrReplace", "Delete", "EditNotebook"],
        "execution": ["Shell", "Bash"],
        "search": ["Grep", "Glob", "SemanticSearch", "WebSearch"],
        "agents": ["Task"],
        "other": ["TodoWrite", "SwitchMode", "CallMcpTool", "ReadLints"],
    }

    result = {}
    for category, tools in categories.items():
        matches = [(t, c) for t, c in tool_counts.items() if t in tools]
        if matches:
            result[category] = sorted(matches, key=lambda x: -x[1])

    return result


def extract_user_queries(session: Session, max_queries: int = 5) -> List[str]:
    """Extract the main user queries from the session."""
    queries = []
    for msg in session.iter_user_messages():
        content = msg.content.strip()
        # Skip empty or very short messages
        if len(content) < 5:
            continue
        # Skip tool results and internal messages
        if msg.is_tool_result or msg.is_internal_message:
            continue
        queries.append(truncate_text(content, 150))
        if len(queries) >= max_queries:
            break
    return queries


def get_files_touched(session: Session) -> Tuple[set[str], set[str], set[str]]:
    """Extract files read, written, and deleted during the session."""
    files_read = set()
    files_written = set()
    files_deleted = set()

    # Tool name variations for file operations
    read_tools = {"Read", "ReadFile", "read_file"}
    write_tools = {"Write", "WriteFile", "write_file", "StrReplace", "str_replace", "EditNotebook"}
    delete_tools = {"Delete", "DeleteFile", "delete_file"}

    for msg in session.iter_assistant_messages():
        for block in msg.content_blocks:
            if isinstance(block, ToolUseBlock):
                input_data = block.input
                # Try multiple possible path keys
                path = (
                    input_data.get("path")
                    or input_data.get("file_path")
                    or input_data.get("target_notebook")
                )

                if path:
                    if block.name in read_tools:
                        files_read.add(path)
                    elif block.name in write_tools:
                        files_written.add(path)
                    elif block.name in delete_tools:
                        files_deleted.add(path)

    return files_read, files_written, files_deleted


def get_shell_commands(session: Session, max_commands: int = 10) -> List[str]:
    """Extract shell commands executed during the session."""
    shell_tools = {"Shell", "Bash", "bash", "shell", "run_command"}
    commands = []
    for msg in session.iter_assistant_messages():
        for block in msg.content_blocks:
            if isinstance(block, ToolUseBlock) and block.name in shell_tools:
                cmd = block.input.get("command", "") or block.input.get("cmd", "")
                if cmd:
                    commands.append(truncate_text(cmd, 80))
                    if len(commands) >= max_commands:
                        return commands
    return commands


def generate_activity_summary(session: Session) -> str:
    """Generate a brief activity summary based on tool usage patterns."""
    tool_counts = session.get_tools_used()
    total_tools = sum(tool_counts.values())

    if total_tools == 0:
        return "a conversation without tool usage"

    # Determine primary activity (handle tool name variations)
    read_count = (
        tool_counts.get("Read", 0)
        + tool_counts.get("Grep", 0)
        + tool_counts.get("SemanticSearch", 0)
        + tool_counts.get("Glob", 0)
        + tool_counts.get("LS", 0)
    )
    write_count = (
        tool_counts.get("Write", 0)
        + tool_counts.get("StrReplace", 0)
        + tool_counts.get("EditNotebook", 0)
    )
    shell_count = tool_counts.get("Shell", 0) + tool_counts.get("Bash", 0)
    subagent_count = tool_counts.get("Task", 0)

    activities = []
    if read_count > 0:
        activities.append("code exploration")
    if write_count > 0:
        activities.append("code changes")
    if shell_count > 0:
        activities.append("command execution")
    if subagent_count > 0:
        activities.append("parallel subagent work")

    if not activities:
        activities.append("tool-assisted work")

    return " and ".join(activities)


def generate_story(session: Session) -> str:
    """Generate a narrative story of the session activity."""
    lines = []

    # Header
    lines.append("=" * 70)
    lines.append("📖 SESSION ACTIVITY STORY")
    lines.append("=" * 70)
    lines.append("")

    # Session metadata
    lines.append("🔹 SESSION OVERVIEW")
    lines.append("-" * 40)
    lines.append(f"   Session ID: {session.uuid[:12]}...")
    lines.append(f"   Started:    {format_timestamp(session.start_time)}")
    lines.append(f"   Duration:   {format_duration(session.duration_seconds)}")
    lines.append(f"   Messages:   {session.message_count}")
    lines.append("")

    # Models used
    models = session.get_models_used()
    if models:
        model_display = ", ".join(
            m.replace("claude-", "").replace("-20", " (20") + ")" if "-20" in m else m
            for m in sorted(models)
        )
        lines.append(f"   Model(s):   {model_display}")
        lines.append("")

    # Git context
    branches = session.get_git_branches()
    if branches:
        lines.append(f"   Git Branch: {', '.join(sorted(branches))}")
        lines.append("")

    # Activity summary
    activity = generate_activity_summary(session)
    lines.append(f"   Activity:   This session involved {activity}")
    lines.append("")

    # User queries
    lines.append("🔹 WHAT THE USER ASKED")
    lines.append("-" * 40)
    queries = extract_user_queries(session)
    if queries:
        for i, query in enumerate(queries, 1):
            lines.append(f'   {i}. "{query}"')
    else:
        lines.append("   (No text queries found)")
    lines.append("")

    # Tool usage
    tool_counts = session.get_tools_used()
    if tool_counts:
        lines.append("🔹 TOOLS USED")
        lines.append("-" * 40)
        total_calls = sum(tool_counts.values())
        lines.append(f"   Total tool calls: {total_calls}")
        lines.append("")
        for tool, count in tool_counts.most_common(10):
            bar = "█" * min(count, 20) + ("+" if count > 20 else "")
            lines.append(f"   {tool:18} {count:4}x  {bar}")
        lines.append("")

    # Files touched
    files_read, files_written, files_deleted = get_files_touched(session)
    if files_read or files_written or files_deleted:
        lines.append("🔹 FILES TOUCHED")
        lines.append("-" * 40)

        if files_written:
            lines.append(f"   📝 Files written/edited: {len(files_written)}")
            for f in sorted(files_written)[:8]:
                lines.append(f"      • {Path(f).name}")
            if len(files_written) > 8:
                lines.append(f"      ... and {len(files_written) - 8} more")

        if files_read - files_written:  # Files only read
            read_only = files_read - files_written
            lines.append(f"   👁️  Files read: {len(read_only)}")
            for f in sorted(read_only)[:5]:
                lines.append(f"      • {Path(f).name}")
            if len(read_only) > 5:
                lines.append(f"      ... and {len(read_only) - 5} more")

        if files_deleted:
            lines.append(f"   🗑️  Files deleted: {len(files_deleted)}")
            for f in sorted(files_deleted):
                lines.append(f"      • {Path(f).name}")

        lines.append("")

    # Shell commands
    commands = get_shell_commands(session)
    if commands:
        lines.append("🔹 COMMANDS EXECUTED")
        lines.append("-" * 40)
        for cmd in commands[:6]:
            lines.append(f"   $ {cmd}")
        if len(commands) > 6:
            lines.append(f"   ... and {len(commands) - 6} more commands")
        lines.append("")

    # Todos
    todos = session.list_todos()
    if todos:
        lines.append("🔹 TASK LIST")
        lines.append("-" * 40)
        status_icons = {"pending": "⬜", "in_progress": "🔄", "completed": "✅"}
        for todo in todos[:8]:
            icon = status_icons.get(todo.status, "•")
            lines.append(f"   {icon} {truncate_text(todo.content, 60)}")
        if len(todos) > 8:
            lines.append(f"   ... and {len(todos) - 8} more tasks")
        lines.append("")

    # Token usage
    usage = session.get_usage_summary()
    if usage.total_tokens > 0:
        lines.append("🔹 TOKEN USAGE")
        lines.append("-" * 40)
        lines.append(f"   Input tokens:      {format_tokens(usage.input_tokens):>10}")
        lines.append(f"   Output tokens:     {format_tokens(usage.output_tokens):>10}")
        if usage.cache_read_input_tokens > 0:
            lines.append(
                f"   Cache hits:        {format_tokens(usage.cache_read_input_tokens):>10}"
            )
            lines.append(f"   Cache hit rate:    {usage.cache_hit_rate:.1%}")
        lines.append("   ─────────────────────────────")
        lines.append(f"   Total tokens:      {format_tokens(usage.total_tokens):>10}")
        lines.append("")

    # Subagents
    subagents = session.list_subagents()
    if subagents:
        lines.append("🔹 SUBAGENTS SPAWNED")
        lines.append("-" * 40)
        for agent in subagents:
            slug_display = f" ({agent.slug})" if agent.slug else ""
            lines.append(
                f"   • Agent {agent.agent_id}{slug_display}: {agent.message_count} messages"
            )
        lines.append("")

    # Footer
    lines.append("=" * 70)

    return "\n".join(lines)


def get_last_session(project: Project) -> Optional[Session]:
    """Get the most recent session by start time."""
    sessions = project.list_sessions()
    if not sessions:
        return None

    # Sort by start time, most recent first
    sessions_with_time = [(s, s.start_time) for s in sessions]
    sessions_with_time = [(s, t) for s, t in sessions_with_time if t is not None]

    if not sessions_with_time:
        # Fall back to first available session
        return sessions[-1] if sessions else None

    sessions_with_time.sort(key=lambda x: x[1], reverse=True)
    return sessions_with_time[0][0]


def main():
    parser = argparse.ArgumentParser(
        description="Generate a session activity story for a Claude Code project",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s /Users/me/my-project
  %(prog)s .
  %(prog)s /path/to/project --session-uuid abc123...
        """,
    )
    parser.add_argument("project_path", type=str, help="Absolute path to the project directory")
    parser.add_argument(
        "--session-uuid", type=str, help="Specific session UUID (defaults to last session)"
    )
    parser.add_argument(
        "--json", action="store_true", help="Output as JSON instead of formatted text"
    )

    args = parser.parse_args()

    # Resolve project path
    project_path = Path(args.project_path).resolve()

    if not project_path.is_absolute():
        print(f"Error: Path must be absolute: {project_path}", file=sys.stderr)
        sys.exit(1)

    # Load project
    try:
        project = Project.from_path(project_path)
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    if not project.exists:
        print(f"Error: No Claude session data found for project: {project_path}", file=sys.stderr)
        print(f"       Expected data at: {project.project_dir}", file=sys.stderr)
        sys.exit(1)

    # Get session
    if args.session_uuid:
        session = project.get_session(args.session_uuid)
        if not session:
            print(f"Error: Session not found: {args.session_uuid}", file=sys.stderr)
            sys.exit(1)
    else:
        session = get_last_session(project)
        if not session:
            print(f"Error: No sessions found for project: {project_path}", file=sys.stderr)
            sys.exit(1)

    # Generate and print story
    if args.json:
        import json

        usage = session.get_usage_summary()
        files_read, files_written, files_deleted = get_files_touched(session)

        output = {
            "session_id": session.uuid,
            "start_time": session.start_time.isoformat() if session.start_time else None,
            "end_time": session.end_time.isoformat() if session.end_time else None,
            "duration_seconds": session.duration_seconds,
            "message_count": session.message_count,
            "models_used": list(session.get_models_used()),
            "git_branches": list(session.get_git_branches()),
            "user_queries": extract_user_queries(session, max_queries=10),
            "tools_used": dict(session.get_tools_used()),
            "files_read": list(files_read),
            "files_written": list(files_written),
            "files_deleted": list(files_deleted),
            "shell_commands": get_shell_commands(session, max_commands=20),
            "todos": [{"content": t.content, "status": t.status} for t in session.list_todos()],
            "token_usage": {
                "input": usage.input_tokens,
                "output": usage.output_tokens,
                "cache_read": usage.cache_read_input_tokens,
                "cache_creation": usage.cache_creation_input_tokens,
                "total": usage.total_tokens,
                "cache_hit_rate": usage.cache_hit_rate,
            },
            "subagents": [
                {"id": a.agent_id, "slug": a.slug, "messages": a.message_count}
                for a in session.list_subagents()
            ],
        }
        print(json.dumps(output, indent=2))
    else:
        story = generate_story(session)
        print(story)


if __name__ == "__main__":
    main()

"""
Commands router - browse and read user-authored command files.

Commands are .md files in ~/.claude/commands/ (global) or .claude/commands/ (project).
They are invoked via slash commands (e.g., /commit, /run-tests) and appear in JSONL
as Skill tool calls without a ':' prefix.
"""

import logging
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request

api_path = Path(__file__).parent.parent
sys.path.insert(0, str(api_path))

from config import Settings, settings
from http_caching import cacheable
from models import Project
from parallel import run_in_thread
from schemas import CommandContent, CommandDetailResponse, CommandInfo, CommandItem

logger = logging.getLogger(__name__)

router = APIRouter()

# File path validation — no colons allowed
ALLOWED_PATH_PATTERN = re.compile(r"^[a-zA-Z0-9_\-./]+$")
# Command name validation — allows ':' for plugin commands (e.g. feature-dev:feature-dev)
ALLOWED_COMMAND_NAME_PATTERN = re.compile(r"^[a-zA-Z0-9_\-./:]+$")


def get_settings() -> Settings:
    return settings


def get_commands_dir(
    config: Annotated[Settings, Depends(get_settings)],
    project: Annotated[
        str | None, Query(description="Project encoded name for project-specific commands")
    ] = None,
) -> Path:
    """Get the commands directory (global or project-specific)."""
    if project:
        try:
            proj = Project.from_encoded_name(project)
            return Path(proj.path) / ".claude" / "commands"
        except Exception as err:
            raise HTTPException(status_code=400, detail="Invalid project name") from err
    return config.commands_dir


def validate_command_path(path: str, commands_dir: Path, max_length: int = 500) -> Path:
    """Validate and sanitize command path for security."""
    if not path or len(path) > max_length:
        raise HTTPException(
            status_code=400, detail=f"Path must be between 1 and {max_length} characters"
        )

    clean_path = path.strip("/").strip()
    if not clean_path:
        raise HTTPException(status_code=400, detail="Invalid path")

    if not ALLOWED_PATH_PATTERN.match(clean_path):
        raise HTTPException(
            status_code=400,
            detail="Path must contain only alphanumeric characters, hyphens, underscores, dots, and forward slashes",
        )

    if ".." in clean_path:
        raise HTTPException(status_code=400, detail="Path traversal not allowed")

    target_path = (commands_dir / clean_path).resolve()

    try:
        resolved_commands_dir = commands_dir.resolve()
        target_path.relative_to(resolved_commands_dir)
    except ValueError as e:
        raise HTTPException(
            status_code=400, detail="Invalid path: outside commands directory"
        ) from e

    return target_path


def safe_read_file(file_path: Path, max_size: int) -> str:
    """Safely read a file with size limits."""
    try:
        if file_path.stat().st_size > max_size:
            raise HTTPException(status_code=413, detail="File too large")
        try:
            return file_path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            return "(Binary content - cannot display)"
    except OSError as e:
        raise HTTPException(status_code=500, detail="Failed to read command file") from e


@router.get("/commands", response_model=list[CommandItem])
@cacheable(max_age=30, stale_while_revalidate=60)
def list_commands(
    request: Request,
    path: Annotated[str | None, Query(description="Subdirectory path")] = None,
    commands_dir: Annotated[Path, Depends(get_commands_dir)] = None,
) -> list[CommandItem]:
    """List command files in the commands directory."""
    try:
        if path:
            target_dir = validate_command_path(path, commands_dir)
        else:
            target_dir = commands_dir

        if not target_dir.exists():
            return []

        if not target_dir.is_dir():
            raise HTTPException(status_code=400, detail="Path is not a directory")

        items: list[CommandItem] = []
        for entry in sorted(target_dir.iterdir()):
            try:
                name = entry.name
                if name.startswith("."):
                    continue

                rel_path = str(entry.relative_to(commands_dir))

                if entry.is_dir():
                    items.append(
                        CommandItem(
                            name=name,
                            path=rel_path,
                            type="directory",
                            size_bytes=None,
                            modified_at=None,
                        )
                    )
                elif entry.is_file() and name.endswith(".md"):
                    stat = entry.stat()
                    items.append(
                        CommandItem(
                            name=name,
                            path=rel_path,
                            type="file",
                            size_bytes=stat.st_size,
                            modified_at=datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc),
                        )
                    )
            except Exception as e:
                logger.warning("Failed to process command entry %s: %s", entry, e)

        return items

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to list commands directory: %s", e)
        raise HTTPException(status_code=500, detail="Failed to list commands directory") from e


@router.get("/commands/content", response_model=CommandContent)
@cacheable(max_age=60, stale_while_revalidate=120)
async def get_command_content(
    request: Request,
    path: Annotated[str, Query(description="Relative path to the command file")],
    commands_dir: Annotated[Path, Depends(get_commands_dir)],
) -> CommandContent:
    """Get content of a specific command file."""
    target_file = validate_command_path(path, commands_dir)

    if not target_file.exists() or not target_file.is_file():
        raise HTTPException(status_code=404, detail="Command file not found")

    try:
        content = await run_in_thread(safe_read_file, target_file, settings.max_skill_size)
        stat = target_file.stat()

        return CommandContent(
            name=target_file.name,
            path=path,
            content=content,
            size_bytes=stat.st_size,
            modified_at=datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc),
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to read command file: {e}")
        raise HTTPException(status_code=500, detail="Failed to read command file") from e


@router.get("/commands/usage")
@cacheable(max_age=120, stale_while_revalidate=300)
def get_command_usage(
    request: Request,
    project: Annotated[str | None, Query(description="Project encoded name filter")] = None,
):
    """Get command usage analytics across all sessions with category classification."""
    from command_helpers import classify_invocation, get_command_description
    from db.connection import sqlite_read
    from db.queries import query_command_usage

    with sqlite_read() as conn:
        if conn is None:
            return []

        rows = query_command_usage(conn, project=project, limit=100)
        results = []
        for row in rows:
            cmd_name = row["command_name"]
            is_plugin = ":" in cmd_name
            plugin_name = cmd_name.split(":")[0] if is_plugin else None
            results.append(
                {
                    "name": cmd_name,
                    "count": row["total_count"],
                    "session_count": row["session_count"],
                    "last_used": row["last_used"],
                    "category": classify_invocation(cmd_name),
                    "description": get_command_description(cmd_name),
                    "is_plugin": is_plugin,
                    "plugin": plugin_name,
                }
            )
        return results


@router.get("/commands/usage/trend")
@cacheable(max_age=120, stale_while_revalidate=300)
def get_command_usage_trend(
    request: Request,
    project: Annotated[str | None, Query(description="Project encoded name filter")] = None,
    period: Annotated[
        Literal["week", "month", "quarter", "all"],
        Query(description="Time period: week, month, quarter, all"),
    ] = "month",
):
    """Get command usage trend data with daily breakdown."""
    import sqlite3

    from db.connection import sqlite_read
    from db.queries import query_command_usage_trend

    try:
        with sqlite_read() as conn:
            if conn is not None:
                return query_command_usage_trend(conn, project=project, period=period)
    except sqlite3.Error as e:
        logger.warning("SQLite command trend query failed: %s", e)

    return {
        "total": 0,
        "by_item": {},
        "trend": [],
        "trend_by_item": {},
        "first_used": None,
        "last_used": None,
    }


def _validate_command_name(command_name: str) -> None:
    """Validate command_name to prevent path traversal and injection."""
    if not command_name or not ALLOWED_COMMAND_NAME_PATTERN.match(command_name):
        raise HTTPException(status_code=400, detail="Invalid command name")
    if ".." in command_name:
        raise HTTPException(status_code=400, detail="Path traversal not allowed")


@router.get("/commands/usage/{command_name}")
@cacheable(max_age=120, stale_while_revalidate=300)
def get_command_usage_detail(command_name: str, request: Request):
    """Get usage detail for a specific command."""
    _validate_command_name(command_name)
    from db.connection import sqlite_read
    from db.queries import query_command_sessions

    with sqlite_read() as conn:
        if conn is None:
            return {"name": command_name, "total_uses": 0, "sessions": []}
        return query_command_sessions(conn, command_name, limit=50)


@router.get("/commands/{command_name}/detail", response_model=CommandDetailResponse)
@cacheable(max_age=120, stale_while_revalidate=300)
async def get_command_detail(
    command_name: str,
    request: Request,
    config: Annotated[Settings, Depends(get_settings)],
    per_page: Annotated[int, Query(ge=1, le=200)] = 100,
    page: Annotated[int, Query(ge=1)] = 1,
    project: Annotated[
        str | None, Query(description="Project encoded name for project-specific lookup")
    ] = None,
):
    """Get detailed command info with usage stats, trend, and session list."""
    _validate_command_name(command_name)
    from command_helpers import (
        classify_invocation,
        get_bundled_skill_prompt,
        get_command_description,
    )
    from db.connection import sqlite_read
    from db.queries import query_command_detail

    category = classify_invocation(command_name)
    description = get_command_description(command_name)

    # Resolve content based on category
    content = None
    file_path = None
    if category == "user_command":
        # Check project then global commands
        cmd_file = None
        if project:
            try:
                proj = Project.from_encoded_name(project)
                project_cmd = Path(proj.path) / ".claude" / "commands" / f"{command_name}.md"
                if project_cmd.is_file():
                    cmd_file = project_cmd
            except Exception as e:
                logger.warning("Failed to resolve project command %s: %s", command_name, e)
        if not cmd_file:
            user_cmd = config.commands_dir / f"{command_name}.md"
            if user_cmd.is_file():
                cmd_file = user_cmd
        if cmd_file:
            try:
                content = await run_in_thread(safe_read_file, cmd_file, settings.max_skill_size)
                file_path = str(cmd_file)
            except Exception as e:
                logger.warning("Failed to read user_command content for %s: %s", command_name, e)
    elif category in ("plugin_command", "plugin_skill"):
        # Resolve plugin command/skill content via skills info resolver
        try:
            from routers.skills import _resolve_skill_info

            skill_info = await _resolve_skill_info(command_name, config)
            content = skill_info.content
            description = description or skill_info.description
            file_path = skill_info.file_path
        except Exception as e:
            logger.warning("Failed to resolve plugin content for %s: %s", command_name, e)
    elif category == "bundled_skill":
        # Extract bundled skill prompt from cli.js
        try:
            content = get_bundled_skill_prompt(command_name)
        except Exception as e:
            logger.warning("Failed to extract bundled_skill content for %s: %s", command_name, e)
    elif category == "custom_skill":
        # User SKILL.md files in ~/.claude/skills/
        try:
            skill_file = config.claude_base / "skills" / command_name / "SKILL.md"
            if skill_file.is_file():
                content = await run_in_thread(safe_read_file, skill_file, settings.max_skill_size)
                file_path = str(skill_file)
        except Exception as e:
            logger.warning("Failed to read custom_skill content for %s: %s", command_name, e)
    elif category == "builtin_command":
        # Built-in CLI commands don't have prompts but we provide descriptions
        from command_helpers import BUILTIN_COMMAND_DESCRIPTIONS

        if not description:
            description = BUILTIN_COMMAND_DESCRIPTIONS.get(command_name)

    # Get usage stats from SQLite
    usage_data = None
    with sqlite_read() as conn:
        if conn is not None:
            offset = (page - 1) * per_page
            usage_data = query_command_detail(conn, command_name, limit=per_page, offset=offset)

    if usage_data is None and content is None and description is None:
        raise HTTPException(status_code=404, detail=f"Command '{command_name}' not found")

    return {
        "name": command_name,
        "description": description,
        "category": category,
        "content": content,
        "is_plugin": ":" in command_name,
        "plugin": command_name.split(":")[0] if ":" in command_name else None,
        "file_path": file_path,
        "calls": usage_data["total_calls"] if usage_data else 0,
        "main_calls": usage_data["main_calls"] if usage_data else 0,
        "subagent_calls": usage_data["subagent_calls"] if usage_data else 0,
        "manual_calls": usage_data["manual_calls"] if usage_data else 0,
        "auto_calls": usage_data["auto_calls"] if usage_data else 0,
        "session_count": usage_data["session_count"] if usage_data else 0,
        "first_used": usage_data["first_used"] if usage_data else None,
        "last_used": usage_data["last_used"] if usage_data else None,
        "trend": usage_data["trend"] if usage_data else [],
        "sessions": usage_data["sessions"] if usage_data else [],
        "sessions_total": usage_data["total"] if usage_data else 0,
    }


@router.get("/commands/info/{command_name}", response_model=CommandInfo)
@cacheable(max_age=60, stale_while_revalidate=120)
async def get_command_info(
    command_name: str,
    request: Request,
    config: Annotated[Settings, Depends(get_settings)],
    project: Annotated[
        str | None, Query(description="Project encoded name for project-specific lookup")
    ] = None,
) -> CommandInfo:
    """
    Get detailed info about a command by name.

    Searches in order:
    1. Project .claude/commands/{name}.md (if project specified)
    2. User ~/.claude/commands/{name}.md
    """
    import yaml

    _validate_command_name(command_name)

    command_file = None

    # 1. Project-level commands
    if project:
        try:
            proj = Project.from_encoded_name(project)
            project_cmd = Path(proj.path) / ".claude" / "commands" / f"{command_name}.md"
            if project_cmd.is_file():
                command_file = project_cmd
        except Exception:
            pass

    # 2. User-level commands
    if not command_file:
        user_cmd = config.commands_dir / f"{command_name}.md"
        if user_cmd.is_file():
            command_file = user_cmd

    if not command_file:
        raise HTTPException(
            status_code=404,
            detail=f"Command '{command_name}' not found in project or user commands",
        )

    try:
        content = await run_in_thread(safe_read_file, command_file, settings.max_skill_size)
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to read command file: %s", e)
        raise HTTPException(status_code=500, detail="Failed to read command file") from e

    # Parse YAML frontmatter
    description = None
    frontmatter_name = command_name

    if content.startswith("---"):
        parts = content.split("---", 2)
        if len(parts) >= 3:
            frontmatter_str = parts[1].strip()
            try:
                frontmatter = yaml.safe_load(frontmatter_str)
                if isinstance(frontmatter, dict):
                    description = frontmatter.get("description")
                    frontmatter_name = frontmatter.get("name", command_name)
            except yaml.YAMLError as e:
                logger.warning("Failed to parse YAML frontmatter for %s: %s", command_name, e)

    return CommandInfo(
        name=frontmatter_name,
        description=description,
        content=content,
        is_plugin=False,
        plugin=None,
        file_path=str(command_file),
    )

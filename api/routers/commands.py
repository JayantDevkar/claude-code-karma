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
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request

api_path = Path(__file__).parent.parent
sys.path.insert(0, str(api_path))

from config import Settings, settings
from http_caching import cacheable
from models import Project
from parallel import run_in_thread
from schemas import CommandContent, CommandInfo, CommandItem

logger = logging.getLogger(__name__)

router = APIRouter()

# Reuse the same safe path pattern from skills router
ALLOWED_PATH_PATTERN = re.compile(r"^[a-zA-Z0-9_\-./]+$")


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
        proj = Project.from_encoded_name(project)
        return Path(proj.path) / ".claude" / "commands"
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
                logger.warning(f"Failed to process command entry {entry}: {e}")

        return items

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to list commands directory: {e}")
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
def get_command_usage(request: Request):
    """Get command usage analytics across all sessions."""
    from db.connection import sqlite_read

    with sqlite_read() as conn:
        if conn is None:
            return []

        rows = conn.execute("""
            SELECT
                sc.command_name,
                SUM(sc.count) as total_uses,
                COUNT(DISTINCT sc.session_uuid) as session_count,
                MAX(s.start_time) as last_used
            FROM session_commands sc
            JOIN sessions s ON sc.session_uuid = s.uuid
            GROUP BY sc.command_name
            ORDER BY total_uses DESC
        """).fetchall()

        return [
            {
                "command_name": row[0],
                "total_uses": row[1],
                "session_count": row[2],
                "last_used": row[3],
            }
            for row in rows
        ]


@router.get("/commands/usage/{command_name}")
@cacheable(max_age=120, stale_while_revalidate=300)
def get_command_usage_detail(command_name: str, request: Request):
    """Get usage detail for a specific command."""
    from db.connection import sqlite_read

    with sqlite_read() as conn:
        if conn is None:
            return {"command_name": command_name, "sessions": []}

        rows = conn.execute(
            """
            SELECT
                sc.session_uuid,
                sc.count,
                s.slug,
                s.project_encoded_name,
                s.start_time
            FROM session_commands sc
            JOIN sessions s ON sc.session_uuid = s.uuid
            WHERE sc.command_name = ?
            ORDER BY s.start_time DESC
            LIMIT 50
        """,
            (command_name,),
        ).fetchall()

        return {
            "command_name": command_name,
            "total_uses": sum(r[1] for r in rows),
            "sessions": [
                {
                    "session_uuid": row[0],
                    "count": row[1],
                    "slug": row[2],
                    "project": row[3],
                    "start_time": row[4],
                }
                for row in rows
            ],
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

    # Sanitize command name
    if not command_name or not ALLOWED_PATH_PATTERN.match(command_name):
        raise HTTPException(status_code=400, detail="Invalid command name")
    if ".." in command_name:
        raise HTTPException(status_code=400, detail="Path traversal not allowed")

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
        logger.error(f"Failed to read command file: {e}")
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
                logger.warning(f"Failed to parse YAML frontmatter for {command_name}: {e}")

    return CommandInfo(
        name=frontmatter_name,
        description=description,
        content=content,
        is_plugin=False,
        plugin=None,
        file_path=str(command_file),
    )

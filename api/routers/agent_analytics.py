"""
Agent usage analytics - data collection and aggregation.

Provides functions to collect and analyze Task tool (subagent) usage
patterns across all projects and sessions.

All data is served from the SQLite metadata index for fast queries.
"""

import logging
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Optional

from cachetools import TTLCache, cached

from schemas import (
    AgentCategory,
    AgentInvocation,
    AgentUsageDetail,
    AgentUsageListResponse,
    AgentUsageSummary,
)
from utils import is_encoded_project_dir

logger = logging.getLogger(__name__)

# TTL caches for filesystem checks (60 second TTL)
# IMPORTANT: These must be separate caches because both functions take the same
# argument (subagent_type str) and cachetools keys by arguments alone, not function name.
_category_cache = TTLCache(maxsize=256, ttl=60)
_definition_cache = TTLCache(maxsize=256, ttl=60)
# Single-entry cache: zero-argument function means cachetools keys on () — maxsize=1 is correct.
_project_agents_cache = TTLCache(maxsize=1, ttl=120)


def _parse_iso(value: Optional[str]) -> Optional[datetime]:
    """Parse an ISO 8601 datetime string, returning None on failure."""
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except (ValueError, TypeError):
        return None


BUILTIN_AGENTS = {
    "Explore",
    "Plan",
    "Bash",
    "general-purpose",
    "statusline-setup",
    "claude-code-guide",
}


def get_custom_agents_dir() -> Path:
    """Get the ~/.claude/agents directory."""
    return Path.home() / ".claude" / "agents"


def _agent_file_exists(agents_dir: Path, name: str) -> bool:
    """Check if an agent exists as {name}.md or {name}/SKILL.md in a directory."""
    return (agents_dir / f"{name}.md").exists() or (agents_dir / name / "SKILL.md").exists()


@cached(_project_agents_cache)
def _get_all_project_agent_names() -> frozenset[str]:
    """
    Scan all project directories for project-level agent definitions.

    Checks {project_real_path}/.claude/agents/ for each known project.
    Returns a frozenset of agent names found across all projects.
    Cached with 120s TTL to avoid repeated filesystem scans.
    """
    agent_names: set[str] = set()
    projects_dir = Path.home() / ".claude" / "projects"
    if not projects_dir.exists():
        return frozenset()

    # Each subdirectory in ~/.claude/projects/ is an encoded project path.
    # Decode it to find the real project directory, then check .claude/agents/.
    for encoded_dir in projects_dir.iterdir():
        if not encoded_dir.is_dir() or encoded_dir.name.startswith("."):
            continue
        if not is_encoded_project_dir(encoded_dir.name):
            continue
        # Decode to real project path using Project model
        from models.project import Project

        decoded_path = Project.decode_path(encoded_dir.name)
        project_dir = Path(decoded_path)
        if not project_dir.is_dir():
            continue
        project_agents_dir = project_dir / ".claude" / "agents"
        if not project_agents_dir.is_dir():
            continue
        # Collect .md files
        for f in project_agents_dir.glob("*.md"):
            if f.is_file():
                agent_names.add(f.stem)
        # Collect directory-based agents ({name}/SKILL.md)
        for child in project_agents_dir.iterdir():
            if child.is_dir() and (child / "SKILL.md").is_file():
                agent_names.add(child.name)

    return frozenset(agent_names)


def parse_agent_source(subagent_type: str) -> tuple[Optional[str], str]:
    """
    Extract plugin source and agent name from subagent_type.

    Examples:
        "Explore" -> (None, "Explore")
        "feature-dev:code-reviewer" -> ("feature-dev", "code-reviewer")
    """
    if ":" in subagent_type:
        parts = subagent_type.split(":", 1)
        return parts[0], parts[1]
    return None, subagent_type


@cached(_category_cache)
def determine_agent_category(subagent_type: str) -> str:
    """
    Determine the category of an agent based on its subagent_type.

    Categories (in priority order):
    - plugin: Has ":" separator (e.g. "oh-my-claudecode:executor")
    - builtin: Hardcoded Claude Code agents (Explore, Plan, Bash, etc.)
    - custom: Definition exists in ~/.claude/agents/ (global custom agents)
    - project: Definition exists in some project's .claude/agents/ directory
    - unknown: No definition found anywhere (deleted agent, one-off, etc.)

    Cached with TTL cache (60 second TTL) for performance.
    """
    plugin_source, agent_name = parse_agent_source(subagent_type)

    if plugin_source:
        return "plugin"

    if subagent_type.startswith("_"):
        return "claude_tax"

    if subagent_type in BUILTIN_AGENTS:
        return "builtin"

    # Check global custom agent definitions (~/.claude/agents/)
    custom_agents_dir = get_custom_agents_dir()
    if custom_agents_dir.exists() and _agent_file_exists(custom_agents_dir, subagent_type):
        return "custom"

    # Check project-level agent definitions ({project}/.claude/agents/)
    project_agent_names = _get_all_project_agent_names()
    if subagent_type in project_agent_names:
        return "project"

    # No definition found — could be a deleted custom agent or unknown source
    return "unknown"


@cached(_definition_cache)
def agent_definition_exists(subagent_type: str) -> bool:
    """
    Check if an agent definition file exists (global or project-level).

    Cached with TTL cache (60 second TTL) for performance.
    """
    plugin_source, agent_name = parse_agent_source(subagent_type)
    if plugin_source:
        return False  # Plugin agents have their own definitions

    custom_agents_dir = get_custom_agents_dir()
    if custom_agents_dir.exists() and _agent_file_exists(custom_agents_dir, subagent_type):
        return True

    # Also check project-level agents
    return subagent_type in _get_all_project_agent_names()


def _get_agent_usage_sqlite(search: Optional[str] = None) -> AgentUsageListResponse | None:
    """SQLite fast path for agent usage aggregation."""
    try:
        from db.connection import sqlite_read
        from db.queries import query_agent_usage

        with sqlite_read() as conn:
            if conn is None:
                return None
            data = query_agent_usage(conn, search=search)

        if not data["agents"]:
            return AgentUsageListResponse(
                agents=[],
                total_runs=0,
                total_cost_usd=0.0,
                by_category={},
            )

        agents = []
        category_counts: dict[str, int] = defaultdict(int)

        for row in data["agents"]:
            subagent_type = row["subagent_type"]
            plugin_source, agent_name = parse_agent_source(subagent_type)
            category = determine_agent_category(subagent_type)

            summary = AgentUsageSummary(
                subagent_type=subagent_type,
                plugin_source=plugin_source,
                agent_name=agent_name,
                category=AgentCategory(category),
                total_runs=row["total_runs"],
                total_cost_usd=row["total_cost_usd"],
                total_input_tokens=row["total_input_tokens"],
                total_output_tokens=row["total_output_tokens"],
                avg_duration_seconds=row["avg_duration_seconds"],
                projects_used_in=row["projects"],
                first_used=_parse_iso(row["first_used"]),
                last_used=_parse_iso(row["last_used"]),
                has_definition=agent_definition_exists(subagent_type),
            )
            agents.append(summary)
            category_counts[category] += 1

        agents.sort(key=lambda a: a.total_runs, reverse=True)

        return AgentUsageListResponse(
            agents=agents,
            total_runs=data["total_runs"],
            total_cost_usd=data["total_cost"],
            by_category=dict(category_counts),
        )
    except Exception as e:
        logger.warning("SQLite agent usage failed, falling back: %s", e)
        return None


def _get_agent_detail_sqlite(subagent_type: str) -> AgentUsageDetail | None:
    """SQLite fast path for single agent type detail."""
    try:
        from db.connection import sqlite_read
        from db.queries import query_agent_detail

        with sqlite_read() as conn:
            if conn is None:
                return None
            data = query_agent_detail(conn, subagent_type)

        if data is None:
            return None

        plugin_source, agent_name = parse_agent_source(subagent_type)
        category = determine_agent_category(subagent_type)

        return AgentUsageDetail(
            subagent_type=subagent_type,
            plugin_source=plugin_source,
            agent_name=agent_name,
            category=AgentCategory(category),
            total_runs=data["total_runs"],
            total_cost_usd=data["total_cost_usd"],
            total_input_tokens=data["total_input_tokens"],
            total_output_tokens=data["total_output_tokens"],
            avg_duration_seconds=data["avg_duration_seconds"],
            projects_used_in=data["projects"],
            first_used=_parse_iso(data["first_used"]),
            last_used=_parse_iso(data["last_used"]),
            has_definition=agent_definition_exists(subagent_type),
            top_tools=data.get("top_tools", {}),
            top_skills=data.get("top_skills", {}),
            top_commands=data.get("top_commands", {}),
            usage_by_project=data["usage_by_project"],
        )
    except Exception as e:
        logger.warning("SQLite agent detail failed, falling back: %s", e)
        return None


def _get_agent_history_sqlite(
    subagent_type: str, page: int, per_page: int
) -> tuple[list[AgentInvocation], int] | None:
    """SQLite fast path for agent invocation history."""
    try:
        from db.connection import sqlite_read
        from db.queries import query_agent_history

        with sqlite_read() as conn:
            if conn is None:
                return None
            offset = (page - 1) * per_page
            data = query_agent_history(conn, subagent_type, limit=per_page, offset=offset)

        invocations = []
        for row in data["invocations"]:
            project_path = row.get("project_path") or ""
            project_display_name = project_path.rstrip("/").split("/")[-1] if project_path else None
            invocations.append(
                AgentInvocation(
                    agent_id=row["agent_id"],
                    session_uuid=row["session_uuid"],
                    project_encoded_name=row["project_encoded_name"],
                    project_display_name=project_display_name,
                    display_name=row.get("agent_display_name"),
                    invoked_at=_parse_iso(row["started_at"]),
                    duration_seconds=row["duration_seconds"],
                    input_tokens=row["input_tokens"],
                    output_tokens=row["output_tokens"],
                    cost_usd=row["cost_usd"],
                    description=None,
                )
            )
        return invocations, data["total"]
    except Exception as e:
        logger.warning("SQLite agent history failed, falling back: %s", e)
        return None


async def collect_all_agent_usage(search: Optional[str] = None) -> AgentUsageListResponse:
    """Collect usage statistics for all agent types from SQLite index."""
    result = _get_agent_usage_sqlite(search=search)
    if result is not None:
        return result
    return AgentUsageListResponse(agents=[], total_runs=0, total_cost_usd=0.0, by_category={})


async def get_agent_detail(subagent_type: str) -> Optional[AgentUsageDetail]:
    """Get detailed usage statistics for a specific agent type from SQLite index."""
    return _get_agent_detail_sqlite(subagent_type)


async def get_agent_history(
    subagent_type: str, page: int = 1, per_page: int = 20
) -> tuple[list[AgentInvocation], int]:
    """Get paginated invocation history from SQLite index."""
    result = _get_agent_history_sqlite(subagent_type, page, per_page)
    if result is not None:
        return result
    return [], 0

"""
API response schemas for Claude Code Karma.
"""

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

# =============================================================================
# Error Response Models
# =============================================================================


class PaginationMeta(BaseModel):
    """Standard pagination metadata included in all paginated responses."""

    total: int = Field(0, description="Total items matching filters")
    page: int = Field(1, description="Current page (1-indexed)")
    per_page: int = Field(20, description="Items per page")
    total_pages: int = Field(0, description="Total pages")


def paginate(total: int, page: int = 1, per_page: int = 20) -> dict:
    """Compute pagination metadata + SQL offset."""
    per_page = max(1, min(per_page, 200))
    total_pages = max(1, -(-total // per_page)) if total > 0 else 1
    page = max(1, min(page, total_pages))
    offset = (page - 1) * per_page
    return {
        "total": total,
        "page": page,
        "per_page": per_page,
        "total_pages": total_pages,
        "offset": offset,
    }


class ErrorDetail(BaseModel):
    """Standardized error response model for consistent API error handling."""

    code: str = Field(..., description="Machine-readable error code (e.g., 'INVALID_AGENT_NAME')")
    message: str = Field(..., description="Human-readable error message")
    field: Optional[str] = Field(
        None, description="Field name that caused the error (if applicable)"
    )
    details: Optional[dict] = Field(None, description="Additional error context")


# =============================================================================
# File Activity and Session Models
# =============================================================================


class FileActivity(BaseModel):
    """File operation tracked from tool usage."""

    path: str = Field(..., description="File path that was accessed")
    operation: Literal["read", "write", "edit", "delete", "search"] = Field(
        ..., description="Type of file operation"
    )
    actor: str = Field(
        ..., description="Who performed the operation: 'session' or subagent agentId"
    )
    actor_type: Literal["session", "subagent"] = Field(
        ..., description="Whether actor is main session or subagent"
    )
    timestamp: datetime = Field(..., description="When the operation occurred")
    tool_name: str = Field(..., description="Tool that performed the operation")


class SubagentSummary(BaseModel):
    """Summary of a subagent's activity."""

    agent_id: str = Field(..., description="Agent short hex ID")
    slug: Optional[str] = Field(None, description="Session slug (inherited from parent session)")
    subagent_type: Optional[str] = Field(
        None, description="Type of subagent: Explore, Plan, Bash, or custom agent name"
    )
    tools_used: dict[str, int] = Field(default_factory=dict, description="Tool name -> usage count")
    message_count: int = Field(0, description="Total messages in subagent conversation")
    initial_prompt: Optional[str] = Field(None, description="First user message to subagent")


class ToolUsageSummary(BaseModel):
    """Tool usage breakdown for a session."""

    tool_name: str = Field(..., description="Name of the tool")
    count: int = Field(..., description="Number of times used")
    by_session: int = Field(0, description="Usage by main session")
    by_subagents: int = Field(0, description="Usage by subagents")


class TodoItemSchema(BaseModel):
    """Schema for a single todo item."""

    model_config = ConfigDict(populate_by_name=True)

    content: str = Field(..., description="Todo item description")
    status: Literal["pending", "in_progress", "completed"] = Field(
        default="pending", description="Current todo status"
    )
    active_form: Optional[str] = Field(
        default=None, alias="activeForm", description="Active verb form for display"
    )


class TaskSchema(BaseModel):
    """
    Schema for a task item (new task system with dependency tracking).

    Unlike TodoItemSchema, TaskSchema includes rich metadata like
    subject, description, and dependency tracking (blocks/blockedBy).
    """

    model_config = ConfigDict(populate_by_name=True)

    id: str = Field(..., description="Unique task identifier")
    subject: str = Field(..., description="Short title for the task")
    description: str = Field(..., description="Detailed task description")
    status: Literal["pending", "in_progress", "completed"] = Field(
        default="pending", description="Current task status"
    )
    active_form: Optional[str] = Field(
        default=None, alias="activeForm", description="Active verb form for display"
    )
    blocks: list[str] = Field(default_factory=list, description="Task IDs that this task blocks")
    blocked_by: list[str] = Field(
        default_factory=list,
        alias="blockedBy",
        description="Task IDs that block this task",
    )
    updated_at: Optional[datetime] = Field(
        default=None,
        description="When the task was last modified (file mtime or reconstruction time)",
    )


class SessionChainInfoSummary(BaseModel):
    """
    Lightweight chain info embedded in session summaries.

    Provides just enough info to show chain badges in list views.
    """

    chain_id: str = Field(..., description="Chain identifier (slug)")
    position: int = Field(0, description="Position in chain (0=first)")
    total: int = Field(1, description="Total sessions in chain")
    is_root: bool = Field(False, description="First in chain")
    is_latest: bool = Field(False, description="Most recent in chain")


class SessionSummary(BaseModel):
    """Summary info for a session."""

    uuid: str
    slug: Optional[str] = Field(
        None, description="Human-readable session name (e.g., 'eager-puzzling-fairy')"
    )
    project_encoded_name: Optional[str] = Field(
        None, description="Encoded name of the project this session belongs to"
    )
    project_slug: Optional[str] = Field(None, description="URL-friendly project slug")
    project_display_name: Optional[str] = Field(None, description="Human-readable project name")
    message_count: int
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    duration_seconds: Optional[float] = None
    models_used: list[str] = Field(default_factory=list)
    subagent_count: int = 0
    has_todos: bool = False
    todo_count: int = Field(0, description="Number of todo items in session")
    initial_prompt: Optional[str] = None
    summary: Optional[str] = Field(
        None, description="Claude's auto-generated session summary (from sessions-index.json)"
    )
    git_branches: list[str] = Field(
        default_factory=list, description="Git branches touched during this session"
    )
    # Chain info for list view badges
    chain_info: Optional[SessionChainInfoSummary] = Field(
        None, description="Chain context if session is part of a resumed chain"
    )
    # Session titles (human-readable names generated by Claude)
    session_titles: list[str] = Field(
        default_factory=list,
        description="Generated session titles from SessionTitleMessage",
    )
    chain_title: Optional[str] = Field(
        None,
        description="Title inherited from chain sibling when session has no own title",
    )
    tool_source: Optional[str] = Field(
        None,
        description="How the tool was used: 'main', 'subagent', or 'both' (only set in tool/server context)",
    )
    subagent_agent_ids: list[str] = Field(
        default_factory=list,
        description="Agent IDs of subagents that used the tool (for deep-linking to agent session view)",
    )
    session_source: Optional[str] = Field(
        None,
        description="Session origin: 'desktop' for Claude Desktop, None for CLI",
    )


class CompactionSummary(BaseModel):
    """Structured compaction event details from CompactBoundaryMessage."""

    summary: str = Field(..., description="Compaction summary text")
    trigger: Optional[str] = Field(None, description="Compaction trigger: 'auto' or 'manual'")
    pre_tokens: Optional[int] = Field(None, description="Token count before compaction")
    timestamp: Optional[datetime] = Field(None, description="When compaction occurred")


class SessionDetail(SessionSummary):
    """Detailed session info including subagents and tools."""

    tools_used: dict[str, int] = Field(default_factory=dict)
    git_branches: list[str] = Field(default_factory=list)
    working_directories: list[str] = Field(default_factory=list)
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    cache_hit_rate: float = 0.0
    total_cost: float = Field(0.0, description="Total estimated cost in USD")
    todos: list[TodoItemSchema] = Field(
        default_factory=list, description="Todo items for this session"
    )
    tasks: list[TaskSchema] = Field(
        default_factory=list,
        description="Task items for this session (new task system with dependencies)",
    )
    has_tasks: bool = Field(False, description="Whether this session has tasks (new task system)")
    # Chain detection (lightweight flag to avoid unnecessary /chain fetches)
    has_chain: bool = Field(
        False,
        description="True if this session belongs to a chain of >= 2 related sessions",
    )
    # Continuation session detection
    is_continuation_marker: bool = Field(
        False,
        description="True if this session is a continuation marker (only file-history-snapshots)",
    )
    file_snapshot_count: int = Field(0, description="Number of file-history-snapshot messages")
    # Project context (summaries from PREVIOUS sessions loaded at session start)
    project_context_summaries: list[str] = Field(
        default_factory=list,
        description="Context summaries from PREVIOUS sessions loaded at session start",
    )
    project_context_leaf_uuids: list[str] = Field(
        default_factory=list,
        description="Leaf UUIDs referencing messages in previous sessions that provided context",
    )
    # Session titles (SessionTitleMessage - naming, NOT compaction)
    session_titles: list[str] = Field(
        default_factory=list,
        description="Session titles generated by Claude Code for naming (NOT compaction indicators)",
    )
    # Session compaction (TRUE compaction from CompactBoundaryMessage)
    was_compacted: bool = Field(
        False,
        description="True if THIS session underwent TRUE context compaction (CompactBoundaryMessage)",
    )
    compaction_summary_count: int = Field(
        0,
        description="Number of compaction events in this session",
    )
    compaction_summaries: list[CompactionSummary] = Field(
        default_factory=list,
        description="Structured compaction events with trigger and token metadata",
    )
    message_type_breakdown: dict[str, int] = Field(
        default_factory=dict,
        description="Breakdown of message types: user, assistant, file_history_snapshot, summary",
    )
    # Skill usage tracking
    skills_used: list["SkillUsage"] = Field(
        default_factory=list,
        description="Skills invoked via the Skill tool during this session",
    )
    # Command usage tracking (user-authored slash commands without ':' prefix)
    commands_used: list["CommandUsage"] = Field(
        default_factory=list,
        description="Commands invoked via slash commands during this session",
    )


class ContinuationSessionInfo(BaseModel):
    """Information about a session found by message UUID lookup.

    Used to link continuation marker sessions to their continuation sessions.
    """

    session_uuid: str = Field(..., description="UUID of the session containing the message")
    project_encoded_name: str = Field(..., description="Encoded project directory name")
    slug: Optional[str] = Field(None, description="Session slug if available")


class SessionLookupResult(BaseModel):
    """
    Fast session lookup result for slug/UUID prefix matching.

    Used by the session page to quickly resolve a slug or UUID prefix
    to a full session UUID without loading all sessions in a project.
    """

    uuid: str = Field(..., description="Full session UUID")
    slug: Optional[str] = Field(None, description="Session slug if available")
    project_encoded_name: str = Field(..., description="Encoded project directory name")
    project_path: str = Field(..., description="Original project path")
    message_count: int = Field(0, description="Number of messages in session")
    start_time: Optional[datetime] = Field(None, description="Session start time")
    end_time: Optional[datetime] = Field(None, description="Session end time")
    initial_prompt: Optional[str] = Field(None, description="First user message (truncated)")
    matched_by: str = Field(
        ..., description="How the session was matched: 'slug', 'uuid_prefix', or 'uuid'"
    )


class ProjectSummary(BaseModel):
    """Summary info for a project."""

    path: str = Field(..., description="Original project path")
    encoded_name: str = Field(..., description="Encoded directory name")
    slug: Optional[str] = Field(None, description="URL-friendly project slug")
    display_name: Optional[str] = Field(None, description="Human-readable project name")
    session_count: int = 0
    agent_count: int = 0
    exists: bool = True
    is_git_repository: bool = Field(
        default=False, description="Whether the project path is a git repository"
    )
    git_root_path: Optional[str] = Field(
        default=None, description="Git repository root path, or None if not in a git repo"
    )
    is_nested_project: bool = Field(
        default=False, description="True if project is inside a git repo but not at the root"
    )
    latest_session_time: Optional[datetime] = Field(
        default=None, description="Start time of the most recent session"
    )


class ProjectDetail(ProjectSummary):
    """Detailed project info with sessions list."""

    sessions: list[SessionSummary] = Field(default_factory=list)


class TimeDistribution(BaseModel):
    """Time-of-day distribution for sessions."""

    morning_pct: float = 0.0  # 06:00-12:00
    afternoon_pct: float = 0.0  # 12:00-18:00
    evening_pct: float = 0.0  # 18:00-24:00
    night_pct: float = 0.0  # 00:00-06:00
    dominant_period: str = ""


class WorkModeDistribution(BaseModel):
    """Distribution of work modes based on tool usage patterns."""

    exploration_pct: float = Field(
        0.0, description="Percentage of exploration activity (Read, Grep, Glob, LS)"
    )
    building_pct: float = Field(
        0.0, description="Percentage of building activity (Write, Edit, NotebookEdit)"
    )
    testing_pct: float = Field(0.0, description="Percentage of testing/execution activity (Bash)")
    primary_mode: str = Field("Unknown", description="The dominant work mode")


class ProjectAnalytics(BaseModel):
    """Analytics data for a project."""

    total_sessions: int = 0
    total_tokens: int = 0
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    total_duration_seconds: float = 0.0
    estimated_cost_usd: float = 0.0
    models_used: dict[str, int] = Field(default_factory=dict)
    cache_hit_rate: float = 0.0
    tools_used: dict[str, int] = Field(default_factory=dict)
    sessions_by_date: dict[str, int] = Field(
        default_factory=dict, description="Date string -> session count"
    )
    projects_active: int = Field(
        default=0, description="Number of projects with sessions in the period"
    )
    # Extended analytics fields
    temporal_heatmap: list[list[int]] = Field(
        default_factory=lambda: [[0] * 24 for _ in range(7)],
        description="7x24 matrix: [day_of_week][hour] = session count",
    )
    peak_hours: list[int] = Field(
        default_factory=list, description="Top 3 most active hours (0-23)"
    )
    models_categorized: dict[str, int] = Field(
        default_factory=dict, description="Model usage grouped by category (Opus, Sonnet, etc.)"
    )
    time_distribution: TimeDistribution = Field(
        default_factory=TimeDistribution, description="Time-of-day distribution"
    )
    work_mode_distribution: WorkModeDistribution = Field(
        default_factory=WorkModeDistribution,
        description="Work mode distribution based on tool usage",
    )


class DashboardStats(BaseModel):
    """Lightweight stats for homepage terminal display."""

    period: str = Field("this_week", description="Time period for stats")
    start_date: str = Field(..., description="Start of period (ISO date YYYY-MM-DD)")
    end_date: str = Field(..., description="End of period (ISO date YYYY-MM-DD)")
    sessions_count: int = Field(0, description="Sessions in the period")
    projects_active: int = Field(0, description="Projects with sessions in the period")
    duration_seconds: float = Field(0.0, description="Total time spent in seconds")


class BranchSummary(BaseModel):
    """Summary of branch activity for a project."""

    name: str = Field(..., description="Branch name")
    session_count: int = Field(0, description="Number of sessions on this branch")
    last_active: Optional[datetime] = Field(
        None, description="Most recent session timestamp on this branch"
    )
    is_active: bool = Field(False, description="True if branch was used in the most recent session")


class ProjectBranchesResponse(BaseModel):
    """Aggregated branch information for a project."""

    branches: list[BranchSummary] = Field(
        default_factory=list, description="All branches with session counts"
    )
    active_branches: list[str] = Field(
        default_factory=list, description="Branches used in the most recent session"
    )
    sessions_by_branch: dict[str, list[str]] = Field(
        default_factory=dict, description="Branch name -> list of session UUIDs"
    )


class InitialPrompt(BaseModel):
    """Initial prompt for a session or agent."""

    content: str = Field(..., description="First user message content")
    timestamp: datetime = Field(..., description="When the prompt was sent")


class TimelineEvent(BaseModel):
    """A single event in a session timeline."""

    id: str = Field(..., description="Unique identifier for the event")
    event_type: Literal[
        "prompt",
        "tool_call",
        "subagent_spawn",
        "thinking",
        "response",
        "todo_update",
        "skill_invocation",
        "command_invocation",
        "builtin_command",
    ] = Field(..., description="Type of timeline event")
    timestamp: datetime = Field(..., description="When the event occurred")
    actor: str = Field(
        ..., description="Who triggered the event: 'user', 'session', or subagent agentId"
    )
    actor_type: Literal["user", "session", "subagent"] = Field(..., description="Type of actor")
    title: str = Field(..., description="Short summary of the event")
    summary: Optional[str] = Field(None, description="Preview text or details")
    metadata: dict = Field(default_factory=dict, description="Tool-specific data for expansion")


# =============================================================================
# Subagent Session View Schemas
# =============================================================================


class ConversationContext(BaseModel):
    """Shared context for conversation views (sessions and subagents)."""

    project_encoded_name: str = Field(..., description="Encoded project directory name")
    parent_session_uuid: Optional[str] = Field(
        None, description="UUID of parent session (for subagents)"
    )
    parent_session_slug: Optional[str] = Field(
        None, description="Slug of parent session (for subagents)"
    )


class SubagentSessionDetail(BaseModel):
    """
    Detailed information about a subagent's conversation.

    This mirrors SessionDetail but for subagent JSONL files, enabling
    the same level of detail in the Agent Session View.
    """

    agent_id: str = Field(..., description="Agent short hex ID (e.g., 'a5793c3')")
    slug: Optional[str] = Field(None, description="Session slug inherited from parent")
    is_subagent: bool = Field(True, description="Always true for subagent sessions")
    context: ConversationContext = Field(..., description="Navigation context")

    # Conversation metrics
    message_count: int = Field(0, description="Total messages in subagent conversation")
    start_time: Optional[datetime] = Field(None, description="First message timestamp")
    end_time: Optional[datetime] = Field(None, description="Last message timestamp")
    duration_seconds: Optional[float] = Field(None, description="Conversation duration")

    # Token analytics
    total_input_tokens: int = Field(0, description="Total input tokens used")
    total_output_tokens: int = Field(0, description="Total output tokens used")
    cache_hit_rate: float = Field(0.0, description="Proportion of tokens served from cache")
    total_cost: float = Field(0.0, description="Estimated cost in USD")

    # Tool usage
    tools_used: dict[str, int] = Field(default_factory=dict, description="Tool name -> usage count")

    # Skill and command usage (extracted from Skill tool inputs)
    skills_used: dict[str, int] = Field(
        default_factory=dict, description="Skill name -> usage count"
    )
    commands_used: dict[str, int] = Field(
        default_factory=dict, description="Command name -> usage count"
    )

    # Context
    git_branches: list[str] = Field(
        default_factory=list, description="Git branches touched during subagent work"
    )
    working_directories: list[str] = Field(
        default_factory=list, description="Working directories accessed"
    )

    # Subagent-specific metadata
    subagent_type: Optional[str] = Field(
        None, description="Type of subagent: Explore, Plan, Bash, or custom"
    )
    initial_prompt: Optional[str] = Field(
        None, description="First user message to subagent (truncated)"
    )


# =============================================================================
# Agent and Skill Schemas
# =============================================================================


class AgentSummary(BaseModel):
    """Summary of a custom agent markdown file."""

    name: str = Field(..., description="Agent name (filename without .md extension)")
    size_bytes: int = Field(..., description="File size in bytes")
    modified_at: datetime = Field(..., description="Last modification time")


class AgentDetail(AgentSummary):
    """Detailed agent information including content."""

    content: str = Field(..., description="Full markdown content of the agent file")


class AgentCreateRequest(BaseModel):
    """Request body for creating/updating an agent."""

    content: str = Field(
        ..., description="Markdown content for the agent", min_length=1, max_length=100_000
    )


class AgentInfo(BaseModel):
    """Detailed information about an agent (including plugin agents)."""

    name: str = Field(..., description="Agent name")
    description: Optional[str] = Field(None, description="Agent description from frontmatter")
    capabilities: Optional[list[str]] = Field(
        None, description="Agent capabilities from frontmatter"
    )
    content: Optional[str] = Field(None, description="Full agent content (markdown)")
    is_plugin: bool = Field(..., description="True if this is a plugin agent")
    plugin: Optional[str] = Field(None, description="Plugin name if is_plugin")
    file_path: Optional[str] = Field(None, description="Path to the agent file")


class SkillUsage(BaseModel):
    """Skill usage tracking from Skill tool invocations."""

    name: str = Field(
        ..., description="Skill name (e.g., 'commit' or 'oh-my-claudecode:security-review')"
    )
    count: int = Field(..., description="Number of times the skill was invoked")
    is_plugin: bool = Field(False, description="True if this is a plugin skill (contains ':')")
    plugin: Optional[str] = Field(
        None, description="Plugin name if is_plugin (e.g., 'oh-my-claudecode')"
    )


class CommandUsage(BaseModel):
    """Command usage tracking from user-authored slash commands."""

    name: str = Field(..., description="Command name (e.g., 'commit', 'run-tests')")
    count: int = Field(..., description="Number of times the command was invoked")
    source: str = Field("unknown", description="Source: 'builtin', 'plugin', 'project', 'user', or 'unknown'")
    plugin: Optional[str] = Field(None, description="Plugin name if source == 'plugin'")


class SkillInfo(BaseModel):
    """Detailed information about a skill."""

    name: str = Field(..., description="Skill name")
    description: Optional[str] = Field(None, description="Skill description from frontmatter")
    content: Optional[str] = Field(None, description="Full skill content (markdown)")
    is_plugin: bool = Field(..., description="True if this is a plugin skill")
    plugin: Optional[str] = Field(None, description="Plugin name if is_plugin")
    file_path: Optional[str] = Field(None, description="Path to the skill file")


class SkillSessionsResponse(BaseModel):
    """Response for sessions that used a specific skill."""

    skill_name: str = Field(..., description="Name of the skill")
    sessions: list["SessionWithContext"] = Field(
        default_factory=list, description="Sessions that used this skill"
    )
    total_count: int = Field(0, description="Total number of sessions using this skill")


class SkillTrendItem(BaseModel):
    """Daily usage data point for a skill."""

    date: str = Field(..., description="Date in YYYY-MM-DD format")
    calls: int = Field(0, description="Total calls on this date")
    sessions: int = Field(0, description="Distinct sessions on this date")


class SkillDetailResponse(BaseModel):
    """Detailed skill info with usage stats, trend, and session list."""

    name: str = Field(..., description="Skill name")
    description: Optional[str] = Field(None, description="Skill description from frontmatter")
    content: Optional[str] = Field(None, description="Full skill content (markdown)")
    is_plugin: bool = Field(False, description="True if this is a plugin skill")
    plugin: Optional[str] = Field(None, description="Plugin name if is_plugin")
    file_path: Optional[str] = Field(None, description="Path to the skill file")
    calls: int = Field(0, description="Total invocations")
    main_calls: int = Field(0, description="Calls from main sessions")
    subagent_calls: int = Field(0, description="Calls from subagents")
    session_count: int = Field(0, description="Distinct sessions using this skill")
    first_used: Optional[str] = Field(None, description="First usage date (ISO)")
    last_used: Optional[str] = Field(None, description="Last usage date (ISO)")
    trend: list[SkillTrendItem] = Field(default_factory=list, description="Daily usage trend")
    sessions: list[SessionSummary] = Field(
        default_factory=list, description="Sessions using this skill"
    )
    sessions_total: int = Field(0, description="Total session count (before pagination)")


class AgentSessionsResponse(BaseModel):
    """Response for sessions that used a specific agent type."""

    subagent_type: str = Field(..., description="Agent type identifier")
    sessions: list[SessionSummary] = Field(
        default_factory=list, description="Sessions that used this agent"
    )
    total_count: int = Field(0, description="Total number of sessions using this agent")


class SkillItem(BaseModel):
    """A skill file or directory in the skills tree."""

    name: str = Field(..., description="Name of the file or directory")
    path: str = Field(..., description="Relative path from skills directory")
    type: Literal["file", "directory"] = Field(
        ..., description="Whether this is a file or directory"
    )
    size_bytes: Optional[int] = Field(None, description="File size in bytes (null for directories)")
    modified_at: Optional[datetime] = Field(None, description="Last modification time")


class SkillContent(BaseModel):
    """Detailed content of a skill file."""

    name: str = Field(..., description="Filename")
    path: str = Field(..., description="Relative path from skills directory")
    type: Literal["file"] = Field("file", description="Always 'file' for content responses")
    content: str = Field(..., description="File content")
    size_bytes: int = Field(..., description="File size in bytes")
    modified_at: datetime = Field(..., description="Last modification time")


class SkillUpdateRequest(BaseModel):
    """Request body for updating skill content."""

    path: str = Field(
        ..., description="Relative path to the skill file", min_length=1, max_length=500
    )
    content: str = Field(..., description="New file content", min_length=0, max_length=1_000_000)


# Command aliases — structurally identical to Skill schemas but semantically distinct.
# Used by routers/commands.py for clarity.
CommandContent = SkillContent
CommandInfo = SkillInfo
CommandItem = SkillItem


# =============================================================================
# Documentation Schemas (About Page)
# =============================================================================


class HookScriptDetail(BaseModel):
    """Detailed view of a hook script including source code."""

    script: Any = Field(..., description="HookScript model with filename, language, etc.")
    source_type: str = Field(..., description="Source type: global, project, or plugin")
    content: Optional[str] = Field(None, description="File content (null if unreadable)")
    size_bytes: Optional[int] = Field(None, description="File size in bytes")
    modified_at: Optional[datetime] = Field(None, description="Last modification time")
    line_count: Optional[int] = Field(None, description="Number of lines in the file")
    error: Optional[str] = Field(
        None, description="Error code: file_not_found, file_too_large, binary_file"
    )


class DocItem(BaseModel):
    """A documentation file metadata."""

    name: str = Field(..., description="Filename (e.g., 'overview.md')")
    title: str = Field(..., description="Human-readable title derived from filename")
    path: str = Field(..., description="Relative path from docs/about/")
    size_bytes: int = Field(..., description="File size in bytes")
    modified_at: datetime = Field(..., description="Last modification time")


class DocsListResponse(BaseModel):
    """List of available documentation files."""

    docs: list[DocItem] = Field(default_factory=list, description="Available documentation files")


class DocContent(BaseModel):
    """Documentation file content."""

    name: str = Field(..., description="Filename")
    path: str = Field(..., description="Relative path from docs/about/")
    content: str = Field(..., description="Markdown content")
    size_bytes: int = Field(..., description="File size in bytes")
    modified_at: datetime = Field(..., description="Last modification time")


# =============================================================================
# Plan Schemas (Phase 3 - Plans Directory)
# =============================================================================


class PlanSummary(BaseModel):
    """Summary info for a plan markdown file."""

    slug: str = Field(..., description="Plan identifier (filename without .md)")
    title: Optional[str] = Field(None, description="First h1 header from markdown, or None")
    preview: str = Field(..., description="First 500 characters of content")
    word_count: int = Field(0, description="Total word count")
    created: datetime = Field(..., description="File creation time")
    modified: datetime = Field(..., description="Last modification time")
    size_bytes: int = Field(0, description="File size in bytes")


class PlanDetail(PlanSummary):
    """Full plan content (extends PlanSummary)."""

    content: str = Field(..., description="Complete markdown content")


class PlanSessionContext(BaseModel):
    """Session context for a plan - links plan to its origin session."""

    session_uuid: str = Field(..., description="UUID of the session that created this plan")
    session_slug: str = Field(..., description="Human-readable session slug")
    project_encoded_name: str = Field(..., description="Encoded project directory name")
    project_path: str = Field(..., description="Original project path")
    git_branches: list[str] = Field(
        default_factory=list, description="Git branches used in the session"
    )


class PlanWithContext(PlanSummary):
    """Plan with its associated session and project context."""

    session_context: Optional[PlanSessionContext] = Field(
        None, description="Session context if plan can be linked to a session"
    )


class PlanListResponse(PaginationMeta):
    """Paginated response for /plans/with-context endpoint."""

    plans: list[PlanWithContext] = Field(
        default_factory=list, description="List of plans with context"
    )


class PlanRelatedSession(BaseModel):
    """A session that interacted with a plan file (read/write/edit)."""

    session_uuid: str = Field(..., description="UUID of the session")
    session_slug: str = Field(..., description="Human-readable session slug")
    project_encoded_name: str = Field(..., description="Encoded project directory name")
    operation: str = Field(..., description="Type of operation: read, write, or edit")
    timestamp: datetime = Field(..., description="When the operation occurred")


# =============================================================================
# Project Memory Schemas
# =============================================================================


class ProjectMemoryResponse(BaseModel):
    """Response for a project's MEMORY.md file."""

    content: str = Field(..., description="Full markdown content of MEMORY.md")
    word_count: int = Field(0, description="Total word count")
    size_bytes: int = Field(0, description="File size in bytes")
    modified: datetime = Field(..., description="Last modification time")
    exists: bool = Field(True, description="Whether the memory file exists")


# =============================================================================
# Live Session Schemas
# =============================================================================


class LiveSessionSummary(BaseModel):
    """Summary of a live session for list display."""

    session_id: str = Field(..., description="Session UUID")
    project_slug: Optional[str] = Field(None, description="URL-friendly project slug")
    state: Literal["STARTING", "LIVE", "WAITING", "STOPPED", "STALE", "ENDED"] = Field(
        ..., description="Current session state"
    )
    status: Literal["starting", "active", "idle", "waiting", "stopped", "stale", "ended"] = Field(
        ..., description="Computed session status based on state and activity"
    )

    # Project context
    cwd: str = Field(..., description="Current working directory")
    project_encoded_name: Optional[str] = Field(None, description="Encoded project name")

    # Timing
    started_at: datetime = Field(..., description="When session started")
    updated_at: datetime = Field(..., description="Last activity timestamp")
    duration_seconds: float = Field(..., description="Current session duration")
    idle_seconds: float = Field(..., description="Seconds since last activity")

    # Hook tracking
    last_hook: str = Field(..., description="Last hook that updated state")
    permission_mode: str = Field("default", description="Current permission mode")

    # End state (only for ENDED sessions)
    end_reason: Optional[str] = Field(None, description="Reason for session end")

    # Session stats (populated from JSONL for live stats updates)
    message_count: Optional[int] = Field(None, description="Current message count from session")
    subagent_count: Optional[int] = Field(None, description="Number of subagents spawned")
    slug: Optional[str] = Field(None, description="Session slug/name")

    # Transcript validation
    transcript_exists: bool = Field(
        True, description="Whether the session JSONL transcript file exists on disk"
    )

    # Rich subagent tracking (from hooks)
    subagents: Optional[Dict[str, Any]] = Field(
        None, description="Full subagent details keyed by agent_id"
    )
    active_subagent_count: Optional[int] = Field(
        None, description="Count of currently running subagents (from hooks)"
    )
    total_subagent_count: Optional[int] = Field(
        None, description="Total subagents tracked (running + completed)"
    )
    session_ids: List[str] = Field(
        default_factory=list,
        description="All session UUIDs that have been part of this slug's lifecycle (for resumed sessions)",
    )


class LiveSessionsResponse(BaseModel):
    """Response for listing live sessions."""

    total: int = Field(..., description="Total number of tracked sessions")
    active_count: int = Field(..., description="Sessions with active status")
    idle_count: int = Field(..., description="Sessions considered idle")
    ended_count: int = Field(..., description="Sessions that have ended")
    sessions: list[LiveSessionSummary] = Field(
        default_factory=list, description="All tracked sessions"
    )


# ============================================================================
# Session Relationship Schemas
# ============================================================================


class SessionRelationshipSchema(BaseModel):
    """
    Represents a directed relationship between two sessions.

    Used for displaying session chains and context inheritance.
    """

    source_uuid: str = Field(..., description="Source session UUID (parent/provider)")
    target_uuid: str = Field(..., description="Target session UUID (child/recipient)")
    relationship_type: Literal["resumed_from", "provided_context_to", "forked_from"] = Field(
        ..., description="Type of relationship between sessions"
    )
    source_slug: Optional[str] = Field(None, description="Source session slug")
    target_slug: Optional[str] = Field(None, description="Target session slug")
    detected_via: str = Field(..., description="Detection method: 'leaf_uuid'")
    confidence: float = Field(
        ..., ge=0.0, le=1.0, description="Confidence score 0.0-1.0 based on detection method"
    )
    source_end_time: Optional[datetime] = Field(None, description="When source session ended")
    target_start_time: Optional[datetime] = Field(None, description="When target session started")


class SessionChainNodeSchema(BaseModel):
    """
    A node in a session chain, representing one session's position.

    Used for frontend display of session chains/families.
    """

    uuid: str = Field(..., description="Session UUID")
    slug: Optional[str] = Field(None, description="Session slug if available")
    start_time: Optional[datetime] = Field(None, description="Session start time")
    end_time: Optional[datetime] = Field(None, description="Session end time")
    is_current: bool = Field(False, description="True if this is the session being viewed")
    chain_depth: int = Field(
        0, description="Depth in chain: 0=root ancestor, 1=child, 2=grandchild, etc."
    )
    parent_uuid: Optional[str] = Field(None, description="Parent session UUID in chain")
    children_uuids: list[str] = Field(
        default_factory=list, description="Child session UUIDs that resumed from this session"
    )
    was_compacted: bool = Field(False, description="True if session underwent context compaction")
    is_continuation_marker: bool = Field(
        False, description="True if session is a continuation marker (no real content)"
    )
    message_count: int = Field(0, description="Number of messages in session")
    initial_prompt: Optional[str] = Field(None, description="First user prompt (truncated)")

    # Resume detection metadata
    resume_detected_via: Optional[str] = Field(
        None, description="How resume was detected: 'leaf_uuid' or None"
    )


class SessionChainSchema(BaseModel):
    """
    Complete session chain for a given session.

    Contains the full tree of related sessions from root ancestor
    to all leaf descendants.
    """

    current_session_uuid: str = Field(
        ..., description="UUID of the session this chain was requested for"
    )
    nodes: list[SessionChainNodeSchema] = Field(
        default_factory=list, description="All sessions in the chain"
    )
    root_uuid: Optional[str] = Field(None, description="UUID of the root ancestor session")
    total_sessions: int = Field(0, description="Total number of sessions in chain")
    max_depth: int = Field(0, description="Maximum chain depth (0 = single session)")
    total_compactions: int = Field(0, description="Total compaction events across all sessions")


class SessionChainInfo(BaseModel):
    """
    Lightweight chain info for session list views.

    Embedded in SessionSummary to show chain context without full chain data.
    """

    chain_id: str = Field(..., description="Identifier for the chain (slug or root UUID)")
    chain_position: int = Field(0, description="Position in chain (0=first/root, 1=second, etc.)")
    chain_length: int = Field(1, description="Total sessions in this chain")
    is_root: bool = Field(False, description="True if this is the first session in the chain")
    is_latest: bool = Field(
        False, description="True if this is the most recent session in the chain"
    )
    parent_uuid: Optional[str] = Field(None, description="UUID of parent session (None if root)")
    detected_via: str = Field(
        "none", description="How chain was detected: 'leaf_uuid', 'slug_match', 'none'"
    )


class ProjectChainsResponse(BaseModel):
    """
    Batch chain data for all sessions in a project.

    Used to annotate session list views with chain badges without N+1 queries.
    """

    project_encoded_name: str = Field(..., description="Encoded project directory name")

    # Map: session_uuid -> chain info
    session_chains: dict[str, SessionChainInfo] = Field(
        default_factory=dict, description="Chain info for each session UUID"
    )

    # Unique chains (grouped by slug or root)
    chains: list[SessionChainSchema] = Field(
        default_factory=list, description="All unique chains in the project"
    )

    # Statistics
    total_sessions: int = Field(0, description="Total sessions in project")
    chained_sessions: int = Field(0, description="Sessions that are part of a chain")
    single_sessions: int = Field(0, description="Sessions with no chain (standalone)")


# =============================================================================
# Agent Usage Analytics Schemas
# =============================================================================


class AgentCategory(str, Enum):
    """Categories of agents based on their source.

    - builtin: Hardcoded Claude Code agents (Explore, Plan, Bash, etc.)
    - plugin: From installed plugins, format "plugin-name:agent-name"
    - custom: Global custom agents defined in ~/.claude/agents/
    - project: Project-level agents defined in {project}/.claude/agents/
    - unknown: No definition found (deleted agent, one-off invocation, etc.)
    """

    ALL = "all"
    BUILTIN = "builtin"
    PLUGIN = "plugin"
    CUSTOM = "custom"
    PROJECT = "project"
    CLAUDE_TAX = "claude_tax"
    UNKNOWN = "unknown"


class AgentUsageSummary(BaseModel):
    """Aggregated stats for a single agent type."""

    subagent_type: str = Field(
        ..., description="Agent type identifier (e.g., 'Explore', 'feature-dev:code-reviewer')"
    )
    plugin_source: Optional[str] = Field(
        None, description="Plugin name extracted from 'plugin:agent' format"
    )
    agent_name: str = Field(..., description="Display name of the agent")
    category: AgentCategory = Field(
        ..., description="Agent category (builtin, plugin, custom, project)"
    )

    # Stats
    total_runs: int = Field(0, description="Total number of times this agent was invoked")
    total_cost_usd: float = Field(0.0, description="Total estimated cost in USD")
    total_input_tokens: int = Field(0, description="Total input tokens used")
    total_output_tokens: int = Field(0, description="Total output tokens used")
    avg_duration_seconds: float = Field(0.0, description="Average duration per invocation")
    success_rate: float = Field(1.0, description="Success rate (0.0-1.0)")

    # Context
    projects_used_in: list[str] = Field(
        default_factory=list, description="List of project encoded names where this agent was used"
    )
    first_used: Optional[datetime] = Field(None, description="First invocation timestamp")
    last_used: Optional[datetime] = Field(None, description="Most recent invocation timestamp")

    # Definition (if custom agent exists)
    has_definition: bool = Field(False, description="True if a .md agent definition file exists")


class AgentUsageDetail(AgentUsageSummary):
    """Extended detail for agent detail page."""

    top_tools: dict[str, int] = Field(default_factory=dict, description="Tool name -> usage count")
    top_skills: dict[str, int] = Field(
        default_factory=dict, description="Skill name -> usage count"
    )
    top_commands: dict[str, int] = Field(
        default_factory=dict, description="Command name -> usage count"
    )
    usage_by_project: dict[str, int] = Field(
        default_factory=dict, description="Project encoded name -> run count"
    )


class AgentInvocation(BaseModel):
    """Single agent invocation record."""

    agent_id: str = Field(..., description="Agent short hex ID")
    session_uuid: str = Field(..., description="Parent session UUID")
    project_encoded_name: str = Field(..., description="Project where invocation occurred")
    project_slug: Optional[str] = Field(None, description="URL-friendly project slug")
    invoked_at: Optional[datetime] = Field(None, description="When the agent was invoked")
    duration_seconds: Optional[float] = Field(None, description="Invocation duration")
    input_tokens: int = Field(0, description="Input tokens used")
    output_tokens: int = Field(0, description="Output tokens used")
    cost_usd: float = Field(0.0, description="Estimated cost for this invocation")
    status: str = Field("completed", description="Invocation status: completed, error, cancelled")
    description: Optional[str] = Field(None, description="Initial prompt/description for the agent")


class AgentUsageListResponse(PaginationMeta):
    """Response for /agents/usage endpoint."""

    agents: list[AgentUsageSummary] = Field(
        default_factory=list, description="List of agent usage summaries"
    )
    total_runs: int = Field(0, description="Total runs across all agents")
    total_cost_usd: float = Field(0.0, description="Total cost across all agents")
    by_category: dict[str, int] = Field(default_factory=dict, description="Agent count by category")


class AgentInvocationHistoryResponse(PaginationMeta):
    """Paginated response for /agents/usage/{subagent_type}/history endpoint."""

    items: list[AgentInvocation] = Field(
        default_factory=list, description="List of agent invocations"
    )


class PluginGroup(BaseModel):
    """Agents grouped by plugin."""

    plugin_name: str = Field(..., description="Plugin name (e.g., 'feature-dev')")
    agents: list[AgentUsageSummary] = Field(
        default_factory=list, description="Agents in this plugin"
    )
    total_runs: int = Field(0, description="Total runs for all agents in this plugin")
    total_cost_usd: float = Field(0.0, description="Total cost for this plugin")


# =============================================================================
# Plugin Installation Schemas (Phase 4 - Plugins Directory)
# =============================================================================


# =============================================================================
# MCP Tools Schemas
# =============================================================================


class McpToolSummary(BaseModel):
    """Summary of a single MCP tool within a server."""

    name: str = Field(..., description="Short tool name (e.g., 'query', 'browser_click')")
    full_name: str = Field(..., description="Full MCP tool name (e.g., 'mcp__coderoots__query')")
    calls: int = Field(0, description="Total invocation count")
    session_count: int = Field(0, description="Number of sessions that used this tool")
    main_calls: int = Field(0, description="Calls from main session")
    subagent_calls: int = Field(0, description="Calls from subagents")


class McpServer(BaseModel):
    """Summary of an MCP server and its tools."""

    name: str = Field(..., description="Server identifier (e.g., 'coderoots')")
    display_name: str = Field(..., description="Human-readable name (e.g., 'Coderoots')")
    source: str = Field(..., description="Server source: 'plugin', 'standalone', or 'builtin'")
    plugin_name: Optional[str] = Field(None, description="Plugin name if source is 'plugin'")
    tool_count: int = Field(0, description="Number of distinct tools")
    total_calls: int = Field(0, description="Total invocations across all tools")
    session_count: int = Field(0, description="Distinct sessions using this server")
    main_calls: int = Field(0, description="Total calls from main sessions")
    subagent_calls: int = Field(0, description="Total calls from subagents")
    first_used: Optional[str] = Field(None, description="First usage date (ISO)")
    last_used: Optional[str] = Field(None, description="Last usage date (ISO)")
    tools: List[McpToolSummary] = Field(default_factory=list, description="Tools in this server")


class McpToolsOverview(BaseModel):
    """Overview of all MCP servers and tools."""

    total_servers: int = Field(0, description="Number of distinct MCP servers")
    total_tools: int = Field(0, description="Number of distinct MCP tools")
    total_calls: int = Field(0, description="Total MCP tool invocations")
    total_sessions: int = Field(0, description="Total sessions using any MCP tool")
    servers: List[McpServer] = Field(default_factory=list, description="All MCP servers")


class McpServerTrend(BaseModel):
    """Daily usage data point for an MCP server."""

    date: str = Field(..., description="Date in YYYY-MM-DD format")
    calls: int = Field(0, description="Total calls on this date")
    sessions: int = Field(0, description="Distinct sessions on this date")
    main_calls: int = Field(0, description="Main session calls on this date")
    subagent_calls: int = Field(0, description="Subagent calls on this date")


class McpServerDetail(McpServer):
    """Detailed MCP server info with trend and session list."""

    trend: List[McpServerTrend] = Field(default_factory=list, description="Daily usage trend")
    sessions: List[SessionSummary] = Field(
        default_factory=list, description="Sessions using this server (paginated)"
    )
    sessions_total: int = Field(0, description="Total session count (before pagination)")


class McpToolDetail(BaseModel):
    """Detailed stats for a single MCP tool."""

    name: str = Field(..., description="Short tool name (e.g., 'query')")
    full_name: str = Field(..., description="Full MCP tool name (e.g., 'mcp__coderoots__query')")
    server_name: str = Field(..., description="Server identifier")
    server_display_name: str = Field(..., description="Human-readable server name")
    calls: int = Field(0, description="Total invocations")
    main_calls: int = Field(0, description="Calls from main session")
    subagent_calls: int = Field(0, description="Calls from subagents")
    session_count: int = Field(0, description="Distinct sessions using this tool")
    first_used: Optional[str] = Field(None, description="First usage date (ISO)")
    last_used: Optional[str] = Field(None, description="Last usage date (ISO)")
    trend: List[McpServerTrend] = Field(default_factory=list, description="Daily usage trend")
    sessions: List[SessionSummary] = Field(
        default_factory=list, description="Sessions using this tool (paginated)"
    )
    sessions_total: int = Field(0, description="Total session count (before pagination)")


class PluginInstallationSchema(BaseModel):
    """API response for a single plugin installation."""

    plugin_name: str = Field(..., description="The key like 'github@claude-plugins-official'")
    scope: str = Field(..., description="Installation scope: 'user' or 'project'")
    install_path: str = Field(..., description="Absolute path to the plugin installation")
    version: str = Field(..., description="Installed plugin version")
    installed_at: datetime = Field(..., description="When the plugin was first installed")
    last_updated: datetime = Field(..., description="Last time the plugin was updated")


class PluginSummary(BaseModel):
    """Summary of a plugin with all its installations."""

    name: str = Field(..., description="Plugin identifier (e.g., 'github@claude-plugins-official')")
    installation_count: int = Field(
        0, description="Total number of installations (user + projects)"
    )
    scopes: list[str] = Field(
        default_factory=list, description="All scopes this plugin is installed in"
    )
    latest_version: str = Field(..., description="Most recent version across all installations")
    latest_update: Optional[datetime] = Field(
        None, description="Most recent update timestamp across all installations"
    )
    agent_count: int = Field(0, description="Number of agents this plugin provides")
    skill_count: int = Field(0, description="Number of skills this plugin provides")
    command_count: int = Field(0, description="Number of commands this plugin provides")
    total_runs: int = Field(0, description="Combined agent + skill usage count")
    estimated_cost_usd: float = Field(0.0, description="Total estimated cost")
    days_since_update: int = Field(0, description="Days since last update")
    description: Optional[str] = Field(None, description="Plugin description from metadata")
    is_official: bool = Field(False, description="True if from official marketplace")


class PluginsOverview(BaseModel):
    """Overview of all installed plugins."""

    version: int = Field(..., description="plugins.json schema version")
    total_plugins: int = Field(0, description="Total number of unique plugins")
    total_installations: int = Field(
        0, description="Total number of installations (counting user + all projects)"
    )
    plugins: list[PluginSummary] = Field(
        default_factory=list, description="List of plugin summaries"
    )


class PluginCapabilities(BaseModel):
    """Plugin capabilities - agents, skills, commands, hooks, MCP tools."""

    plugin_name: str = Field(..., description="Plugin identifier")
    agents: list[str] = Field(
        default_factory=list, description="Agent names provided by this plugin"
    )
    skills: list[str] = Field(
        default_factory=list, description="Skill names provided by this plugin"
    )
    commands: list[str] = Field(
        default_factory=list, description="Command names provided by this plugin"
    )
    mcp_tools: list[str] = Field(
        default_factory=list, description="MCP tool servers provided by this plugin"
    )
    hooks: list[str] = Field(default_factory=list, description="Hook types provided by this plugin")


class PluginCommandDetail(BaseModel):
    """Detail for a single plugin command including its markdown content."""

    name: str = Field(..., description="Command name (e.g., 'commit')")
    content: Optional[str] = Field(None, description="Markdown content of the command file")


class PluginCommandsResponse(BaseModel):
    """Response for the plugin commands endpoint."""

    plugin_name: str = Field(..., description="Plugin identifier")
    commands: list[PluginCommandDetail] = Field(
        default_factory=list, description="List of commands with their content"
    )


class DailyUsage(BaseModel):
    """Daily usage data point for trend analysis."""

    date: str = Field(..., description="Date in YYYY-MM-DD format")
    agent_runs: int = Field(0, description="Agent invocations on this date")
    skill_invocations: int = Field(0, description="Skill invocations on this date")
    mcp_tool_calls: int = Field(0, description="MCP tool calls on this date")
    cost_usd: float = Field(0.0, description="Estimated cost for this date")


class PluginUsageStats(BaseModel):
    """Usage analytics for a specific plugin."""

    plugin_name: str = Field(..., description="Plugin identifier")
    total_agent_runs: int = Field(0, description="Total agent invocations")
    total_skill_invocations: int = Field(0, description="Total skill invocations")
    total_mcp_tool_calls: int = Field(0, description="Total MCP tool invocations")
    estimated_cost_usd: float = Field(0.0, description="Total estimated cost")
    by_agent: dict[str, int] = Field(default_factory=dict, description="Agent name -> run count")
    by_skill: dict[str, int] = Field(
        default_factory=dict, description="Skill name -> invocation count"
    )
    by_mcp_tool: dict[str, int] = Field(
        default_factory=dict, description="MCP tool short name -> call count"
    )
    by_agent_daily: dict[str, dict[str, int]] = Field(
        default_factory=dict, description="Agent name -> {date -> count}"
    )
    by_skill_daily: dict[str, dict[str, int]] = Field(
        default_factory=dict, description="Skill name -> {date -> count}"
    )
    by_mcp_tool_daily: dict[str, dict[str, int]] = Field(
        default_factory=dict, description="MCP tool name -> {date -> count}"
    )
    trend: list[DailyUsage] = Field(default_factory=list, description="Usage trend over time")
    first_used: Optional[datetime] = Field(None, description="First usage timestamp")
    last_used: Optional[datetime] = Field(None, description="Most recent usage timestamp")


class UsageTrendItem(BaseModel):
    """Single data point in a usage trend."""

    date: str = Field(..., description="Date in YYYY-MM-DD format")
    count: int = Field(0, description="Usage count for this date")


class UsageTrendResponse(BaseModel):
    """Generic usage trend response for skills and agents."""

    total: int = Field(0, description="Total usage count")
    by_item: dict[str, int] = Field(default_factory=dict, description="Item name -> usage count")
    trend: list[UsageTrendItem] = Field(default_factory=list, description="Daily usage trend")
    trend_by_item: dict[str, list[UsageTrendItem]] = Field(
        default_factory=dict,
        description="Per-item daily trend for top items (item name -> daily counts)",
    )
    first_used: Optional[datetime] = Field(None, description="First usage timestamp")
    last_used: Optional[datetime] = Field(None, description="Most recent usage timestamp")


class PluginDetail(BaseModel):
    """Detailed view of a specific plugin."""

    name: str = Field(..., description="Plugin identifier (e.g., 'github@claude-plugins-official')")
    installations: list[PluginInstallationSchema] = Field(
        default_factory=list, description="All installations of this plugin across scopes"
    )
    description: Optional[str] = Field(None, description="Plugin description")
    capabilities: Optional[PluginCapabilities] = Field(
        None, description="What this plugin provides"
    )
    usage: Optional[PluginUsageStats] = Field(None, description="Usage analytics")


# =============================================================================
# All Sessions Listing Schemas (Global Sessions Page)
# =============================================================================


class SessionWithContext(SessionSummary):
    """
    Session summary with full project context for global session listings.

    Extends SessionSummary with project display information needed when
    showing sessions outside of a project context (e.g., /sessions page).
    """

    project_path: str = Field(..., description="Original project path for display")
    project_name: str = Field(..., description="Human-readable project name (last path component)")
    project_slug: Optional[str] = Field(None, description="URL-friendly project slug")


class ProjectFilterOption(BaseModel):
    """Project option for filter dropdowns."""

    encoded_name: str = Field(..., description="Encoded project directory name")
    path: str = Field(..., description="Original project path")
    name: str = Field(..., description="Human-readable project name")
    slug: Optional[str] = Field(None, description="URL-friendly project slug")
    display_name: Optional[str] = Field(None, description="Human-readable project name")
    session_count: int = Field(0, description="Number of sessions in this project")


class StatusFilterOption(BaseModel):
    """Status option for filter dropdowns."""

    value: str = Field(..., description="Status value for API queries")
    label: str = Field(..., description="Human-readable label for display")
    count: int = Field(0, description="Number of sessions with this status")


class AllSessionsResponse(PaginationMeta):
    """
    Response for GET /sessions/all endpoint.

    Provides sessions across all projects with filter options.
    """

    sessions: list[SessionWithContext] = Field(
        default_factory=list, description="Sessions with project context"
    )
    projects: list[ProjectFilterOption] = Field(
        default_factory=list, description="Available projects for filtering"
    )
    status_options: list[StatusFilterOption] = Field(
        default_factory=list, description="Status filter options with counts"
    )
    applied_filters: dict = Field(default_factory=dict, description="Echo of applied filter values")

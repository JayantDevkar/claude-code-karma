"""
Pydantic models for Claude Code local storage (~/.claude/).

This package provides typed models for parsing and querying Claude Code's
local storage structure, enabling activity tracking and analytics.

Hierarchy:
    Project
    ├── Session (UUID.jsonl)
    │   ├── Message (UserMessage, AssistantMessage, FileHistorySnapshot)
    │   ├── Agent (subagents)
    │   ├── ToolResult
    │   └── TodoItem
    └── Agent (standalone agents)

Example usage:
    from models import Project, Session

    # Load a project
    project = Project.from_path("/Users/me/my-project")

    # List all sessions
    for session in project.list_sessions():
        print(f"Session {session.uuid}: {session.message_count} messages")

        # Get usage stats
        usage = session.get_usage_summary()
        print(f"  Tokens: {usage.total_tokens}")

        # List tools used
        for tool, count in session.get_tools_used().items():
            print(f"  {tool}: {count} calls")
"""

from .agent import Agent
from .batch_loader import BatchSessionLoader, load_sessions_metadata_batch
from .bounded_cache import BoundedCache, BoundedCacheConfig
from .content import (
    ContentBlock,
    TextBlock,
    ThinkingBlock,
    ToolUseBlock,
    parse_content_block,
)
from .conversation import ConversationEntity, is_agent, is_session
from .hook import (
    HookEventDetail,
    HookEventSchema,
    HookEventSummary,
    HookRegistration,
    HookScript,
    HookSource,
    HookSourceDetail,
    HooksOverview,
    HookStats,
    RelatedEvent,
    build_hooks_overview,
    discover_hooks,
    discover_hooks_cached,
    get_event_schema,
)
from .jsonl_utils import iter_messages_from_jsonl
from .message import (
    AssistantMessage,
    CompactBoundaryMessage,
    FileHistorySnapshot,
    FileSnapshot,
    Message,
    MessageBase,
    SessionTitleMessage,
    UserMessage,
    parse_message,
)
from .plan import Plan, get_plans_dir, load_all_plans, load_plan
from .plugin import (
    InstalledPlugins,
    PluginInstallation,
    get_plugins_file,
    load_installed_plugins,
)
from .project import Project
from .session import Session
from .session_index import SessionIndex, SessionIndexEntry
from .task import Task, load_task_from_file, load_tasks_from_directory
from .todo import TodoItem, load_todos_from_file
from .tool_result import ToolResult
from .usage import TokenUsage

# Async session is optional (requires aiofiles)
try:
    from .async_session import (
        AsyncSession,
        calculate_analytics_async,
        get_sessions_metadata_async,
    )

    ASYNC_AVAILABLE = True
except ImportError:
    AsyncSession = None  # type: ignore
    calculate_analytics_async = None  # type: ignore
    get_sessions_metadata_async = None  # type: ignore
    ASYNC_AVAILABLE = False

__all__ = [
    # Core entities
    "Project",
    "Session",
    "Agent",
    # Protocol
    "ConversationEntity",
    "is_agent",
    "is_session",
    # Messages
    "Message",
    "MessageBase",
    "UserMessage",
    "AssistantMessage",
    "CompactBoundaryMessage",
    "FileHistorySnapshot",
    "FileSnapshot",
    "SessionTitleMessage",
    "parse_message",
    # Content blocks
    "ContentBlock",
    "TextBlock",
    "ThinkingBlock",
    "ToolUseBlock",
    "parse_content_block",
    # Supporting models
    "TokenUsage",
    "ToolResult",
    "TodoItem",
    "load_todos_from_file",
    "Task",
    "load_task_from_file",
    "load_tasks_from_directory",
    "SessionIndex",
    "SessionIndexEntry",
    # Phase 3: Plans
    "Plan",
    "get_plans_dir",
    "load_plan",
    "load_all_plans",
    # Phase 5: Hooks
    "HookRegistration",
    "HookScript",
    "HookSource",
    "HookEventSummary",
    "HookEventSchema",
    "HookEventDetail",
    "HookSourceDetail",
    "HookStats",
    "HooksOverview",
    "RelatedEvent",
    "discover_hooks",
    "discover_hooks_cached",
    "build_hooks_overview",
    "get_event_schema",
    # Phase 4: Plugins
    "PluginInstallation",
    "InstalledPlugins",
    "get_plugins_file",
    "load_installed_plugins",
    # Utilities
    "iter_messages_from_jsonl",
    # Phase 4: Batch and async utilities
    "BatchSessionLoader",
    "load_sessions_metadata_batch",
    "AsyncSession",
    "calculate_analytics_async",
    "get_sessions_metadata_async",
    "ASYNC_AVAILABLE",
    # Cache utilities
    "BoundedCache",
    "BoundedCacheConfig",
]

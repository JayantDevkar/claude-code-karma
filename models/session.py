"""
Session model for Claude Code main sessions.

Sessions are stored as {uuid}.jsonl in ~/.claude/projects/{project}/
with related resources in {uuid}/ subdirectory.
"""

from __future__ import annotations

import json
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, Iterator, List, Optional, Set

from pydantic import BaseModel, ConfigDict, Field

from command_helpers import (
    classify_invocation,
    detect_slash_commands_in_text,
    parse_command_from_content,
)

from .agent import Agent
from .base_cache import (
    BaseCache,
    clear_all_caches,
    clear_cache,
    get_file_mtime,
    get_or_create_cache,
    is_cache_stale,
)
from .bounded_cache import BoundedCache
from .jsonl_utils import iter_messages_from_jsonl
from .message import (
    AssistantMessage,
    CompactBoundaryMessage,
    FileHistorySnapshot,
    Message,
    ProgressMessage,
    QueueOperationMessage,
    SessionTitleMessage,
    UserMessage,
)
from .task import Task, load_tasks_from_directory, reconstruct_tasks_from_jsonl
from .todo import TodoItem, load_todos_from_file
from .tool_result import ToolResult
from .usage import TokenUsage

if TYPE_CHECKING:
    pass


class SessionCache(BaseCache):
    """
    Mutable cache for session's computed properties.

    Used to avoid redundant JSONL file I/O when accessing properties like
    start_time, end_time, slug, etc. multiple times on the same Session.

    Inherits file mtime tracking from BaseCache for automatic cache
    invalidation when the underlying JSONL file is modified.

    Uses __slots__ for memory efficiency.
    """

    __slots__ = (
        "start_time",
        "end_time",
        "slug",
        "usage_summary",
        "tools_used",
        "skills_used",
        "commands_used",
        "git_branches",
        "working_dirs",
        "models_used",
        "message_count",
        "total_cost",
        # Continuation session detection
        "user_message_count",
        "assistant_message_count",
        "file_snapshot_count",
        "summary_count",  # SessionTitleMessage count (type: "summary")
        "compact_boundary_count",  # CompactBoundaryMessage count (real compaction)
        # Project context (summaries from PREVIOUS sessions loaded at start)
        "project_context_summaries",
        "project_context_leaf_uuids",
        # Session titles (type: "summary" - NOT compaction, just naming)
        "session_titles",
        # Session compaction (type: "system", subtype: "compact_boundary")
        "was_compacted",
        "compaction_summary_count",
        "compaction_details",  # Structured: list of dicts with summary, trigger, pre_tokens, timestamp
        # Cached tasks (reconstructed from JSONL or loaded from task files)
        "tasks",
    )

    def __init__(self) -> None:
        super().__init__()
        self.start_time: Optional[datetime] = None
        self.end_time: Optional[datetime] = None
        self.slug: Optional[str] = None
        self.usage_summary: Optional[TokenUsage] = None
        self.tools_used: Optional[Dict[str, int]] = None
        self.skills_used: Optional[Dict[str, int]] = None
        self.commands_used: Optional[Dict[str, int]] = None
        self.git_branches: Optional[Set[str]] = None
        self.working_dirs: Optional[Set[str]] = None
        self.models_used: Optional[Set[str]] = None
        self.message_count: Optional[int] = None
        self.total_cost: Optional[float] = None
        # Continuation session detection
        self.user_message_count: int = 0
        self.assistant_message_count: int = 0
        self.file_snapshot_count: int = 0
        self.summary_count: int = 0  # SessionTitleMessage count
        self.compact_boundary_count: int = 0  # CompactBoundaryMessage count
        # Project context (summaries from PREVIOUS sessions loaded at start)
        self.project_context_summaries: Optional[List[str]] = None
        self.project_context_leaf_uuids: Optional[List[str]] = None
        # Session titles (type: "summary" - NOT compaction, just naming)
        self.session_titles: Optional[List[str]] = None
        # Session compaction (type: "system", subtype: "compact_boundary")
        self.was_compacted: bool = False
        self.compaction_summary_count: int = 0
        # Structured compaction details: list of dicts with summary, trigger, pre_tokens, timestamp
        self.compaction_details: Optional[List[Dict[str, Any]]] = None
        # Cached tasks
        self.tasks: Optional[List["Task"]] = None

    def reset(self) -> None:
        """Reset all cache values to initial state."""
        self.start_time = None
        self.end_time = None
        self.slug = None
        self.usage_summary = None
        self.tools_used = None
        self.skills_used = None
        self.commands_used = None
        self.git_branches = None
        self.working_dirs = None
        self.models_used = None
        self.message_count = None
        self.total_cost = None
        self.user_message_count = 0
        self.assistant_message_count = 0
        self.file_snapshot_count = 0
        self.summary_count = 0
        self.compact_boundary_count = 0
        self.project_context_summaries = None
        self.project_context_leaf_uuids = None
        self.session_titles = None
        self.was_compacted = False
        self.compaction_summary_count = 0
        self.compaction_details = None
        self.tasks = None
        super().reset()


# Module-level cache: maps session JSONL path -> SessionCache
# Uses bounded cache with LRU eviction and TTL expiration to prevent unbounded memory growth
# Default: 1000 entries max, 1 hour TTL (configurable via environment variables)
_session_cache: BoundedCache[SessionCache] = BoundedCache()


class Session(BaseModel):
    """
    Represents a Claude Code main session.

    A session consists of:
    - Main JSONL file: {uuid}.jsonl
    - Session folder: {uuid}/ containing:
      - tool-results/toolu_xxx.txt
      - subagents/agent-xxx.jsonl

    External resources linked by UUID:
    - Debug log: ~/.claude/debug/{uuid}.txt
    - File history: ~/.claude/file-history/{uuid}/
    - Todos: ~/.claude/todos/{uuid}-*.json

    Attributes:
        uuid: Session UUID
        jsonl_path: Path to session JSONL file
        claude_base_dir: Base ~/.claude directory for finding related resources
    """

    model_config = ConfigDict(frozen=True)

    uuid: str = Field(..., description="Session UUID")
    jsonl_path: Path = Field(..., description="Path to session JSONL file")
    claude_base_dir: Path = Field(
        default_factory=lambda: Path.home() / ".claude",
        description="Base ~/.claude directory",
    )

    @classmethod
    def from_path(cls, path: Path, claude_base_dir: Optional[Path] = None) -> "Session":
        """
        Create a Session from a JSONL file path.

        Args:
            path: Path to session JSONL file
            claude_base_dir: Optional override for ~/.claude directory

        Returns:
            Session instance
        """
        uuid = path.stem  # Remove .jsonl extension
        base_dir = claude_base_dir or Path.home() / ".claude"
        return cls(uuid=uuid, jsonl_path=path, claude_base_dir=base_dir)

    # =========================================================================
    # Cache management (uses shared base_cache utilities)
    # =========================================================================

    def _get_cache(self) -> SessionCache:
        """Get or create cache for this session."""
        return get_or_create_cache(_session_cache, self.jsonl_path, SessionCache)

    def _get_file_mtime(self) -> Optional[float]:
        """Get file modification time, or None if file doesn't exist."""
        return get_file_mtime(self.jsonl_path)

    def _is_cache_stale(self, cache: SessionCache) -> bool:
        """Check if cache is stale (file has been modified since cache was populated)."""
        return is_cache_stale(cache, self.jsonl_path)

    def _load_metadata(self) -> None:
        """
        Single-pass extraction of all session metadata.

        Loads timestamps, slug, usage stats, tool counts, git branches,
        working directories, and message type counts in a single iteration.
        Automatically invalidates cache if file has been modified.
        """
        cache = self._get_cache()

        # Check if cache is stale and needs refresh
        if self._is_cache_stale(cache):
            cache.reset()

        if cache._metadata_loaded:
            return

        from .content import ToolUseBlock

        # Initialize accumulators
        first_ts: Optional[datetime] = None
        last_ts: Optional[datetime] = None
        slug: Optional[str] = None
        usage = TokenUsage.zero()
        tools: Counter[str] = Counter()
        skills: Counter[str] = Counter()
        commands: Counter[str] = Counter()
        user_prompt_skills: Set[str] = set()
        user_prompt_commands: Set[str] = set()
        git_branches: Set[str] = set()
        working_dirs: Set[str] = set()
        models_used: Set[str] = set()
        message_count = 0
        total_cost = 0.0

        # Message type counters for continuation session detection
        user_msg_count = 0
        assistant_msg_count = 0
        file_snapshot_count = 0
        summary_count = 0  # SessionTitleMessage (type: "summary")
        compact_boundary_count = 0  # CompactBoundaryMessage (real compaction)

        # Use CompactionDetector to detect true compaction events
        # True compaction = CompactBoundaryMessage (type: "system", subtype: "compact_boundary")
        # Session titles = SessionTitleMessage (type: "summary") - NOT compaction!
        from .compaction_detector import CompactionDetector

        compaction_detector = CompactionDetector()

        for msg in self.iter_messages():
            message_count += 1

            # Feed message to compaction detector
            compaction_detector.process(msg)

            # Track message types
            if isinstance(msg, UserMessage):
                user_msg_count += 1
                # Detect commands/skills from <command-message> tags in user prompts
                # These fire when users type /command but may not result in a Skill tool call
                if msg.content:
                    cmd_name, _ = parse_command_from_content(msg.content)
                    # Fallback: detect /command in plain text (hook-triggered skills).
                    # ONLY run on real user prompts — tool results, internal messages,
                    # and system injections contain code/diffs/paths that produce
                    # false positives (e.g. "/plugin:command" in a code comment).
                    if cmd_name is None and not msg.is_tool_result and not msg.is_internal_message:
                        for candidate in detect_slash_commands_in_text(msg.content):
                            # Only detect skills — builtins always have <command-message>
                            # tags when actually invoked, so they're caught above.
                            if classify_invocation(candidate) == "skill":
                                cmd_name = candidate
                                break
                    if cmd_name:
                        kind = classify_invocation(cmd_name)
                        if kind == "skill":
                            user_prompt_skills.add(cmd_name)
                        else:
                            # Both "command" and "builtin" go into commands
                            user_prompt_commands.add(cmd_name)
            elif isinstance(msg, AssistantMessage):
                assistant_msg_count += 1
            elif isinstance(msg, FileHistorySnapshot):
                file_snapshot_count += 1
            elif isinstance(msg, SessionTitleMessage):
                summary_count += 1
            elif isinstance(msg, CompactBoundaryMessage):
                compact_boundary_count += 1
            elif isinstance(msg, QueueOperationMessage):
                pass  # Counted but no special handling needed
            elif isinstance(msg, ProgressMessage):
                pass  # Counted but no special handling needed

            # Timestamps (skip SessionTitleMessage which has no timestamp)
            if hasattr(msg, "timestamp") and msg.timestamp:
                if first_ts is None:
                    first_ts = msg.timestamp
                last_ts = msg.timestamp

            # Slug (from any message)
            if not slug:
                msg_slug = getattr(msg, "slug", None)
                if msg_slug:
                    slug = msg_slug

            # Assistant message specific data
            if isinstance(msg, AssistantMessage):
                if msg.usage:
                    usage = usage + msg.usage
                    total_cost += msg.usage.calculate_cost(msg.model)
                if msg.model:
                    models_used.add(msg.model)
                for block in msg.content_blocks:
                    if isinstance(block, ToolUseBlock):
                        tools[block.name] += 1
                        if block.name == "Skill" and block.input:
                            skill_name = block.input.get("skill")
                            if skill_name:
                                kind = classify_invocation(skill_name)
                                if kind == "skill":
                                    skills[skill_name] += 1
                                else:
                                    # Both "command" and "builtin" go into commands
                                    commands[skill_name] += 1

            # Git branches
            git_branch = getattr(msg, "git_branch", None)
            if git_branch:
                git_branches.add(git_branch)

            # Working directories
            cwd = getattr(msg, "cwd", None)
            if cwd:
                working_dirs.add(cwd)

        # Merge user-prompt detected commands/skills (avoid double-counting)
        for name in user_prompt_skills:
            if name not in skills:
                skills[name] += 1
        for name in user_prompt_commands:
            if name not in commands:
                commands[name] += 1

        # Store all computed values
        cache.start_time = first_ts
        cache.end_time = last_ts
        cache.slug = slug
        cache.usage_summary = usage
        cache.tools_used = dict(tools)
        cache.skills_used = dict(skills)
        cache.commands_used = dict(commands)
        cache.git_branches = git_branches
        cache.working_dirs = working_dirs
        cache.models_used = models_used
        cache.message_count = message_count
        cache.total_cost = total_cost
        # Message type counts
        cache.user_message_count = user_msg_count
        cache.assistant_message_count = assistant_msg_count
        cache.file_snapshot_count = file_snapshot_count
        cache.summary_count = summary_count  # SessionTitleMessage count
        cache.compact_boundary_count = compact_boundary_count  # CompactBoundaryMessage count

        # Project context (from previous sessions) - extracted by CompactionDetector
        # Note: We use None for empty lists to be consistent with the API schema
        # where default_factory=list handles empty case. This avoids confusion
        # where [] in cache vs [] in response could differ.
        project_context_summaries = compaction_detector.project_context_summaries
        project_context_leaf_uuids = compaction_detector.project_context_leaf_uuids
        cache.project_context_summaries = (
            project_context_summaries if project_context_summaries else None
        )
        cache.project_context_leaf_uuids = (
            project_context_leaf_uuids if project_context_leaf_uuids else None
        )

        # Session titles (from SessionTitleMessage after conversation)
        session_titles = compaction_detector.session_titles
        cache.session_titles = session_titles if session_titles else None

        # Compaction tracking - CompactBoundaryMessage entries indicate TRUE compaction
        cache.was_compacted = compaction_detector.was_compacted
        cache.compaction_summary_count = compaction_detector.compaction_count
        compaction_details = compaction_detector.get_compaction_details()
        cache.compaction_details = compaction_details if compaction_details else None
        cache.mark_loaded(self._get_file_mtime())

    def clear_cache(self) -> None:
        """Clear cache for this session (useful for testing)."""
        clear_cache(_session_cache, self.jsonl_path)

    @classmethod
    def clear_all_caches(cls) -> None:
        """Clear all session caches (useful for testing)."""
        clear_all_caches(_session_cache)

    @classmethod
    def get_cache_stats(cls) -> Dict[str, int]:
        """
        Get cache statistics.

        Returns:
            Dict with 'size', 'max_size', and 'ttl_seconds' keys.
        """
        return _session_cache.stats()

    # =========================================================================
    # Session folder paths
    # =========================================================================

    @property
    def session_dir(self) -> Path:
        """Path to session's resource folder ({uuid}/)."""
        return self.jsonl_path.parent / self.uuid

    @property
    def tool_results_dir(self) -> Path:
        """Path to tool-results folder."""
        return self.session_dir / "tool-results"

    @property
    def subagents_dir(self) -> Path:
        """Path to subagents folder."""
        return self.session_dir / "subagents"

    # =========================================================================
    # External resource paths
    # =========================================================================

    @property
    def debug_log_path(self) -> Path:
        """Path to debug log file."""
        return self.claude_base_dir / "debug" / f"{self.uuid}.txt"

    @property
    def file_history_dir(self) -> Path:
        """Path to file history directory."""
        return self.claude_base_dir / "file-history" / self.uuid

    @property
    def todos_dir(self) -> Path:
        """Path to todos directory."""
        return self.claude_base_dir / "todos"

    @property
    def tasks_dir(self) -> Path:
        """Path to tasks directory for this session."""
        return self.claude_base_dir / "tasks" / self.uuid

    # =========================================================================
    # Existence checks
    # =========================================================================

    @property
    def exists(self) -> bool:
        """Check if the session JSONL file exists."""
        return self.jsonl_path.exists()

    @property
    def has_debug_log(self) -> bool:
        """Check if debug log exists."""
        return self.debug_log_path.exists()

    @property
    def has_file_history(self) -> bool:
        """Check if file history directory exists and has content."""
        return self.file_history_dir.exists() and any(self.file_history_dir.iterdir())

    @property
    def has_subagents(self) -> bool:
        """Check if session has any subagents."""
        return self.subagents_dir.exists() and any(self.subagents_dir.glob("agent-*.jsonl"))

    @property
    def has_tool_results(self) -> bool:
        """Check if session has any stored tool results."""
        return self.tool_results_dir.exists() and any(self.tool_results_dir.glob("toolu_*.txt"))

    @property
    def has_todos(self) -> bool:
        """Check if session has any associated todos with actual content."""
        return len(self.list_todos()) > 0

    @property
    def has_tasks(self) -> bool:
        """Check if session has any tasks (new task system)."""
        return self.tasks_dir.exists() and any(self.tasks_dir.glob("*.json"))

    # =========================================================================
    # Message access
    # =========================================================================

    def iter_messages(self) -> Iterator[Message]:
        """
        Iterate over messages in this session's JSONL file.

        Yields:
            Message instances (UserMessage, AssistantMessage, FileHistorySnapshot)
        """
        yield from iter_messages_from_jsonl(self.jsonl_path)

    def list_messages(self) -> List[Message]:
        """
        Load all messages from this session.

        Returns:
            List of Message instances
        """
        return list(self.iter_messages())

    def iter_user_messages(self) -> Iterator[UserMessage]:
        """Iterate over user messages only."""
        for msg in self.iter_messages():
            if isinstance(msg, UserMessage):
                yield msg

    def iter_assistant_messages(self) -> Iterator[AssistantMessage]:
        """Iterate over assistant messages only."""
        for msg in self.iter_messages():
            if isinstance(msg, AssistantMessage):
                yield msg

    # =========================================================================
    # Related resources
    # =========================================================================

    def list_subagents(self) -> List[Agent]:
        """
        List all subagents for this session.

        Returns:
            List of Agent instances
        """
        if not self.subagents_dir.exists():
            return []

        return sorted(
            [Agent.from_path(p) for p in self.subagents_dir.glob("agent-*.jsonl") if p.is_file()],
            key=lambda a: a.agent_id,
        )

    def count_subagents(self) -> int:
        """
        Count subagents without instantiating Agent objects.

        More efficient than len(list_subagents()) when only the count is needed.
        """
        subagents_dir = self.session_dir / "subagents"
        if not subagents_dir.exists():
            return 0
        return len(list(subagents_dir.glob("agent-*.jsonl")))

    def list_tool_results(self) -> List[ToolResult]:
        """
        List all stored tool results for this session.

        Returns:
            List of ToolResult instances
        """
        if not self.tool_results_dir.exists():
            return []

        return sorted(
            [
                ToolResult.from_path(p)
                for p in self.tool_results_dir.glob("toolu_*.txt")
                if p.is_file()
            ],
            key=lambda tr: tr.tool_use_id,
        )

    def list_todos(self) -> List[TodoItem]:
        """
        Load todos associated with this session.

        Looks for files matching {uuid}-*.json in the todos directory.

        Returns:
            List of TodoItem instances
        """
        if not self.todos_dir.exists():
            return []

        todos: List[TodoItem] = []
        for todo_file in self.todos_dir.glob(f"{self.uuid}-*.json"):
            try:
                todos.extend(load_todos_from_file(todo_file))
            except (FileNotFoundError, json.JSONDecodeError):
                continue

        return todos

    def list_tasks(self) -> List[Task]:
        """
        Load tasks associated with this session (new task system).

        Tasks are stored in ~/.claude/tasks/{uuid}/ as individual JSON files.
        If task files don't exist (ephemeral/cleaned up), falls back to
        reconstructing tasks from TaskCreate/TaskUpdate events in the JSONL file.

        Results are cached to prevent expensive JSONL reconstruction on every call.
        Cache is automatically invalidated when the JSONL file is modified.

        Returns:
            List of Task instances sorted by ID
        """
        cache = self._get_cache()

        # Return cached tasks if valid (not stale and populated)
        if cache.tasks is not None and not is_cache_stale(cache, self.jsonl_path):
            return cache.tasks

        # First try loading from task files (authoritative source when available)
        tasks = load_tasks_from_directory(self.tasks_dir)
        if tasks:
            cache.tasks = tasks
            return tasks

        # Fallback: reconstruct from JSONL events
        tasks = reconstruct_tasks_from_jsonl(self.jsonl_path)
        cache.tasks = tasks
        return tasks

    def read_debug_log(self) -> Optional[str]:
        """
        Read the debug log content.

        Returns:
            Debug log content or None if not found
        """
        if not self.has_debug_log:
            return None
        return self.debug_log_path.read_text(encoding="utf-8")

    # =========================================================================
    # Analytics and computed properties
    # =========================================================================

    @property
    def message_count(self) -> int:
        """Count total messages (cached)."""
        self._load_metadata()
        return self._get_cache().message_count or 0

    @property
    def start_time(self) -> Optional[datetime]:
        """Get timestamp of first message (cached)."""
        self._load_metadata()
        return self._get_cache().start_time

    @property
    def end_time(self) -> Optional[datetime]:
        """Get timestamp of last message (cached)."""
        self._load_metadata()
        return self._get_cache().end_time

    @property
    def duration_seconds(self) -> Optional[float]:
        """Get session duration in seconds."""
        start = self.start_time
        end = self.end_time
        if start and end:
            return (end - start).total_seconds()
        return None

    def get_usage_summary(self) -> TokenUsage:
        """
        Aggregate token usage across all assistant messages (cached).

        Returns:
            Combined TokenUsage instance
        """
        self._load_metadata()
        return self._get_cache().usage_summary or TokenUsage.zero()

    def get_total_cost(self) -> float:
        """
        Calculate total cost by summing per-message costs (cached).

        Each message's cost is calculated based on its model and token usage.

        Returns:
            Total estimated cost in USD.
        """
        self._load_metadata()
        return self._get_cache().total_cost or 0.0

    def get_models_used(self) -> Set[str]:
        """
        Get set of all models used in this session (cached).

        Returns:
            Set of model names
        """
        self._load_metadata()
        return self._get_cache().models_used or set()

    def get_tools_used(self) -> Counter[str]:
        """
        Count tool usage across all assistant messages (cached).

        Returns:
            Counter mapping tool name to usage count
        """
        self._load_metadata()
        return Counter(self._get_cache().tools_used or {})

    def get_skills_used(self) -> Counter[str]:
        """
        Count skill usage from Skill tool invocations (cached).

        Tracks both file-based skills and plugin skills (e.g., 'oh-my-claudecode:security-review').

        Returns:
            Counter mapping skill name to usage count
        """
        self._load_metadata()
        return Counter(self._get_cache().skills_used or {})

    def get_commands_used(self) -> Counter[str]:
        """
        Count command usage from Skill tool invocations without ':' prefix (cached).

        Commands are user-authored .md files in ~/.claude/commands/ or .claude/commands/.

        Returns:
            Counter mapping command name to usage count
        """
        self._load_metadata()
        return Counter(self._get_cache().commands_used or {})

    def get_git_branches(self) -> Set[str]:
        """
        Get all git branches referenced in this session (cached).

        Returns:
            Set of branch names
        """
        self._load_metadata()
        return self._get_cache().git_branches or set()

    def get_working_directories(self) -> Set[str]:
        """
        Get all working directories used in this session (cached).

        Returns:
            Set of directory paths
        """
        self._load_metadata()
        return self._get_cache().working_dirs or set()

    @property
    def slug(self) -> Optional[str]:
        """
        Get the session's human-readable slug (cached).

        The slug is stored in message entries and is consistent across
        all messages in a session.

        Returns:
            Session slug (e.g., "refactored-meandering-knuth") or None
        """
        self._load_metadata()
        return self._get_cache().slug

    # =========================================================================
    # Continuation session detection
    # =========================================================================

    @property
    def is_continuation_marker(self) -> bool:
        """
        Check if this session is a continuation marker (metadata-only session).

        When a user resumes/continues a session, the old session file receives
        only file-history-snapshot entries while the conversation continues
        in a new session file. This property detects such "orphan" sessions.

        Returns:
            True if session contains only file-history-snapshots (no conversation)
        """
        self._load_metadata()
        cache = self._get_cache()
        # A continuation marker has file snapshots but no user/assistant messages
        return (
            cache.file_snapshot_count > 0
            and cache.user_message_count == 0
            and cache.assistant_message_count == 0
        )

    @property
    def file_snapshot_count(self) -> int:
        """Get count of file-history-snapshot messages."""
        self._load_metadata()
        return self._get_cache().file_snapshot_count

    @property
    def project_context_summaries(self) -> Optional[List[str]]:
        """
        Get project context summaries from previous sessions.

        These are summaries loaded at session start to provide context
        from prior sessions in the same project. They appear BEFORE the
        first user/assistant message and are NOT indicators of compaction.

        Returns:
            List of summary strings, or None if no context summaries exist
        """
        self._load_metadata()
        return self._get_cache().project_context_summaries

    @property
    def project_context_leaf_uuids(self) -> Optional[List[str]]:
        """
        Get leaf UUIDs from project context summary messages.

        These UUIDs reference messages in PREVIOUS sessions that provided
        context for this session. Can be used to trace project history.

        Returns:
            List of message UUIDs, or None if no leaf UUIDs exist
        """
        self._load_metadata()
        return self._get_cache().project_context_leaf_uuids

    @property
    def session_titles(self) -> Optional[List[str]]:
        """
        Get session titles generated for this session.

        These are human-readable names generated by Claude to describe
        the session content. They appear as SessionTitleMessage entries
        AFTER the conversation and are NOT indicators of compaction.

        Returns:
            List of title strings, or None if no titles exist
        """
        self._load_metadata()
        return self._get_cache().session_titles

    @property
    def was_compacted(self) -> bool:
        """
        Check if THIS session underwent context compaction.

        Compaction is detected by finding summary messages that appear
        AFTER the conversation has started (after user/assistant messages).
        This indicates the context window filled and Claude summarized
        the conversation mid-session.

        Returns:
            True if this session was compacted during its lifetime
        """
        self._load_metadata()
        return self._get_cache().was_compacted

    @property
    def compaction_summary_count(self) -> int:
        """
        Get the number of compaction events in this session.

        Each compaction event adds summary messages after the conversation
        has started. Multiple compaction events indicate a very long session.

        Returns:
            Number of compaction summary messages (0 if no compaction occurred)
        """
        self._load_metadata()
        return self._get_cache().compaction_summary_count

    @property
    def compaction_summaries(self) -> Optional[List[Dict[str, Any]]]:
        """
        Get structured compaction details from THIS session.

        These are the compaction events from when this session's context was compacted.
        Each dict contains: summary, trigger, pre_tokens, timestamp.

        Returns:
            List of compaction detail dicts, or None if no compaction occurred
        """
        self._load_metadata()
        return self._get_cache().compaction_details

    def get_message_type_breakdown(self) -> Dict[str, int]:
        """
        Get breakdown of message types in this session.

        Returns:
            Dict mapping message type to count
        """
        self._load_metadata()
        cache = self._get_cache()
        return {
            "user": cache.user_message_count,
            "assistant": cache.assistant_message_count,
            "file_history_snapshot": cache.file_snapshot_count,
            "summary": cache.summary_count,  # SessionTitleMessage (not compaction)
            "compact_boundary": cache.compact_boundary_count,  # True compaction events
        }

"""
Agent model for Claude Code standalone agents and subagents.

Standalone agents: ~/.claude/projects/{project}/agent-{id}.jsonl
Subagents: ~/.claude/projects/{project}/{session-uuid}/subagents/agent-{id}.jsonl
"""

from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Dict, Iterator, List, Optional

from pydantic import BaseModel, ConfigDict, Field

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
from .message import Message
from .task import Task, reconstruct_tasks_from_jsonl

if TYPE_CHECKING:
    from .usage import TokenUsage


class AgentCache(BaseCache):
    """
    Mutable cache for agent's computed properties.

    Used to avoid redundant JSONL file I/O when accessing properties like
    start_time, end_time, etc. multiple times on the same Agent.

    Inherits file mtime tracking from BaseCache for automatic cache
    invalidation when the underlying JSONL file is modified.

    Uses __slots__ for memory efficiency.
    """

    __slots__ = (
        "start_time",
        "end_time",
        "usage_summary",
        "message_count",
        "tasks",
        "skills_used",
        "commands_used",
    )

    def __init__(self) -> None:
        super().__init__()
        self.start_time: Optional[datetime] = None
        self.end_time: Optional[datetime] = None
        self.usage_summary: Optional["TokenUsage"] = None
        self.message_count: Optional[int] = None
        self.tasks: Optional[List["Task"]] = None
        self.skills_used: Optional[Dict[str, int]] = None
        self.commands_used: Optional[Dict[str, int]] = None

    def reset(self) -> None:
        """Reset all cache values to initial state."""
        self.start_time = None
        self.end_time = None
        self.usage_summary = None
        self.message_count = None
        self.tasks = None
        self.skills_used = None
        self.commands_used = None
        super().reset()


# Module-level cache: maps agent JSONL path -> AgentCache
# Uses bounded cache with LRU eviction and TTL expiration to prevent unbounded memory growth
# Default: 1000 entries max, 1 hour TTL (configurable via environment variables)
_agent_cache: BoundedCache[AgentCache] = BoundedCache()


class Agent(BaseModel):
    """
    Represents a Claude Code agent session.

    Agents can be:
    - Standalone: agent-{id}.jsonl at project root
    - Subagent: agent-{id}.jsonl inside {session-uuid}/subagents/

    Attributes:
        agent_id: Short hex identifier (e.g., "a5793c3")
        jsonl_path: Path to the agent's JSONL file
        is_subagent: True if this is a subagent of a session
        parent_session_uuid: UUID of parent session (if subagent)
        slug: Session slug inherited from parent (e.g., "eager-puzzling-fairy")
    """

    model_config = ConfigDict(frozen=True)

    agent_id: str = Field(..., description="Agent short hex ID")
    jsonl_path: Path = Field(..., description="Path to agent JSONL file")
    is_subagent: bool = Field(default=False, description="Whether this is a subagent")
    parent_session_uuid: Optional[str] = Field(
        default=None, description="Parent session UUID if subagent"
    )
    slug: Optional[str] = Field(
        default=None,
        description="Session slug (human-readable session name, inherited from parent session)",
    )

    @classmethod
    def from_path(cls, path: Path) -> "Agent":
        """
        Create an Agent from a JSONL file path.

        Infers agent_id from filename and parent_session_uuid from path structure.

        Args:
            path: Path to agent JSONL file

        Returns:
            Agent instance
        """
        # Extract agent_id from filename: agent-{id}.jsonl -> {id}
        filename = path.stem  # agent-a5793c3
        match = re.match(r"agent-([a-f0-9]+)", filename)
        agent_id = match.group(1) if match else filename.replace("agent-", "")

        # Determine if subagent by checking path structure
        # Subagent path: .../{session-uuid}/subagents/agent-xxx.jsonl
        is_subagent = "subagents" in path.parts
        parent_session_uuid = None

        if is_subagent:
            # Find the session UUID from path
            # Path structure: .../{session-uuid}/subagents/agent-xxx.jsonl
            subagents_idx = path.parts.index("subagents")
            if subagents_idx > 0:
                parent_session_uuid = path.parts[subagents_idx - 1]

        # Try to extract agentId, slug, and isSidechain from JSONL data
        slug = None
        jsonl_agent_id = None
        jsonl_is_sidechain = None
        if path.exists():
            try:
                with open(path, "r", encoding="utf-8") as f:
                    first_line = f.readline()
                    if first_line:
                        data = json.loads(first_line)
                        slug = data.get("slug")
                        jsonl_agent_id = data.get("agentId")
                        jsonl_is_sidechain = data.get("isSidechain")
            except (json.JSONDecodeError, IOError):
                pass

        # Use JSONL agentId if available, otherwise fall back to filename
        final_agent_id = jsonl_agent_id if jsonl_agent_id else agent_id
        # Use JSONL isSidechain if available, otherwise infer from path
        final_is_subagent = jsonl_is_sidechain if jsonl_is_sidechain is not None else is_subagent

        return cls(
            agent_id=final_agent_id,
            jsonl_path=path,
            is_subagent=final_is_subagent,
            parent_session_uuid=parent_session_uuid,
            slug=slug,
        )

    # =========================================================================
    # Cache management (uses shared base_cache utilities)
    # =========================================================================

    def _get_cache(self) -> AgentCache:
        """Get or create cache for this agent."""
        return get_or_create_cache(_agent_cache, self.jsonl_path, AgentCache)

    def _get_file_mtime(self) -> Optional[float]:
        """Get file modification time, or None if file doesn't exist."""
        return get_file_mtime(self.jsonl_path)

    def _is_cache_stale(self, cache: AgentCache) -> bool:
        """Check if cache is stale (file has been modified since cache was populated)."""
        return is_cache_stale(cache, self.jsonl_path)

    def _load_metadata(self) -> None:
        """
        Single-pass extraction of all agent metadata.

        Loads timestamps, message count, and usage stats in a single iteration.
        Automatically invalidates cache if file has been modified.
        """
        cache = self._get_cache()

        # Check if cache is stale and needs refresh
        if self._is_cache_stale(cache):
            cache.reset()

        if cache._metadata_loaded:
            return

        from collections import Counter

        from command_helpers import classify_invocation

        from .content import ToolUseBlock
        from .message import AssistantMessage
        from .usage import TokenUsage

        # Initialize accumulators
        first_ts: Optional[datetime] = None
        last_ts: Optional[datetime] = None
        usage = TokenUsage.zero()
        message_count = 0
        skills: Counter = Counter()
        commands: Counter = Counter()

        for msg in self.iter_messages():
            message_count += 1

            # Timestamps
            if first_ts is None:
                first_ts = msg.timestamp
            last_ts = msg.timestamp

            # Usage (assistant messages only)
            if isinstance(msg, AssistantMessage):
                if msg.usage:
                    usage = usage + msg.usage

                # Extract skills/commands from Skill tool uses
                for block in msg.content_blocks:
                    if (
                        isinstance(block, ToolUseBlock)
                        and block.name == "Skill"
                        and block.input
                    ):
                        skill_name = block.input.get("skill")
                        if skill_name:
                            kind = classify_invocation(skill_name)
                            if kind == "skill":
                                skills[skill_name] += 1
                            elif kind == "command":
                                commands[skill_name] += 1

        # Store all computed values
        cache.start_time = first_ts
        cache.end_time = last_ts
        cache.usage_summary = usage
        cache.message_count = message_count
        cache.skills_used = dict(skills)
        cache.commands_used = dict(commands)
        cache.mark_loaded(self._get_file_mtime())

    def clear_cache(self) -> None:
        """Clear cache for this agent (useful for testing)."""
        clear_cache(_agent_cache, self.jsonl_path)

    @classmethod
    def clear_all_caches(cls) -> None:
        """Clear all agent caches (useful for testing)."""
        clear_all_caches(_agent_cache)

    @classmethod
    def get_cache_stats(cls) -> Dict[str, int]:
        """
        Get cache statistics.

        Returns:
            Dict with 'size', 'max_size', and 'ttl_seconds' keys.
        """
        return _agent_cache.stats()

    # =========================================================================
    # Message access
    # =========================================================================

    def iter_messages(self) -> Iterator[Message]:
        """
        Iterate over messages in this agent's JSONL file.

        Yields:
            Message instances (UserMessage, AssistantMessage, etc.)
        """
        yield from iter_messages_from_jsonl(self.jsonl_path)

    def list_messages(self) -> List[Message]:
        """
        Load all messages from this agent's JSONL file.

        Returns:
            List of Message instances
        """
        return list(self.iter_messages())

    @property
    def message_count(self) -> int:
        """Count messages (cached)."""
        self._load_metadata()
        return self._get_cache().message_count or 0

    @property
    def exists(self) -> bool:
        """Check if the JSONL file exists."""
        return self.jsonl_path.exists()

    def get_usage_summary(self) -> "TokenUsage":
        """
        Aggregate token usage across all assistant messages (cached).

        Returns:
            Combined TokenUsage instance
        """
        from .usage import TokenUsage

        self._load_metadata()
        return self._get_cache().usage_summary or TokenUsage.zero()

    def get_skills_used(self) -> Dict[str, int]:
        """Get skill usage counts (cached)."""
        self._load_metadata()
        return self._get_cache().skills_used or {}

    def get_commands_used(self) -> Dict[str, int]:
        """Get command usage counts (cached)."""
        self._load_metadata()
        return self._get_cache().commands_used or {}

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

    def list_tasks(self) -> List[Task]:
        """
        Load tasks created by this agent from its JSONL file.

        Subagents don't have persistent task directories like sessions do.
        Tasks are reconstructed from TaskCreate/TaskUpdate tool_use events
        in the agent's JSONL file.

        Results are cached to prevent expensive JSONL reconstruction on every call.
        Cache is automatically invalidated when the JSONL file is modified.

        Returns:
            List of Task instances sorted by ID
        """
        cache = self._get_cache()

        # Return cached tasks if valid (not stale and populated)
        if cache.tasks is not None and not is_cache_stale(cache, self.jsonl_path):
            return cache.tasks

        # Reconstruct from JSONL events
        tasks = reconstruct_tasks_from_jsonl(self.jsonl_path)
        cache.tasks = tasks
        return tasks

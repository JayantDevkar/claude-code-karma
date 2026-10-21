"""
Single-pass data collection utilities for session endpoints.

Phase 2 optimization: Extract all needed data from session messages in one
iteration instead of multiple passes.
"""

import os
import threading
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from cachetools import TTLCache

from command_helpers import classify_invocation, is_command_category, is_skill_category
from config import FILE_TOOL_MAPPINGS
from models import AssistantMessage, Session, ToolUseBlock, UserMessage
from models.conversation import ConversationEntity
from utils import (
    FileOperation,
    extract_file_operation,
    normalize_key,
    prompt_from_user_message,
)


@dataclass
class ConversationData:
    """
    Common data extracted from any ConversationEntity (Session or Agent).

    This represents the shared data that can be collected from both Session
    and Agent entities using the unified _collect_conversation_data_core function.
    """

    # Tool usage (single counter - caller determines attribution)
    tool_counts: Counter = field(default_factory=Counter)

    # Skill and command usage (extracted from Skill tool inputs)
    skills: Counter = field(default_factory=Counter)
    commands: Counter = field(default_factory=Counter)

    # File activity
    file_operations: List[FileOperation] = field(default_factory=list)

    # Context
    git_branches: Set[str] = field(default_factory=set)
    working_directories: Set[str] = field(default_factory=set)

    # Initial prompt
    initial_prompt: Optional[str] = None


@dataclass
class SessionData:
    """All extractable data from a session's messages in a single pass."""

    # Timestamps
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None

    # Identity
    slug: Optional[str] = None

    # Initial prompt
    initial_prompt: Optional[str] = None

    # Tool usage
    session_tool_counts: Counter = field(default_factory=Counter)
    subagent_tool_counts: Counter = field(default_factory=Counter)

    # Subagent skill/command usage (aggregated across all subagents)
    subagent_skill_counts: Counter = field(default_factory=Counter)
    subagent_command_counts: Counter = field(default_factory=Counter)

    # File activity
    file_operations: List[FileOperation] = field(default_factory=list)

    # Subagent spawning info
    task_tool_to_type: Dict[str, str] = field(default_factory=dict)  # tool_use_id -> subagent_type
    task_descriptions: Dict[str, str] = field(
        default_factory=dict
    )  # normalized_desc -> subagent_type

    # Context
    git_branches: Set[str] = field(default_factory=set)
    working_directories: Set[str] = field(default_factory=set)


# Known system agent prefixes (auto-spawned by Claude Code, not via Task tool)
SYSTEM_AGENT_PREFIXES = frozenset({"aprompt_suggestion", "acompact"})


def _infer_type_from_agent_id(agent_id: str) -> Optional[str]:
    """
    Infer subagent_type from agent_id prefix for system agents.

    System agents are auto-spawned by Claude Code (not via Task tool) and have
    IDs like "aprompt_suggestion-7796cd" or "acompact-abc123" where the prefix
    before the last hyphen+hex is the type.

    Args:
        agent_id: The agent identifier (e.g., "aprompt_suggestion-7796cd")

    Returns:
        The inferred type if it matches a known system agent prefix, None otherwise
    """
    # Look for pattern: {type}-{hex_id}
    # The hex_id is typically 6-8 characters
    if "-" not in agent_id:
        return None

    # Extract everything before the last hyphen as potential type
    last_hyphen_idx = agent_id.rfind("-")
    potential_type = agent_id[:last_hyphen_idx]

    # Check if it's a known system agent prefix
    if potential_type in SYSTEM_AGENT_PREFIXES:
        return potential_type

    return None


def _extract_file_operation(
    block: ToolUseBlock,
    timestamp: datetime,
    actor: str,
    actor_type: str,
) -> Optional[FileOperation]:
    """
    Extract file operation from a tool use block if applicable.

    Wrapper around the shared extract_file_operation function in utils.py.
    """
    return extract_file_operation(
        tool_name=block.name,
        tool_input=block.input,
        timestamp=timestamp,
        actor=actor,
        actor_type=actor_type,
        file_tool_mappings=FILE_TOOL_MAPPINGS,
    )


def _collect_conversation_data_core(
    entity: ConversationEntity,
    actor: str,
    actor_type: str,
) -> ConversationData:
    """
    Single-pass extraction of common data from any ConversationEntity.

    This is the unified core function that extracts data common to both
    Session and Agent entities: tool counts, file operations, git branches,
    working directories, and initial prompt.

    Args:
        entity: A ConversationEntity (Session or Agent)
        actor: The actor identifier (e.g., "session" or agent_id)
        actor_type: The actor type ("session" or "subagent")

    Returns:
        ConversationData with extracted information
    """
    data = ConversationData()

    for msg in entity.iter_messages():
        # Extract context from any message
        git_branch = getattr(msg, "git_branch", None)
        if git_branch:
            data.git_branches.add(git_branch)

        cwd = getattr(msg, "cwd", None)
        if cwd:
            data.working_directories.add(cwd)

        # User message - get initial prompt
        if isinstance(msg, UserMessage):
            if data.initial_prompt is None:
                content = msg.content or ""
                # Skip tool result and internal messages
                if not msg.is_tool_result and not msg.is_internal_message:
                    data.initial_prompt = content[:5000] if content else None

        # Assistant message - extract tools and file operations
        elif isinstance(msg, AssistantMessage):
            for block in msg.content_blocks:
                if isinstance(block, ToolUseBlock):
                    tool_name = block.name
                    data.tool_counts[tool_name] += 1

                    # Extract skill/command names from Skill tool inputs
                    if tool_name == "Skill" and block.input:
                        skill_name = block.input.get("skill")
                        if skill_name:
                            kind = classify_invocation(skill_name, source="skill_tool")
                            if is_skill_category(kind):
                                data.skills[skill_name] += 1
                            elif is_command_category(kind):
                                data.commands[skill_name] += 1

                    # Extract file operations using shared utility
                    file_op = _extract_file_operation(block, msg.timestamp, actor, actor_type)
                    if file_op:
                        data.file_operations.append(file_op)

    return data


def collect_agent_data(agent: ConversationEntity) -> ConversationData:
    """
    Single-pass collection of agent data.

    Extracts tool counts, file operations, git branches, and working directories
    in a single iteration through the agent's messages.

    Args:
        agent: The Agent to collect data from

    Returns:
        ConversationData with tool_counts, file_operations, git_branches,
        working_directories, initial_prompt
    """
    # Get agent_id if available (for Agent entities)
    agent_id = getattr(agent, "agent_id", "unknown-agent")

    # Use core collection function
    data = _collect_conversation_data_core(agent, actor=agent_id, actor_type="subagent")

    # For subagents, the first UserMessage is always the Task prompt.
    # The core function may skip it if is_internal_message is a false positive
    # (e.g., prompt text discusses <local-command-caveat> patterns).
    if data.initial_prompt is None:
        for msg in agent.iter_messages():
            if isinstance(msg, UserMessage) and msg.content:
                data.initial_prompt = msg.content[:5000]
                break

    return data


def collect_session_data(session: Session, include_subagents: bool = False) -> SessionData:
    """
    Single-pass extraction of all session data.

    This replaces multiple iterations over session messages with a single pass
    that collects all relevant data simultaneously.

    Args:
        session: The session to collect data from
        include_subagents: Whether to also collect subagent data

    Returns:
        SessionData with all extracted information
    """
    data = SessionData()
    prev_user: Optional[UserMessage] = None

    for msg in session.iter_messages():
        # Timestamps: track first and last (skip messages without timestamp like SessionTitleMessage)
        msg_timestamp = getattr(msg, "timestamp", None)
        if msg_timestamp:
            if data.start_time is None:
                data.start_time = msg_timestamp
            data.end_time = msg_timestamp

        # Slug from any message that has it
        if data.slug is None:
            msg_slug = getattr(msg, "slug", None)
            if msg_slug:
                data.slug = msg_slug

        # Git branches and working directories
        git_branch = getattr(msg, "git_branch", None)
        if git_branch:
            data.git_branches.add(git_branch)

        cwd = getattr(msg, "cwd", None)
        if cwd:
            data.working_directories.add(cwd)

        # User message processing
        if isinstance(msg, UserMessage):
            # Initial prompt (first user message holding a real prompt)
            if data.initial_prompt is None:
                prompt = prompt_from_user_message(msg, prev_user)
                if prompt:
                    data.initial_prompt = prompt[:5000]
            prev_user = msg

        # Assistant message processing
        elif isinstance(msg, AssistantMessage):
            # Determine actor info
            if msg.is_sidechain or msg.agent_id:
                actor = msg.agent_id or "unknown-subagent"
                actor_type = "subagent"
            else:
                actor = "session"
                actor_type = "session"

            # Process content blocks
            for block in msg.content_blocks:
                if isinstance(block, ToolUseBlock):
                    tool_name = block.name

                    # Count tools by actor
                    if actor_type == "session":
                        data.session_tool_counts[tool_name] += 1
                    else:
                        data.subagent_tool_counts[tool_name] += 1

                    # Extract file operations
                    file_op = _extract_file_operation(block, msg.timestamp, actor, actor_type)
                    if file_op:
                        data.file_operations.append(file_op)

                    # Extract Task -> subagent_type mapping
                    if tool_name in ("Task", "Agent"):
                        subagent_type = block.input.get("subagent_type")
                        if subagent_type:
                            data.task_tool_to_type[block.id] = subagent_type
                            # Store both description and prompt for fallback matching
                            # The subagent's initial_prompt comes from Task's "prompt" field,
                            # not the "description" field, so we need to match by prompt
                            prompt = block.input.get("prompt", "")[:100]
                            if prompt:
                                data.task_descriptions[normalize_key(prompt)] = subagent_type
                            # Also store description as secondary fallback
                            desc = block.input.get("description", "")[:100]
                            if desc:
                                data.task_descriptions[normalize_key(desc)] = subagent_type

    # Collect subagent data if requested
    if include_subagents:
        for subagent in session.list_subagents():
            _collect_subagent_data(subagent, data)

    return data


def _collect_subagent_data(subagent, data: SessionData) -> None:
    """Add subagent data to the session data collector."""
    digest = _subagent_digest(subagent)
    data.subagent_tool_counts.update(digest.tool_counts)
    data.subagent_skill_counts.update(digest.skill_counts)
    data.subagent_command_counts.update(digest.command_counts)
    data.file_operations.extend(digest.file_operations)


@dataclass(frozen=True)
class _SubagentDigest:
    """Everything the collectors need from one subagent file, read in one pass."""

    tool_counts: Counter
    skill_counts: Counter
    command_counts: Counter
    file_operations: Tuple[FileOperation, ...]
    initial_prompt: Optional[str]
    message_count: int


# Keyed by (path, mtime_ns, size): a finished subagent's file never changes, so its digest
# is reused by every endpoint and request; a growing one is re-read only when it changes.
_digest_cache: TTLCache = TTLCache(maxsize=2048, ttl=3600)
_digest_lock = threading.Lock()
_digest_key_locks: Dict[tuple, threading.Lock] = {}


def clear_subagent_digest_cache() -> None:
    with _digest_lock:
        _digest_cache.clear()


def _file_version(path: Path) -> Optional[tuple]:
    try:
        stat = os.stat(path)
    except OSError:
        return None
    return (str(path), stat.st_mtime_ns, stat.st_size)


def _subagent_digest(subagent) -> _SubagentDigest:
    """Cached digest of a subagent file; concurrent callers wait for one parse."""
    key = _file_version(subagent.jsonl_path)
    if key is None:
        return _read_subagent_digest(subagent)
    with _digest_lock:
        digest = _digest_cache.get(key)
        if digest is not None:
            return digest
        key_lock = _digest_key_locks.setdefault(key, threading.Lock())
    with key_lock:
        with _digest_lock:
            digest = _digest_cache.get(key)
        if digest is None:
            digest = _read_subagent_digest(subagent)
            with _digest_lock:
                _digest_cache[key] = digest
                _digest_key_locks.pop(key, None)
    return digest


def _read_subagent_digest(subagent) -> _SubagentDigest:
    agent_id = subagent.agent_id
    tool_counts: Counter = Counter()
    skill_counts: Counter = Counter()
    command_counts: Counter = Counter()
    file_operations: List[FileOperation] = []
    initial_prompt: Optional[str] = None
    message_count = 0

    for msg in subagent.iter_messages():
        message_count += 1
        if isinstance(msg, UserMessage):
            if initial_prompt is None:
                initial_prompt = msg.content[:5000] if msg.content else None
        elif isinstance(msg, AssistantMessage):
            for block in msg.content_blocks:
                if not isinstance(block, ToolUseBlock):
                    continue
                tool_counts[block.name] += 1
                file_op = _extract_file_operation(block, msg.timestamp, agent_id, "subagent")
                if file_op:
                    file_operations.append(file_op)
                if block.name == "Skill" and block.input:
                    skill_name = block.input.get("skill")
                    if skill_name:
                        kind = classify_invocation(skill_name, source="skill_tool")
                        if is_skill_category(kind):
                            skill_counts[skill_name] += 1
                        elif is_command_category(kind):
                            command_counts[skill_name] += 1

    return _SubagentDigest(
        tool_counts=tool_counts,
        skill_counts=skill_counts,
        command_counts=command_counts,
        file_operations=tuple(file_operations),
        initial_prompt=initial_prompt,
        message_count=message_count,
    )


@dataclass
class SubagentInfo:
    """Collected information about a subagent."""

    agent_id: str
    slug: Optional[str]
    tool_counts: Counter
    skills_used: Counter
    commands_used: Counter
    initial_prompt: Optional[str]
    subagent_type: Optional[str]
    message_count: int


def collect_subagent_info(
    session: Session, session_data: SessionData, tool_results: Dict[str, Any]
) -> List[SubagentInfo]:
    """
    Collect subagent information using pre-collected session data.

    Args:
        session: The session containing subagents
        session_data: Pre-collected session data with Task mappings
        tool_results: Dict of tool_use_id -> ToolResultData for agent ID extraction

    Returns:
        List of SubagentInfo for each subagent
    """
    # Build agent_id -> subagent_type mapping from tool results
    agent_id_to_type: Dict[str, str] = {}

    for tool_use_id, subagent_type in session_data.task_tool_to_type.items():
        result_data = tool_results.get(tool_use_id)
        if (
            result_data
            and hasattr(result_data, "spawned_agent_id")
            and result_data.spawned_agent_id
        ):
            agent_id_to_type[result_data.spawned_agent_id] = subagent_type

    subagents_info: List[SubagentInfo] = []

    for subagent in session.list_subagents():
        digest = _subagent_digest(subagent)
        initial_prompt = digest.initial_prompt

        # Match subagent to Task invocation
        subagent_type = agent_id_to_type.get(subagent.agent_id)

        # Fallback: match by normalized description prefix
        if subagent_type is None and initial_prompt:
            prompt_prefix = initial_prompt[:100]
            subagent_type = session_data.task_descriptions.get(normalize_key(prompt_prefix))

        # Fallback: infer type from agent_id prefix for system agents
        # System agents have IDs like "aprompt_suggestion-7796cd" or "acompact-abc123"
        # where the prefix before the last hyphen+hex is the type
        if subagent_type is None:
            subagent_type = _infer_type_from_agent_id(subagent.agent_id)

        # Detect warmup agents - Claude Code spawns these to warm up model cache
        # They have "Warmup" as their initial prompt and are internal Claude overhead
        if initial_prompt and initial_prompt.strip().lower() == "warmup":
            subagent_type = "Claude Tax"

        subagents_info.append(
            SubagentInfo(
                agent_id=subagent.agent_id,
                slug=subagent.slug,
                # Copies: callers own these, the cached digest must not change
                tool_counts=Counter(digest.tool_counts),
                skills_used=Counter(digest.skill_counts),
                commands_used=Counter(digest.command_counts),
                initial_prompt=initial_prompt,
                subagent_type=subagent_type,
                message_count=digest.message_count,
            )
        )

    return subagents_info

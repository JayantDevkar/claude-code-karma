"""
Shared conversation endpoint services for Session and Agent.

Phase 3 DRY refactor: Consolidates nearly identical timeline, tools, and
file-activity endpoint logic that was duplicated across routers/sessions.py
and routers/subagent_sessions.py (~400 lines reduced).

These functions work with any ConversationEntity (Session or Agent) via
the protocol in models/conversation.py.
"""

from collections import Counter
from typing import Optional

from command_helpers import (
    classify_invocation,
    detect_slash_commands_in_text,
    parse_command_from_content,
    strip_command_tags,
)
from models import AssistantMessage, ConversationEntity, ToolUseBlock, UserMessage
from models.content import TextBlock, ThinkingBlock
from schemas import FileActivity, TimelineEvent, ToolUsageSummary
from utils import (
    FileOperation,
    ToolResultData,
    collect_tool_results,
    get_tool_summary,
)

# =============================================================================
# Timeline Generation
# =============================================================================


def build_conversation_timeline(
    conversation: ConversationEntity,
    working_dirs: list[str],
    actor: str = "session",
    actor_type: str = "session",
    subagent_info: Optional[dict[str, Optional[str]]] = None,
) -> list[TimelineEvent]:
    """
    Build chronological timeline of events from a conversation.

    Shared implementation for session and subagent timeline endpoints.

    Args:
        conversation: Session or Agent to build timeline from
        working_dirs: Working directories for path relativization
        actor: Default actor identifier
        actor_type: Default actor type ("session" or "subagent")
        subagent_info: Optional dict mapping agent_id -> slug (for sessions)

    Returns:
        List of TimelineEvent sorted by timestamp
    """
    subagent_info = subagent_info or {}

    # Pass 1: Collect all tool results for later merging
    tool_results = collect_tool_results(conversation, extract_spawned_agent=True, parse_xml=True)

    # Pass 2: Build events with merged results
    events: list[TimelineEvent] = []
    event_counter = 0

    is_first_user_message = True

    for msg in conversation.iter_messages():
        if isinstance(msg, UserMessage):
            # For subagents, the first UserMessage is always the Task prompt.
            # Don't skip it even if is_internal_message is a false positive
            # (e.g., prompt text discusses <local-command-caveat> patterns).
            is_task_prompt = is_first_user_message and actor_type == "subagent"
            is_first_user_message = False

            # Skip tool results and internal messages (but not the Task prompt)
            if not is_task_prompt and (msg.is_tool_result or msg.is_internal_message):
                continue

            # Create standalone event for actual user prompts
            event_counter += 1
            content = msg.content or ""

            # Detect command invocation from <command-message> tags
            prompt_event_type, prompt_title, cmd_summary, cmd_name = _detect_command_from_content(
                content
            )

            # Strip XML tags from display summary
            display_content = _strip_command_tags(content)

            content_preview = cmd_summary or (display_content[:200] if display_content else "")
            prompt_metadata: dict = {"full_content": content}
            if cmd_name:
                prompt_metadata["command_name"] = cmd_name
                prompt_metadata["is_plugin"] = ":" in cmd_name
                if ":" in cmd_name:
                    prompt_metadata["plugin"] = cmd_name.split(":")[0]
            events.append(
                TimelineEvent(
                    id=f"evt-{event_counter}",
                    event_type=prompt_event_type,
                    timestamp=msg.timestamp,
                    actor="user",
                    actor_type="user",
                    title=prompt_title,
                    summary=content_preview if content_preview else None,
                    metadata=prompt_metadata,
                )
            )

        elif isinstance(msg, AssistantMessage):
            # Determine actor for this message
            if msg.is_sidechain or msg.agent_id:
                msg_actor = msg.agent_id or "subagent"
                msg_actor_type = "subagent"
            else:
                msg_actor = actor
                msg_actor_type = actor_type

            # Process content blocks
            for block in msg.content_blocks:
                event_counter += 1

                if isinstance(block, ToolUseBlock):
                    title, summary, base_metadata = get_tool_summary(
                        block, working_dirs=working_dirs
                    )

                    # Get pre-collected result data if available
                    result_data = tool_results.get(block.id)

                    # Build complete metadata with merged result
                    metadata = _build_tool_call_metadata(
                        block, base_metadata, result_data, subagent_info
                    )

                    # Add agent context for subagent messages
                    if msg_actor_type == "subagent":
                        metadata["agent_id"] = msg.agent_id
                        metadata["agent_slug"] = msg.slug

                    # Determine event type based on tool
                    if block.name == "TodoWrite":
                        event_type = "todo_update"
                    elif block.name == "Task":
                        event_type = "subagent_spawn"
                    elif block.name == "Skill":
                        # Extract skill details from tool input
                        skill_name = block.input.get("skill", "Unknown")
                        kind = classify_invocation(skill_name)
                        if kind == "builtin":
                            event_type = "builtin_command"
                            title = f"Built-in: /{skill_name}"
                        elif kind == "skill":
                            event_type = "skill_invocation"
                            title = f"Skill: /{skill_name}"
                        else:
                            event_type = "command_invocation"
                            title = f"Command: /{skill_name}"
                        metadata["command_name"] = skill_name
                        metadata["is_plugin"] = ":" in skill_name
                        if ":" in skill_name:
                            metadata["plugin"] = skill_name.split(":")[0]
                        summary = f"Invoked /{skill_name}"
                    else:
                        event_type = "tool_call"

                    events.append(
                        TimelineEvent(
                            id=f"evt-{event_counter}",
                            event_type=event_type,
                            timestamp=msg.timestamp,
                            actor=msg_actor,
                            actor_type=msg_actor_type,
                            title=title,
                            summary=summary,
                            metadata=metadata,
                        )
                    )

                elif isinstance(block, ThinkingBlock):
                    thinking_preview = block.thinking[:150] if block.thinking else ""
                    events.append(
                        TimelineEvent(
                            id=f"evt-{event_counter}",
                            event_type="thinking",
                            timestamp=msg.timestamp,
                            actor=msg_actor,
                            actor_type=msg_actor_type,
                            title="Thinking",
                            summary=thinking_preview if thinking_preview else None,
                            metadata={"full_thinking": block.thinking},
                        )
                    )

                elif isinstance(block, TextBlock):
                    # Only include substantial text responses
                    if len(block.text) > 50:
                        text_preview = block.text[:150]
                        events.append(
                            TimelineEvent(
                                id=f"evt-{event_counter}",
                                event_type="response",
                                timestamp=msg.timestamp,
                                actor=msg_actor,
                                actor_type=msg_actor_type,
                                title="Response",
                                summary=text_preview,
                                metadata={"full_text": block.text},
                            )
                        )

    # Sort by timestamp
    events.sort(key=lambda e: e.timestamp)
    return events


def _detect_command_from_content(
    content: str,
) -> tuple[str, str, str | None, str | None]:
    """Parse <command-message> tags or slash-command patterns from user prompt content.

    First checks for structured <command-message> tags (Claude Code's standard format).
    Falls back to detecting /command patterns in plain text for skills invoked via hooks
    (magic keywords) where the slash command is embedded in a larger message.

    Returns (event_type, title, summary, command_name).
    """
    cmd_name, args = parse_command_from_content(content)

    # Fallback: detect /command patterns in plain text (hook-triggered skills)
    if cmd_name is None:
        slash_cmds = detect_slash_commands_in_text(content)
        # Pick the most specific (skill-like) command if multiple found
        for candidate in slash_cmds:
            kind = classify_invocation(candidate)
            if kind == "skill":
                cmd_name = candidate
                args = None
                break
        # Don't fall back to "command" or "builtin" detection in plain text.
        # Both user-authored commands and builtins are always wrapped in
        # <command-message> tags when actually invoked, so they're caught
        # by the primary path above.  Only skills need the fallback
        # (hook-triggered skills bypass the tag wrapping).

    if cmd_name is None:
        return "prompt", "User prompt", None, None

    kind = classify_invocation(cmd_name)
    summary = args[:200] if args else f"Invoked /{cmd_name}"

    if kind == "builtin":
        return "builtin_command", f"Built-in: /{cmd_name}", summary, cmd_name
    elif kind == "skill":
        return "skill_invocation", f"Skill: /{cmd_name}", summary, cmd_name
    else:
        return "command_invocation", f"Command: /{cmd_name}", summary, cmd_name


def _strip_command_tags(content: str) -> str:
    """Remove command XML tags from content for display."""
    return strip_command_tags(content)


def _build_tool_call_metadata(
    block: ToolUseBlock,
    base_metadata: dict,
    result_data: Optional[ToolResultData],
    subagent_info: dict[str, Optional[str]],
) -> dict:
    """Build complete metadata for a tool call, merging in result if available."""
    metadata = {"tool_name": block.name, "tool_id": block.id, **base_metadata}

    # For Task tool, add spawning context
    if block.name == "Task":
        metadata["is_spawn_task"] = True

    if result_data is None:
        return metadata

    # Merge result data
    metadata["has_result"] = True
    metadata["result_timestamp"] = result_data.timestamp.isoformat()
    metadata["result_content"] = result_data.content

    if result_data.parsed:
        metadata["result_parsed"] = result_data.parsed

    # Special handling for Task tool - use pre-extracted spawned agent ID
    if block.name == "Task" and result_data.spawned_agent_id:
        metadata["spawned_agent_id"] = result_data.spawned_agent_id
        metadata["spawned_agent_slug"] = subagent_info.get(result_data.spawned_agent_id)

    # Determine result status (success/error) for display
    if "error" in result_data.content.lower()[:100]:
        metadata["result_status"] = "error"
    else:
        metadata["result_status"] = "success"

    return metadata


# =============================================================================
# Tool Usage Summary
# =============================================================================


def build_tool_usage_summaries(
    session_tool_counts: Counter,
    subagent_tool_counts: Optional[Counter] = None,
) -> list[ToolUsageSummary]:
    """
    Build tool usage summaries from tool count data.

    Args:
        session_tool_counts: Tool counts from main session/agent
        subagent_tool_counts: Tool counts from subagents (sessions only)

    Returns:
        List of ToolUsageSummary sorted by count descending
    """
    subagent_tool_counts = subagent_tool_counts or Counter()

    # Combine into summaries
    all_tools = set(session_tool_counts.keys()) | set(subagent_tool_counts.keys())
    summaries = []

    for tool_name in sorted(all_tools):
        by_session = session_tool_counts.get(tool_name, 0)
        by_subagents = subagent_tool_counts.get(tool_name, 0)
        summaries.append(
            ToolUsageSummary(
                tool_name=tool_name,
                count=by_session + by_subagents,
                by_session=by_session,
                by_subagents=by_subagents,
            )
        )

    # Sort by total count descending
    summaries.sort(key=lambda s: s.count, reverse=True)
    return summaries


def build_agent_tool_summaries(tool_counts: Counter) -> list[ToolUsageSummary]:
    """
    Build tool usage summaries for an agent (subagent or standalone).

    For agents, all usage is attributed to the agent itself (by_subagents field).

    Args:
        tool_counts: Tool counts from the agent

    Returns:
        List of ToolUsageSummary sorted by count descending
    """
    summaries = [
        ToolUsageSummary(
            tool_name=tool_name,
            count=count,
            by_session=0,  # Agents don't have subagents themselves
            by_subagents=count,  # All usage is from this agent
        )
        for tool_name, count in tool_counts.items()
    ]

    # Sort by count descending
    summaries.sort(key=lambda s: s.count, reverse=True)
    return summaries


# =============================================================================
# File Activity
# =============================================================================


def build_file_activities(file_operations: list[FileOperation]) -> list[FileActivity]:
    """
    Convert FileOperation dataclasses to FileActivity schemas.

    Args:
        file_operations: List of FileOperation objects from data collection

    Returns:
        List of FileActivity sorted by timestamp
    """
    activities = [
        FileActivity(
            path=op.path,
            operation=op.operation,
            actor=op.actor,
            actor_type=op.actor_type,
            timestamp=op.timestamp,
            tool_name=op.tool_name,
        )
        for op in file_operations
    ]

    # Sort by timestamp
    activities.sort(key=lambda a: a.timestamp)
    return activities

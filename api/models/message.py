"""
Message models for Claude Code session JSONL entries.

Each line in a session .jsonl file is one of:
- UserMessage: User input/prompts
- AssistantMessage: Claude's responses
- FileHistorySnapshot: File backup checkpoint
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Callable, Dict, List, Literal, Optional, Union

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .api_error import ApiError, classify_api_error
from .content import ContentBlock, parse_content_block
from .usage import TokenUsage

UserSource = Literal[
    "human",
    "command",
    "shell",
    "interrupt",
    "tool_result",
    "peer_session",
    "agent",
    "task_notification",
    "scheduled",
    "skill_body",
    "system_reminder",
    "meta",
    "compact_summary",
    "local_command",
]


class MessageBase(BaseModel):
    """
    Base fields common to all JSONL message entries.

    These fields appear at the top level of each JSONL line.
    """

    model_config = ConfigDict(frozen=True, populate_by_name=True)

    uuid: str = Field(..., description="Unique message identifier")
    timestamp: datetime = Field(..., description="Message timestamp (ISO format)")
    parent_uuid: Optional[str] = Field(
        default=None, alias="parentUuid", description="Parent message UUID for threading"
    )
    session_id: Optional[str] = Field(default=None, alias="sessionId", description="Session UUID")
    is_sidechain: bool = Field(
        default=False, alias="isSidechain", description="True if subagent/sidechain message"
    )
    cwd: Optional[str] = Field(default=None, description="Working directory at message time")
    git_branch: Optional[str] = Field(
        default=None, alias="gitBranch", description="Git branch at message time"
    )
    version: Optional[str] = Field(default=None, description="Claude Code version")


class UserMessage(MessageBase):
    """
    User message entry from session JSONL.

    The actual content is nested under message.content in the raw JSONL.
    """

    type: Literal["user"] = "user"
    content: str = Field(..., description="User message text content")
    user_type: Optional[str] = Field(
        default=None, alias="userType", description="User type (e.g., 'external')"
    )
    agent_id: Optional[str] = Field(
        default=None, alias="agentId", description="Agent ID if from subagent"
    )
    slug: Optional[str] = Field(default=None, description="Subagent slug name")
    thinking_metadata: Optional[Dict[str, Any]] = Field(
        default=None,
        alias="thinkingMetadata",
        description="Thinking metadata (level, disabled, triggers)",
    )
    todos: List[Any] = Field(
        default_factory=list, description="Todo items associated with this message"
    )
    is_tool_result: bool = Field(
        default=False, description="True if content was a tool_result wrapper"
    )
    tool_result_id: Optional[str] = Field(default=None, description="tool_use_id if is_tool_result")
    image_attachments: List[Dict[str, str]] = Field(
        default_factory=list, description="Image attachments extracted from content blocks"
    )
    is_internal_message: bool = Field(
        default=False,
        description="True if content is internal (local commands, task notifications, etc)",
    )
    is_meta: bool = Field(
        default=False,
        alias="isMeta",
        description="True if Claude Code marked the message as meta (not typed by the user)",
    )
    source: UserSource = Field(
        default="human", description="Who or what produced this entry (see classify_user_source)"
    )
    origin_kind: Optional[str] = Field(default=None, description="origin.kind as written")
    origin_name: Optional[str] = Field(default=None, description="Sender name from origin.name")
    origin_from: Optional[str] = Field(default=None, description="Sender address from origin.from")
    origin_sender_task_id: Optional[str] = Field(
        default=None, description="origin.senderTaskId: the sending agent's id"
    )
    origin_relayed: bool = Field(default=False, description="True when origin.hopChain is set")
    source_tool_use_id: Optional[str] = Field(
        default=None, alias="sourceToolUseID", description="Tool call that injected this entry"
    )
    is_compact_summary: bool = Field(
        default=False, alias="isCompactSummary", description="True for a compaction summary"
    )
    prompt_source: Optional[str] = Field(
        default=None, alias="promptSource", description="typed, queued, sdk, system, ..."
    )
    turn_origin: Optional[str] = Field(
        default=None, alias="turnOrigin", description="human, peer, scheduled, ..."
    )
    scheduled_task_id: Optional[str] = Field(default=None, alias="scheduledTaskId")
    wakeup_source: Optional[str] = Field(default=None, alias="wakeupSource")
    spawned_agent_id: Optional[str] = Field(
        default=None, description="toolUseResult.agentId of an Agent tool result"
    )
    tool_result_is_error: Optional[bool] = Field(
        default=None, description="is_error of the tool_result block, when the block has it"
    )
    prompt_text: Optional[str] = Field(
        default=None,
        description="Text a tool_result entry carries beside the result (fork prompts)",
    )

    @model_validator(mode="before")
    @classmethod
    def _extract_nested_content(cls, data: Any) -> Any:
        """Extract content from nested message.content structure."""
        if not isinstance(data, dict):
            return data
        data = _extract_sender_fields(data)
        # If content is already set at top level, use it directly
        if "content" in data and not isinstance(data.get("content"), (dict, list)):
            _apply_source(data, data.get("content") or "")
            return data
        # Extract from nested message.content
        nested_msg = data.get("message", {})
        content = nested_msg.get("content", data.get("content", ""))
        # Handle case where content is a list (tool results)
        if isinstance(content, list):
            content_parts = content
            # Detect tool_result wrappers BEFORE stripping the structure
            for part in content:
                if isinstance(part, dict) and part.get("type") == "tool_result":
                    data["is_tool_result"] = True
                    data["tool_result_id"] = part.get("tool_use_id")
                    if isinstance(part.get("is_error"), bool):
                        data["tool_result_is_error"] = part["is_error"]
                    break
            parts = []
            images = []
            for part in content:
                if isinstance(part, dict):
                    if part.get("type") == "image":
                        source = part.get("source", {})
                        if source.get("type") == "base64":
                            _ALLOWED_IMAGE_TYPES = {
                                "image/png",
                                "image/jpeg",
                                "image/gif",
                                "image/webp",
                                "image/svg+xml",
                            }
                            mt = source.get("media_type", "image/png")
                            if mt not in _ALLOWED_IMAGE_TYPES:
                                mt = "image/png"
                            images.append(
                                {
                                    "media_type": mt,
                                    "data": source.get("data", ""),
                                }
                            )
                        continue  # Don't stringify image blocks
                    text = part.get("text") or part.get("content")
                    if isinstance(text, str):
                        parts.append(text)
                    else:
                        parts.append(str(part))
                elif isinstance(part, str):
                    parts.append(part)
            content = "\n".join(parts) or ""
            if images:
                data["image_attachments"] = images
            if data.get("is_tool_result"):
                texts = [
                    p["text"]
                    for p in content_parts
                    if isinstance(p, dict)
                    and p.get("type") == "text"
                    and isinstance(p.get("text"), str)
                ]
                data["prompt_text"] = "\n".join(texts) or None
        _apply_source(data, content if isinstance(content, str) else "")
        return {**data, "content": content}


# Sources that are not something the user typed or ran.
_INTERNAL_SOURCES = frozenset(
    {
        "peer_session",
        "agent",
        "task_notification",
        "scheduled",
        "skill_body",
        "system_reminder",
        "meta",
        "compact_summary",
        "local_command",
    }
)

_SYSTEM_NOTIFICATION_PREFIX = "[SYSTEM NOTIFICATION - NOT USER INPUT]"

# Text patterns for sessions written before the structured sender fields existed.
_LEGACY_TEXT_SOURCES: tuple[tuple[tuple[str, ...], UserSource], ...] = (
    (("<task-notification>", _SYSTEM_NOTIFICATION_PREFIX), "task_notification"),
    (("<teammate-message", "<agent-message"), "agent"),
    (("The coordinator sent a message",), "agent"),
    (("<cross-session-message", "Another Claude session sent a message"), "peer_session"),
    (("<bash-input>", "<bash-stdout>", "<bash-stderr>"), "shell"),
    (
        ("<local-command-caveat>", "<local-command-stdout>", "<local-command-stderr>"),
        "local_command",
    ),
    (("<command-name>", "<command-message>"), "command"),
    (("This session is being continued from a previous",), "compact_summary"),
    (("[Request interrupted by user",), "interrupt"),
    (
        (
            "<retrieval_status>",
            "Command running in background",
            "Command was manually backgrounded",
        ),
        "meta",
    ),
)


def _extract_sender_fields(data: dict) -> dict:
    """Flatten origin and toolUseResult.agentId into top-level keys; returns a copy."""
    result = dict(data)
    origin = data.get("origin")
    if isinstance(origin, dict):
        result["origin_kind"] = _str_or_none(origin.get("kind"))
        result["origin_name"] = _str_or_none(origin.get("name"))
        result["origin_from"] = _str_or_none(origin.get("from"))
        result["origin_sender_task_id"] = _str_or_none(origin.get("senderTaskId"))
        result["origin_relayed"] = bool(origin.get("hopChain"))
    tool_use_result = data.get("toolUseResult")
    if isinstance(tool_use_result, dict) and isinstance(tool_use_result.get("agentId"), str):
        result["spawned_agent_id"] = tool_use_result["agentId"]
    for key in ("promptSource", "turnOrigin", "scheduledTaskId", "wakeupSource", "sourceToolUseID"):
        if key in result and not isinstance(result[key], str):
            del result[key]
    return result


def _str_or_none(value: Any) -> Optional[str]:
    return value if isinstance(value, str) and value else None


def _first(data: dict, *keys: str) -> Any:
    for key in keys:
        if data.get(key):
            return data[key]
    return None


def classify_text_source(content: str) -> Optional[UserSource]:
    """Source implied by how the text starts, or None if nothing matches."""
    head = content.lstrip()[:200]
    if head.startswith("Another Claude session sent a message") and (
        "<agent-message" in head or "<teammate-message" in head
    ):
        return "agent"
    for prefixes, source in _LEGACY_TEXT_SOURCES:
        if head.startswith(prefixes):
            return source
    return None


def classify_user_source(data: dict, content: str) -> UserSource:
    """Who produced a user entry: structured fields first, text patterns as fallback."""
    if data.get("is_tool_result"):
        return "tool_result"
    if _first(data, "isCompactSummary", "is_compact_summary"):
        return "compact_summary"
    kind = data.get("origin_kind")
    head = content.lstrip()[:120]
    if kind == "peer":
        if data.get("origin_sender_task_id") or "<agent-message" in head:
            return "agent"
        return "peer_session"
    if kind == "coordinator":
        return "agent"
    turn_origin = _first(data, "turnOrigin", "turn_origin")
    if kind == "task-notification" or turn_origin == "task_notification":
        return "task_notification"
    if turn_origin == "scheduled" or _first(data, "wakeupSource", "wakeup_source"):
        return "scheduled"
    if _first(data, "sourceToolUseID", "source_tool_use_id"):
        return "skill_body"
    from_text = classify_text_source(content)
    if from_text is not None:
        return from_text
    if kind == "human":
        return "human"
    if head.startswith("<system-reminder>"):
        return "system_reminder"
    if _first(data, "isMeta", "is_meta"):
        return "meta"
    return "human"


def _apply_source(data: dict, content: str) -> None:
    """Set source and is_internal_message on the raw dict."""
    # Always derived: an entry's own top-level "source" key means something else
    data["source"] = classify_user_source(data, content)
    text_source = classify_text_source(content) if content else None
    if data["source"] in _INTERNAL_SOURCES or text_source in _INTERNAL_SOURCES:
        data["is_internal_message"] = True


class AssistantMessage(MessageBase):
    """
    Assistant message entry from session JSONL.

    Contains model info, content blocks, and token usage.
    """

    type: Literal["assistant"] = "assistant"
    model: Optional[str] = Field(
        default=None, description="Model used (e.g., claude-opus-4-5-20251101)"
    )
    message_id: Optional[str] = Field(
        default=None, alias="messageId", description="API message ID (msg_xxx)"
    )
    content_blocks: List[ContentBlock] = Field(
        default_factory=list, description="Response content blocks"
    )
    usage: Optional[TokenUsage] = Field(default=None, description="Token usage statistics")
    stop_reason: Optional[str] = Field(
        default=None, description="Stop reason (end_turn, tool_use, etc.)"
    )
    request_id: Optional[str] = Field(default=None, alias="requestId", description="API request ID")
    agent_id: Optional[str] = Field(
        default=None, alias="agentId", description="Agent ID if from subagent"
    )
    slug: Optional[str] = Field(default=None, description="Subagent slug name")
    api_error: Optional[ApiError] = Field(
        default=None, description="Set when this turn is a synthetic API-error turn"
    )

    @property
    def is_synthetic(self) -> bool:
        """True for Claude Code's own placeholder turns (model `<synthetic>`)."""
        return self.model == "<synthetic>"

    @model_validator(mode="before")
    @classmethod
    def _extract_nested_message(cls, data: Any) -> Any:
        """Extract fields from nested message structure and parse content blocks."""
        if not isinstance(data, dict):
            return data
        # If content_blocks already set (direct instantiation), skip extraction
        if "content_blocks" in data:
            if "api_error" not in data:
                api_error = classify_api_error(data)
                if api_error is not None:
                    return {**data, "api_error": api_error}
            return data

        nested_msg = data.get("message", {})
        result = dict(data)

        # Classify from the raw top-level dict
        if "api_error" not in result:
            result["api_error"] = classify_api_error(data)

        # Extract fields from nested message
        if "model" not in result and "model" in nested_msg:
            result["model"] = nested_msg.get("model")
        if "messageId" not in result and "message_id" not in result:
            result["messageId"] = nested_msg.get("id")
        if "stop_reason" not in result:
            result["stop_reason"] = nested_msg.get("stop_reason")

        # Parse content blocks
        raw_content = nested_msg.get("content", [])
        content_blocks = []
        for block_data in raw_content:
            if isinstance(block_data, dict):
                try:
                    content_blocks.append(parse_content_block(block_data))
                except ValueError:
                    pass  # Skip unknown block types
        result["content_blocks"] = content_blocks

        # Parse usage
        if "usage" not in result and "usage" in nested_msg:
            result["usage"] = TokenUsage.model_validate(nested_msg["usage"])

        return result

    @property
    def text_content(self) -> str:
        """Extract concatenated text from all text blocks."""
        from .content import TextBlock

        return "\n".join(
            block.text for block in self.content_blocks if isinstance(block, TextBlock)
        )

    @property
    def tool_calls(self) -> List["ContentBlock"]:
        """Extract all tool use blocks."""
        from .content import ToolUseBlock

        return [block for block in self.content_blocks if isinstance(block, ToolUseBlock)]

    @property
    def tool_names(self) -> List[str]:
        """Get list of tool names used in this message."""
        from .content import ToolUseBlock

        return [block.name for block in self.content_blocks if isinstance(block, ToolUseBlock)]


class SessionTitleMessage(BaseModel):
    """
    Session title/naming message from session JSONL.

    These are generated by Claude Code to give sessions human-readable titles.
    They are NOT compaction events. The leafUuid typically points to a message
    in the same session that the title was derived from.

    Note: Due to a known Claude Code bug (issue #2597), these can sometimes
    appear in wrong session files with leafUuid pointing to different sessions.

    Structure:
    {
      "type": "summary",
      "summary": "Session title text",
      "leafUuid": "uuid"
    }
    """

    model_config = ConfigDict(frozen=True, populate_by_name=True)

    type: Literal["summary"] = "summary"
    summary: str = Field(..., description="Session title text")
    leaf_uuid: Optional[str] = Field(
        default=None, alias="leafUuid", description="Associated leaf message UUID"
    )


class CompactBoundaryMessage(BaseModel):
    """
    Compact boundary message indicating true context compaction.

    This is the real compaction marker - created when Claude Code runs /compact
    (manually or automatically when context window fills).

    Structure:
    {
      "type": "system",
      "subtype": "compact_boundary",
      "content": "Conversation compacted",
      "compactMetadata": {"trigger": "auto"|"manual", "preTokens": 155206},
      "logicalParentUuid": "uuid",
      "timestamp": "...",
      "uuid": "..."
    }
    """

    model_config = ConfigDict(frozen=True, populate_by_name=True)

    type: Literal["system"] = "system"
    subtype: Literal["compact_boundary"] = "compact_boundary"
    content: str = Field(default="Conversation compacted", description="Compaction marker text")
    uuid: str = Field(..., description="Unique message identifier")
    timestamp: datetime = Field(..., description="Compaction timestamp")
    logical_parent_uuid: Optional[str] = Field(
        default=None,
        alias="logicalParentUuid",
        description="Last message UUID before compaction",
    )
    session_id: Optional[str] = Field(default=None, alias="sessionId", description="Session UUID")
    slug: Optional[str] = Field(default=None, description="Session slug name")
    trigger: Optional[str] = Field(
        default=None, description="Compaction trigger: 'auto' or 'manual'"
    )
    pre_tokens: Optional[int] = Field(default=None, description="Token count before compaction")

    @model_validator(mode="before")
    @classmethod
    def _extract_compact_metadata(cls, data: Any) -> Any:
        """Extract trigger and pre_tokens from compactMetadata."""
        if not isinstance(data, dict):
            return data

        result = dict(data)
        compact_metadata = data.get("compactMetadata", {})

        if "trigger" not in result:
            result["trigger"] = compact_metadata.get("trigger")
        if "pre_tokens" not in result:
            result["pre_tokens"] = compact_metadata.get("preTokens")

        return result


class FileSnapshot(BaseModel):
    """Nested snapshot data within FileHistorySnapshot."""

    model_config = ConfigDict(frozen=True, populate_by_name=True)

    message_id: Optional[str] = Field(default=None, alias="messageId")
    tracked_file_backups: Dict[str, Any] = Field(
        default_factory=dict, alias="trackedFileBackups", description="Map of tracked file backups"
    )
    timestamp: Optional[datetime] = Field(default=None, description="Snapshot creation timestamp")


class FileHistorySnapshot(MessageBase):
    """
    File history snapshot entry from session JSONL.

    Records file backup checkpoints during a session.
    Structure:
    {
      "type": "file-history-snapshot",
      "messageId": "uuid",
      "snapshot": {
        "messageId": "uuid",
        "trackedFileBackups": {},
        "timestamp": "..."
      },
      "isSnapshotUpdate": false
    }
    """

    type: Literal["file-history-snapshot"] = "file-history-snapshot"
    message_id: Optional[str] = Field(
        default=None, alias="messageId", description="Associated message ID"
    )
    is_snapshot_update: bool = Field(
        default=False,
        alias="isSnapshotUpdate",
        description="Whether this updates existing snapshot",
    )
    snapshot: Optional[FileSnapshot] = Field(default=None, description="Nested snapshot data")
    # Keep these for backward compatibility
    tracked_file_backups: Dict[str, Any] = Field(
        default_factory=dict, description="Map of tracked file backups (from snapshot)"
    )
    snapshot_timestamp: Optional[datetime] = Field(
        default=None, description="Snapshot creation timestamp (from snapshot)"
    )

    @model_validator(mode="before")
    @classmethod
    def _extract_snapshot_data(cls, data: Any) -> Any:
        """Extract snapshot data and populate backward compatibility fields."""
        if not isinstance(data, dict):
            return data

        result = dict(data)
        snapshot_data = data.get("snapshot")

        # Use uuid if present, otherwise fall back to messageId
        if "uuid" not in result or not result.get("uuid"):
            result["uuid"] = data.get("uuid", data.get("messageId", ""))

        # If snapshot is already a FileSnapshot object, skip processing
        if isinstance(snapshot_data, FileSnapshot):
            return result

        # Handle dict snapshot data
        if snapshot_data is None:
            snapshot_data = {}

        # Use top-level timestamp or fall back to snapshot timestamp
        if "timestamp" not in result or not result.get("timestamp"):
            result["timestamp"] = data.get("timestamp", snapshot_data.get("timestamp"))

        # Create nested FileSnapshot from dict
        if snapshot_data:
            result["snapshot"] = FileSnapshot(
                message_id=snapshot_data.get("messageId"),
                tracked_file_backups=snapshot_data.get("trackedFileBackups", {}),
                timestamp=snapshot_data.get("timestamp"),
            )

            # Backward compatibility: populate flat fields from snapshot
            if "tracked_file_backups" not in result or not result.get("tracked_file_backups"):
                result["tracked_file_backups"] = snapshot_data.get("trackedFileBackups", {})
            if "snapshot_timestamp" not in result or not result.get("snapshot_timestamp"):
                result["snapshot_timestamp"] = snapshot_data.get("timestamp")

        return result


class QueueOperationMessage(BaseModel):
    """Queue operation message for plan-mode sessions."""

    model_config = ConfigDict(frozen=True, populate_by_name=True)

    type: Literal["queue-operation"] = "queue-operation"
    operation: str = Field(..., description="Operation type (enqueue/dequeue)")
    content: Optional[str] = Field(default=None, description="Queued content")
    timestamp: Optional[datetime] = Field(default=None, description="Operation timestamp")
    session_id: Optional[str] = Field(default=None, alias="sessionId", description="Session UUID")
    uuid: str = Field(default="", description="Message identifier")


class ProgressMessage(BaseModel):
    """Progress message emitted during plan-mode execution."""

    model_config = ConfigDict(frozen=True, populate_by_name=True)

    type: Literal["progress"] = "progress"
    uuid: str = Field(default="", description="Message identifier")
    timestamp: Optional[datetime] = Field(default=None, description="Progress timestamp")
    session_id: Optional[str] = Field(default=None, alias="sessionId", description="Session UUID")


# Union type for all message types
Message = Union[
    UserMessage,
    AssistantMessage,
    FileHistorySnapshot,
    SessionTitleMessage,
    CompactBoundaryMessage,
    QueueOperationMessage,
    ProgressMessage,
]

# Registry mapping message type to parser class
# Each class has model_validators that handle nested structure extraction
_MESSAGE_PARSERS: Dict[str, Callable[[Dict[str, Any]], Message]] = {
    "user": UserMessage.model_validate,
    "assistant": AssistantMessage.model_validate,
    "file-history-snapshot": FileHistorySnapshot.model_validate,
    "summary": SessionTitleMessage.model_validate,
    "queue-operation": QueueOperationMessage.model_validate,
    "progress": ProgressMessage.model_validate,
}


def parse_message(data: Dict[str, Any]) -> Message:
    """
    Parse a raw JSONL line dict into the appropriate Message type.

    Uses Pydantic model_validators for nested structure extraction.

    Args:
        data: Raw dict from JSONL line

    Returns:
        Typed Message instance

    Raises:
        ValueError: If message type is unknown
    """
    msg_type = data.get("type")

    # Handle system messages specially (need subtype check)
    if msg_type == "system":
        subtype = data.get("subtype")
        if subtype == "compact_boundary":
            return CompactBoundaryMessage.model_validate(data)
        raise ValueError(f"Unsupported system subtype: {subtype}")

    # Use registry for all other message types
    parser = _MESSAGE_PARSERS.get(msg_type)  # type: ignore[arg-type]
    if parser is None:
        raise ValueError(f"Unknown message type: {msg_type}")

    return parser(data)

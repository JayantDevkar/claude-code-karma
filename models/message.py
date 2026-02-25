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

from .content import ContentBlock, parse_content_block
from .usage import TokenUsage


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
    is_internal_message: bool = Field(
        default=False,
        description="True if content is internal (local commands, task notifications, etc)",
    )

    @model_validator(mode="before")
    @classmethod
    def _extract_nested_content(cls, data: Any) -> Any:
        """Extract content from nested message.content structure."""
        if not isinstance(data, dict):
            return data
        # If content is already set at top level, use it directly
        if "content" in data and not isinstance(data.get("content"), (dict, list)):
            # Detect internal message patterns on pre-set string content
            _detect_internal_message(data, data.get("content", ""))
            return data
        # Extract from nested message.content
        nested_msg = data.get("message", {})
        content = nested_msg.get("content", data.get("content", ""))
        # Handle case where content is a list (tool results)
        if isinstance(content, list):
            # Detect tool_result wrappers BEFORE stripping the structure
            for part in content:
                if isinstance(part, dict) and part.get("type") == "tool_result":
                    data["is_tool_result"] = True
                    data["tool_result_id"] = part.get("tool_use_id")
                    break
            parts = []
            for part in content:
                if isinstance(part, dict):
                    text = part.get("text") or part.get("content")
                    if isinstance(text, str):
                        parts.append(text)
                    else:
                        parts.append(str(part))
                elif isinstance(part, str):
                    parts.append(part)
            content = "\n".join(parts) or str(content)
        # Detect internal message patterns on the extracted text
        _detect_internal_message(data, content if isinstance(content, str) else "")
        return {**data, "content": content}


def _detect_internal_message(data: dict, content: str) -> None:
    """Set is_internal_message flag if content matches internal patterns."""
    if not content:
        return
    if (
        "<local-command-caveat>" in content
        or "<local-command-stdout>" in content
        or "<task-notification>" in content
        or "<retrieval_status>" in content
        or content.startswith("Command running in background")
        or content.startswith("Command was manually backgrounded")
        or content.startswith("This session is being continued from a previous")
    ):
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

    @model_validator(mode="before")
    @classmethod
    def _extract_nested_message(cls, data: Any) -> Any:
        """Extract fields from nested message structure and parse content blocks."""
        if not isinstance(data, dict):
            return data
        # If content_blocks already set (direct instantiation), skip extraction
        if "content_blocks" in data:
            return data

        nested_msg = data.get("message", {})
        result = dict(data)

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

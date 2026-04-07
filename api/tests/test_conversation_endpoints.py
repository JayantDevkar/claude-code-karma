"""
Unit tests for build_conversation_timeline task-subject mapping logic.

Covers the Pass 1b logic that:
1. Walks AssistantMessages for TaskCreate tool-use blocks.
2. Parses the matching tool result to extract the runtime-assigned task ID
   using the regex ``Task #(\\d+)``.
3. Builds a taskId -> subject map used to annotate TaskUpdate events.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from datetime import datetime, timezone
from typing import Iterator, List

import pytest

from models.content import ToolUseBlock
from models.message import AssistantMessage, UserMessage
from services.conversation_endpoints import build_conversation_timeline

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_TS = datetime(2026, 1, 8, 12, 0, 0, tzinfo=timezone.utc)
_TOOL_RESULT_TS = datetime(2026, 1, 8, 12, 0, 5, tzinfo=timezone.utc)


def _user_msg(uuid: str, content: str, *, is_tool_result: bool = False, tool_result_id: str | None = None) -> UserMessage:
    """Build a UserMessage directly without going through JSONL parsing."""
    return UserMessage(
        uuid=uuid,
        timestamp=_TS,
        type="user",
        content=content,
        is_tool_result=is_tool_result,
        tool_result_id=tool_result_id,
    )


def _assistant_msg_with_blocks(uuid: str, blocks: list) -> AssistantMessage:
    """Build an AssistantMessage with pre-parsed content blocks."""
    return AssistantMessage(
        uuid=uuid,
        timestamp=_TS,
        type="assistant",
        content_blocks=blocks,
    )


def _task_create_block(block_id: str, subject: str) -> ToolUseBlock:
    return ToolUseBlock(type="tool_use", id=block_id, name="TaskCreate", input={"subject": subject, "description": "desc"})


def _task_update_block(block_id: str, task_id: str, status: str = "in_progress") -> ToolUseBlock:
    return ToolUseBlock(type="tool_use", id=block_id, name="TaskUpdate", input={"taskId": task_id, "status": status})


class FakeConversation:
    """Minimal ConversationEntity for testing — satisfies MessageSource protocol."""

    def __init__(self, messages: List):
        self._messages = messages
        # Attributes expected by build_conversation_timeline callers
        self.cwd = "/fake/project"

    def iter_messages(self) -> Iterator:
        return iter(self._messages)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestTaskUpdateInheritsSubject:
    """TaskUpdate events should carry task_subject from matching TaskCreate."""

    def test_task_update_inherits_subject_from_task_create(self):
        """TaskCreate result supplies task ID; TaskUpdate metadata gets task_subject."""
        create_block_id = "toolu_create_001"
        update_block_id = "toolu_update_001"
        task_id = "1"
        subject = "Fix login bug"

        # Tool result UserMessage: content is the raw extracted string (already
        # handled by model validator when is_tool_result=True).
        result_content = f"Task #{task_id} created successfully: {subject}"

        messages = [
            _assistant_msg_with_blocks(
                "asst-001",
                [_task_create_block(create_block_id, subject)],
            ),
            _user_msg(
                "user-result-001",
                result_content,
                is_tool_result=True,
                tool_result_id=create_block_id,
            ),
            _assistant_msg_with_blocks(
                "asst-002",
                [_task_update_block(update_block_id, task_id)],
            ),
        ]

        conversation = FakeConversation(messages)
        events = build_conversation_timeline(conversation, working_dirs=["/fake/project"])

        # Find the TaskUpdate event
        update_events = [e for e in events if e.metadata.get("tool_name") == "TaskUpdate"]
        assert len(update_events) == 1, "Expected exactly one TaskUpdate event"
        assert update_events[0].metadata.get("task_subject") == subject

    def test_task_update_without_matching_task_create_has_no_subject(self):
        """TaskUpdate referencing an unknown taskId gets no task_subject in metadata."""
        update_block_id = "toolu_update_orphan"

        messages = [
            # No TaskCreate at all — just a TaskUpdate for task #99
            _assistant_msg_with_blocks(
                "asst-001",
                [_task_update_block(update_block_id, "99")],
            ),
        ]

        conversation = FakeConversation(messages)
        events = build_conversation_timeline(conversation, working_dirs=["/fake/project"])

        update_events = [e for e in events if e.metadata.get("tool_name") == "TaskUpdate"]
        assert len(update_events) == 1
        assert "task_subject" not in update_events[0].metadata

    def test_task_create_result_without_id_is_ignored(self):
        """TaskCreate result that doesn't match 'Task #<digits>' leaves map empty."""
        create_block_id = "toolu_create_bad"
        update_block_id = "toolu_update_bad"
        subject = "Should not appear"

        # Result content lacks "#N" pattern — regex won't match
        result_content = "Task created successfully (no ID in message)"

        messages = [
            _assistant_msg_with_blocks(
                "asst-001",
                [_task_create_block(create_block_id, subject)],
            ),
            _user_msg(
                "user-result-bad",
                result_content,
                is_tool_result=True,
                tool_result_id=create_block_id,
            ),
            _assistant_msg_with_blocks(
                "asst-002",
                [_task_update_block(update_block_id, "1")],
            ),
        ]

        conversation = FakeConversation(messages)
        events = build_conversation_timeline(conversation, working_dirs=["/fake/project"])

        update_events = [e for e in events if e.metadata.get("tool_name") == "TaskUpdate"]
        assert len(update_events) == 1
        assert "task_subject" not in update_events[0].metadata

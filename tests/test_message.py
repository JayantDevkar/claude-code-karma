"""
Unit tests for message models.

Tests MessageBase, UserMessage, AssistantMessage, FileHistorySnapshot,
FileSnapshot, and parse_message() function.
"""

from datetime import datetime
from typing import Any, Dict

import pytest

from models import (
    AssistantMessage,
    FileHistorySnapshot,
    FileSnapshot,
    MessageBase,
    TextBlock,
    ThinkingBlock,
    TokenUsage,
    ToolUseBlock,
    UserMessage,
    parse_message,
)


class TestMessageBase:
    """Tests for MessageBase common fields."""

    def test_required_fields(self):
        """MessageBase requires uuid and timestamp."""
        msg = MessageBase(
            uuid="test-uuid-123",
            timestamp=datetime(2026, 1, 8, 13, 0, 0),
        )
        assert msg.uuid == "test-uuid-123"
        assert msg.timestamp == datetime(2026, 1, 8, 13, 0, 0)

    def test_optional_fields_default_values(self):
        """Optional fields should have correct defaults."""
        msg = MessageBase(
            uuid="test-uuid",
            timestamp=datetime(2026, 1, 8),
        )
        assert msg.parent_uuid is None
        assert msg.session_id is None
        assert msg.is_sidechain is False
        assert msg.cwd is None
        assert msg.git_branch is None
        assert msg.version is None

    def test_all_fields_populated(self):
        """All MessageBase fields can be set."""
        msg = MessageBase(
            uuid="test-uuid",
            timestamp=datetime(2026, 1, 8, 13, 3, 26),
            parent_uuid="parent-uuid",
            session_id="session-uuid",
            is_sidechain=True,
            cwd="/Users/test/project",
            git_branch="feature/branch",
            version="2.1.1",
        )
        assert msg.uuid == "test-uuid"
        assert msg.parent_uuid == "parent-uuid"
        assert msg.session_id == "session-uuid"
        assert msg.is_sidechain is True
        assert msg.cwd == "/Users/test/project"
        assert msg.git_branch == "feature/branch"
        assert msg.version == "2.1.1"

    def test_timestamp_parsing_iso_format(self):
        """Timestamp can be parsed from ISO format string."""
        msg = MessageBase(
            uuid="test-uuid",
            timestamp="2026-01-08T13:03:26.654Z",
        )
        assert isinstance(msg.timestamp, datetime)
        assert msg.timestamp.year == 2026
        assert msg.timestamp.month == 1
        assert msg.timestamp.day == 8

    def test_field_aliases(self):
        """Field aliases (camelCase) should work."""
        data = {
            "uuid": "test-uuid",
            "timestamp": "2026-01-08T13:00:00Z",
            "parentUuid": "parent-uuid-via-alias",
            "sessionId": "session-via-alias",
            "isSidechain": True,
            "gitBranch": "main",
        }
        msg = MessageBase.model_validate(data)
        assert msg.parent_uuid == "parent-uuid-via-alias"
        assert msg.session_id == "session-via-alias"
        assert msg.is_sidechain is True
        assert msg.git_branch == "main"

    def test_immutability_frozen_model(self):
        """MessageBase should be immutable (frozen=True)."""
        msg = MessageBase(
            uuid="test-uuid",
            timestamp=datetime(2026, 1, 8),
        )
        with pytest.raises(Exception):
            msg.uuid = "new-uuid"

    def test_populate_by_name(self):
        """Both snake_case and camelCase field names should work."""
        # Using snake_case
        msg1 = MessageBase(
            uuid="test-uuid",
            timestamp=datetime(2026, 1, 8),
            parent_uuid="parent-snake",
            is_sidechain=False,
        )
        assert msg1.parent_uuid == "parent-snake"

        # Using camelCase via model_validate
        msg2 = MessageBase.model_validate(
            {
                "uuid": "test-uuid",
                "timestamp": "2026-01-08T00:00:00Z",
                "parentUuid": "parent-camel",
                "isSidechain": True,
            }
        )
        assert msg2.parent_uuid == "parent-camel"


class TestUserMessage:
    """Tests for UserMessage model."""

    def test_type_literal(self):
        """UserMessage type should be 'user'."""
        msg = UserMessage(
            uuid="user-uuid",
            timestamp=datetime(2026, 1, 8),
            content="Hello",
        )
        assert msg.type == "user"

    def test_content_field(self):
        """UserMessage content should be required."""
        msg = UserMessage(
            uuid="user-uuid",
            timestamp=datetime(2026, 1, 8),
            content="Help me understand this code",
        )
        assert msg.content == "Help me understand this code"

    def test_user_type_field(self):
        """UserMessage user_type field with alias."""
        msg = UserMessage(
            uuid="user-uuid",
            timestamp=datetime(2026, 1, 8),
            content="test",
            user_type="external",
        )
        assert msg.user_type == "external"

        # Via alias
        msg2 = UserMessage.model_validate(
            {
                "uuid": "user-uuid",
                "timestamp": "2026-01-08T00:00:00Z",
                "content": "test",
                "userType": "internal",
            }
        )
        assert msg2.user_type == "internal"

    def test_agent_id_field(self):
        """UserMessage agent_id field with alias."""
        msg = UserMessage.model_validate(
            {
                "uuid": "user-uuid",
                "timestamp": "2026-01-08T00:00:00Z",
                "content": "test",
                "agentId": "agent-123",
            }
        )
        assert msg.agent_id == "agent-123"

    def test_slug_field(self):
        """UserMessage slug field for subagent identification."""
        msg = UserMessage(
            uuid="user-uuid",
            timestamp=datetime(2026, 1, 8),
            content="test",
            slug="eager-puzzling-fairy",
        )
        assert msg.slug == "eager-puzzling-fairy"

    def test_thinking_metadata_field(self):
        """UserMessage thinking_metadata field with alias."""
        metadata = {"level": "high", "disabled": False, "triggers": []}
        msg = UserMessage(
            uuid="user-uuid",
            timestamp=datetime(2026, 1, 8),
            content="test",
            thinking_metadata=metadata,
        )
        assert msg.thinking_metadata == metadata
        assert msg.thinking_metadata["level"] == "high"

        # Via alias
        msg2 = UserMessage.model_validate(
            {
                "uuid": "user-uuid",
                "timestamp": "2026-01-08T00:00:00Z",
                "content": "test",
                "thinkingMetadata": {"level": "low", "disabled": True, "triggers": []},
            }
        )
        assert msg2.thinking_metadata["level"] == "low"
        assert msg2.thinking_metadata["disabled"] is True

    def test_todos_field_default_empty_list(self):
        """UserMessage todos should default to empty list."""
        msg = UserMessage(
            uuid="user-uuid",
            timestamp=datetime(2026, 1, 8),
            content="test",
        )
        assert msg.todos == []
        assert isinstance(msg.todos, list)

    def test_todos_field_with_data(self):
        """UserMessage todos can contain todo items."""
        todos = [
            {"content": "Task 1", "status": "pending"},
            {"content": "Task 2", "status": "completed"},
        ]
        msg = UserMessage(
            uuid="user-uuid",
            timestamp=datetime(2026, 1, 8),
            content="test",
            todos=todos,
        )
        assert len(msg.todos) == 2
        assert msg.todos[0]["content"] == "Task 1"

    def test_inherits_message_base_fields(self):
        """UserMessage should inherit all MessageBase fields."""
        msg = UserMessage(
            uuid="user-uuid",
            timestamp=datetime(2026, 1, 8),
            parent_uuid="parent",
            session_id="session",
            is_sidechain=True,
            cwd="/path",
            git_branch="main",
            version="2.1.1",
            content="test",
        )
        assert msg.parent_uuid == "parent"
        assert msg.session_id == "session"
        assert msg.is_sidechain is True
        assert msg.cwd == "/path"
        assert msg.git_branch == "main"
        assert msg.version == "2.1.1"

    def test_immutability(self):
        """UserMessage should be immutable."""
        msg = UserMessage(
            uuid="user-uuid",
            timestamp=datetime(2026, 1, 8),
            content="test",
        )
        with pytest.raises(Exception):
            msg.content = "modified"


class TestAssistantMessage:
    """Tests for AssistantMessage model."""

    def test_type_literal(self):
        """AssistantMessage type should be 'assistant'."""
        msg = AssistantMessage(
            uuid="asst-uuid",
            timestamp=datetime(2026, 1, 8),
        )
        assert msg.type == "assistant"

    def test_model_field(self):
        """AssistantMessage model field."""
        msg = AssistantMessage(
            uuid="asst-uuid",
            timestamp=datetime(2026, 1, 8),
            model="claude-opus-4-5-20251101",
        )
        assert msg.model == "claude-opus-4-5-20251101"

    def test_message_id_field_with_alias(self):
        """AssistantMessage message_id field with alias."""
        msg = AssistantMessage(
            uuid="asst-uuid",
            timestamp=datetime(2026, 1, 8),
            message_id="msg_test123",
        )
        assert msg.message_id == "msg_test123"

        # Via alias
        msg2 = AssistantMessage.model_validate(
            {
                "uuid": "asst-uuid",
                "timestamp": "2026-01-08T00:00:00Z",
                "messageId": "msg_via_alias",
            }
        )
        assert msg2.message_id == "msg_via_alias"

    def test_content_blocks_default_empty(self):
        """AssistantMessage content_blocks should default to empty list."""
        msg = AssistantMessage(
            uuid="asst-uuid",
            timestamp=datetime(2026, 1, 8),
        )
        assert msg.content_blocks == []

    def test_content_blocks_with_text(self):
        """AssistantMessage can have text content blocks."""
        text_block = TextBlock(text="Hello, I can help you.")
        msg = AssistantMessage(
            uuid="asst-uuid",
            timestamp=datetime(2026, 1, 8),
            content_blocks=[text_block],
        )
        assert len(msg.content_blocks) == 1
        assert isinstance(msg.content_blocks[0], TextBlock)

    def test_content_blocks_mixed_types(self):
        """AssistantMessage can have mixed content block types."""
        blocks = [
            ThinkingBlock(thinking="Let me analyze..."),
            TextBlock(text="Here is my response."),
            ToolUseBlock(id="toolu_01", name="Read", input={"file_path": "/test.py"}),
        ]
        msg = AssistantMessage(
            uuid="asst-uuid",
            timestamp=datetime(2026, 1, 8),
            content_blocks=blocks,
        )
        assert len(msg.content_blocks) == 3
        assert isinstance(msg.content_blocks[0], ThinkingBlock)
        assert isinstance(msg.content_blocks[1], TextBlock)
        assert isinstance(msg.content_blocks[2], ToolUseBlock)

    def test_usage_field(self):
        """AssistantMessage usage field."""
        usage = TokenUsage(
            input_tokens=100,
            output_tokens=500,
            cache_creation_input_tokens=50000,
            cache_read_input_tokens=10000,
        )
        msg = AssistantMessage(
            uuid="asst-uuid",
            timestamp=datetime(2026, 1, 8),
            usage=usage,
        )
        assert msg.usage is not None
        assert msg.usage.input_tokens == 100
        assert msg.usage.output_tokens == 500

    def test_stop_reason_field(self):
        """AssistantMessage stop_reason field."""
        msg = AssistantMessage(
            uuid="asst-uuid",
            timestamp=datetime(2026, 1, 8),
            stop_reason="end_turn",
        )
        assert msg.stop_reason == "end_turn"

        msg2 = AssistantMessage(
            uuid="asst-uuid",
            timestamp=datetime(2026, 1, 8),
            stop_reason="tool_use",
        )
        assert msg2.stop_reason == "tool_use"

    def test_request_id_field_with_alias(self):
        """AssistantMessage request_id field with alias."""
        msg = AssistantMessage.model_validate(
            {
                "uuid": "asst-uuid",
                "timestamp": "2026-01-08T00:00:00Z",
                "requestId": "req_test123",
            }
        )
        assert msg.request_id == "req_test123"

    def test_inherits_message_base_fields(self):
        """AssistantMessage should inherit all MessageBase fields."""
        msg = AssistantMessage(
            uuid="asst-uuid",
            timestamp=datetime(2026, 1, 8),
            parent_uuid="parent",
            session_id="session",
            is_sidechain=False,
            cwd="/path",
            git_branch="feature",
            version="2.1.1",
        )
        assert msg.parent_uuid == "parent"
        assert msg.session_id == "session"
        assert msg.cwd == "/path"

    def test_immutability(self):
        """AssistantMessage should be immutable."""
        msg = AssistantMessage(
            uuid="asst-uuid",
            timestamp=datetime(2026, 1, 8),
            model="claude-opus-4-5-20251101",
        )
        with pytest.raises(Exception):
            msg.model = "different-model"


class TestAssistantMessageProperties:
    """Tests for AssistantMessage computed properties."""

    def test_text_content_empty(self):
        """text_content returns empty string when no text blocks."""
        msg = AssistantMessage(
            uuid="asst-uuid",
            timestamp=datetime(2026, 1, 8),
            content_blocks=[],
        )
        assert msg.text_content == ""

    def test_text_content_single_block(self):
        """text_content extracts text from single text block."""
        msg = AssistantMessage(
            uuid="asst-uuid",
            timestamp=datetime(2026, 1, 8),
            content_blocks=[TextBlock(text="Hello world")],
        )
        assert msg.text_content == "Hello world"

    def test_text_content_multiple_blocks(self):
        """text_content concatenates multiple text blocks."""
        msg = AssistantMessage(
            uuid="asst-uuid",
            timestamp=datetime(2026, 1, 8),
            content_blocks=[
                TextBlock(text="First line."),
                TextBlock(text="Second line."),
            ],
        )
        assert msg.text_content == "First line.\nSecond line."

    def test_text_content_filters_non_text_blocks(self):
        """text_content ignores non-text blocks."""
        msg = AssistantMessage(
            uuid="asst-uuid",
            timestamp=datetime(2026, 1, 8),
            content_blocks=[
                ThinkingBlock(thinking="Internal thinking..."),
                TextBlock(text="Visible response."),
                ToolUseBlock(id="toolu_01", name="Read", input={}),
            ],
        )
        assert msg.text_content == "Visible response."

    def test_tool_calls_empty(self):
        """tool_calls returns empty list when no tool blocks."""
        msg = AssistantMessage(
            uuid="asst-uuid",
            timestamp=datetime(2026, 1, 8),
            content_blocks=[TextBlock(text="No tools")],
        )
        assert msg.tool_calls == []

    def test_tool_calls_single_tool(self):
        """tool_calls extracts single tool use block."""
        tool = ToolUseBlock(id="toolu_01", name="Read", input={"file_path": "/test.py"})
        msg = AssistantMessage(
            uuid="asst-uuid",
            timestamp=datetime(2026, 1, 8),
            content_blocks=[tool],
        )
        assert len(msg.tool_calls) == 1
        assert msg.tool_calls[0] == tool

    def test_tool_calls_multiple_tools(self):
        """tool_calls extracts multiple tool use blocks."""
        tool1 = ToolUseBlock(id="toolu_01", name="Read", input={})
        tool2 = ToolUseBlock(id="toolu_02", name="Write", input={})
        msg = AssistantMessage(
            uuid="asst-uuid",
            timestamp=datetime(2026, 1, 8),
            content_blocks=[
                TextBlock(text="Let me help."),
                tool1,
                TextBlock(text="And also..."),
                tool2,
            ],
        )
        assert len(msg.tool_calls) == 2
        assert msg.tool_calls[0].name == "Read"
        assert msg.tool_calls[1].name == "Write"

    def test_tool_names_empty(self):
        """tool_names returns empty list when no tools."""
        msg = AssistantMessage(
            uuid="asst-uuid",
            timestamp=datetime(2026, 1, 8),
            content_blocks=[],
        )
        assert msg.tool_names == []

    def test_tool_names_single(self):
        """tool_names returns single tool name."""
        msg = AssistantMessage(
            uuid="asst-uuid",
            timestamp=datetime(2026, 1, 8),
            content_blocks=[
                ToolUseBlock(id="toolu_01", name="Bash", input={"command": "ls"}),
            ],
        )
        assert msg.tool_names == ["Bash"]

    def test_tool_names_multiple(self):
        """tool_names returns list of all tool names."""
        msg = AssistantMessage(
            uuid="asst-uuid",
            timestamp=datetime(2026, 1, 8),
            content_blocks=[
                ToolUseBlock(id="toolu_01", name="Read", input={}),
                TextBlock(text="Reading file..."),
                ToolUseBlock(id="toolu_02", name="Write", input={}),
                ToolUseBlock(id="toolu_03", name="Bash", input={}),
            ],
        )
        assert msg.tool_names == ["Read", "Write", "Bash"]


class TestFileSnapshot:
    """Tests for FileSnapshot nested model."""

    def test_basic_creation(self):
        """FileSnapshot can be created with minimal fields."""
        snapshot = FileSnapshot()
        assert snapshot.message_id is None
        assert snapshot.tracked_file_backups == {}
        assert snapshot.timestamp is None

    def test_all_fields(self):
        """FileSnapshot all fields populated."""
        snapshot = FileSnapshot(
            message_id="msg-123",
            tracked_file_backups={"/path/file.py": "hash@v1"},
            timestamp=datetime(2026, 1, 8, 13, 0, 0),
        )
        assert snapshot.message_id == "msg-123"
        assert snapshot.tracked_file_backups == {"/path/file.py": "hash@v1"}
        assert snapshot.timestamp == datetime(2026, 1, 8, 13, 0, 0)

    def test_field_aliases(self):
        """FileSnapshot aliases (messageId, trackedFileBackups)."""
        snapshot = FileSnapshot.model_validate(
            {
                "messageId": "msg-via-alias",
                "trackedFileBackups": {"/test.py": "abc@v1"},
                "timestamp": "2026-01-08T13:00:00Z",
            }
        )
        assert snapshot.message_id == "msg-via-alias"
        assert snapshot.tracked_file_backups == {"/test.py": "abc@v1"}

    def test_immutability(self):
        """FileSnapshot should be immutable."""
        snapshot = FileSnapshot(message_id="msg-123")
        with pytest.raises(Exception):
            snapshot.message_id = "different"

    def test_multiple_tracked_files(self):
        """FileSnapshot can track multiple files."""
        snapshot = FileSnapshot(
            tracked_file_backups={
                "/path/file1.py": "hash1@v1",
                "/path/file2.py": "hash2@v1",
                "/path/subdir/file3.py": "hash3@v1",
            }
        )
        assert len(snapshot.tracked_file_backups) == 3


class TestFileHistorySnapshot:
    """Tests for FileHistorySnapshot model."""

    def test_type_literal(self):
        """FileHistorySnapshot type should be 'file-history-snapshot'."""
        snapshot = FileHistorySnapshot(
            uuid="snapshot-uuid",
            timestamp=datetime(2026, 1, 8),
        )
        assert snapshot.type == "file-history-snapshot"

    def test_message_id_field_with_alias(self):
        """FileHistorySnapshot message_id with alias."""
        snapshot = FileHistorySnapshot.model_validate(
            {
                "uuid": "snapshot-uuid",
                "timestamp": "2026-01-08T00:00:00Z",
                "messageId": "msg-123",
            }
        )
        assert snapshot.message_id == "msg-123"

    def test_is_snapshot_update_field(self):
        """FileHistorySnapshot is_snapshot_update with alias."""
        snapshot1 = FileHistorySnapshot(
            uuid="snapshot-uuid",
            timestamp=datetime(2026, 1, 8),
            is_snapshot_update=False,
        )
        assert snapshot1.is_snapshot_update is False

        snapshot2 = FileHistorySnapshot.model_validate(
            {
                "uuid": "snapshot-uuid",
                "timestamp": "2026-01-08T00:00:00Z",
                "isSnapshotUpdate": True,
            }
        )
        assert snapshot2.is_snapshot_update is True

    def test_snapshot_nested_field(self):
        """FileHistorySnapshot snapshot field contains FileSnapshot."""
        nested = FileSnapshot(
            message_id="nested-msg",
            tracked_file_backups={"/test.py": "hash@v1"},
            timestamp=datetime(2026, 1, 8),
        )
        snapshot = FileHistorySnapshot(
            uuid="snapshot-uuid",
            timestamp=datetime(2026, 1, 8),
            snapshot=nested,
        )
        assert snapshot.snapshot is not None
        assert snapshot.snapshot.message_id == "nested-msg"
        assert "/test.py" in snapshot.snapshot.tracked_file_backups

    def test_backward_compat_tracked_file_backups(self):
        """FileHistorySnapshot backward compat tracked_file_backups field."""
        snapshot = FileHistorySnapshot(
            uuid="snapshot-uuid",
            timestamp=datetime(2026, 1, 8),
            tracked_file_backups={"/old/path.py": "oldhash@v1"},
        )
        assert snapshot.tracked_file_backups == {"/old/path.py": "oldhash@v1"}

    def test_backward_compat_snapshot_timestamp(self):
        """FileHistorySnapshot backward compat snapshot_timestamp field."""
        snapshot = FileHistorySnapshot(
            uuid="snapshot-uuid",
            timestamp=datetime(2026, 1, 8),
            snapshot_timestamp=datetime(2026, 1, 8, 12, 0, 0),
        )
        assert snapshot.snapshot_timestamp == datetime(2026, 1, 8, 12, 0, 0)

    def test_inherits_message_base_fields(self):
        """FileHistorySnapshot inherits MessageBase fields."""
        snapshot = FileHistorySnapshot(
            uuid="snapshot-uuid",
            timestamp=datetime(2026, 1, 8),
            parent_uuid="parent",
            session_id="session",
            cwd="/path",
            git_branch="main",
            version="2.1.1",
        )
        assert snapshot.parent_uuid == "parent"
        assert snapshot.session_id == "session"
        assert snapshot.cwd == "/path"

    def test_immutability(self):
        """FileHistorySnapshot should be immutable."""
        snapshot = FileHistorySnapshot(
            uuid="snapshot-uuid",
            timestamp=datetime(2026, 1, 8),
        )
        with pytest.raises(Exception):
            snapshot.is_snapshot_update = True


class TestParseMessageUserMessage:
    """Tests for parse_message() parsing UserMessage."""

    def test_parse_user_message(self, sample_user_message_data: Dict[str, Any]):
        """parse_message correctly parses user message data."""
        msg = parse_message(sample_user_message_data)

        assert isinstance(msg, UserMessage)
        assert msg.type == "user"
        assert msg.uuid == "user-msg-uuid-001"
        assert msg.content == "Help me understand this code"

    def test_parse_user_message_extracts_nested_content(
        self, sample_user_message_data: Dict[str, Any]
    ):
        """parse_message extracts content from message.content."""
        msg = parse_message(sample_user_message_data)
        assert msg.content == "Help me understand this code"

    def test_parse_user_message_metadata(self, sample_user_message_data: Dict[str, Any]):
        """parse_message preserves user message metadata."""
        msg = parse_message(sample_user_message_data)

        assert msg.user_type == "external"
        assert msg.cwd == "/Users/test/project"
        assert msg.session_id == "test-session-uuid"
        assert msg.version == "2.1.1"
        assert msg.git_branch == "main"
        assert msg.is_sidechain is False

    def test_parse_user_message_thinking_metadata(self, sample_user_message_data: Dict[str, Any]):
        """parse_message preserves thinking metadata."""
        msg = parse_message(sample_user_message_data)

        assert msg.thinking_metadata is not None
        assert msg.thinking_metadata["level"] == "high"
        assert msg.thinking_metadata["disabled"] is False

    def test_parse_user_message_todos_empty(self, sample_user_message_data: Dict[str, Any]):
        """parse_message handles empty todos list."""
        msg = parse_message(sample_user_message_data)
        assert msg.todos == []

    def test_parse_user_message_list_content(self):
        """parse_message handles list content (tool results)."""
        data = {
            "type": "user",
            "uuid": "test-uuid",
            "timestamp": "2026-01-08T00:00:00Z",
            "message": {
                "content": [
                    {"type": "tool_result", "text": "File content here"},
                    {"type": "tool_result", "text": "More content"},
                ]
            },
        }
        msg = parse_message(data)
        assert isinstance(msg, UserMessage)
        assert "File content here" in msg.content
        assert "More content" in msg.content


class TestParseMessageAssistantMessage:
    """Tests for parse_message() parsing AssistantMessage."""

    def test_parse_assistant_message(self, sample_assistant_message_data: Dict[str, Any]):
        """parse_message correctly parses assistant message data."""
        msg = parse_message(sample_assistant_message_data)

        assert isinstance(msg, AssistantMessage)
        assert msg.type == "assistant"
        assert msg.uuid == "assistant-msg-uuid-001"
        assert msg.model == "claude-opus-4-5-20251101"

    def test_parse_assistant_message_content_blocks(
        self, sample_assistant_message_data: Dict[str, Any]
    ):
        """parse_message parses content blocks correctly."""
        msg = parse_message(sample_assistant_message_data)

        assert len(msg.content_blocks) == 3
        assert isinstance(msg.content_blocks[0], ThinkingBlock)
        assert isinstance(msg.content_blocks[1], TextBlock)
        assert isinstance(msg.content_blocks[2], ToolUseBlock)

    def test_parse_assistant_message_thinking_block(
        self, sample_assistant_message_data: Dict[str, Any]
    ):
        """parse_message correctly parses thinking block."""
        msg = parse_message(sample_assistant_message_data)

        thinking = msg.content_blocks[0]
        assert isinstance(thinking, ThinkingBlock)
        assert thinking.thinking == "Let me analyze this..."
        assert thinking.signature == "sig123"

    def test_parse_assistant_message_text_block(
        self, sample_assistant_message_data: Dict[str, Any]
    ):
        """parse_message correctly parses text block."""
        msg = parse_message(sample_assistant_message_data)

        text = msg.content_blocks[1]
        assert isinstance(text, TextBlock)
        assert text.text == "I can help you with that."

    def test_parse_assistant_message_tool_use_block(
        self, sample_assistant_message_data: Dict[str, Any]
    ):
        """parse_message correctly parses tool use block."""
        msg = parse_message(sample_assistant_message_data)

        tool = msg.content_blocks[2]
        assert isinstance(tool, ToolUseBlock)
        assert tool.id == "toolu_01ABC"
        assert tool.name == "Read"
        assert tool.input == {"file_path": "/test/file.py"}

    def test_parse_assistant_message_usage(self, sample_assistant_message_data: Dict[str, Any]):
        """parse_message parses usage statistics."""
        msg = parse_message(sample_assistant_message_data)

        assert msg.usage is not None
        assert msg.usage.input_tokens == 100
        assert msg.usage.output_tokens == 500
        assert msg.usage.cache_creation_input_tokens == 50000
        assert msg.usage.cache_read_input_tokens == 10000

    def test_parse_assistant_message_stop_reason(
        self, sample_assistant_message_data: Dict[str, Any]
    ):
        """parse_message preserves stop_reason."""
        msg = parse_message(sample_assistant_message_data)
        assert msg.stop_reason == "tool_use"

    def test_parse_assistant_message_request_id(
        self, sample_assistant_message_data: Dict[str, Any]
    ):
        """parse_message preserves request_id."""
        msg = parse_message(sample_assistant_message_data)
        assert msg.request_id == "req_test123"

    def test_parse_assistant_message_metadata(self, sample_assistant_message_data: Dict[str, Any]):
        """parse_message preserves assistant message metadata."""
        msg = parse_message(sample_assistant_message_data)

        assert msg.parent_uuid == "user-msg-uuid-001"
        assert msg.cwd == "/Users/test/project"
        assert msg.session_id == "test-session-uuid"
        assert msg.git_branch == "main"

    def test_parse_assistant_message_skips_unknown_blocks(self):
        """parse_message skips unknown content block types."""
        data = {
            "type": "assistant",
            "uuid": "test-uuid",
            "timestamp": "2026-01-08T00:00:00Z",
            "message": {
                "model": "claude-opus-4-5-20251101",
                "content": [
                    {"type": "text", "text": "Known block"},
                    {"type": "unknown_type", "data": "ignored"},
                    {"type": "text", "text": "Another known block"},
                ],
            },
        }
        msg = parse_message(data)
        assert len(msg.content_blocks) == 2
        assert all(isinstance(b, TextBlock) for b in msg.content_blocks)


class TestParseMessageFileHistorySnapshot:
    """Tests for parse_message() parsing FileHistorySnapshot."""

    def test_parse_file_history_snapshot(self, sample_file_history_snapshot_data: Dict[str, Any]):
        """parse_message correctly parses file history snapshot."""
        msg = parse_message(sample_file_history_snapshot_data)

        assert isinstance(msg, FileHistorySnapshot)
        assert msg.type == "file-history-snapshot"

    def test_parse_file_history_snapshot_uuid(
        self, sample_file_history_snapshot_data: Dict[str, Any]
    ):
        """parse_message extracts uuid from snapshot data."""
        msg = parse_message(sample_file_history_snapshot_data)
        assert msg.uuid == "snapshot-uuid-001"

    def test_parse_file_history_snapshot_message_id(
        self, sample_file_history_snapshot_data: Dict[str, Any]
    ):
        """parse_message extracts message_id."""
        msg = parse_message(sample_file_history_snapshot_data)
        assert msg.message_id == "snapshot-msg-uuid-001"

    def test_parse_file_history_snapshot_is_snapshot_update(
        self, sample_file_history_snapshot_data: Dict[str, Any]
    ):
        """parse_message extracts is_snapshot_update flag."""
        msg = parse_message(sample_file_history_snapshot_data)
        assert msg.is_snapshot_update is False

    def test_parse_file_history_snapshot_nested_snapshot(
        self, sample_file_history_snapshot_data: Dict[str, Any]
    ):
        """parse_message creates nested FileSnapshot object."""
        msg = parse_message(sample_file_history_snapshot_data)

        assert msg.snapshot is not None
        assert isinstance(msg.snapshot, FileSnapshot)
        assert msg.snapshot.message_id == "snapshot-msg-uuid-001"

    def test_parse_file_history_snapshot_tracked_backups(
        self, sample_file_history_snapshot_data: Dict[str, Any]
    ):
        """parse_message extracts tracked file backups."""
        msg = parse_message(sample_file_history_snapshot_data)

        assert msg.snapshot.tracked_file_backups == {"/test/file.py": "abc123@v1"}
        # Also available via backward compat field
        assert msg.tracked_file_backups == {"/test/file.py": "abc123@v1"}

    def test_parse_file_history_snapshot_timestamps(
        self, sample_file_history_snapshot_data: Dict[str, Any]
    ):
        """parse_message handles snapshot timestamps."""
        msg = parse_message(sample_file_history_snapshot_data)

        assert msg.timestamp is not None
        assert msg.snapshot.timestamp is not None
        # Backward compat field
        assert msg.snapshot_timestamp is not None

    def test_parse_file_history_snapshot_fallback_uuid(self):
        """parse_message falls back to messageId for uuid."""
        data = {
            "type": "file-history-snapshot",
            "messageId": "fallback-msg-id",
            "snapshot": {
                "trackedFileBackups": {},
                "timestamp": "2026-01-08T00:00:00Z",
            },
            "timestamp": "2026-01-08T00:00:00Z",
        }
        msg = parse_message(data)
        # Falls back to messageId when uuid not present
        assert msg.uuid == "fallback-msg-id"


class TestParseMessageErrors:
    """Tests for parse_message() error handling."""

    def test_parse_message_unknown_type_raises_error(self):
        """parse_message raises ValueError for unknown message types."""
        data = {
            "type": "unknown_type",
            "uuid": "test-uuid",
            "timestamp": "2026-01-08T00:00:00Z",
        }
        with pytest.raises(ValueError) as exc_info:
            parse_message(data)
        assert "Unknown message type: unknown_type" in str(exc_info.value)

    def test_parse_message_none_type_raises_error(self):
        """parse_message raises ValueError when type is None/missing."""
        data = {
            "uuid": "test-uuid",
            "timestamp": "2026-01-08T00:00:00Z",
        }
        with pytest.raises(ValueError) as exc_info:
            parse_message(data)
        assert "Unknown message type: None" in str(exc_info.value)

    def test_parse_message_empty_type_raises_error(self):
        """parse_message raises ValueError for empty type string."""
        data = {
            "type": "",
            "uuid": "test-uuid",
            "timestamp": "2026-01-08T00:00:00Z",
        }
        with pytest.raises(ValueError) as exc_info:
            parse_message(data)
        assert "Unknown message type:" in str(exc_info.value)


class TestFieldAliases:
    """Tests for field alias mappings (camelCase -> snake_case)."""

    def test_parent_uuid_alias(self):
        """parentUuid maps to parent_uuid."""
        data = {
            "uuid": "test",
            "timestamp": "2026-01-08T00:00:00Z",
            "parentUuid": "parent-via-alias",
        }
        msg = MessageBase.model_validate(data)
        assert msg.parent_uuid == "parent-via-alias"

    def test_session_id_alias(self):
        """sessionId maps to session_id."""
        data = {
            "uuid": "test",
            "timestamp": "2026-01-08T00:00:00Z",
            "sessionId": "session-via-alias",
        }
        msg = MessageBase.model_validate(data)
        assert msg.session_id == "session-via-alias"

    def test_is_sidechain_alias(self):
        """isSidechain maps to is_sidechain."""
        data = {
            "uuid": "test",
            "timestamp": "2026-01-08T00:00:00Z",
            "isSidechain": True,
        }
        msg = MessageBase.model_validate(data)
        assert msg.is_sidechain is True

    def test_git_branch_alias(self):
        """gitBranch maps to git_branch."""
        data = {
            "uuid": "test",
            "timestamp": "2026-01-08T00:00:00Z",
            "gitBranch": "feature/test",
        }
        msg = MessageBase.model_validate(data)
        assert msg.git_branch == "feature/test"

    def test_user_type_alias(self):
        """userType maps to user_type."""
        data = {
            "uuid": "test",
            "timestamp": "2026-01-08T00:00:00Z",
            "content": "test",
            "userType": "external",
        }
        msg = UserMessage.model_validate(data)
        assert msg.user_type == "external"

    def test_agent_id_alias(self):
        """agentId maps to agent_id."""
        data = {
            "uuid": "test",
            "timestamp": "2026-01-08T00:00:00Z",
            "content": "test",
            "agentId": "agent-123",
        }
        msg = UserMessage.model_validate(data)
        assert msg.agent_id == "agent-123"

    def test_thinking_metadata_alias(self):
        """thinkingMetadata maps to thinking_metadata."""
        data = {
            "uuid": "test",
            "timestamp": "2026-01-08T00:00:00Z",
            "content": "test",
            "thinkingMetadata": {"level": "high"},
        }
        msg = UserMessage.model_validate(data)
        assert msg.thinking_metadata == {"level": "high"}

    def test_message_id_alias(self):
        """messageId maps to message_id."""
        data = {
            "uuid": "test",
            "timestamp": "2026-01-08T00:00:00Z",
            "messageId": "msg-via-alias",
        }
        msg = AssistantMessage.model_validate(data)
        assert msg.message_id == "msg-via-alias"

    def test_request_id_alias(self):
        """requestId maps to request_id."""
        data = {
            "uuid": "test",
            "timestamp": "2026-01-08T00:00:00Z",
            "requestId": "req-via-alias",
        }
        msg = AssistantMessage.model_validate(data)
        assert msg.request_id == "req-via-alias"

    def test_is_snapshot_update_alias(self):
        """isSnapshotUpdate maps to is_snapshot_update."""
        data = {
            "uuid": "test",
            "timestamp": "2026-01-08T00:00:00Z",
            "isSnapshotUpdate": True,
        }
        msg = FileHistorySnapshot.model_validate(data)
        assert msg.is_snapshot_update is True

    def test_tracked_file_backups_alias(self):
        """trackedFileBackups maps to tracked_file_backups in FileSnapshot."""
        data = {
            "messageId": "msg-123",
            "trackedFileBackups": {"/test.py": "hash@v1"},
        }
        snapshot = FileSnapshot.model_validate(data)
        assert snapshot.tracked_file_backups == {"/test.py": "hash@v1"}


class TestImmutability:
    """Tests to verify frozen=True behavior across all models."""

    def test_message_base_immutable(self):
        """MessageBase should be frozen."""
        msg = MessageBase(uuid="test", timestamp=datetime(2026, 1, 8))
        with pytest.raises(Exception):
            msg.uuid = "modified"
        with pytest.raises(Exception):
            msg.timestamp = datetime(2025, 1, 1)

    def test_user_message_immutable(self):
        """UserMessage should be frozen."""
        msg = UserMessage(uuid="test", timestamp=datetime(2026, 1, 8), content="original")
        with pytest.raises(Exception):
            msg.content = "modified"
        with pytest.raises(Exception):
            msg.uuid = "modified"

    def test_assistant_message_immutable(self):
        """AssistantMessage should be frozen."""
        msg = AssistantMessage(uuid="test", timestamp=datetime(2026, 1, 8))
        with pytest.raises(Exception):
            msg.model = "modified"
        with pytest.raises(Exception):
            msg.content_blocks = []

    def test_file_snapshot_immutable(self):
        """FileSnapshot should be frozen."""
        snapshot = FileSnapshot(message_id="test")
        with pytest.raises(Exception):
            snapshot.message_id = "modified"

    def test_file_history_snapshot_immutable(self):
        """FileHistorySnapshot should be frozen."""
        snapshot = FileHistorySnapshot(uuid="test", timestamp=datetime(2026, 1, 8))
        with pytest.raises(Exception):
            snapshot.is_snapshot_update = True
        with pytest.raises(Exception):
            snapshot.message_id = "modified"

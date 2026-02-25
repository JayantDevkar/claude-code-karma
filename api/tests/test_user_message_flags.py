"""
Tests for UserMessage is_tool_result, tool_result_id, and is_internal_message flags.

These flags are set during _extract_nested_content model_validator to reliably
detect tool results and internal messages before the raw content structure is stripped.
"""

from datetime import datetime

from models import UserMessage, parse_message


class TestToolResultDetection:
    """Tests for is_tool_result and tool_result_id flag detection."""

    def test_tool_result_list_content_sets_flag(self):
        """List content with tool_result dict sets is_tool_result and tool_result_id."""
        data = {
            "type": "user",
            "uuid": "test-uuid",
            "timestamp": "2026-01-08T00:00:00Z",
            "message": {
                "content": [
                    {
                        "type": "tool_result",
                        "tool_use_id": "toolu_abc123",
                        "content": "File content here",
                    }
                ]
            },
        }
        msg = parse_message(data)
        assert isinstance(msg, UserMessage)
        assert msg.is_tool_result is True
        assert msg.tool_result_id == "toolu_abc123"

    def test_tool_result_string_inner_content(self):
        """tool_result with string inner content sets flags correctly."""
        data = {
            "type": "user",
            "uuid": "test-uuid",
            "timestamp": "2026-01-08T00:00:00Z",
            "message": {
                "content": [
                    {
                        "type": "tool_result",
                        "tool_use_id": "toolu_xyz789",
                        "text": "Success!",
                    }
                ]
            },
        }
        msg = parse_message(data)
        assert isinstance(msg, UserMessage)
        assert msg.is_tool_result is True
        assert msg.tool_result_id == "toolu_xyz789"

    def test_multiple_tool_results_uses_first(self):
        """Multiple tool_result entries: first one's ID is captured."""
        data = {
            "type": "user",
            "uuid": "test-uuid",
            "timestamp": "2026-01-08T00:00:00Z",
            "message": {
                "content": [
                    {
                        "type": "tool_result",
                        "tool_use_id": "toolu_first",
                        "content": "Result 1",
                    },
                    {
                        "type": "tool_result",
                        "tool_use_id": "toolu_second",
                        "content": "Result 2",
                    },
                ]
            },
        }
        msg = parse_message(data)
        assert msg.is_tool_result is True
        assert msg.tool_result_id == "toolu_first"

    def test_regular_prompt_no_flags(self):
        """Normal user text has all flags as False/None."""
        msg = UserMessage(
            uuid="test-uuid",
            timestamp=datetime(2026, 1, 8),
            content="Help me understand this code",
        )
        assert msg.is_tool_result is False
        assert msg.tool_result_id is None
        assert msg.is_internal_message is False

    def test_regular_prompt_via_parse_message(self):
        """Normal user prompt via parse_message has flags False."""
        data = {
            "type": "user",
            "uuid": "test-uuid",
            "timestamp": "2026-01-08T00:00:00Z",
            "message": {"content": "What does this function do?"},
        }
        msg = parse_message(data)
        assert isinstance(msg, UserMessage)
        assert msg.is_tool_result is False
        assert msg.tool_result_id is None
        assert msg.is_internal_message is False

    def test_list_content_without_tool_result_type(self):
        """List content without tool_result type does not set flag."""
        data = {
            "type": "user",
            "uuid": "test-uuid",
            "timestamp": "2026-01-08T00:00:00Z",
            "message": {
                "content": [
                    {"type": "text", "text": "Just some text"},
                ]
            },
        }
        msg = parse_message(data)
        assert msg.is_tool_result is False
        assert msg.tool_result_id is None


class TestInternalMessageDetection:
    """Tests for is_internal_message flag detection."""

    def test_local_command_stdout_detected(self):
        """<local-command-stdout> content is detected as internal."""
        data = {
            "type": "user",
            "uuid": "test-uuid",
            "timestamp": "2026-01-08T00:00:00Z",
            "message": {
                "content": "<local-command-stdout>total 42\ndrwxr-xr-x  5 user  staff  160</local-command-stdout>",
            },
        }
        msg = parse_message(data)
        assert msg.is_internal_message is True
        assert msg.is_tool_result is False

    def test_local_command_caveat_detected(self):
        """<local-command-caveat> content is detected as internal."""
        msg = UserMessage(
            uuid="test-uuid",
            timestamp=datetime(2026, 1, 8),
            content="<local-command-caveat>Note: output truncated</local-command-caveat>",
        )
        assert msg.is_internal_message is True

    def test_task_notification_detected(self):
        """<task-notification> content is detected as internal."""
        msg = UserMessage(
            uuid="test-uuid",
            timestamp=datetime(2026, 1, 8),
            content="<task-notification>Agent completed task</task-notification>",
        )
        assert msg.is_internal_message is True

    def test_retrieval_status_detected(self):
        """<retrieval_status> content is detected as internal."""
        msg = UserMessage(
            uuid="test-uuid",
            timestamp=datetime(2026, 1, 8),
            content="<retrieval_status>success</retrieval_status><task_id>abc</task_id>",
        )
        assert msg.is_internal_message is True

    def test_compaction_resume_detected(self):
        """Compaction resume message is detected as internal."""
        msg = UserMessage(
            uuid="test-uuid",
            timestamp=datetime(2026, 1, 8),
            content="This session is being continued from a previous conversation that was compacted.",
        )
        assert msg.is_internal_message is True

    def test_background_command_detected(self):
        """Background command message is detected as internal."""
        msg = UserMessage(
            uuid="test-uuid",
            timestamp=datetime(2026, 1, 8),
            content="Command running in background with id bg_12345",
        )
        assert msg.is_internal_message is True

    def test_manually_backgrounded_detected(self):
        """Manually backgrounded command is detected as internal."""
        msg = UserMessage(
            uuid="test-uuid",
            timestamp=datetime(2026, 1, 8),
            content="Command was manually backgrounded with id bg_67890",
        )
        assert msg.is_internal_message is True

    def test_normal_text_not_internal(self):
        """Normal user text is not detected as internal."""
        msg = UserMessage(
            uuid="test-uuid",
            timestamp=datetime(2026, 1, 8),
            content="Please fix the bug in the login form",
        )
        assert msg.is_internal_message is False

    def test_internal_detection_via_nested_content(self):
        """Internal message patterns detected from nested message.content."""
        data = {
            "type": "user",
            "uuid": "test-uuid",
            "timestamp": "2026-01-08T00:00:00Z",
            "message": {
                "content": "This session is being continued from a previous conversation.",
            },
        }
        msg = parse_message(data)
        assert msg.is_internal_message is True


class TestFlagCombinations:
    """Tests for combined flag scenarios."""

    def test_tool_result_not_internal(self):
        """A tool_result is not also flagged as internal (unless content matches)."""
        data = {
            "type": "user",
            "uuid": "test-uuid",
            "timestamp": "2026-01-08T00:00:00Z",
            "message": {
                "content": [
                    {
                        "type": "tool_result",
                        "tool_use_id": "toolu_abc",
                        "content": "Some file contents here",
                    }
                ]
            },
        }
        msg = parse_message(data)
        assert msg.is_tool_result is True
        assert msg.is_internal_message is False

    def test_tool_result_with_internal_content(self):
        """A tool_result containing internal markers gets both flags."""
        data = {
            "type": "user",
            "uuid": "test-uuid",
            "timestamp": "2026-01-08T00:00:00Z",
            "message": {
                "content": [
                    {
                        "type": "tool_result",
                        "tool_use_id": "toolu_abc",
                        "text": "<task-notification>done</task-notification>",
                    }
                ]
            },
        }
        msg = parse_message(data)
        assert msg.is_tool_result is True
        assert msg.is_internal_message is True

    def test_immutability_of_new_fields(self):
        """New fields should be immutable (frozen model)."""
        msg = UserMessage(
            uuid="test-uuid",
            timestamp=datetime(2026, 1, 8),
            content="test",
        )
        import pytest

        with pytest.raises(Exception):
            msg.is_tool_result = True
        with pytest.raises(Exception):
            msg.tool_result_id = "toolu_test"
        with pytest.raises(Exception):
            msg.is_internal_message = True

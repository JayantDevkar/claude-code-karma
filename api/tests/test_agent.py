"""
Comprehensive unit tests for the Agent model.

Tests cover:
- Agent instantiation with all fields
- from_path() for standalone and subagent paths
- agent_id extraction from filename and JSONL
- slug extraction from JSONL first line
- iter_messages() and list_messages()
- message_count property
- exists property
- get_usage_summary() aggregation
- start_time and end_time properties
- is_subagent detection
- Immutability (frozen=True)
- list_tasks() for task reconstruction from JSONL
"""

import json
from datetime import datetime
from pathlib import Path

import pytest
from pydantic import ValidationError

from models import (
    Agent,
    AssistantMessage,
    TokenUsage,
    UserMessage,
)


class TestAgentInstantiation:
    """Test Agent instantiation with various field combinations."""

    def test_agent_with_all_fields(self, temp_project_dir: Path) -> None:
        """Test creating an Agent with all fields populated."""
        jsonl_path = temp_project_dir / "agent-abc123.jsonl"
        jsonl_path.touch()

        agent = Agent(
            agent_id="abc123",
            jsonl_path=jsonl_path,
            is_subagent=True,
            parent_session_uuid="test-session-uuid",
            slug="eager-puzzling-fairy",
        )

        assert agent.agent_id == "abc123"
        assert agent.jsonl_path == jsonl_path
        assert agent.is_subagent is True
        assert agent.parent_session_uuid == "test-session-uuid"
        assert agent.slug == "eager-puzzling-fairy"

    def test_agent_with_required_fields_only(self, temp_project_dir: Path) -> None:
        """Test creating an Agent with only required fields."""
        jsonl_path = temp_project_dir / "agent-def456.jsonl"
        jsonl_path.touch()

        agent = Agent(
            agent_id="def456",
            jsonl_path=jsonl_path,
        )

        assert agent.agent_id == "def456"
        assert agent.jsonl_path == jsonl_path
        assert agent.is_subagent is False
        assert agent.parent_session_uuid is None
        assert agent.slug is None

    def test_agent_missing_required_fields_raises_error(self) -> None:
        """Test that missing required fields raise ValidationError."""
        with pytest.raises(ValidationError):
            Agent(jsonl_path=Path("/some/path.jsonl"))  # Missing agent_id

        with pytest.raises(ValidationError):
            Agent(agent_id="abc123")  # Missing jsonl_path


class TestAgentFromPathStandalone:
    """Test Agent.from_path() for standalone agent paths."""

    def test_from_path_standalone_agent(self, standalone_agent_jsonl: Path) -> None:
        """Test creating an Agent from a standalone agent path."""
        agent = Agent.from_path(standalone_agent_jsonl)

        assert agent.agent_id == "b1234ef"
        assert agent.jsonl_path == standalone_agent_jsonl
        assert agent.is_subagent is False
        assert agent.parent_session_uuid is None

    def test_from_path_extracts_agent_id_from_filename(self, temp_project_dir: Path) -> None:
        """Test that agent_id is correctly extracted from filename."""
        agent_path = temp_project_dir / "agent-fedcba98.jsonl"
        agent_path.touch()

        agent = Agent.from_path(agent_path)

        assert agent.agent_id == "fedcba98"

    def test_from_path_handles_nonexistent_file(self, temp_project_dir: Path) -> None:
        """Test from_path with a file that doesn't exist."""
        nonexistent_path = temp_project_dir / "agent-nonexistent.jsonl"

        agent = Agent.from_path(nonexistent_path)

        assert agent.agent_id == "nonexistent"
        assert agent.jsonl_path == nonexistent_path
        assert agent.slug is None  # Can't read slug from nonexistent file


class TestAgentFromPathSubagent:
    """Test Agent.from_path() for subagent paths."""

    def test_from_path_subagent(
        self, sample_session_with_subagents: Path, temp_project_dir: Path
    ) -> None:
        """Test creating an Agent from a subagent path."""
        subagent_path = temp_project_dir / "test-session-uuid" / "subagents" / "agent-a5793c3.jsonl"

        agent = Agent.from_path(subagent_path)

        assert agent.agent_id == "a5793c3"
        assert agent.jsonl_path == subagent_path
        assert agent.is_subagent is True
        assert agent.parent_session_uuid == "test-session-uuid"

    def test_from_path_detects_parent_session_uuid(self, temp_project_dir: Path) -> None:
        """Test that parent_session_uuid is correctly extracted from path."""
        session_uuid = "unique-parent-session-12345"
        subagents_dir = temp_project_dir / session_uuid / "subagents"
        subagents_dir.mkdir(parents=True)

        agent_path = subagents_dir / "agent-xyz789.jsonl"
        agent_path.touch()

        agent = Agent.from_path(agent_path)

        assert agent.parent_session_uuid == session_uuid
        assert agent.is_subagent is True


class TestAgentIdExtraction:
    """Test agent_id extraction from filename and JSONL."""

    def test_agent_id_from_filename_hex(self, temp_project_dir: Path) -> None:
        """Test extracting hex agent_id from filename."""
        for hex_id in ["a1b2c3", "fedcba", "0123456789abcdef"]:
            agent_path = temp_project_dir / f"agent-{hex_id}.jsonl"
            agent_path.touch()

            agent = Agent.from_path(agent_path)
            assert agent.agent_id == hex_id

    def test_agent_id_from_jsonl_takes_precedence(self, temp_project_dir: Path) -> None:
        """Test that agentId from JSONL takes precedence over filename."""
        agent_path = temp_project_dir / "agent-filename-id.jsonl"

        # Write JSONL with different agentId
        first_line = {
            "agentId": "jsonl-agent-id",
            "slug": "test-slug",
            "type": "user",
            "message": {"role": "user", "content": "test"},
            "uuid": "test-uuid",
            "timestamp": "2026-01-08T13:00:00.000Z",
        }
        with open(agent_path, "w") as f:
            f.write(json.dumps(first_line) + "\n")

        agent = Agent.from_path(agent_path)

        assert agent.agent_id == "jsonl-agent-id"

    def test_agent_id_fallback_to_filename(self, temp_project_dir: Path) -> None:
        """Test fallback to filename when JSONL has no agentId.

        Note: The regex only matches hex characters [a-f0-9], so non-hex
        filenames may result in partial matches.
        """
        # Use a hex-only filename to avoid partial matching issues
        agent_path = temp_project_dir / "agent-abc123def.jsonl"

        # Write JSONL without agentId
        first_line = {
            "type": "user",
            "message": {"role": "user", "content": "test"},
            "uuid": "test-uuid",
            "timestamp": "2026-01-08T13:00:00.000Z",
        }
        with open(agent_path, "w") as f:
            f.write(json.dumps(first_line) + "\n")

        agent = Agent.from_path(agent_path)

        assert agent.agent_id == "abc123def"


class TestSlugExtraction:
    """Test slug extraction from JSONL first line."""

    def test_slug_extracted_from_jsonl(
        self, sample_session_with_subagents: Path, temp_project_dir: Path
    ) -> None:
        """Test that slug is extracted from JSONL first line."""
        subagent_path = temp_project_dir / "test-session-uuid" / "subagents" / "agent-a5793c3.jsonl"

        agent = Agent.from_path(subagent_path)

        assert agent.slug == "eager-puzzling-fairy"

    def test_slug_is_none_when_not_present(self, temp_project_dir: Path) -> None:
        """Test that slug is None when not in JSONL."""
        agent_path = temp_project_dir / "agent-noslug.jsonl"

        first_line = {
            "type": "user",
            "message": {"role": "user", "content": "test"},
            "uuid": "test-uuid",
            "timestamp": "2026-01-08T13:00:00.000Z",
        }
        with open(agent_path, "w") as f:
            f.write(json.dumps(first_line) + "\n")

        agent = Agent.from_path(agent_path)

        assert agent.slug is None

    def test_slug_is_none_for_nonexistent_file(self, temp_project_dir: Path) -> None:
        """Test that slug is None for nonexistent file."""
        agent_path = temp_project_dir / "agent-missing.jsonl"

        agent = Agent.from_path(agent_path)

        assert agent.slug is None


class TestIterMessages:
    """Test iter_messages() method."""

    def test_iter_messages_yields_messages(self, standalone_agent_jsonl: Path) -> None:
        """Test that iter_messages yields Message instances."""
        agent = Agent.from_path(standalone_agent_jsonl)

        messages = list(agent.iter_messages())

        assert len(messages) == 2
        assert isinstance(messages[0], UserMessage)
        assert isinstance(messages[1], AssistantMessage)

    def test_iter_messages_handles_missing_file(self, temp_project_dir: Path) -> None:
        """Test iter_messages with a missing file returns empty iterator."""
        agent_path = temp_project_dir / "agent-missing.jsonl"
        agent = Agent.from_path(agent_path)

        messages = list(agent.iter_messages())

        assert messages == []

    def test_iter_messages_skips_malformed_lines(self, temp_project_dir: Path) -> None:
        """Test that malformed JSONL lines are skipped."""
        agent_path = temp_project_dir / "agent-malformed.jsonl"

        with open(agent_path, "w") as f:
            # Valid user message
            valid_msg = {
                "type": "user",
                "message": {"role": "user", "content": "valid"},
                "uuid": "valid-uuid",
                "timestamp": "2026-01-08T13:00:00.000Z",
            }
            f.write(json.dumps(valid_msg) + "\n")
            # Malformed JSON
            f.write("this is not valid json\n")
            # Empty line
            f.write("\n")
            # Valid JSON but invalid message structure
            f.write('{"invalid": "structure"}\n')
            # Another valid message
            valid_msg2 = {
                "type": "user",
                "message": {"role": "user", "content": "also valid"},
                "uuid": "valid-uuid-2",
                "timestamp": "2026-01-08T13:01:00.000Z",
            }
            f.write(json.dumps(valid_msg2) + "\n")

        agent = Agent.from_path(agent_path)
        messages = list(agent.iter_messages())

        # Should only get the 2 valid messages
        assert len(messages) == 2
        assert all(isinstance(m, UserMessage) for m in messages)

    def test_iter_messages_preserves_order(self, temp_project_dir: Path) -> None:
        """Test that messages are yielded in file order."""
        agent_path = temp_project_dir / "agent-ordered.jsonl"

        with open(agent_path, "w") as f:
            for i in range(5):
                msg = {
                    "type": "user",
                    "message": {"role": "user", "content": f"message {i}"},
                    "uuid": f"uuid-{i}",
                    "timestamp": f"2026-01-08T13:0{i}:00.000Z",
                }
                f.write(json.dumps(msg) + "\n")

        agent = Agent.from_path(agent_path)
        messages = list(agent.iter_messages())

        assert len(messages) == 5
        for i, msg in enumerate(messages):
            assert msg.content == f"message {i}"


class TestListMessages:
    """Test list_messages() method."""

    def test_list_messages_returns_list(self, standalone_agent_jsonl: Path) -> None:
        """Test that list_messages returns a list."""
        agent = Agent.from_path(standalone_agent_jsonl)

        messages = agent.list_messages()

        assert isinstance(messages, list)
        assert len(messages) == 2

    def test_list_messages_equals_iter_messages(self, standalone_agent_jsonl: Path) -> None:
        """Test that list_messages matches iter_messages output."""
        agent = Agent.from_path(standalone_agent_jsonl)

        list_result = agent.list_messages()
        iter_result = list(agent.iter_messages())

        assert len(list_result) == len(iter_result)
        for list_msg, iter_msg in zip(list_result, iter_result):
            assert list_msg.uuid == iter_msg.uuid


class TestMessageCount:
    """Test message_count property."""

    def test_message_count_returns_correct_count(self, standalone_agent_jsonl: Path) -> None:
        """Test message_count returns accurate count."""
        agent = Agent.from_path(standalone_agent_jsonl)

        assert agent.message_count == 2

    def test_message_count_for_missing_file(self, temp_project_dir: Path) -> None:
        """Test message_count returns 0 for missing file."""
        agent_path = temp_project_dir / "agent-missing.jsonl"
        agent = Agent.from_path(agent_path)

        assert agent.message_count == 0

    def test_message_count_skips_empty_lines(self, temp_project_dir: Path) -> None:
        """Test that empty lines don't count toward message_count."""
        agent_path = temp_project_dir / "agent-with-empty.jsonl"

        with open(agent_path, "w") as f:
            msg = {
                "type": "user",
                "message": {"role": "user", "content": "test"},
                "uuid": "uuid-1",
                "timestamp": "2026-01-08T13:00:00.000Z",
            }
            f.write(json.dumps(msg) + "\n")
            f.write("\n")  # Empty line
            f.write("   \n")  # Whitespace only line
            f.write(json.dumps(msg) + "\n")

        agent = Agent.from_path(agent_path)

        assert agent.message_count == 2


class TestExistsProperty:
    """Test exists property."""

    def test_exists_true_for_existing_file(self, standalone_agent_jsonl: Path) -> None:
        """Test exists returns True for existing file."""
        agent = Agent.from_path(standalone_agent_jsonl)

        assert agent.exists is True

    def test_exists_false_for_missing_file(self, temp_project_dir: Path) -> None:
        """Test exists returns False for missing file."""
        agent_path = temp_project_dir / "agent-missing.jsonl"
        agent = Agent.from_path(agent_path)

        assert agent.exists is False


class TestGetUsageSummary:
    """Test get_usage_summary() method."""

    def test_get_usage_summary_aggregates_usage(self, standalone_agent_jsonl: Path) -> None:
        """Test that usage is aggregated from all assistant messages."""
        agent = Agent.from_path(standalone_agent_jsonl)

        usage = agent.get_usage_summary()

        assert isinstance(usage, TokenUsage)
        # From sample_assistant_message_data fixture:
        # input_tokens: 100, output_tokens: 500
        # cache_creation_input_tokens: 50000, cache_read_input_tokens: 10000
        assert usage.input_tokens == 100
        assert usage.output_tokens == 500
        assert usage.cache_creation_input_tokens == 50000
        assert usage.cache_read_input_tokens == 10000

    def test_get_usage_summary_multiple_assistant_messages(self, temp_project_dir: Path) -> None:
        """Test usage aggregation across multiple assistant messages."""
        agent_path = temp_project_dir / "agent-multi-usage.jsonl"

        with open(agent_path, "w") as f:
            for i in range(3):
                msg = {
                    "type": "assistant",
                    "message": {
                        "role": "assistant",
                        "content": [{"type": "text", "text": f"response {i}"}],
                        "usage": {
                            "input_tokens": 100,
                            "output_tokens": 50,
                            "cache_creation_input_tokens": 0,
                            "cache_read_input_tokens": 0,
                        },
                    },
                    "uuid": f"uuid-{i}",
                    "timestamp": f"2026-01-08T13:0{i}:00.000Z",
                }
                f.write(json.dumps(msg) + "\n")

        agent = Agent.from_path(agent_path)
        usage = agent.get_usage_summary()

        assert usage.input_tokens == 300  # 100 * 3
        assert usage.output_tokens == 150  # 50 * 3

    def test_get_usage_summary_zero_for_user_only(self, temp_project_dir: Path) -> None:
        """Test usage is zero when only user messages exist."""
        agent_path = temp_project_dir / "agent-user-only.jsonl"

        with open(agent_path, "w") as f:
            msg = {
                "type": "user",
                "message": {"role": "user", "content": "test"},
                "uuid": "uuid-1",
                "timestamp": "2026-01-08T13:00:00.000Z",
            }
            f.write(json.dumps(msg) + "\n")

        agent = Agent.from_path(agent_path)
        usage = agent.get_usage_summary()

        assert usage.input_tokens == 0
        assert usage.output_tokens == 0
        assert usage.cache_creation_input_tokens == 0
        assert usage.cache_read_input_tokens == 0

    def test_get_usage_summary_missing_file(self, temp_project_dir: Path) -> None:
        """Test usage is zero for missing file."""
        agent_path = temp_project_dir / "agent-missing.jsonl"
        agent = Agent.from_path(agent_path)

        usage = agent.get_usage_summary()

        assert usage == TokenUsage.zero()


class TestTimeProperties:
    """Test start_time and end_time properties."""

    def test_start_time_returns_first_message_timestamp(self, standalone_agent_jsonl: Path) -> None:
        """Test start_time returns timestamp of first message."""
        agent = Agent.from_path(standalone_agent_jsonl)

        start = agent.start_time

        assert start is not None
        assert isinstance(start, datetime)
        # From sample_user_message_data fixture
        assert start.year == 2026
        assert start.month == 1
        assert start.day == 8

    def test_end_time_returns_last_message_timestamp(self, standalone_agent_jsonl: Path) -> None:
        """Test end_time returns timestamp of last message."""
        agent = Agent.from_path(standalone_agent_jsonl)

        end = agent.end_time

        assert end is not None
        assert isinstance(end, datetime)
        # Should be later than or equal to start_time
        assert end >= agent.start_time

    def test_start_time_none_for_empty_file(self, temp_project_dir: Path) -> None:
        """Test start_time is None for empty file."""
        agent_path = temp_project_dir / "agent-empty.jsonl"
        agent_path.touch()

        agent = Agent.from_path(agent_path)

        assert agent.start_time is None

    def test_end_time_none_for_empty_file(self, temp_project_dir: Path) -> None:
        """Test end_time is None for empty file."""
        agent_path = temp_project_dir / "agent-empty.jsonl"
        agent_path.touch()

        agent = Agent.from_path(agent_path)

        assert agent.end_time is None

    def test_start_time_none_for_missing_file(self, temp_project_dir: Path) -> None:
        """Test start_time is None for missing file."""
        agent_path = temp_project_dir / "agent-missing.jsonl"
        agent = Agent.from_path(agent_path)

        assert agent.start_time is None

    def test_end_time_none_for_missing_file(self, temp_project_dir: Path) -> None:
        """Test end_time is None for missing file."""
        agent_path = temp_project_dir / "agent-missing.jsonl"
        agent = Agent.from_path(agent_path)

        assert agent.end_time is None

    def test_start_equals_end_for_single_message(self, temp_project_dir: Path) -> None:
        """Test start_time equals end_time for single message."""
        agent_path = temp_project_dir / "agent-single.jsonl"

        msg = {
            "type": "user",
            "message": {"role": "user", "content": "only message"},
            "uuid": "uuid-1",
            "timestamp": "2026-01-08T13:00:00.000Z",
        }
        with open(agent_path, "w") as f:
            f.write(json.dumps(msg) + "\n")

        agent = Agent.from_path(agent_path)

        assert agent.start_time == agent.end_time


class TestIsSubagent:
    """Test is_subagent detection."""

    def test_is_subagent_true_from_path_structure(
        self, sample_session_with_subagents: Path, temp_project_dir: Path
    ) -> None:
        """Test is_subagent is True when path contains 'subagents'."""
        subagent_path = temp_project_dir / "test-session-uuid" / "subagents" / "agent-a5793c3.jsonl"

        agent = Agent.from_path(subagent_path)

        assert agent.is_subagent is True

    def test_is_subagent_false_for_standalone(self, standalone_agent_jsonl: Path) -> None:
        """Test is_subagent is False for standalone agents."""
        agent = Agent.from_path(standalone_agent_jsonl)

        assert agent.is_subagent is False

    def test_is_subagent_from_jsonl_isSidechain(self, temp_project_dir: Path) -> None:
        """Test is_subagent uses isSidechain from JSONL when available."""
        # Create a standalone path but with isSidechain=True in JSONL
        agent_path = temp_project_dir / "agent-sidechain.jsonl"

        msg = {
            "type": "user",
            "isSidechain": True,
            "agentId": "sidechain-id",
            "message": {"role": "user", "content": "test"},
            "uuid": "uuid-1",
            "timestamp": "2026-01-08T13:00:00.000Z",
        }
        with open(agent_path, "w") as f:
            f.write(json.dumps(msg) + "\n")

        agent = Agent.from_path(agent_path)

        # isSidechain from JSONL should take precedence
        assert agent.is_subagent is True

    def test_is_subagent_respects_jsonl_isSidechain_false(self, temp_project_dir: Path) -> None:
        """Test is_subagent uses isSidechain=false from JSONL."""
        # Create path that looks like subagent but with isSidechain=False
        session_dir = temp_project_dir / "some-session" / "subagents"
        session_dir.mkdir(parents=True)
        agent_path = session_dir / "agent-test.jsonl"

        msg = {
            "type": "user",
            "isSidechain": False,
            "message": {"role": "user", "content": "test"},
            "uuid": "uuid-1",
            "timestamp": "2026-01-08T13:00:00.000Z",
        }
        with open(agent_path, "w") as f:
            f.write(json.dumps(msg) + "\n")

        agent = Agent.from_path(agent_path)

        # isSidechain from JSONL should take precedence over path
        assert agent.is_subagent is False


class TestImmutability:
    """Test that Agent model is immutable (frozen=True)."""

    def test_cannot_modify_agent_id(self, standalone_agent_jsonl: Path) -> None:
        """Test that agent_id cannot be modified after creation."""
        agent = Agent.from_path(standalone_agent_jsonl)

        with pytest.raises(ValidationError):
            agent.agent_id = "new-id"

    def test_cannot_modify_jsonl_path(
        self, standalone_agent_jsonl: Path, temp_project_dir: Path
    ) -> None:
        """Test that jsonl_path cannot be modified after creation."""
        agent = Agent.from_path(standalone_agent_jsonl)

        with pytest.raises(ValidationError):
            agent.jsonl_path = temp_project_dir / "new-path.jsonl"

    def test_cannot_modify_is_subagent(self, standalone_agent_jsonl: Path) -> None:
        """Test that is_subagent cannot be modified after creation."""
        agent = Agent.from_path(standalone_agent_jsonl)

        with pytest.raises(ValidationError):
            agent.is_subagent = True

    def test_cannot_modify_parent_session_uuid(self, standalone_agent_jsonl: Path) -> None:
        """Test that parent_session_uuid cannot be modified after creation."""
        agent = Agent.from_path(standalone_agent_jsonl)

        with pytest.raises(ValidationError):
            agent.parent_session_uuid = "new-uuid"

    def test_cannot_modify_slug(self, standalone_agent_jsonl: Path) -> None:
        """Test that slug cannot be modified after creation."""
        agent = Agent.from_path(standalone_agent_jsonl)

        with pytest.raises(ValidationError):
            agent.slug = "new-slug"

    def test_agent_is_hashable(self, standalone_agent_jsonl: Path) -> None:
        """Test that frozen Agent instances are hashable."""
        agent = Agent.from_path(standalone_agent_jsonl)

        # Should not raise - frozen models are hashable
        hash_value = hash(agent)
        assert isinstance(hash_value, int)

    def test_agents_can_be_set_members(
        self, standalone_agent_jsonl: Path, temp_project_dir: Path
    ) -> None:
        """Test that Agent instances can be members of a set."""
        agent1 = Agent.from_path(standalone_agent_jsonl)

        # Create second agent
        agent_path2 = temp_project_dir / "agent-second.jsonl"
        agent_path2.touch()
        agent2 = Agent.from_path(agent_path2)

        # Should be able to create a set
        agent_set = {agent1, agent2}
        assert len(agent_set) == 2


class TestEdgeCases:
    """Test edge cases and error handling."""

    def test_from_path_with_malformed_json(self, temp_project_dir: Path) -> None:
        """Test from_path handles malformed JSON in first line."""
        agent_path = temp_project_dir / "agent-malformed.jsonl"

        with open(agent_path, "w") as f:
            f.write("not valid json at all\n")

        agent = Agent.from_path(agent_path)

        # Should still create agent, just without slug/jsonl agentId
        assert agent.agent_id == "malformed"
        assert agent.slug is None

    def test_from_path_with_empty_file(self, temp_project_dir: Path) -> None:
        """Test from_path handles empty file.

        Note: The regex only matches hex chars, so 'empty' matches only 'e'.
        """
        agent_path = temp_project_dir / "agent-abc123.jsonl"
        agent_path.touch()

        agent = Agent.from_path(agent_path)

        assert agent.agent_id == "abc123"
        assert agent.slug is None

    def test_from_path_non_standard_filename(self, temp_project_dir: Path) -> None:
        """Test from_path handles non-standard filename patterns.

        The regex r"agent-([a-f0-9]+)" only captures hex chars.
        For 'agent-custom_name', it matches 'c' as partial hex.
        For completely non-matching, it falls back to removing 'agent-' prefix.
        """
        # Filename that has no hex prefix at all (starts with non-hex char)
        agent_path = temp_project_dir / "agent-xyz_name.jsonl"
        agent_path.touch()

        agent = Agent.from_path(agent_path)

        # 'xyz_name' has no hex prefix, so regex fails and fallback is used
        assert agent.agent_id == "xyz_name"

    def test_deeply_nested_subagent_path(self, temp_project_dir: Path) -> None:
        """Test from_path with deeply nested subagent directory."""
        deep_path = temp_project_dir / "session-uuid-123" / "subagents" / "agent-deep.jsonl"
        deep_path.parent.mkdir(parents=True)
        deep_path.touch()

        agent = Agent.from_path(deep_path)

        assert agent.is_subagent is True
        assert agent.parent_session_uuid == "session-uuid-123"


class TestListTasks:
    """Test list_tasks() method for reconstructing tasks from JSONL."""

    def test_list_tasks_returns_empty_for_missing_file(self, temp_project_dir: Path) -> None:
        """Test list_tasks returns empty list for missing file."""
        agent_path = temp_project_dir / "agent-missing.jsonl"
        agent = Agent.from_path(agent_path)

        tasks = agent.list_tasks()

        assert tasks == []

    def test_list_tasks_returns_empty_when_no_task_events(
        self, standalone_agent_jsonl: Path
    ) -> None:
        """Test list_tasks returns empty list when no TaskCreate events exist."""
        agent = Agent.from_path(standalone_agent_jsonl)

        tasks = agent.list_tasks()

        assert tasks == []

    def test_list_tasks_reconstructs_single_task(self, temp_project_dir: Path) -> None:
        """Test list_tasks reconstructs a single task from TaskCreate event."""
        agent_path = temp_project_dir / "agent-with-tasks.jsonl"

        # Create JSONL with TaskCreate tool_use
        with open(agent_path, "w") as f:
            # User message
            user_msg = {
                "type": "user",
                "message": {"role": "user", "content": "Create a task"},
                "uuid": "user-uuid-1",
                "timestamp": "2026-01-08T13:00:00.000Z",
            }
            f.write(json.dumps(user_msg) + "\n")

            # Assistant message with TaskCreate
            asst_msg = {
                "type": "assistant",
                "message": {
                    "role": "assistant",
                    "content": [
                        {
                            "type": "tool_use",
                            "id": "toolu_task_1",
                            "name": "TaskCreate",
                            "input": {
                                "subject": "Implement feature",
                                "description": "Add the new feature",
                                "activeForm": "Implementing feature",
                            },
                        }
                    ],
                },
                "uuid": "asst-uuid-1",
                "timestamp": "2026-01-08T13:01:00.000Z",
            }
            f.write(json.dumps(asst_msg) + "\n")

        agent = Agent.from_path(agent_path)
        tasks = agent.list_tasks()

        assert len(tasks) == 1
        assert tasks[0].id == "1"
        assert tasks[0].subject == "Implement feature"
        assert tasks[0].description == "Add the new feature"
        assert tasks[0].active_form == "Implementing feature"
        assert tasks[0].status == "pending"

    def test_list_tasks_reconstructs_multiple_tasks(self, temp_project_dir: Path) -> None:
        """Test list_tasks reconstructs multiple tasks in order."""
        agent_path = temp_project_dir / "agent-multi-tasks.jsonl"

        with open(agent_path, "w") as f:
            # User message
            user_msg = {
                "type": "user",
                "message": {"role": "user", "content": "Create tasks"},
                "uuid": "user-uuid-1",
                "timestamp": "2026-01-08T13:00:00.000Z",
            }
            f.write(json.dumps(user_msg) + "\n")

            # Assistant message with multiple TaskCreate
            asst_msg = {
                "type": "assistant",
                "message": {
                    "role": "assistant",
                    "content": [
                        {
                            "type": "tool_use",
                            "id": "toolu_task_1",
                            "name": "TaskCreate",
                            "input": {
                                "subject": "Task One",
                                "description": "First task",
                            },
                        },
                        {
                            "type": "tool_use",
                            "id": "toolu_task_2",
                            "name": "TaskCreate",
                            "input": {
                                "subject": "Task Two",
                                "description": "Second task",
                            },
                        },
                        {
                            "type": "tool_use",
                            "id": "toolu_task_3",
                            "name": "TaskCreate",
                            "input": {
                                "subject": "Task Three",
                                "description": "Third task",
                            },
                        },
                    ],
                },
                "uuid": "asst-uuid-1",
                "timestamp": "2026-01-08T13:01:00.000Z",
            }
            f.write(json.dumps(asst_msg) + "\n")

        agent = Agent.from_path(agent_path)
        tasks = agent.list_tasks()

        assert len(tasks) == 3
        assert tasks[0].id == "1"
        assert tasks[0].subject == "Task One"
        assert tasks[1].id == "2"
        assert tasks[1].subject == "Task Two"
        assert tasks[2].id == "3"
        assert tasks[2].subject == "Task Three"

    def test_list_tasks_applies_task_updates(self, temp_project_dir: Path) -> None:
        """Test list_tasks applies TaskUpdate events to modify task state."""
        agent_path = temp_project_dir / "agent-task-updates.jsonl"

        with open(agent_path, "w") as f:
            # User message
            user_msg = {
                "type": "user",
                "message": {"role": "user", "content": "Work on tasks"},
                "uuid": "user-uuid-1",
                "timestamp": "2026-01-08T13:00:00.000Z",
            }
            f.write(json.dumps(user_msg) + "\n")

            # Create task
            create_msg = {
                "type": "assistant",
                "message": {
                    "role": "assistant",
                    "content": [
                        {
                            "type": "tool_use",
                            "id": "toolu_create",
                            "name": "TaskCreate",
                            "input": {
                                "subject": "My Task",
                                "description": "Task description",
                            },
                        }
                    ],
                },
                "uuid": "asst-uuid-1",
                "timestamp": "2026-01-08T13:01:00.000Z",
            }
            f.write(json.dumps(create_msg) + "\n")

            # Update task to in_progress
            update_msg = {
                "type": "assistant",
                "message": {
                    "role": "assistant",
                    "content": [
                        {
                            "type": "tool_use",
                            "id": "toolu_update",
                            "name": "TaskUpdate",
                            "input": {
                                "taskId": "1",
                                "status": "in_progress",
                            },
                        }
                    ],
                },
                "uuid": "asst-uuid-2",
                "timestamp": "2026-01-08T13:02:00.000Z",
            }
            f.write(json.dumps(update_msg) + "\n")

            # Update task to completed
            complete_msg = {
                "type": "assistant",
                "message": {
                    "role": "assistant",
                    "content": [
                        {
                            "type": "tool_use",
                            "id": "toolu_complete",
                            "name": "TaskUpdate",
                            "input": {
                                "taskId": "1",
                                "status": "completed",
                            },
                        }
                    ],
                },
                "uuid": "asst-uuid-3",
                "timestamp": "2026-01-08T13:03:00.000Z",
            }
            f.write(json.dumps(complete_msg) + "\n")

        agent = Agent.from_path(agent_path)
        tasks = agent.list_tasks()

        assert len(tasks) == 1
        assert tasks[0].id == "1"
        assert tasks[0].subject == "My Task"
        assert tasks[0].status == "completed"

    def test_list_tasks_handles_dependency_tracking(self, temp_project_dir: Path) -> None:
        """Test list_tasks reconstructs task dependencies from addBlocks/addBlockedBy."""
        agent_path = temp_project_dir / "agent-task-deps.jsonl"

        with open(agent_path, "w") as f:
            # User message
            user_msg = {
                "type": "user",
                "message": {"role": "user", "content": "Create dependent tasks"},
                "uuid": "user-uuid-1",
                "timestamp": "2026-01-08T13:00:00.000Z",
            }
            f.write(json.dumps(user_msg) + "\n")

            # Create two tasks
            create_msg = {
                "type": "assistant",
                "message": {
                    "role": "assistant",
                    "content": [
                        {
                            "type": "tool_use",
                            "id": "toolu_create_1",
                            "name": "TaskCreate",
                            "input": {
                                "subject": "Task 1",
                                "description": "First task",
                            },
                        },
                        {
                            "type": "tool_use",
                            "id": "toolu_create_2",
                            "name": "TaskCreate",
                            "input": {
                                "subject": "Task 2",
                                "description": "Second task depends on first",
                            },
                        },
                    ],
                },
                "uuid": "asst-uuid-1",
                "timestamp": "2026-01-08T13:01:00.000Z",
            }
            f.write(json.dumps(create_msg) + "\n")

            # Add dependency: task 2 blocked by task 1
            dep_msg = {
                "type": "assistant",
                "message": {
                    "role": "assistant",
                    "content": [
                        {
                            "type": "tool_use",
                            "id": "toolu_dep",
                            "name": "TaskUpdate",
                            "input": {
                                "taskId": "2",
                                "addBlockedBy": ["1"],
                            },
                        }
                    ],
                },
                "uuid": "asst-uuid-2",
                "timestamp": "2026-01-08T13:02:00.000Z",
            }
            f.write(json.dumps(dep_msg) + "\n")

        agent = Agent.from_path(agent_path)
        tasks = agent.list_tasks()

        assert len(tasks) == 2
        task_1 = next(t for t in tasks if t.id == "1")
        task_2 = next(t for t in tasks if t.id == "2")

        assert task_1.blocked_by == []
        assert task_2.blocked_by == ["1"]

"""
Unit tests for the Session model.

Tests session instantiation, path properties, existence checks,
message iteration, related resources, and analytics methods.
"""

import copy
import json
from collections import Counter
from datetime import datetime
from pathlib import Path

import pytest
from pydantic import ValidationError

from models import (
    Agent,
    AssistantMessage,
    Session,
    TodoItem,
    TokenUsage,
    ToolResult,
    UserMessage,
)

# =============================================================================
# Session Instantiation Tests
# =============================================================================


class TestSessionInstantiation:
    """Tests for Session creation and from_path() method."""

    def test_session_direct_instantiation(self, temp_claude_dir: Path, sample_session_jsonl: Path):
        """Test creating a Session directly with constructor."""
        session = Session(
            uuid="test-session-uuid",
            jsonl_path=sample_session_jsonl,
            claude_base_dir=temp_claude_dir,
        )

        assert session.uuid == "test-session-uuid"
        assert session.jsonl_path == sample_session_jsonl
        assert session.claude_base_dir == temp_claude_dir

    def test_session_from_path(self, temp_claude_dir: Path, sample_session_jsonl: Path):
        """Test creating a Session from a JSONL file path."""
        session = Session.from_path(sample_session_jsonl, claude_base_dir=temp_claude_dir)

        assert session.uuid == "test-session-uuid"
        assert session.jsonl_path == sample_session_jsonl
        assert session.claude_base_dir == temp_claude_dir

    def test_session_from_path_without_base_dir(self, sample_session_jsonl: Path):
        """Test from_path uses default ~/.claude when base_dir not provided."""
        session = Session.from_path(sample_session_jsonl)

        assert session.uuid == "test-session-uuid"
        assert session.jsonl_path == sample_session_jsonl
        assert session.claude_base_dir == Path.home() / ".claude"

    def test_session_extracts_uuid_from_stem(self, temp_project_dir: Path):
        """Test that UUID is correctly extracted from filename stem."""
        # Create a file with a specific UUID-like name
        custom_uuid = "abc123-def456-ghi789"
        jsonl_path = temp_project_dir / f"{custom_uuid}.jsonl"
        jsonl_path.write_text("")

        session = Session.from_path(jsonl_path)

        assert session.uuid == custom_uuid


# =============================================================================
# Path Properties Tests
# =============================================================================


class TestPathProperties:
    """Tests for session path properties."""

    def test_session_dir(self, temp_claude_dir: Path, sample_session_jsonl: Path):
        """Test session_dir returns path to session's resource folder."""
        session = Session.from_path(sample_session_jsonl, claude_base_dir=temp_claude_dir)

        expected = sample_session_jsonl.parent / "test-session-uuid"
        assert session.session_dir == expected

    def test_tool_results_dir(self, temp_claude_dir: Path, sample_session_jsonl: Path):
        """Test tool_results_dir returns path to tool-results folder."""
        session = Session.from_path(sample_session_jsonl, claude_base_dir=temp_claude_dir)

        expected = session.session_dir / "tool-results"
        assert session.tool_results_dir == expected

    def test_subagents_dir(self, temp_claude_dir: Path, sample_session_jsonl: Path):
        """Test subagents_dir returns path to subagents folder."""
        session = Session.from_path(sample_session_jsonl, claude_base_dir=temp_claude_dir)

        expected = session.session_dir / "subagents"
        assert session.subagents_dir == expected

    def test_debug_log_path(self, temp_claude_dir: Path, sample_session_jsonl: Path):
        """Test debug_log_path returns correct path in debug directory."""
        session = Session.from_path(sample_session_jsonl, claude_base_dir=temp_claude_dir)

        expected = temp_claude_dir / "debug" / "test-session-uuid.txt"
        assert session.debug_log_path == expected

    def test_file_history_dir(self, temp_claude_dir: Path, sample_session_jsonl: Path):
        """Test file_history_dir returns correct path in file-history directory."""
        session = Session.from_path(sample_session_jsonl, claude_base_dir=temp_claude_dir)

        expected = temp_claude_dir / "file-history" / "test-session-uuid"
        assert session.file_history_dir == expected

    def test_todos_dir(self, temp_claude_dir: Path, sample_session_jsonl: Path):
        """Test todos_dir returns path to todos directory."""
        session = Session.from_path(sample_session_jsonl, claude_base_dir=temp_claude_dir)

        expected = temp_claude_dir / "todos"
        assert session.todos_dir == expected


# =============================================================================
# Existence Checks Tests
# =============================================================================


class TestExistenceChecks:
    """Tests for session existence check properties."""

    def test_exists_returns_true_when_jsonl_exists(
        self, temp_claude_dir: Path, sample_session_jsonl: Path
    ):
        """Test exists returns True when JSONL file exists."""
        session = Session.from_path(sample_session_jsonl, claude_base_dir=temp_claude_dir)

        assert session.exists is True

    def test_exists_returns_false_when_jsonl_missing(
        self, temp_claude_dir: Path, temp_project_dir: Path
    ):
        """Test exists returns False when JSONL file doesn't exist."""
        missing_path = temp_project_dir / "non-existent-uuid.jsonl"
        session = Session(
            uuid="non-existent-uuid",
            jsonl_path=missing_path,
            claude_base_dir=temp_claude_dir,
        )

        assert session.exists is False

    def test_has_debug_log_true(
        self, temp_claude_dir: Path, sample_session_jsonl: Path, sample_debug_log: Path
    ):
        """Test has_debug_log returns True when debug log exists."""
        session = Session.from_path(sample_session_jsonl, claude_base_dir=temp_claude_dir)

        assert session.has_debug_log is True

    def test_has_debug_log_false(self, temp_claude_dir: Path, sample_session_jsonl: Path):
        """Test has_debug_log returns False when debug log doesn't exist."""
        session = Session.from_path(sample_session_jsonl, claude_base_dir=temp_claude_dir)

        # Debug log not created by sample_session_jsonl fixture
        assert session.has_debug_log is False

    def test_has_file_history_true(
        self, temp_claude_dir: Path, sample_session_jsonl: Path, sample_file_history: Path
    ):
        """Test has_file_history returns True when file history exists with content."""
        session = Session.from_path(sample_session_jsonl, claude_base_dir=temp_claude_dir)

        assert session.has_file_history is True

    def test_has_file_history_false_no_dir(self, temp_claude_dir: Path, sample_session_jsonl: Path):
        """Test has_file_history returns False when directory doesn't exist."""
        session = Session.from_path(sample_session_jsonl, claude_base_dir=temp_claude_dir)

        assert session.has_file_history is False

    def test_has_file_history_false_empty_dir(
        self, temp_claude_dir: Path, sample_session_jsonl: Path
    ):
        """Test has_file_history returns False when directory is empty."""
        session = Session.from_path(sample_session_jsonl, claude_base_dir=temp_claude_dir)

        # Create empty file history dir
        session.file_history_dir.mkdir(parents=True)

        assert session.has_file_history is False

    def test_has_subagents_true(self, temp_claude_dir: Path, sample_session_with_subagents: Path):
        """Test has_subagents returns True when subagents exist."""
        session = Session.from_path(sample_session_with_subagents, claude_base_dir=temp_claude_dir)

        assert session.has_subagents is True

    def test_has_subagents_false(self, temp_claude_dir: Path, sample_session_jsonl: Path):
        """Test has_subagents returns False when no subagents exist."""
        session = Session.from_path(sample_session_jsonl, claude_base_dir=temp_claude_dir)

        assert session.has_subagents is False

    def test_has_tool_results_true(
        self, temp_claude_dir: Path, sample_session_with_tool_results: Path
    ):
        """Test has_tool_results returns True when tool results exist."""
        session = Session.from_path(
            sample_session_with_tool_results, claude_base_dir=temp_claude_dir
        )

        assert session.has_tool_results is True

    def test_has_tool_results_false(self, temp_claude_dir: Path, sample_session_jsonl: Path):
        """Test has_tool_results returns False when no tool results exist."""
        session = Session.from_path(sample_session_jsonl, claude_base_dir=temp_claude_dir)

        assert session.has_tool_results is False

    def test_has_todos_true(
        self, temp_claude_dir: Path, sample_session_jsonl: Path, sample_todos_file: Path
    ):
        """Test has_todos returns True when todos exist."""
        session = Session.from_path(sample_session_jsonl, claude_base_dir=temp_claude_dir)

        assert session.has_todos is True

    def test_has_todos_false(self, temp_claude_dir: Path, sample_session_jsonl: Path):
        """Test has_todos returns False when no todos exist."""
        session = Session.from_path(sample_session_jsonl, claude_base_dir=temp_claude_dir)

        assert session.has_todos is False

    def test_has_todos_false_when_file_exists_but_empty(
        self, temp_claude_dir: Path, sample_session_jsonl: Path
    ):
        """Test has_todos returns False when todo file exists but contains empty array."""
        # Create an empty todos file (this is the bug case)
        todos_dir = temp_claude_dir / "todos"
        todo_file = todos_dir / "test-session-uuid-agent-test-session-uuid.json"
        todo_file.write_text("[]")

        session = Session.from_path(sample_session_jsonl, claude_base_dir=temp_claude_dir)

        # File exists but has no actual todos
        assert todo_file.exists()
        assert session.has_todos is False


# =============================================================================
# Message Iteration Tests
# =============================================================================


class TestMessageIteration:
    """Tests for message iteration and listing."""

    def test_iter_messages_yields_messages(self, temp_claude_dir: Path, sample_session_jsonl: Path):
        """Test iter_messages yields Message instances from JSONL."""
        session = Session.from_path(sample_session_jsonl, claude_base_dir=temp_claude_dir)

        messages = list(session.iter_messages())

        # Sample session has 3 messages: file history snapshot, user, assistant
        assert len(messages) == 3

    def test_iter_messages_handles_missing_file(
        self, temp_claude_dir: Path, temp_project_dir: Path
    ):
        """Test iter_messages returns empty iterator when file doesn't exist."""
        missing_path = temp_project_dir / "missing.jsonl"
        session = Session(
            uuid="missing",
            jsonl_path=missing_path,
            claude_base_dir=temp_claude_dir,
        )

        messages = list(session.iter_messages())

        assert messages == []

    def test_iter_messages_skips_malformed_lines(
        self, temp_claude_dir: Path, temp_project_dir: Path, sample_user_message_data
    ):
        """Test iter_messages skips malformed JSON lines."""
        jsonl_path = temp_project_dir / "malformed.jsonl"

        with open(jsonl_path, "w") as f:
            f.write("not valid json\n")
            f.write(json.dumps(sample_user_message_data) + "\n")
            f.write('{"incomplete": }\n')
            f.write("\n")  # Empty line

        session = Session.from_path(jsonl_path, claude_base_dir=temp_claude_dir)

        messages = list(session.iter_messages())

        # Only the valid user message should be parsed
        assert len(messages) == 1
        assert isinstance(messages[0], UserMessage)

    def test_list_messages_returns_list(self, temp_claude_dir: Path, sample_session_jsonl: Path):
        """Test list_messages returns a list of all messages."""
        session = Session.from_path(sample_session_jsonl, claude_base_dir=temp_claude_dir)

        messages = session.list_messages()

        assert isinstance(messages, list)
        assert len(messages) == 3

    def test_iter_user_messages_filters_correctly(
        self, temp_claude_dir: Path, sample_session_jsonl: Path
    ):
        """Test iter_user_messages only yields UserMessage instances."""
        session = Session.from_path(sample_session_jsonl, claude_base_dir=temp_claude_dir)

        user_messages = list(session.iter_user_messages())

        assert len(user_messages) == 1
        assert all(isinstance(m, UserMessage) for m in user_messages)

    def test_iter_assistant_messages_filters_correctly(
        self, temp_claude_dir: Path, sample_session_jsonl: Path
    ):
        """Test iter_assistant_messages only yields AssistantMessage instances."""
        session = Session.from_path(sample_session_jsonl, claude_base_dir=temp_claude_dir)

        assistant_messages = list(session.iter_assistant_messages())

        assert len(assistant_messages) == 1
        assert all(isinstance(m, AssistantMessage) for m in assistant_messages)


# =============================================================================
# Related Resources Tests
# =============================================================================


class TestRelatedResources:
    """Tests for accessing related session resources."""

    def test_list_subagents_returns_agents(
        self, temp_claude_dir: Path, sample_session_with_subagents: Path
    ):
        """Test list_subagents returns Agent instances."""
        session = Session.from_path(sample_session_with_subagents, claude_base_dir=temp_claude_dir)

        subagents = session.list_subagents()

        assert len(subagents) == 1
        assert all(isinstance(a, Agent) for a in subagents)
        assert subagents[0].agent_id == "a5793c3"

    def test_list_subagents_returns_empty_when_none(
        self, temp_claude_dir: Path, sample_session_jsonl: Path
    ):
        """Test list_subagents returns empty list when no subagents exist."""
        session = Session.from_path(sample_session_jsonl, claude_base_dir=temp_claude_dir)

        subagents = session.list_subagents()

        assert subagents == []

    def test_list_subagents_sorted_by_agent_id(
        self, temp_claude_dir: Path, sample_session_jsonl: Path, sample_subagent_message_data
    ):
        """Test list_subagents returns agents sorted by agent_id."""
        session = Session.from_path(sample_session_jsonl, claude_base_dir=temp_claude_dir)

        # Create multiple subagents
        subagents_dir = session.subagents_dir
        subagents_dir.mkdir(parents=True)

        for agent_id in ["z9999", "a1111", "m5555"]:
            msg_data = sample_subagent_message_data.copy()
            msg_data["agentId"] = agent_id
            agent_path = subagents_dir / f"agent-{agent_id}.jsonl"
            with open(agent_path, "w") as f:
                f.write(json.dumps(msg_data) + "\n")

        subagents = session.list_subagents()

        assert len(subagents) == 3
        assert [a.agent_id for a in subagents] == ["a1111", "m5555", "z9999"]

    def test_list_tool_results_returns_tool_results(
        self, temp_claude_dir: Path, sample_session_with_tool_results: Path
    ):
        """Test list_tool_results returns ToolResult instances."""
        session = Session.from_path(
            sample_session_with_tool_results, claude_base_dir=temp_claude_dir
        )

        tool_results = session.list_tool_results()

        assert len(tool_results) == 1
        assert all(isinstance(tr, ToolResult) for tr in tool_results)
        assert tool_results[0].tool_use_id == "toolu_01ABC"

    def test_list_tool_results_returns_empty_when_none(
        self, temp_claude_dir: Path, sample_session_jsonl: Path
    ):
        """Test list_tool_results returns empty list when no results exist."""
        session = Session.from_path(sample_session_jsonl, claude_base_dir=temp_claude_dir)

        tool_results = session.list_tool_results()

        assert tool_results == []

    def test_list_tool_results_sorted_by_tool_use_id(
        self, temp_claude_dir: Path, sample_session_jsonl: Path
    ):
        """Test list_tool_results returns results sorted by tool_use_id."""
        session = Session.from_path(sample_session_jsonl, claude_base_dir=temp_claude_dir)

        # Create multiple tool results
        tool_results_dir = session.tool_results_dir
        tool_results_dir.mkdir(parents=True)

        for tool_id in ["toolu_Z999", "toolu_A111", "toolu_M555"]:
            (tool_results_dir / f"{tool_id}.txt").write_text(f"Result for {tool_id}")

        tool_results = session.list_tool_results()

        assert len(tool_results) == 3
        assert [tr.tool_use_id for tr in tool_results] == [
            "toolu_A111",
            "toolu_M555",
            "toolu_Z999",
        ]

    def test_list_todos_returns_todo_items(
        self, temp_claude_dir: Path, sample_session_jsonl: Path, sample_todos_file: Path
    ):
        """Test list_todos returns TodoItem instances."""
        session = Session.from_path(sample_session_jsonl, claude_base_dir=temp_claude_dir)

        todos = session.list_todos()

        assert len(todos) == 3
        assert all(isinstance(t, TodoItem) for t in todos)
        assert todos[0].content == "Explore codebase structure"
        assert todos[1].status == "in_progress"
        assert todos[2].status == "pending"

    def test_list_todos_returns_empty_when_none(
        self, temp_claude_dir: Path, sample_session_jsonl: Path
    ):
        """Test list_todos returns empty list when no todos exist."""
        session = Session.from_path(sample_session_jsonl, claude_base_dir=temp_claude_dir)

        todos = session.list_todos()

        assert todos == []

    def test_list_todos_handles_malformed_file(
        self, temp_claude_dir: Path, sample_session_jsonl: Path
    ):
        """Test list_todos skips malformed todo files."""
        session = Session.from_path(sample_session_jsonl, claude_base_dir=temp_claude_dir)

        # Create a malformed todo file
        todos_dir = temp_claude_dir / "todos"
        malformed_file = todos_dir / f"{session.uuid}-malformed.json"
        malformed_file.write_text("not valid json")

        todos = session.list_todos()

        assert todos == []

    def test_read_debug_log_returns_content(
        self, temp_claude_dir: Path, sample_session_jsonl: Path, sample_debug_log: Path
    ):
        """Test read_debug_log returns debug log content."""
        session = Session.from_path(sample_session_jsonl, claude_base_dir=temp_claude_dir)

        content = session.read_debug_log()

        assert content is not None
        assert "[DEBUG] Watching for changes in setting files" in content
        assert "[DEBUG] [init] configureGlobalMTLS starting" in content

    def test_read_debug_log_returns_none_when_missing(
        self, temp_claude_dir: Path, sample_session_jsonl: Path
    ):
        """Test read_debug_log returns None when file doesn't exist."""
        session = Session.from_path(sample_session_jsonl, claude_base_dir=temp_claude_dir)

        content = session.read_debug_log()

        assert content is None


# =============================================================================
# Analytics Tests
# =============================================================================


class TestAnalytics:
    """Tests for session analytics properties and methods."""

    def test_message_count(self, temp_claude_dir: Path, sample_session_jsonl: Path):
        """Test message_count returns correct count."""
        session = Session.from_path(sample_session_jsonl, claude_base_dir=temp_claude_dir)

        assert session.message_count == 3

    def test_message_count_missing_file(self, temp_claude_dir: Path, temp_project_dir: Path):
        """Test message_count returns 0 for missing file."""
        missing_path = temp_project_dir / "missing.jsonl"
        session = Session(
            uuid="missing",
            jsonl_path=missing_path,
            claude_base_dir=temp_claude_dir,
        )

        assert session.message_count == 0

    def test_start_time(self, temp_claude_dir: Path, sample_session_jsonl: Path):
        """Test start_time returns timestamp of first message."""
        session = Session.from_path(sample_session_jsonl, claude_base_dir=temp_claude_dir)

        start = session.start_time

        assert start is not None
        assert isinstance(start, datetime)
        # First message is file history snapshot at 2026-01-08T13:03:26.669Z
        assert start.year == 2026
        assert start.month == 1
        assert start.day == 8

    def test_start_time_empty_session(self, temp_claude_dir: Path, temp_project_dir: Path):
        """Test start_time returns None for empty session."""
        empty_path = temp_project_dir / "empty.jsonl"
        empty_path.write_text("")

        session = Session.from_path(empty_path, claude_base_dir=temp_claude_dir)

        assert session.start_time is None

    def test_end_time(self, temp_claude_dir: Path, sample_session_jsonl: Path):
        """Test end_time returns timestamp of last message."""
        session = Session.from_path(sample_session_jsonl, claude_base_dir=temp_claude_dir)

        end = session.end_time

        assert end is not None
        assert isinstance(end, datetime)
        # Last message is assistant at 2026-01-08T13:03:30.123Z
        assert end.year == 2026
        assert end.second == 30

    def test_end_time_empty_session(self, temp_claude_dir: Path, temp_project_dir: Path):
        """Test end_time returns None for empty session."""
        empty_path = temp_project_dir / "empty.jsonl"
        empty_path.write_text("")

        session = Session.from_path(empty_path, claude_base_dir=temp_claude_dir)

        assert session.end_time is None

    def test_duration_seconds(self, temp_claude_dir: Path, sample_session_jsonl: Path):
        """Test duration_seconds calculates session duration."""
        session = Session.from_path(sample_session_jsonl, claude_base_dir=temp_claude_dir)

        duration = session.duration_seconds

        assert duration is not None
        # Duration from 13:03:26.669 to 13:03:30.123 is about 3.454 seconds
        assert 3.0 <= duration <= 4.0

    def test_duration_seconds_empty_session(self, temp_claude_dir: Path, temp_project_dir: Path):
        """Test duration_seconds returns None for empty session."""
        empty_path = temp_project_dir / "empty.jsonl"
        empty_path.write_text("")

        session = Session.from_path(empty_path, claude_base_dir=temp_claude_dir)

        assert session.duration_seconds is None


# =============================================================================
# Usage Summary Tests
# =============================================================================


class TestUsageSummary:
    """Tests for token usage aggregation."""

    def test_get_usage_summary(self, temp_claude_dir: Path, sample_session_jsonl: Path):
        """Test get_usage_summary aggregates token usage."""
        session = Session.from_path(sample_session_jsonl, claude_base_dir=temp_claude_dir)

        usage = session.get_usage_summary()

        assert isinstance(usage, TokenUsage)
        assert usage.input_tokens == 100
        assert usage.output_tokens == 500
        assert usage.cache_creation_input_tokens == 50000
        assert usage.cache_read_input_tokens == 10000

    def test_get_usage_summary_empty_session(self, temp_claude_dir: Path, temp_project_dir: Path):
        """Test get_usage_summary returns zero for empty session."""
        empty_path = temp_project_dir / "empty.jsonl"
        empty_path.write_text("")

        session = Session.from_path(empty_path, claude_base_dir=temp_claude_dir)

        usage = session.get_usage_summary()

        assert usage.input_tokens == 0
        assert usage.output_tokens == 0
        assert usage.cache_creation_input_tokens == 0
        assert usage.cache_read_input_tokens == 0

    def test_get_usage_summary_multiple_messages(
        self, temp_claude_dir: Path, temp_project_dir: Path, sample_assistant_message_data
    ):
        """Test get_usage_summary aggregates across multiple assistant messages."""
        jsonl_path = temp_project_dir / "multi-assistant.jsonl"

        msg1 = copy.deepcopy(sample_assistant_message_data)
        msg2 = copy.deepcopy(sample_assistant_message_data)
        msg2["uuid"] = "assistant-msg-uuid-002"
        msg2["message"]["usage"]["input_tokens"] = 200
        msg2["message"]["usage"]["output_tokens"] = 300

        with open(jsonl_path, "w") as f:
            f.write(json.dumps(msg1) + "\n")
            f.write(json.dumps(msg2) + "\n")

        session = Session.from_path(jsonl_path, claude_base_dir=temp_claude_dir)

        usage = session.get_usage_summary()

        # 100 + 200 input, 500 + 300 output
        assert usage.input_tokens == 300
        assert usage.output_tokens == 800
        # 50000 + 50000 cache creation
        assert usage.cache_creation_input_tokens == 100000


# =============================================================================
# Models and Tools Used Tests
# =============================================================================


class TestModelsAndToolsUsed:
    """Tests for models and tools discovery methods."""

    def test_get_models_used(self, temp_claude_dir: Path, sample_session_jsonl: Path):
        """Test get_models_used returns set of model names."""
        session = Session.from_path(sample_session_jsonl, claude_base_dir=temp_claude_dir)

        models = session.get_models_used()

        assert isinstance(models, set)
        assert "claude-opus-4-5-20251101" in models

    def test_get_models_used_empty_session(self, temp_claude_dir: Path, temp_project_dir: Path):
        """Test get_models_used returns empty set for session without assistant messages."""
        empty_path = temp_project_dir / "empty.jsonl"
        empty_path.write_text("")

        session = Session.from_path(empty_path, claude_base_dir=temp_claude_dir)

        models = session.get_models_used()

        assert models == set()

    def test_get_models_used_multiple_models(
        self, temp_claude_dir: Path, temp_project_dir: Path, sample_assistant_message_data
    ):
        """Test get_models_used returns all unique models."""
        jsonl_path = temp_project_dir / "multi-model.jsonl"

        msg1 = copy.deepcopy(sample_assistant_message_data)
        msg2 = copy.deepcopy(sample_assistant_message_data)
        msg2["uuid"] = "assistant-msg-uuid-002"
        msg2["message"]["model"] = "claude-sonnet-4-20250514"

        with open(jsonl_path, "w") as f:
            f.write(json.dumps(msg1) + "\n")
            f.write(json.dumps(msg2) + "\n")

        session = Session.from_path(jsonl_path, claude_base_dir=temp_claude_dir)

        models = session.get_models_used()

        assert len(models) == 2
        assert "claude-opus-4-5-20251101" in models
        assert "claude-sonnet-4-20250514" in models

    def test_get_tools_used(self, temp_claude_dir: Path, sample_session_jsonl: Path):
        """Test get_tools_used returns Counter of tool names."""
        session = Session.from_path(sample_session_jsonl, claude_base_dir=temp_claude_dir)

        tools = session.get_tools_used()

        assert isinstance(tools, Counter)
        assert tools["Read"] == 1

    def test_get_tools_used_empty_session(self, temp_claude_dir: Path, temp_project_dir: Path):
        """Test get_tools_used returns empty Counter for empty session."""
        empty_path = temp_project_dir / "empty.jsonl"
        empty_path.write_text("")

        session = Session.from_path(empty_path, claude_base_dir=temp_claude_dir)

        tools = session.get_tools_used()

        assert tools == Counter()

    def test_get_tools_used_counts_multiple(
        self, temp_claude_dir: Path, temp_project_dir: Path, sample_assistant_message_data
    ):
        """Test get_tools_used counts multiple tool uses correctly."""
        jsonl_path = temp_project_dir / "multi-tool.jsonl"

        msg = sample_assistant_message_data.copy()
        msg["message"]["content"] = [
            {"type": "tool_use", "id": "toolu_01", "name": "Read", "input": {}},
            {"type": "tool_use", "id": "toolu_02", "name": "Read", "input": {}},
            {"type": "tool_use", "id": "toolu_03", "name": "Write", "input": {}},
        ]

        with open(jsonl_path, "w") as f:
            f.write(json.dumps(msg) + "\n")

        session = Session.from_path(jsonl_path, claude_base_dir=temp_claude_dir)

        tools = session.get_tools_used()

        assert tools["Read"] == 2
        assert tools["Write"] == 1


# =============================================================================
# Git Branches and Working Directories Tests
# =============================================================================


class TestGitBranchesAndWorkingDirs:
    """Tests for git branch and working directory discovery."""

    def test_get_git_branches(self, temp_claude_dir: Path, sample_session_jsonl: Path):
        """Test get_git_branches returns set of branch names."""
        session = Session.from_path(sample_session_jsonl, claude_base_dir=temp_claude_dir)

        branches = session.get_git_branches()

        assert isinstance(branches, set)
        assert "main" in branches

    def test_get_git_branches_empty(self, temp_claude_dir: Path, temp_project_dir: Path):
        """Test get_git_branches returns empty set for empty session."""
        empty_path = temp_project_dir / "empty.jsonl"
        empty_path.write_text("")

        session = Session.from_path(empty_path, claude_base_dir=temp_claude_dir)

        branches = session.get_git_branches()

        assert branches == set()

    def test_get_git_branches_multiple(
        self, temp_claude_dir: Path, temp_project_dir: Path, sample_user_message_data
    ):
        """Test get_git_branches returns all unique branches."""
        jsonl_path = temp_project_dir / "multi-branch.jsonl"

        msg1 = sample_user_message_data.copy()
        msg1["gitBranch"] = "main"

        msg2 = sample_user_message_data.copy()
        msg2["uuid"] = "user-msg-002"
        msg2["timestamp"] = "2026-01-08T13:01:00.000Z"
        msg2["gitBranch"] = "feature/new-stuff"

        msg3 = sample_user_message_data.copy()
        msg3["uuid"] = "user-msg-003"
        msg3["timestamp"] = "2026-01-08T13:02:00.000Z"
        msg3["gitBranch"] = "main"  # Duplicate

        with open(jsonl_path, "w") as f:
            f.write(json.dumps(msg1) + "\n")
            f.write(json.dumps(msg2) + "\n")
            f.write(json.dumps(msg3) + "\n")

        session = Session.from_path(jsonl_path, claude_base_dir=temp_claude_dir)

        branches = session.get_git_branches()

        assert len(branches) == 2
        assert "main" in branches
        assert "feature/new-stuff" in branches

    def test_get_working_directories(self, temp_claude_dir: Path, sample_session_jsonl: Path):
        """Test get_working_directories returns set of cwd paths."""
        session = Session.from_path(sample_session_jsonl, claude_base_dir=temp_claude_dir)

        cwds = session.get_working_directories()

        assert isinstance(cwds, set)
        assert "/Users/test/project" in cwds

    def test_get_working_directories_empty(self, temp_claude_dir: Path, temp_project_dir: Path):
        """Test get_working_directories returns empty set for empty session."""
        empty_path = temp_project_dir / "empty.jsonl"
        empty_path.write_text("")

        session = Session.from_path(empty_path, claude_base_dir=temp_claude_dir)

        cwds = session.get_working_directories()

        assert cwds == set()

    def test_get_working_directories_multiple(
        self, temp_claude_dir: Path, temp_project_dir: Path, sample_user_message_data
    ):
        """Test get_working_directories returns all unique directories."""
        jsonl_path = temp_project_dir / "multi-cwd.jsonl"

        msg1 = sample_user_message_data.copy()
        msg1["cwd"] = "/Users/test/project1"

        msg2 = sample_user_message_data.copy()
        msg2["uuid"] = "user-msg-002"
        msg2["timestamp"] = "2026-01-08T13:01:00.000Z"
        msg2["cwd"] = "/Users/test/project2"

        with open(jsonl_path, "w") as f:
            f.write(json.dumps(msg1) + "\n")
            f.write(json.dumps(msg2) + "\n")

        session = Session.from_path(jsonl_path, claude_base_dir=temp_claude_dir)

        cwds = session.get_working_directories()

        assert len(cwds) == 2
        assert "/Users/test/project1" in cwds
        assert "/Users/test/project2" in cwds


# =============================================================================
# Immutability Tests
# =============================================================================


class TestImmutability:
    """Tests for Session immutability (frozen=True)."""

    def test_session_is_frozen(self, temp_claude_dir: Path, sample_session_jsonl: Path):
        """Test that Session instances are immutable."""
        session = Session.from_path(sample_session_jsonl, claude_base_dir=temp_claude_dir)

        with pytest.raises(ValidationError):
            session.uuid = "new-uuid"

    def test_cannot_modify_uuid(self, temp_claude_dir: Path, sample_session_jsonl: Path):
        """Test that uuid cannot be modified after creation."""
        session = Session.from_path(sample_session_jsonl, claude_base_dir=temp_claude_dir)

        with pytest.raises(ValidationError):
            session.uuid = "modified-uuid"

    def test_cannot_modify_jsonl_path(self, temp_claude_dir: Path, sample_session_jsonl: Path):
        """Test that jsonl_path cannot be modified after creation."""
        session = Session.from_path(sample_session_jsonl, claude_base_dir=temp_claude_dir)

        with pytest.raises(ValidationError):
            session.jsonl_path = Path("/new/path.jsonl")

    def test_cannot_modify_claude_base_dir(self, temp_claude_dir: Path, sample_session_jsonl: Path):
        """Test that claude_base_dir cannot be modified after creation."""
        session = Session.from_path(sample_session_jsonl, claude_base_dir=temp_claude_dir)

        with pytest.raises(ValidationError):
            session.claude_base_dir = Path("/new/base")


class TestSlugProperty:
    """Tests for Session.slug property and slug behavior across subagents."""

    def test_session_slug_extracted_from_messages(
        self, temp_claude_dir: Path, temp_project_dir: Path
    ):
        """Test that Session.slug is extracted from message data."""
        session_uuid = "slug-test-session"
        jsonl_path = temp_project_dir / f"{session_uuid}.jsonl"

        # Write a message with a slug
        msg = {
            "type": "user",
            "slug": "refactored-meandering-knuth",
            "message": {"role": "user", "content": "test"},
            "uuid": "test-uuid",
            "timestamp": "2026-01-08T13:00:00.000Z",
        }
        with open(jsonl_path, "w") as f:
            f.write(json.dumps(msg) + "\n")

        session = Session.from_path(jsonl_path, claude_base_dir=temp_claude_dir)

        assert session.slug == "refactored-meandering-knuth"

    def test_session_slug_is_none_when_not_present(
        self, temp_claude_dir: Path, temp_project_dir: Path
    ):
        """Test that Session.slug is None when no slug in messages."""
        session_uuid = "no-slug-session"
        jsonl_path = temp_project_dir / f"{session_uuid}.jsonl"

        # Write a message without a slug
        msg = {
            "type": "user",
            "message": {"role": "user", "content": "test"},
            "uuid": "test-uuid",
            "timestamp": "2026-01-08T13:00:00.000Z",
        }
        with open(jsonl_path, "w") as f:
            f.write(json.dumps(msg) + "\n")

        session = Session.from_path(jsonl_path, claude_base_dir=temp_claude_dir)

        assert session.slug is None

    def test_multiple_subagents_share_session_slug(
        self, temp_claude_dir: Path, temp_project_dir: Path
    ):
        """All subagents from same session should have same slug.

        This test verifies the bug fix: slug is session-scoped, not agent-scoped.
        """
        session_uuid = "multi-subagent-session"
        session_slug = "eager-puzzling-fairy"
        jsonl_path = temp_project_dir / f"{session_uuid}.jsonl"

        # Create session JSONL
        session_msg = {
            "type": "user",
            "slug": session_slug,
            "message": {"role": "user", "content": "main session"},
            "uuid": "session-msg-1",
            "timestamp": "2026-01-08T13:00:00.000Z",
        }
        with open(jsonl_path, "w") as f:
            f.write(json.dumps(session_msg) + "\n")

        # Create subagents directory with multiple subagents
        subagents_dir = temp_project_dir / session_uuid / "subagents"
        subagents_dir.mkdir(parents=True)

        agent_ids = ["a3c3f19", "a549947", "a768842"]
        for agent_id in agent_ids:
            subagent_msg = {
                "type": "user",
                "isSidechain": True,
                "agentId": agent_id,
                "slug": session_slug,  # All inherit the same session slug
                "message": {"role": "user", "content": f"task for {agent_id}"},
                "uuid": f"subagent-{agent_id}-uuid",
                "timestamp": "2026-01-08T14:00:00.000Z",
            }
            agent_path = subagents_dir / f"agent-{agent_id}.jsonl"
            with open(agent_path, "w") as f:
                f.write(json.dumps(subagent_msg) + "\n")

        session = Session.from_path(jsonl_path, claude_base_dir=temp_claude_dir)
        subagents = session.list_subagents()

        # Verify we have all subagents
        assert len(subagents) == 3

        # Key assertion: All subagents share the same session slug
        slugs = [sa.slug for sa in subagents if sa.slug]
        assert len(slugs) == 3
        assert len(set(slugs)) == 1, "All subagents should share the same session slug"
        assert slugs[0] == session_slug

    def test_agent_id_is_unique_per_subagent(self, temp_claude_dir: Path, temp_project_dir: Path):
        """Each subagent should have unique agentId.

        This test verifies that agent_id is the correct identifier for
        distinguishing subagents, not slug.
        """
        session_uuid = "unique-agent-id-session"
        jsonl_path = temp_project_dir / f"{session_uuid}.jsonl"

        # Create session JSONL
        session_msg = {
            "type": "user",
            "slug": "test-session-slug",
            "message": {"role": "user", "content": "main session"},
            "uuid": "session-msg-1",
            "timestamp": "2026-01-08T13:00:00.000Z",
        }
        with open(jsonl_path, "w") as f:
            f.write(json.dumps(session_msg) + "\n")

        # Create subagents directory with multiple subagents
        subagents_dir = temp_project_dir / session_uuid / "subagents"
        subagents_dir.mkdir(parents=True)

        agent_ids = ["abc1234", "def5678", "ghi9012", "jkl3456"]
        for agent_id in agent_ids:
            subagent_msg = {
                "type": "user",
                "isSidechain": True,
                "agentId": agent_id,
                "slug": "test-session-slug",
                "message": {"role": "user", "content": f"task for {agent_id}"},
                "uuid": f"subagent-{agent_id}-uuid",
                "timestamp": "2026-01-08T14:00:00.000Z",
            }
            agent_path = subagents_dir / f"agent-{agent_id}.jsonl"
            with open(agent_path, "w") as f:
                f.write(json.dumps(subagent_msg) + "\n")

        session = Session.from_path(jsonl_path, claude_base_dir=temp_claude_dir)
        subagents = session.list_subagents()

        # Verify we have all subagents
        assert len(subagents) == 4

        # Key assertion: Each subagent has a unique agent_id
        retrieved_agent_ids = [sa.agent_id for sa in subagents]
        assert len(retrieved_agent_ids) == len(set(retrieved_agent_ids)), (
            "agentIds must be unique per subagent"
        )
        assert set(retrieved_agent_ids) == set(agent_ids)

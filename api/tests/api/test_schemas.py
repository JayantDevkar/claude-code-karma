"""
Unit tests for API response schemas.

Tests Pydantic models for proper instantiation, validation,
default values, inheritance, serialization, and field descriptions.
"""

import json
from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from schemas import (
    FileActivity,
    InitialPrompt,
    ProjectAnalytics,
    ProjectDetail,
    ProjectSummary,
    SessionDetail,
    SessionSummary,
    SubagentSummary,
    ToolUsageSummary,
)

# =============================================================================
# FileActivity Tests
# =============================================================================


class TestFileActivity:
    """Tests for FileActivity schema."""

    def test_valid_instantiation_all_fields(self):
        """Test creating FileActivity with all required fields."""
        timestamp = datetime.now(timezone.utc)
        activity = FileActivity(
            path="/src/main.py",
            operation="read",
            actor="session",
            actor_type="session",
            timestamp=timestamp,
            tool_name="Read",
        )

        assert activity.path == "/src/main.py"
        assert activity.operation == "read"
        assert activity.actor == "session"
        assert activity.actor_type == "session"
        assert activity.timestamp == timestamp
        assert activity.tool_name == "Read"

    def test_all_operation_types(self):
        """Test all valid operation literal values."""
        timestamp = datetime.now(timezone.utc)
        operations = ["read", "write", "edit", "delete", "search"]

        for op in operations:
            activity = FileActivity(
                path="/test.py",
                operation=op,
                actor="session",
                actor_type="session",
                timestamp=timestamp,
                tool_name="TestTool",
            )
            assert activity.operation == op

    def test_invalid_operation_raises_error(self):
        """Test that invalid operation value raises ValidationError."""
        with pytest.raises(ValidationError) as exc_info:
            FileActivity(
                path="/test.py",
                operation="invalid_operation",
                actor="session",
                actor_type="session",
                timestamp=datetime.now(timezone.utc),
                tool_name="Read",
            )

        assert "operation" in str(exc_info.value)

    def test_actor_type_literals(self):
        """Test valid actor_type literal values."""
        timestamp = datetime.now(timezone.utc)

        session_activity = FileActivity(
            path="/test.py",
            operation="read",
            actor="main",
            actor_type="session",
            timestamp=timestamp,
            tool_name="Read",
        )
        assert session_activity.actor_type == "session"

        subagent_activity = FileActivity(
            path="/test.py",
            operation="write",
            actor="eager-fairy",
            actor_type="subagent",
            timestamp=timestamp,
            tool_name="Write",
        )
        assert subagent_activity.actor_type == "subagent"

    def test_invalid_actor_type_raises_error(self):
        """Test that invalid actor_type raises ValidationError."""
        with pytest.raises(ValidationError) as exc_info:
            FileActivity(
                path="/test.py",
                operation="read",
                actor="session",
                actor_type="invalid_type",
                timestamp=datetime.now(timezone.utc),
                tool_name="Read",
            )

        assert "actor_type" in str(exc_info.value)

    def test_missing_required_field_raises_error(self):
        """Test that missing required fields raise ValidationError."""
        with pytest.raises(ValidationError):
            FileActivity(
                path="/test.py",
                operation="read",
                # missing actor, actor_type, timestamp, tool_name
            )

    def test_serialization_to_dict(self):
        """Test model_dump produces correct dictionary."""
        timestamp = datetime(2026, 1, 8, 13, 0, 0, tzinfo=timezone.utc)
        activity = FileActivity(
            path="/src/main.py",
            operation="write",
            actor="eager-fairy",
            actor_type="subagent",
            timestamp=timestamp,
            tool_name="Write",
        )

        data = activity.model_dump()

        assert data["path"] == "/src/main.py"
        assert data["operation"] == "write"
        assert data["actor"] == "eager-fairy"
        assert data["actor_type"] == "subagent"
        assert data["timestamp"] == timestamp
        assert data["tool_name"] == "Write"

    def test_serialization_to_json(self):
        """Test model_dump_json produces valid JSON."""
        timestamp = datetime(2026, 1, 8, 13, 0, 0, tzinfo=timezone.utc)
        activity = FileActivity(
            path="/src/main.py",
            operation="edit",
            actor="session",
            actor_type="session",
            timestamp=timestamp,
            tool_name="Edit",
        )

        json_str = activity.model_dump_json()
        parsed = json.loads(json_str)

        assert parsed["path"] == "/src/main.py"
        assert parsed["operation"] == "edit"

    def test_field_descriptions_present(self):
        """Test that all fields have descriptions."""
        schema = FileActivity.model_json_schema()
        properties = schema["properties"]

        assert "description" in properties["path"]
        assert "description" in properties["operation"]
        assert "description" in properties["actor"]
        assert "description" in properties["actor_type"]
        assert "description" in properties["timestamp"]
        assert "description" in properties["tool_name"]

    def test_model_validate(self):
        """Test model_validate creates instance from dict."""
        data = {
            "path": "/test.py",
            "operation": "search",
            "actor": "session",
            "actor_type": "session",
            "timestamp": "2026-01-08T13:00:00Z",
            "tool_name": "Grep",
        }

        activity = FileActivity.model_validate(data)

        assert activity.path == "/test.py"
        assert activity.operation == "search"


# =============================================================================
# SubagentSummary Tests
# =============================================================================


class TestSubagentSummary:
    """Tests for SubagentSummary schema."""

    def test_valid_instantiation_required_only(self):
        """Test creating SubagentSummary with only required field."""
        summary = SubagentSummary(agent_id="a5793c3")

        assert summary.agent_id == "a5793c3"
        assert summary.slug is None
        assert summary.tools_used == {}
        assert summary.message_count == 0
        assert summary.initial_prompt is None

    def test_valid_instantiation_all_fields(self):
        """Test creating SubagentSummary with all fields."""
        summary = SubagentSummary(
            agent_id="b1234ef",
            slug="eager-puzzling-fairy",
            tools_used={"Read": 5, "Write": 2},
            message_count=15,
            initial_prompt="Analyze this codebase",
        )

        assert summary.agent_id == "b1234ef"
        assert summary.slug == "eager-puzzling-fairy"
        assert summary.tools_used == {"Read": 5, "Write": 2}
        assert summary.message_count == 15
        assert summary.initial_prompt == "Analyze this codebase"

    def test_default_values(self):
        """Test that default values are correctly applied."""
        summary = SubagentSummary(agent_id="test123")

        assert summary.slug is None
        assert summary.tools_used == {}
        assert summary.message_count == 0
        assert summary.initial_prompt is None

    def test_tools_used_default_factory(self):
        """Test that tools_used uses default_factory for new dict per instance."""
        summary1 = SubagentSummary(agent_id="test1")
        summary2 = SubagentSummary(agent_id="test2")

        # Modify summary1's dict (if mutable) - they should be independent
        # Note: Pydantic models are typically immutable, but testing the factory behavior
        assert summary1.tools_used is not summary2.tools_used

    def test_serialization_to_dict(self):
        """Test model_dump produces correct dictionary."""
        summary = SubagentSummary(
            agent_id="abc123",
            slug="test-slug",
            tools_used={"Bash": 3},
            message_count=10,
        )

        data = summary.model_dump()

        assert data["agent_id"] == "abc123"
        assert data["slug"] == "test-slug"
        assert data["tools_used"] == {"Bash": 3}
        assert data["message_count"] == 10
        assert data["initial_prompt"] is None

    def test_field_descriptions_present(self):
        """Test that all fields have descriptions."""
        schema = SubagentSummary.model_json_schema()
        properties = schema["properties"]

        assert "description" in properties["agent_id"]
        assert "description" in properties["slug"]
        assert "description" in properties["tools_used"]
        assert "description" in properties["message_count"]
        assert "description" in properties["initial_prompt"]


# =============================================================================
# ToolUsageSummary Tests
# =============================================================================


class TestToolUsageSummary:
    """Tests for ToolUsageSummary schema."""

    def test_valid_instantiation_required_only(self):
        """Test creating ToolUsageSummary with required fields."""
        summary = ToolUsageSummary(tool_name="Read", count=10)

        assert summary.tool_name == "Read"
        assert summary.count == 10
        assert summary.by_session == 0
        assert summary.by_subagents == 0

    def test_valid_instantiation_all_fields(self):
        """Test creating ToolUsageSummary with all fields."""
        summary = ToolUsageSummary(
            tool_name="Write",
            count=25,
            by_session=15,
            by_subagents=10,
        )

        assert summary.tool_name == "Write"
        assert summary.count == 25
        assert summary.by_session == 15
        assert summary.by_subagents == 10

    def test_default_values(self):
        """Test default values for optional fields."""
        summary = ToolUsageSummary(tool_name="Bash", count=5)

        assert summary.by_session == 0
        assert summary.by_subagents == 0

    def test_missing_required_field_raises_error(self):
        """Test that missing tool_name or count raises error."""
        with pytest.raises(ValidationError):
            ToolUsageSummary(tool_name="Read")  # missing count

        with pytest.raises(ValidationError):
            ToolUsageSummary(count=10)  # missing tool_name

    def test_serialization_to_dict(self):
        """Test model_dump produces correct dictionary."""
        summary = ToolUsageSummary(
            tool_name="Edit",
            count=20,
            by_session=12,
            by_subagents=8,
        )

        data = summary.model_dump()

        assert data["tool_name"] == "Edit"
        assert data["count"] == 20
        assert data["by_session"] == 12
        assert data["by_subagents"] == 8

    def test_field_descriptions_present(self):
        """Test that all fields have descriptions."""
        schema = ToolUsageSummary.model_json_schema()
        properties = schema["properties"]

        assert "description" in properties["tool_name"]
        assert "description" in properties["count"]
        assert "description" in properties["by_session"]
        assert "description" in properties["by_subagents"]


# =============================================================================
# SessionSummary Tests
# =============================================================================


class TestSessionSummary:
    """Tests for SessionSummary schema."""

    def test_valid_instantiation_required_only(self):
        """Test creating SessionSummary with required fields."""
        summary = SessionSummary(
            uuid="test-uuid-12345",
            message_count=50,
        )

        assert summary.uuid == "test-uuid-12345"
        assert summary.message_count == 50

    def test_valid_instantiation_all_fields(self):
        """Test creating SessionSummary with all fields."""
        start = datetime(2026, 1, 8, 10, 0, 0, tzinfo=timezone.utc)
        end = datetime(2026, 1, 8, 11, 30, 0, tzinfo=timezone.utc)

        summary = SessionSummary(
            uuid="full-uuid",
            message_count=100,
            start_time=start,
            end_time=end,
            duration_seconds=5400.0,
            models_used=["claude-opus-4-5", "claude-sonnet-4"],
            subagent_count=3,
            has_todos=True,
            initial_prompt="Help me refactor this code",
        )

        assert summary.uuid == "full-uuid"
        assert summary.message_count == 100
        assert summary.start_time == start
        assert summary.end_time == end
        assert summary.duration_seconds == 5400.0
        assert summary.models_used == ["claude-opus-4-5", "claude-sonnet-4"]
        assert summary.subagent_count == 3
        assert summary.has_todos is True
        assert summary.initial_prompt == "Help me refactor this code"

    def test_default_values(self):
        """Test default values are applied correctly."""
        summary = SessionSummary(uuid="test", message_count=0)

        assert summary.start_time is None
        assert summary.end_time is None
        assert summary.duration_seconds is None
        assert summary.models_used == []
        assert summary.subagent_count == 0
        assert summary.has_todos is False
        assert summary.initial_prompt is None

    def test_models_used_default_factory(self):
        """Test that models_used creates new list per instance."""
        summary1 = SessionSummary(uuid="s1", message_count=1)
        summary2 = SessionSummary(uuid="s2", message_count=2)

        assert summary1.models_used is not summary2.models_used

    def test_serialization_to_dict(self):
        """Test model_dump produces correct dictionary."""
        start = datetime(2026, 1, 8, 10, 0, 0, tzinfo=timezone.utc)

        summary = SessionSummary(
            uuid="test-uuid",
            message_count=25,
            start_time=start,
            models_used=["claude-opus-4-5"],
            has_todos=True,
        )

        data = summary.model_dump()

        assert data["uuid"] == "test-uuid"
        assert data["message_count"] == 25
        assert data["start_time"] == start
        assert data["models_used"] == ["claude-opus-4-5"]
        assert data["has_todos"] is True

    def test_serialization_to_json(self):
        """Test model_dump_json produces valid JSON."""
        summary = SessionSummary(uuid="json-test", message_count=10)

        json_str = summary.model_dump_json()
        parsed = json.loads(json_str)

        assert parsed["uuid"] == "json-test"
        assert parsed["message_count"] == 10


# =============================================================================
# SessionDetail Tests
# =============================================================================


class TestSessionDetail:
    """Tests for SessionDetail schema (extends SessionSummary)."""

    def test_inherits_from_session_summary(self):
        """Test that SessionDetail inherits from SessionSummary."""
        assert issubclass(SessionDetail, SessionSummary)

    def test_valid_instantiation_with_inherited_fields(self):
        """Test creating SessionDetail with inherited and own fields."""
        start = datetime(2026, 1, 8, 10, 0, 0, tzinfo=timezone.utc)

        detail = SessionDetail(
            # Inherited from SessionSummary
            uuid="detail-uuid",
            message_count=75,
            start_time=start,
            models_used=["claude-opus-4-5"],
            subagent_count=2,
            # SessionDetail specific
            tools_used={"Read": 20, "Write": 10, "Bash": 5},
            git_branches=["main", "feature/auth"],
            working_directories=["/home/user/project"],
            total_input_tokens=50000,
            total_output_tokens=25000,
            cache_hit_rate=0.85,
        )

        # Check inherited fields
        assert detail.uuid == "detail-uuid"
        assert detail.message_count == 75
        assert detail.start_time == start
        assert detail.models_used == ["claude-opus-4-5"]
        assert detail.subagent_count == 2

        # Check own fields
        assert detail.tools_used == {"Read": 20, "Write": 10, "Bash": 5}
        assert detail.git_branches == ["main", "feature/auth"]
        assert detail.working_directories == ["/home/user/project"]
        assert detail.total_input_tokens == 50000
        assert detail.total_output_tokens == 25000
        assert detail.cache_hit_rate == 0.85

    def test_default_values(self):
        """Test default values for SessionDetail specific fields."""
        detail = SessionDetail(uuid="test", message_count=0)

        # SessionDetail defaults
        assert detail.tools_used == {}
        assert detail.git_branches == []
        assert detail.working_directories == []
        assert detail.total_input_tokens == 0
        assert detail.total_output_tokens == 0
        assert detail.cache_hit_rate == 0.0

        # Inherited defaults
        assert detail.start_time is None
        assert detail.models_used == []
        assert detail.has_todos is False

    def test_default_factory_independence(self):
        """Test that default_factory creates independent instances."""
        detail1 = SessionDetail(uuid="d1", message_count=1)
        detail2 = SessionDetail(uuid="d2", message_count=2)

        assert detail1.tools_used is not detail2.tools_used
        assert detail1.git_branches is not detail2.git_branches
        assert detail1.working_directories is not detail2.working_directories

    def test_serialization_includes_all_fields(self):
        """Test that serialization includes both inherited and own fields."""
        detail = SessionDetail(
            uuid="ser-test",
            message_count=10,
            models_used=["claude-sonnet-4"],
            tools_used={"Read": 5},
            git_branches=["develop"],
            total_input_tokens=1000,
        )

        data = detail.model_dump()

        # Check inherited fields present
        assert "uuid" in data
        assert "message_count" in data
        assert "models_used" in data
        assert "has_todos" in data

        # Check own fields present
        assert "tools_used" in data
        assert "git_branches" in data
        assert "total_input_tokens" in data
        assert "cache_hit_rate" in data


# =============================================================================
# ProjectSummary Tests
# =============================================================================


class TestProjectSummary:
    """Tests for ProjectSummary schema."""

    def test_valid_instantiation_required_only(self):
        """Test creating ProjectSummary with required fields."""
        summary = ProjectSummary(
            path="/Users/test/myproject",
            encoded_name="-Users-test-myproject",
        )

        assert summary.path == "/Users/test/myproject"
        assert summary.encoded_name == "-Users-test-myproject"

    def test_valid_instantiation_all_fields(self):
        """Test creating ProjectSummary with all fields."""
        summary = ProjectSummary(
            path="/home/dev/project",
            encoded_name="-home-dev-project",
            session_count=15,
            agent_count=5,
            exists=True,
        )

        assert summary.path == "/home/dev/project"
        assert summary.encoded_name == "-home-dev-project"
        assert summary.session_count == 15
        assert summary.agent_count == 5
        assert summary.exists is True

    def test_default_values(self):
        """Test default values are applied correctly."""
        summary = ProjectSummary(
            path="/test",
            encoded_name="-test",
        )

        assert summary.session_count == 0
        assert summary.agent_count == 0
        assert summary.exists is True

    def test_exists_can_be_false(self):
        """Test that exists field can be set to False."""
        summary = ProjectSummary(
            path="/deleted/project",
            encoded_name="-deleted-project",
            exists=False,
        )

        assert summary.exists is False

    def test_missing_required_field_raises_error(self):
        """Test that missing path or encoded_name raises error."""
        with pytest.raises(ValidationError):
            ProjectSummary(path="/test")  # missing encoded_name

        with pytest.raises(ValidationError):
            ProjectSummary(encoded_name="-test")  # missing path

    def test_field_descriptions_present(self):
        """Test that fields have descriptions."""
        schema = ProjectSummary.model_json_schema()
        properties = schema["properties"]

        assert "description" in properties["path"]
        assert "description" in properties["encoded_name"]

    def test_serialization_to_dict(self):
        """Test model_dump produces correct dictionary."""
        summary = ProjectSummary(
            path="/home/user/repo",
            encoded_name="-home-user-repo",
            session_count=10,
        )

        data = summary.model_dump()

        assert data["path"] == "/home/user/repo"
        assert data["encoded_name"] == "-home-user-repo"
        assert data["session_count"] == 10
        assert data["exists"] is True


# =============================================================================
# ProjectDetail Tests
# =============================================================================


class TestProjectDetail:
    """Tests for ProjectDetail schema (extends ProjectSummary)."""

    def test_inherits_from_project_summary(self):
        """Test that ProjectDetail inherits from ProjectSummary."""
        assert issubclass(ProjectDetail, ProjectSummary)

    def test_valid_instantiation_with_sessions(self):
        """Test creating ProjectDetail with sessions list."""
        session1 = SessionSummary(uuid="sess1", message_count=10)
        session2 = SessionSummary(uuid="sess2", message_count=20)

        detail = ProjectDetail(
            path="/home/user/project",
            encoded_name="-home-user-project",
            session_count=2,
            sessions=[session1, session2],
        )

        assert detail.path == "/home/user/project"
        assert detail.session_count == 2
        assert len(detail.sessions) == 2
        assert detail.sessions[0].uuid == "sess1"
        assert detail.sessions[1].uuid == "sess2"

    def test_default_sessions_list(self):
        """Test that sessions defaults to empty list."""
        detail = ProjectDetail(
            path="/test",
            encoded_name="-test",
        )

        assert detail.sessions == []

    def test_sessions_default_factory_independence(self):
        """Test that sessions creates independent lists."""
        detail1 = ProjectDetail(path="/p1", encoded_name="-p1")
        detail2 = ProjectDetail(path="/p2", encoded_name="-p2")

        assert detail1.sessions is not detail2.sessions

    def test_sessions_contain_session_summary_objects(self):
        """Test that sessions list contains SessionSummary instances."""
        session = SessionSummary(uuid="test", message_count=5)
        detail = ProjectDetail(
            path="/project",
            encoded_name="-project",
            sessions=[session],
        )

        assert isinstance(detail.sessions[0], SessionSummary)

    def test_serialization_includes_sessions(self):
        """Test serialization includes nested sessions."""
        session = SessionSummary(uuid="nested", message_count=15, has_todos=True)
        detail = ProjectDetail(
            path="/home/project",
            encoded_name="-home-project",
            sessions=[session],
        )

        data = detail.model_dump()

        assert "sessions" in data
        assert len(data["sessions"]) == 1
        assert data["sessions"][0]["uuid"] == "nested"
        assert data["sessions"][0]["has_todos"] is True


# =============================================================================
# ProjectAnalytics Tests
# =============================================================================


class TestProjectAnalytics:
    """Tests for ProjectAnalytics schema."""

    def test_valid_instantiation_defaults_only(self):
        """Test creating ProjectAnalytics with all defaults."""
        analytics = ProjectAnalytics()

        assert analytics.total_sessions == 0
        assert analytics.total_tokens == 0
        assert analytics.total_input_tokens == 0
        assert analytics.total_output_tokens == 0
        assert analytics.total_duration_seconds == 0.0
        assert analytics.estimated_cost_usd == 0.0
        assert analytics.models_used == {}
        assert analytics.cache_hit_rate == 0.0
        assert analytics.tools_used == {}
        assert analytics.sessions_by_date == {}

    def test_valid_instantiation_all_fields(self):
        """Test creating ProjectAnalytics with all fields."""
        analytics = ProjectAnalytics(
            total_sessions=50,
            total_tokens=1000000,
            total_input_tokens=600000,
            total_output_tokens=400000,
            total_duration_seconds=36000.0,
            estimated_cost_usd=25.50,
            models_used={"claude-opus-4-5": 30, "claude-sonnet-4": 20},
            cache_hit_rate=0.75,
            tools_used={"Read": 500, "Write": 200, "Bash": 100},
            sessions_by_date={"2026-01-08": 10, "2026-01-07": 15},
        )

        assert analytics.total_sessions == 50
        assert analytics.total_tokens == 1000000
        assert analytics.total_input_tokens == 600000
        assert analytics.total_output_tokens == 400000
        assert analytics.total_duration_seconds == 36000.0
        assert analytics.estimated_cost_usd == 25.50
        assert analytics.models_used == {"claude-opus-4-5": 30, "claude-sonnet-4": 20}
        assert analytics.cache_hit_rate == 0.75
        assert analytics.tools_used == {"Read": 500, "Write": 200, "Bash": 100}
        assert analytics.sessions_by_date == {"2026-01-08": 10, "2026-01-07": 15}

    def test_default_factory_independence(self):
        """Test that dict defaults create independent instances."""
        analytics1 = ProjectAnalytics()
        analytics2 = ProjectAnalytics()

        assert analytics1.models_used is not analytics2.models_used
        assert analytics1.tools_used is not analytics2.tools_used
        assert analytics1.sessions_by_date is not analytics2.sessions_by_date

    def test_field_descriptions_present(self):
        """Test that sessions_by_date has description."""
        schema = ProjectAnalytics.model_json_schema()
        properties = schema["properties"]

        assert "description" in properties["sessions_by_date"]

    def test_serialization_to_dict(self):
        """Test model_dump produces correct dictionary."""
        analytics = ProjectAnalytics(
            total_sessions=5,
            total_tokens=10000,
            cache_hit_rate=0.5,
            sessions_by_date={"2026-01-08": 5},
        )

        data = analytics.model_dump()

        assert data["total_sessions"] == 5
        assert data["total_tokens"] == 10000
        assert data["cache_hit_rate"] == 0.5
        assert data["sessions_by_date"] == {"2026-01-08": 5}

    def test_serialization_to_json(self):
        """Test model_dump_json produces valid JSON."""
        analytics = ProjectAnalytics(
            total_sessions=10,
            estimated_cost_usd=5.25,
        )

        json_str = analytics.model_dump_json()
        parsed = json.loads(json_str)

        assert parsed["total_sessions"] == 10
        assert parsed["estimated_cost_usd"] == 5.25


# =============================================================================
# InitialPrompt Tests
# =============================================================================


class TestInitialPrompt:
    """Tests for InitialPrompt schema."""

    def test_valid_instantiation(self):
        """Test creating InitialPrompt with required fields."""
        timestamp = datetime(2026, 1, 8, 13, 0, 0, tzinfo=timezone.utc)
        prompt = InitialPrompt(
            content="Help me understand this codebase",
            timestamp=timestamp,
        )

        assert prompt.content == "Help me understand this codebase"
        assert prompt.timestamp == timestamp

    def test_missing_content_raises_error(self):
        """Test that missing content raises ValidationError."""
        with pytest.raises(ValidationError):
            InitialPrompt(timestamp=datetime.now(timezone.utc))

    def test_missing_timestamp_raises_error(self):
        """Test that missing timestamp raises ValidationError."""
        with pytest.raises(ValidationError):
            InitialPrompt(content="Test prompt")

    def test_field_descriptions_present(self):
        """Test that all fields have descriptions."""
        schema = InitialPrompt.model_json_schema()
        properties = schema["properties"]

        assert "description" in properties["content"]
        assert "description" in properties["timestamp"]

    def test_serialization_to_dict(self):
        """Test model_dump produces correct dictionary."""
        timestamp = datetime(2026, 1, 8, 14, 30, 0, tzinfo=timezone.utc)
        prompt = InitialPrompt(
            content="Refactor the authentication module",
            timestamp=timestamp,
        )

        data = prompt.model_dump()

        assert data["content"] == "Refactor the authentication module"
        assert data["timestamp"] == timestamp

    def test_serialization_to_json(self):
        """Test model_dump_json produces valid JSON."""
        timestamp = datetime(2026, 1, 8, 10, 0, 0, tzinfo=timezone.utc)
        prompt = InitialPrompt(
            content="Add unit tests",
            timestamp=timestamp,
        )

        json_str = prompt.model_dump_json()
        parsed = json.loads(json_str)

        assert parsed["content"] == "Add unit tests"
        assert "timestamp" in parsed

    def test_model_validate(self):
        """Test model_validate creates instance from dict."""
        data = {
            "content": "Build a new feature",
            "timestamp": "2026-01-08T15:00:00Z",
        }

        prompt = InitialPrompt.model_validate(data)

        assert prompt.content == "Build a new feature"


# =============================================================================
# Cross-Model Integration Tests
# =============================================================================


class TestModelIntegration:
    """Integration tests for schema relationships."""

    def test_project_detail_with_session_details(self):
        """Test ProjectDetail can contain full SessionSummary objects."""
        sessions = [
            SessionSummary(
                uuid="sess-1",
                message_count=50,
                models_used=["claude-opus-4-5"],
                has_todos=True,
            ),
            SessionSummary(
                uuid="sess-2",
                message_count=30,
                subagent_count=2,
            ),
        ]

        project = ProjectDetail(
            path="/home/dev/myproject",
            encoded_name="-home-dev-myproject",
            session_count=2,
            sessions=sessions,
        )

        assert len(project.sessions) == 2
        assert project.sessions[0].models_used == ["claude-opus-4-5"]
        assert project.sessions[1].subagent_count == 2

    def test_session_detail_is_valid_session_summary(self):
        """Test that SessionDetail can be used where SessionSummary is expected."""
        detail = SessionDetail(
            uuid="detail-session",
            message_count=100,
            tools_used={"Read": 50},
            git_branches=["main"],
        )

        # Should be usable as SessionSummary
        assert isinstance(detail, SessionSummary)
        assert detail.uuid == "detail-session"

    def test_full_serialization_round_trip(self):
        """Test full serialization and deserialization cycle."""
        original = ProjectAnalytics(
            total_sessions=25,
            total_tokens=500000,
            estimated_cost_usd=12.75,
            models_used={"claude-opus-4-5": 20, "claude-sonnet-4": 5},
            tools_used={"Read": 100, "Write": 50},
            sessions_by_date={"2026-01-08": 15, "2026-01-07": 10},
        )

        # Serialize to JSON
        json_str = original.model_dump_json()

        # Deserialize back
        restored = ProjectAnalytics.model_validate_json(json_str)

        assert restored.total_sessions == original.total_sessions
        assert restored.estimated_cost_usd == original.estimated_cost_usd
        assert restored.models_used == original.models_used
        assert restored.tools_used == original.tools_used
        assert restored.sessions_by_date == original.sessions_by_date


# =============================================================================
# Edge Cases and Boundary Tests
# =============================================================================


class TestEdgeCases:
    """Tests for edge cases and boundary conditions."""

    def test_empty_string_fields(self):
        """Test models accept empty strings where valid."""
        summary = SessionSummary(
            uuid="",
            message_count=0,
            initial_prompt="",
        )

        assert summary.uuid == ""
        assert summary.initial_prompt == ""

    def test_large_token_counts(self):
        """Test models handle large integer values."""
        analytics = ProjectAnalytics(
            total_tokens=999999999999,
            total_input_tokens=600000000000,
            total_output_tokens=399999999999,
        )

        assert analytics.total_tokens == 999999999999

    def test_float_precision(self):
        """Test float fields maintain precision."""
        analytics = ProjectAnalytics(
            cache_hit_rate=0.123456789,
            estimated_cost_usd=123.456789,
        )

        assert analytics.cache_hit_rate == 0.123456789
        assert analytics.estimated_cost_usd == 123.456789

    def test_unicode_content(self):
        """Test models handle unicode content."""
        prompt = InitialPrompt(
            content="Help me with Python code",
            timestamp=datetime.now(timezone.utc),
        )

        assert "Python" in prompt.content

    def test_special_characters_in_path(self):
        """Test models handle special characters in paths."""
        activity = FileActivity(
            path="/path/with spaces/and-dashes/file_name.py",
            operation="read",
            actor="session",
            actor_type="session",
            timestamp=datetime.now(timezone.utc),
            tool_name="Read",
        )

        assert activity.path == "/path/with spaces/and-dashes/file_name.py"

    def test_nested_session_in_project_detail_validation(self):
        """Test that invalid nested session raises error."""
        with pytest.raises(ValidationError):
            ProjectDetail(
                path="/test",
                encoded_name="-test",
                sessions=[{"invalid": "session_data"}],  # Missing required fields
            )

    def test_negative_values_accepted(self):
        """Test that integer fields accept negative values (no constraints)."""
        # Note: These may be logically invalid but should be syntactically valid
        summary = SessionSummary(
            uuid="test",
            message_count=-1,
            subagent_count=-5,
        )

        assert summary.message_count == -1
        assert summary.subagent_count == -5

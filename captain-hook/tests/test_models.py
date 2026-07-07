"""
Test Suite for Claude Code Hook Models

Systematic, maintainable tests organized by:
1. Base hook validation
2. Individual hook types (parametrized)
3. Parser function
4. Forward compatibility
5. Output models

Run with: pytest test_models.py -v
"""

import pytest
from typing import Any, Dict, Type
from pydantic import ValidationError

from models import (
    # Base
    BaseHook,
    HookEvent,
    parse_hook_event,
    HOOK_TYPE_MAP,
    # Hook Types
    PreToolUseHook,
    PostToolUseHook,
    PostToolUseFailureHook,
    UserPromptSubmitHook,
    SessionStartHook,
    SessionEndHook,
    StopHook,
    SubagentStartHook,
    SubagentStopHook,
    PreCompactHook,
    PermissionRequestHook,
    NotificationHook,
    SetupHook,
    # New hook types (v2.1.83 - v2.1.92)
    InstructionsLoadedHook,
    PermissionDeniedHook,
    ElicitationHook,
    ElicitationResultHook,
    CwdChangedHook,
    FileChangedHook,
    TaskCreatedHook,
    TaskCompletedHook,
    TeammateIdleHook,
    WorktreeCreateHook,
    WorktreeRemoveHook,
    # Output Types
    HookOutput,
    PreToolUseOutput,
    StopOutput,
    PermissionRequestOutput,
    PermissionDeniedOutput,
)


# =============================================================================
# Test Data Fixtures
# =============================================================================

@pytest.fixture
def base_hook_data() -> Dict[str, Any]:
    """Minimal valid data for any hook type."""
    return {
        "session_id": "sess_abc123",
        "transcript_path": "/tmp/transcript.jsonl",
        "cwd": "/home/user/project",
        "permission_mode": "default",
        "hook_event_name": "BaseHook",
    }


@pytest.fixture
def pre_tool_use_data(base_hook_data) -> Dict[str, Any]:
    """Valid PreToolUse hook data."""
    return {
        **base_hook_data,
        "hook_event_name": "PreToolUse",
        "tool_name": "Write",
        "tool_use_id": "tool_xyz789",
        "tool_input": {"file_path": "/tmp/test.txt", "content": "hello"},
    }


@pytest.fixture
def post_tool_use_data(base_hook_data) -> Dict[str, Any]:
    """Valid PostToolUse hook data."""
    return {
        **base_hook_data,
        "hook_event_name": "PostToolUse",
        "tool_name": "Bash",
        "tool_use_id": "tool_abc123",
        "tool_input": {"command": "ls -la"},
        "tool_response": "total 0\ndrwxr-xr-x  2 user user 40 Jan  1 00:00 .",
    }


@pytest.fixture
def user_prompt_submit_data(base_hook_data) -> Dict[str, Any]:
    """Valid UserPromptSubmit hook data."""
    return {
        **base_hook_data,
        "hook_event_name": "UserPromptSubmit",
        "prompt": "Please help me refactor this code",
    }


@pytest.fixture
def session_start_data(base_hook_data) -> Dict[str, Any]:
    """Valid SessionStart hook data."""
    return {
        **base_hook_data,
        "hook_event_name": "SessionStart",
        "source": "startup",
    }


@pytest.fixture
def session_end_data(base_hook_data) -> Dict[str, Any]:
    """Valid SessionEnd hook data."""
    return {
        **base_hook_data,
        "hook_event_name": "SessionEnd",
        "reason": "prompt_input_exit",
    }


@pytest.fixture
def stop_data(base_hook_data) -> Dict[str, Any]:
    """Valid Stop hook data."""
    return {
        **base_hook_data,
        "hook_event_name": "Stop",
        "stop_hook_active": False,
    }


@pytest.fixture
def subagent_stop_data(base_hook_data) -> Dict[str, Any]:
    """Valid SubagentStop hook data."""
    return {
        **base_hook_data,
        "hook_event_name": "SubagentStop",
        "stop_hook_active": True,
        "agent_id": "agent-abc123",
        "agent_transcript_path": "~/.claude/projects/-Users-me-repo/sess_abc123/subagents/agent-abc123.jsonl",
    }


@pytest.fixture
def pre_compact_data(base_hook_data) -> Dict[str, Any]:
    """Valid PreCompact hook data."""
    return {
        **base_hook_data,
        "hook_event_name": "PreCompact",
        "trigger": "auto",
        "custom_instructions": "",
    }


@pytest.fixture
def permission_request_data(base_hook_data) -> Dict[str, Any]:
    """Valid PermissionRequest hook data."""
    return {
        **base_hook_data,
        "hook_event_name": "PermissionRequest",
        "notification_type": "permission_prompt",
        "message": "Allow Write to /etc/passwd?",
    }


@pytest.fixture
def notification_data(base_hook_data) -> Dict[str, Any]:
    """Valid Notification hook data."""
    return {
        **base_hook_data,
        "hook_event_name": "Notification",
        "notification_type": "idle_prompt",
    }


@pytest.fixture
def instructions_loaded_data(base_hook_data) -> Dict[str, Any]:
    """Valid InstructionsLoaded hook data."""
    return {
        **base_hook_data,
        "hook_event_name": "InstructionsLoaded",
        "file_path": "/Users/me/repo/CLAUDE.md",
        "memory_type": "project",
        "load_reason": "startup",
        "globs": [],
    }


@pytest.fixture
def permission_denied_data(base_hook_data) -> Dict[str, Any]:
    """Valid PermissionDenied hook data."""
    return {
        **base_hook_data,
        "hook_event_name": "PermissionDenied",
        "tool_name": "Bash",
        "tool_use_id": "tool_denied_001",
        "reason": "Auto mode policy: dangerous command",
        "tool_input": {"command": "rm -rf /"},
    }


@pytest.fixture
def elicitation_data(base_hook_data) -> Dict[str, Any]:
    """Valid Elicitation hook data."""
    return {
        **base_hook_data,
        "hook_event_name": "Elicitation",
        "mcp_server": "github",
        "tool_name": "create_issue",
        "request": {"title": "string", "body": "string"},
    }


@pytest.fixture
def elicitation_result_data(base_hook_data) -> Dict[str, Any]:
    """Valid ElicitationResult hook data."""
    return {
        **base_hook_data,
        "hook_event_name": "ElicitationResult",
        "mcp_server": "github",
        "user_response": {"title": "Bug report", "body": "Steps to reproduce..."},
    }


@pytest.fixture
def cwd_changed_data(base_hook_data) -> Dict[str, Any]:
    """Valid CwdChanged hook data."""
    return {
        **base_hook_data,
        "hook_event_name": "CwdChanged",
        "old_cwd": "/Users/me/old_project",
        "new_cwd": "/Users/me/new_project",
    }


@pytest.fixture
def file_changed_data(base_hook_data) -> Dict[str, Any]:
    """Valid FileChanged hook data."""
    return {
        **base_hook_data,
        "hook_event_name": "FileChanged",
        "file_path": "/Users/me/project/src/main.py",
        "file_name": "main.py",
    }


@pytest.fixture
def task_created_data(base_hook_data) -> Dict[str, Any]:
    """Valid TaskCreated hook data."""
    return {
        **base_hook_data,
        "hook_event_name": "TaskCreated",
        "task_id": "task_001",
        "task_subject": "Refactor auth module",
        "task_description": "Split auth.py into smaller files",
        "teammate_name": "Alice",
        "team_name": "core-team",
    }


@pytest.fixture
def task_completed_data(base_hook_data) -> Dict[str, Any]:
    """Valid TaskCompleted hook data."""
    return {
        **base_hook_data,
        "hook_event_name": "TaskCompleted",
        "task_id": "task_002",
        "task_subject": "Add tests",
        "task_description": "Cover edge cases",
        "teammate_name": "Bob",
        "team_name": "core-team",
    }


@pytest.fixture
def teammate_idle_data(base_hook_data) -> Dict[str, Any]:
    """Valid TeammateIdle hook data."""
    return {
        **base_hook_data,
        "hook_event_name": "TeammateIdle",
        "agent_id": "agent_idle_001",
        "agent_type": "Explore",
        "team_name": "core-team",
    }


@pytest.fixture
def worktree_create_data(base_hook_data) -> Dict[str, Any]:
    """Valid WorktreeCreate hook data."""
    return {
        **base_hook_data,
        "hook_event_name": "WorktreeCreate",
        "worktree_name": "feat-auth",
        "base_ref": "main",
    }


@pytest.fixture
def worktree_remove_data(base_hook_data) -> Dict[str, Any]:
    """Valid WorktreeRemove hook data."""
    return {
        **base_hook_data,
        "hook_event_name": "WorktreeRemove",
        "worktree_path": "/Users/me/.claude-worktrees/repo/feat-auth",
        "worktree_name": "feat-auth",
    }


# =============================================================================
# Test Data Registry (for parametrized tests)
# =============================================================================

HOOK_TEST_DATA: Dict[str, Dict[str, Any]] = {
    "PreToolUse": {
        "hook_event_name": "PreToolUse",
        "tool_name": "Write",
        "tool_use_id": "tool_001",
        "tool_input": {"file_path": "/tmp/test.txt"},
    },
    "PostToolUse": {
        "hook_event_name": "PostToolUse",
        "tool_name": "Bash",
        "tool_use_id": "tool_002",
        "tool_input": {"command": "ls"},
        "tool_response": "file.txt",
    },
    "PostToolUseFailure": {
        "hook_event_name": "PostToolUseFailure",
        "tool_name": "Bash",
        "tool_use_id": "tool_003",
        "tool_input": {"command": "rm -rf /"},
        "error": "Permission denied",
    },
    "UserPromptSubmit": {
        "hook_event_name": "UserPromptSubmit",
        "prompt": "Hello Claude",
    },
    "SessionStart": {
        "hook_event_name": "SessionStart",
        "source": "startup",
    },
    "SessionEnd": {
        "hook_event_name": "SessionEnd",
        "reason": "logout",
    },
    "Stop": {
        "hook_event_name": "Stop",
        "stop_hook_active": False,
    },
    "SubagentStart": {
        "hook_event_name": "SubagentStart",
        "agent_id": "agent-abc123",
        "agent_type": "Bash",
    },
    "SubagentStop": {
        "hook_event_name": "SubagentStop",
        "stop_hook_active": True,
        "agent_id": "agent-xyz789",
        "agent_transcript_path": "~/.claude/projects/-Users-me-repo/sess_001/subagents/agent-xyz789.jsonl",
    },
    "PreCompact": {
        "hook_event_name": "PreCompact",
        "trigger": "manual",
        "custom_instructions": "Keep API keys",
    },
    "PermissionRequest": {
        "hook_event_name": "PermissionRequest",
        "notification_type": "permission_prompt",
        "message": "Allow this action?",
    },
    "Notification": {
        "hook_event_name": "Notification",
        "notification_type": "auth_success",
    },
    "Setup": {
        "hook_event_name": "Setup",
        "trigger": "init",
    },
    # New in v2.1.83 - v2.1.92
    "InstructionsLoaded": {
        "hook_event_name": "InstructionsLoaded",
        "file_path": "/Users/me/repo/CLAUDE.md",
        "memory_type": "project",
        "load_reason": "startup",
        "globs": [],
    },
    "PermissionDenied": {
        "hook_event_name": "PermissionDenied",
        "tool_name": "Write",
        "tool_use_id": "tool_denied_002",
        "reason": "Auto mode policy: protected path",
        "tool_input": {"file_path": "/etc/passwd"},
    },
    "Elicitation": {
        "hook_event_name": "Elicitation",
        "mcp_server": "linear",
        "tool_name": "create_issue",
        "request": {"title": "string"},
    },
    "ElicitationResult": {
        "hook_event_name": "ElicitationResult",
        "mcp_server": "linear",
        "user_response": {"title": "Bug"},
    },
    "CwdChanged": {
        "hook_event_name": "CwdChanged",
        "old_cwd": "/Users/me/old",
        "new_cwd": "/Users/me/new",
    },
    "FileChanged": {
        "hook_event_name": "FileChanged",
        "file_path": "/Users/me/project/file.py",
        "file_name": "file.py",
    },
    "TaskCreated": {
        "hook_event_name": "TaskCreated",
        "task_id": "task_test_001",
        "task_subject": "Add login flow",
        "team_name": "frontend-team",
    },
    "TaskCompleted": {
        "hook_event_name": "TaskCompleted",
        "task_id": "task_test_002",
        "task_subject": "Add login flow",
        "team_name": "frontend-team",
    },
    "TeammateIdle": {
        "hook_event_name": "TeammateIdle",
        "agent_id": "agent_test_idle",
        "agent_type": "Explore",
    },
    "WorktreeCreate": {
        "hook_event_name": "WorktreeCreate",
        "worktree_name": "feat-x",
        "base_ref": "main",
    },
    "WorktreeRemove": {
        "hook_event_name": "WorktreeRemove",
        "worktree_path": "/Users/me/.claude-worktrees/repo/feat-x",
        "worktree_name": "feat-x",
    },
}


def make_full_hook_data(hook_name: str) -> Dict[str, Any]:
    """Generate complete hook data with base fields."""
    base = {
        "session_id": f"sess_{hook_name.lower()}",
        "transcript_path": f"/tmp/{hook_name.lower()}_transcript.jsonl",
        "cwd": "/home/user/project",
        "permission_mode": "default",
    }
    return {**base, **HOOK_TEST_DATA[hook_name]}


# =============================================================================
# 1. Base Hook Tests
# =============================================================================

class TestBaseHook:
    """Tests for BaseHook class and common field validation."""

    def test_valid_base_hook(self, base_hook_data):
        """BaseHook accepts valid data."""
        hook = BaseHook.model_validate(base_hook_data)
        assert hook.session_id == "sess_abc123"
        assert hook.transcript_path == "/tmp/transcript.jsonl"
        assert hook.cwd == "/home/user/project"
        assert hook.permission_mode == "default"

    def test_missing_required_field(self, base_hook_data):
        """BaseHook rejects missing required fields."""
        del base_hook_data["session_id"]
        with pytest.raises(ValidationError) as exc_info:
            BaseHook.model_validate(base_hook_data)
        assert "session_id" in str(exc_info.value)

    @pytest.mark.parametrize("field", [
        "session_id",
        "transcript_path",
        "cwd",
        "permission_mode",
        "hook_event_name",
    ])
    def test_required_fields(self, base_hook_data, field):
        """Each base field is required."""
        del base_hook_data[field]
        with pytest.raises(ValidationError):
            BaseHook.model_validate(base_hook_data)

    def test_extra_fields_allowed(self, base_hook_data):
        """BaseHook accepts unknown fields (forward compatibility)."""
        base_hook_data["future_field"] = "future_value"
        base_hook_data["another_new_field"] = {"nested": "data"}
        hook = BaseHook.model_validate(base_hook_data)
        assert hook.future_field == "future_value"
        assert hook.another_new_field == {"nested": "data"}

    @pytest.mark.parametrize("permission_mode", [
        "default",
        "plan",
        "acceptEdits",
        "dontAsk",
        "bypassPermissions",
    ])
    def test_permission_modes(self, base_hook_data, permission_mode):
        """All permission modes are accepted."""
        base_hook_data["permission_mode"] = permission_mode
        hook = BaseHook.model_validate(base_hook_data)
        assert hook.permission_mode == permission_mode


# =============================================================================
# 2. Individual Hook Type Tests (Parametrized)
# =============================================================================

class TestHookTypes:
    """Parametrized tests for all hook types."""

    @pytest.mark.parametrize("hook_name,hook_class", list(HOOK_TYPE_MAP.items()))
    def test_hook_type_validation(self, hook_name: str, hook_class: Type[BaseHook]):
        """Each hook type validates its specific data correctly."""
        data = make_full_hook_data(hook_name)
        hook = hook_class.model_validate(data)
        assert hook.hook_event_name == hook_name

    @pytest.mark.parametrize("hook_name,hook_class", list(HOOK_TYPE_MAP.items()))
    def test_hook_type_inherits_base_fields(self, hook_name: str, hook_class: Type[BaseHook]):
        """Each hook type has all base fields."""
        data = make_full_hook_data(hook_name)
        hook = hook_class.model_validate(data)
        assert hasattr(hook, "session_id")
        assert hasattr(hook, "transcript_path")
        assert hasattr(hook, "cwd")
        assert hasattr(hook, "permission_mode")
        assert hasattr(hook, "hook_event_name")

    @pytest.mark.parametrize("hook_name,hook_class", list(HOOK_TYPE_MAP.items()))
    def test_hook_type_extra_fields_allowed(self, hook_name: str, hook_class: Type[BaseHook]):
        """Each hook type accepts unknown fields."""
        data = make_full_hook_data(hook_name)
        data["unknown_future_field"] = "some_value"
        hook = hook_class.model_validate(data)
        assert hook.unknown_future_field == "some_value"


# =============================================================================
# 3. Hook-Specific Field Tests
# =============================================================================

class TestPreToolUseHook:
    """Tests specific to PreToolUse hook."""

    def test_tool_input_dict(self, pre_tool_use_data):
        """tool_input accepts arbitrary dict."""
        hook = PreToolUseHook.model_validate(pre_tool_use_data)
        assert hook.tool_input == {"file_path": "/tmp/test.txt", "content": "hello"}

    def test_tool_input_empty(self, pre_tool_use_data):
        """tool_input can be empty."""
        pre_tool_use_data["tool_input"] = {}
        hook = PreToolUseHook.model_validate(pre_tool_use_data)
        assert hook.tool_input == {}

    def test_mcp_tool_name(self, pre_tool_use_data):
        """MCP tool names are accepted."""
        pre_tool_use_data["tool_name"] = "mcp__plane-project-task-manager__list_work_items"
        hook = PreToolUseHook.model_validate(pre_tool_use_data)
        assert "mcp__" in hook.tool_name


class TestPostToolUseHook:
    """Tests specific to PostToolUse hook."""

    def test_tool_response_string(self, post_tool_use_data):
        """tool_response is captured as string."""
        hook = PostToolUseHook.model_validate(post_tool_use_data)
        assert "drwxr-xr-x" in hook.tool_response

    def test_tool_response_error(self, post_tool_use_data):
        """tool_response can contain error messages."""
        post_tool_use_data["tool_response"] = "Error: Permission denied"
        hook = PostToolUseHook.model_validate(post_tool_use_data)
        assert "Error" in hook.tool_response


class TestSessionStartHook:
    """Tests specific to SessionStart hook."""

    @pytest.mark.parametrize("source", ["startup", "resume", "clear", "compact"])
    def test_valid_sources(self, session_start_data, source):
        """All source values are accepted."""
        session_start_data["source"] = source
        hook = SessionStartHook.model_validate(session_start_data)
        assert hook.source == source


class TestSessionEndHook:
    """Tests specific to SessionEnd hook."""

    @pytest.mark.parametrize("reason", ["prompt_input_exit", "clear", "logout", "other"])
    def test_valid_reasons(self, session_end_data, reason):
        """All reason values are accepted."""
        session_end_data["reason"] = reason
        hook = SessionEndHook.model_validate(session_end_data)
        assert hook.reason == reason


class TestPreCompactHook:
    """Tests specific to PreCompact hook."""

    @pytest.mark.parametrize("trigger", ["auto", "manual"])
    def test_valid_triggers(self, pre_compact_data, trigger):
        """Both trigger values are accepted."""
        pre_compact_data["trigger"] = trigger
        hook = PreCompactHook.model_validate(pre_compact_data)
        assert hook.trigger == trigger

    def test_custom_instructions_optional(self, pre_compact_data):
        """custom_instructions defaults to empty string."""
        del pre_compact_data["custom_instructions"]
        hook = PreCompactHook.model_validate(pre_compact_data)
        assert hook.custom_instructions == ""

    def test_custom_instructions_with_content(self, pre_compact_data):
        """custom_instructions accepts text."""
        pre_compact_data["custom_instructions"] = "Preserve all API endpoints"
        hook = PreCompactHook.model_validate(pre_compact_data)
        assert "API endpoints" in hook.custom_instructions


class TestStopHook:
    """Tests specific to Stop hook."""

    @pytest.mark.parametrize("active", [True, False])
    def test_stop_hook_active_boolean(self, stop_data, active):
        """stop_hook_active is boolean."""
        stop_data["stop_hook_active"] = active
        hook = StopHook.model_validate(stop_data)
        assert hook.stop_hook_active is active


class TestNotificationHook:
    """Tests specific to Notification hook."""

    @pytest.mark.parametrize("notification_type", [
        "permission_prompt",
        "idle_prompt",
        "auth_success",
        "elicitation_dialog",
    ])
    def test_notification_types(self, notification_data, notification_type):
        """All notification types are accepted."""
        notification_data["notification_type"] = notification_type
        hook = NotificationHook.model_validate(notification_data)
        assert hook.notification_type == notification_type


# =============================================================================
# 3b. New Hook Type Tests (v2.1.83 - v2.1.92)
# =============================================================================

class TestInstructionsLoadedHook:
    """Tests specific to InstructionsLoaded hook."""

    def test_basic_instantiation(self, instructions_loaded_data):
        """All required fields produce a valid hook."""
        hook = InstructionsLoadedHook.model_validate(instructions_loaded_data)
        assert hook.file_path == "/Users/me/repo/CLAUDE.md"
        assert hook.memory_type == "project"
        assert hook.load_reason == "startup"
        assert hook.globs == []
        assert hook.trigger_file_path is None
        assert hook.parent_file_path is None

    def test_round_trip_via_parser(self, instructions_loaded_data):
        """Hook round-trips through parse_hook_event."""
        hook = parse_hook_event(instructions_loaded_data)
        assert isinstance(hook, InstructionsLoadedHook)
        assert hook.hook_event_name == "InstructionsLoaded"

    def test_extra_fields_preserved(self, instructions_loaded_data):
        """Unknown fields are preserved (forward compat)."""
        instructions_loaded_data["future_field"] = {"x": 1}
        hook = InstructionsLoadedHook.model_validate(instructions_loaded_data)
        assert hook.future_field == {"x": 1}

    def test_with_imports(self, instructions_loaded_data):
        """Imported CLAUDE.md files include trigger/parent paths."""
        instructions_loaded_data["load_reason"] = "import"
        instructions_loaded_data["trigger_file_path"] = "/Users/me/repo/CLAUDE.md"
        instructions_loaded_data["parent_file_path"] = "/Users/me/repo/CLAUDE.md"
        hook = InstructionsLoadedHook.model_validate(instructions_loaded_data)
        assert hook.load_reason == "import"
        assert hook.trigger_file_path == "/Users/me/repo/CLAUDE.md"


class TestPermissionDeniedHook:
    """Tests specific to PermissionDenied hook."""

    def test_basic_instantiation(self, permission_denied_data):
        """All required fields produce a valid hook."""
        hook = PermissionDeniedHook.model_validate(permission_denied_data)
        assert hook.tool_name == "Bash"
        assert hook.tool_use_id == "tool_denied_001"
        assert "dangerous" in hook.reason
        assert hook.tool_input["command"] == "rm -rf /"

    def test_round_trip_via_parser(self, permission_denied_data):
        """Hook round-trips through parse_hook_event."""
        hook = parse_hook_event(permission_denied_data)
        assert isinstance(hook, PermissionDeniedHook)
        assert hook.hook_event_name == "PermissionDenied"

    def test_extra_fields_preserved(self, permission_denied_data):
        """Unknown fields are preserved (forward compat)."""
        permission_denied_data["denial_id"] = "den_xyz"
        hook = PermissionDeniedHook.model_validate(permission_denied_data)
        assert hook.denial_id == "den_xyz"


class TestElicitationHook:
    """Tests specific to Elicitation hook."""

    def test_basic_instantiation(self, elicitation_data):
        """All required fields produce a valid hook."""
        hook = ElicitationHook.model_validate(elicitation_data)
        assert hook.mcp_server == "github"
        assert hook.tool_name == "create_issue"
        assert hook.request == {"title": "string", "body": "string"}

    def test_round_trip_via_parser(self, elicitation_data):
        """Hook round-trips through parse_hook_event."""
        hook = parse_hook_event(elicitation_data)
        assert isinstance(hook, ElicitationHook)
        assert hook.hook_event_name == "Elicitation"

    def test_extra_fields_preserved(self, elicitation_data):
        """Unknown fields are preserved (forward compat)."""
        elicitation_data["request_id"] = "elicit_123"
        hook = ElicitationHook.model_validate(elicitation_data)
        assert hook.request_id == "elicit_123"


class TestElicitationResultHook:
    """Tests specific to ElicitationResult hook."""

    def test_basic_instantiation(self, elicitation_result_data):
        """All required fields produce a valid hook."""
        hook = ElicitationResultHook.model_validate(elicitation_result_data)
        assert hook.mcp_server == "github"
        assert hook.user_response["title"] == "Bug report"

    def test_round_trip_via_parser(self, elicitation_result_data):
        """Hook round-trips through parse_hook_event."""
        hook = parse_hook_event(elicitation_result_data)
        assert isinstance(hook, ElicitationResultHook)
        assert hook.hook_event_name == "ElicitationResult"

    def test_extra_fields_preserved(self, elicitation_result_data):
        """Unknown fields are preserved (forward compat)."""
        elicitation_result_data["request_id"] = "elicit_456"
        hook = ElicitationResultHook.model_validate(elicitation_result_data)
        assert hook.request_id == "elicit_456"


class TestCwdChangedHook:
    """Tests specific to CwdChanged hook."""

    def test_basic_instantiation(self, cwd_changed_data):
        """All required fields produce a valid hook."""
        hook = CwdChangedHook.model_validate(cwd_changed_data)
        assert hook.old_cwd == "/Users/me/old_project"
        assert hook.new_cwd == "/Users/me/new_project"

    def test_round_trip_via_parser(self, cwd_changed_data):
        """Hook round-trips through parse_hook_event."""
        hook = parse_hook_event(cwd_changed_data)
        assert isinstance(hook, CwdChangedHook)
        assert hook.hook_event_name == "CwdChanged"

    def test_extra_fields_preserved(self, cwd_changed_data):
        """Unknown fields are preserved (forward compat)."""
        cwd_changed_data["change_source"] = "cd_command"
        hook = CwdChangedHook.model_validate(cwd_changed_data)
        assert hook.change_source == "cd_command"


class TestFileChangedHook:
    """Tests specific to FileChanged hook."""

    def test_basic_instantiation(self, file_changed_data):
        """All required fields produce a valid hook."""
        hook = FileChangedHook.model_validate(file_changed_data)
        assert hook.file_path == "/Users/me/project/src/main.py"
        assert hook.file_name == "main.py"

    def test_round_trip_via_parser(self, file_changed_data):
        """Hook round-trips through parse_hook_event."""
        hook = parse_hook_event(file_changed_data)
        assert isinstance(hook, FileChangedHook)
        assert hook.hook_event_name == "FileChanged"

    def test_extra_fields_preserved(self, file_changed_data):
        """Unknown fields are preserved (forward compat)."""
        file_changed_data["change_type"] = "modified"
        hook = FileChangedHook.model_validate(file_changed_data)
        assert hook.change_type == "modified"


class TestTaskCreatedHook:
    """Tests specific to TaskCreated hook."""

    def test_basic_instantiation(self, task_created_data):
        """All required fields produce a valid hook."""
        hook = TaskCreatedHook.model_validate(task_created_data)
        assert hook.task_id == "task_001"
        assert hook.task_subject == "Refactor auth module"
        assert hook.team_name == "core-team"
        assert hook.teammate_name == "Alice"

    def test_round_trip_via_parser(self, task_created_data):
        """Hook round-trips through parse_hook_event."""
        hook = parse_hook_event(task_created_data)
        assert isinstance(hook, TaskCreatedHook)
        assert hook.hook_event_name == "TaskCreated"

    def test_extra_fields_preserved(self, task_created_data):
        """Unknown fields are preserved (forward compat)."""
        task_created_data["priority"] = "high"
        hook = TaskCreatedHook.model_validate(task_created_data)
        assert hook.priority == "high"

    def test_optional_fields_default_none(self, task_created_data):
        """Optional fields default to None when omitted."""
        del task_created_data["task_description"]
        del task_created_data["teammate_name"]
        hook = TaskCreatedHook.model_validate(task_created_data)
        assert hook.task_description is None
        assert hook.teammate_name is None


class TestTaskCompletedHook:
    """Tests specific to TaskCompleted hook."""

    def test_basic_instantiation(self, task_completed_data):
        """All required fields produce a valid hook."""
        hook = TaskCompletedHook.model_validate(task_completed_data)
        assert hook.task_id == "task_002"
        assert hook.task_subject == "Add tests"
        assert hook.team_name == "core-team"

    def test_round_trip_via_parser(self, task_completed_data):
        """Hook round-trips through parse_hook_event."""
        hook = parse_hook_event(task_completed_data)
        assert isinstance(hook, TaskCompletedHook)
        assert hook.hook_event_name == "TaskCompleted"

    def test_extra_fields_preserved(self, task_completed_data):
        """Unknown fields are preserved (forward compat)."""
        task_completed_data["completion_time_ms"] = 12345
        hook = TaskCompletedHook.model_validate(task_completed_data)
        assert hook.completion_time_ms == 12345


class TestTeammateIdleHook:
    """Tests specific to TeammateIdle hook."""

    def test_basic_instantiation(self, teammate_idle_data):
        """All required fields produce a valid hook."""
        hook = TeammateIdleHook.model_validate(teammate_idle_data)
        assert hook.agent_id == "agent_idle_001"
        assert hook.agent_type == "Explore"
        assert hook.team_name == "core-team"

    def test_round_trip_via_parser(self, teammate_idle_data):
        """Hook round-trips through parse_hook_event."""
        hook = parse_hook_event(teammate_idle_data)
        assert isinstance(hook, TeammateIdleHook)
        assert hook.hook_event_name == "TeammateIdle"

    def test_extra_fields_preserved(self, teammate_idle_data):
        """Unknown fields are preserved (forward compat)."""
        teammate_idle_data["idle_seconds"] = 30
        hook = TeammateIdleHook.model_validate(teammate_idle_data)
        assert hook.idle_seconds == 30

    def test_optional_team_name(self, teammate_idle_data):
        """team_name is optional."""
        del teammate_idle_data["team_name"]
        hook = TeammateIdleHook.model_validate(teammate_idle_data)
        assert hook.team_name is None


class TestWorktreeCreateHook:
    """Tests specific to WorktreeCreate hook."""

    def test_basic_instantiation(self, worktree_create_data):
        """All required fields produce a valid hook."""
        hook = WorktreeCreateHook.model_validate(worktree_create_data)
        assert hook.worktree_name == "feat-auth"
        assert hook.base_ref == "main"

    def test_round_trip_via_parser(self, worktree_create_data):
        """Hook round-trips through parse_hook_event."""
        hook = parse_hook_event(worktree_create_data)
        assert isinstance(hook, WorktreeCreateHook)
        assert hook.hook_event_name == "WorktreeCreate"

    def test_extra_fields_preserved(self, worktree_create_data):
        """Unknown fields are preserved (forward compat)."""
        worktree_create_data["requested_path"] = "/tmp/wt"
        hook = WorktreeCreateHook.model_validate(worktree_create_data)
        assert hook.requested_path == "/tmp/wt"


class TestWorktreeRemoveHook:
    """Tests specific to WorktreeRemove hook."""

    def test_basic_instantiation(self, worktree_remove_data):
        """All required fields produce a valid hook."""
        hook = WorktreeRemoveHook.model_validate(worktree_remove_data)
        assert hook.worktree_path == "/Users/me/.claude-worktrees/repo/feat-auth"
        assert hook.worktree_name == "feat-auth"

    def test_round_trip_via_parser(self, worktree_remove_data):
        """Hook round-trips through parse_hook_event."""
        hook = parse_hook_event(worktree_remove_data)
        assert isinstance(hook, WorktreeRemoveHook)
        assert hook.hook_event_name == "WorktreeRemove"

    def test_extra_fields_preserved(self, worktree_remove_data):
        """Unknown fields are preserved (forward compat)."""
        worktree_remove_data["removed_at"] = "2026-04-06T12:00:00Z"
        hook = WorktreeRemoveHook.model_validate(worktree_remove_data)
        assert hook.removed_at == "2026-04-06T12:00:00Z"


# =============================================================================
# 4. Parser Function Tests
# =============================================================================

class TestParseHookEvent:
    """Tests for the parse_hook_event dispatcher function."""

    @pytest.mark.parametrize("hook_name,expected_class", list(HOOK_TYPE_MAP.items()))
    def test_dispatches_to_correct_class(self, hook_name: str, expected_class: Type[BaseHook]):
        """Parser returns correct class type for each hook."""
        data = make_full_hook_data(hook_name)
        hook = parse_hook_event(data)
        assert isinstance(hook, expected_class)
        assert type(hook).__name__ == expected_class.__name__

    def test_missing_hook_event_name(self, base_hook_data):
        """Parser raises ValueError for missing hook_event_name."""
        del base_hook_data["hook_event_name"]
        with pytest.raises(ValueError, match="Missing 'hook_event_name'"):
            parse_hook_event(base_hook_data)

    def test_unknown_hook_type_falls_back(self, base_hook_data):
        """Unknown hook types fall back to BaseHook."""
        base_hook_data["hook_event_name"] = "FutureHookType"
        hook = parse_hook_event(base_hook_data)
        assert isinstance(hook, BaseHook)
        assert hook.hook_event_name == "FutureHookType"

    def test_parser_preserves_extra_fields(self, pre_tool_use_data):
        """Parser preserves unknown fields in result."""
        pre_tool_use_data["new_field_2025"] = {"data": "value"}
        hook = parse_hook_event(pre_tool_use_data)
        assert hook.new_field_2025 == {"data": "value"}


# =============================================================================
# 5. Forward Compatibility Tests
# =============================================================================

class TestForwardCompatibility:
    """Tests ensuring models handle future schema changes gracefully."""

    def test_new_base_field(self, pre_tool_use_data):
        """New fields in base schema are preserved."""
        pre_tool_use_data["model_version"] = "claude-3.5"
        pre_tool_use_data["api_version"] = "2025-01"
        hook = parse_hook_event(pre_tool_use_data)
        assert hook.model_version == "claude-3.5"
        assert hook.api_version == "2025-01"

    def test_new_hook_specific_field(self, pre_tool_use_data):
        """New hook-specific fields are preserved."""
        pre_tool_use_data["tool_metadata"] = {
            "execution_time_ms": 150,
            "retry_count": 0,
        }
        hook = parse_hook_event(pre_tool_use_data)
        assert hook.tool_metadata["execution_time_ms"] == 150

    def test_nested_extra_fields(self, post_tool_use_data):
        """Deeply nested unknown structures are preserved."""
        post_tool_use_data["metrics"] = {
            "timing": {
                "start": "2025-01-01T00:00:00Z",
                "end": "2025-01-01T00:00:01Z",
            },
            "resources": {
                "memory_mb": 128,
                "cpu_percent": 15.5,
            },
        }
        hook = parse_hook_event(post_tool_use_data)
        assert hook.metrics["timing"]["start"] == "2025-01-01T00:00:00Z"
        assert hook.metrics["resources"]["memory_mb"] == 128

    def test_new_enum_value_in_source(self, session_start_data):
        """New enum values should be handled (string type allows it)."""
        session_start_data["source"] = "hot_reload"  # Hypothetical future value
        # This will fail validation due to Literal type
        # This test documents the current behavior
        with pytest.raises(ValidationError):
            SessionStartHook.model_validate(session_start_data)


# =============================================================================
# 6. Output Model Tests
# =============================================================================

class TestHookOutputModels:
    """Tests for hook output/response models."""

    def test_pre_tool_use_output_allow(self):
        """PreToolUseOutput with allow decision."""
        output = PreToolUseOutput.model_validate({
            "hookSpecificOutput": {
                "permissionDecision": "allow",
                "permissionDecisionReason": "Trusted directory",
            }
        })
        assert output.hook_specific_output.permission_decision == "allow"

    def test_pre_tool_use_output_deny(self):
        """PreToolUseOutput with deny decision."""
        output = PreToolUseOutput.model_validate({
            "hookSpecificOutput": {
                "permissionDecision": "deny",
                "permissionDecisionReason": "Sensitive file",
            }
        })
        assert output.hook_specific_output.permission_decision == "deny"

    def test_pre_tool_use_output_modified_input(self):
        """PreToolUseOutput with modified input."""
        output = PreToolUseOutput.model_validate({
            "hookSpecificOutput": {
                "updatedInput": {
                    "file_path": "/tmp/safe_location.txt",
                    "content": "sanitized content",
                },
            }
        })
        assert output.hook_specific_output.updated_input["file_path"] == "/tmp/safe_location.txt"

    def test_stop_output_continue(self):
        """StopOutput with continue decision."""
        output = StopOutput.model_validate({
            "hookSpecificOutput": {
                "decision": "continue",
                "reason": "Task not complete",
            }
        })
        assert output.hook_specific_output.decision == "continue"

    def test_stop_output_stop(self):
        """StopOutput with stop decision."""
        output = StopOutput.model_validate({
            "hookSpecificOutput": {
                "decision": "stop",
                "reason": "All tasks done",
            }
        })
        assert output.hook_specific_output.decision == "stop"

    def test_permission_request_output(self):
        """PermissionRequestOutput validation."""
        output = PermissionRequestOutput.model_validate({
            "hookSpecificOutput": {
                "permissionDecision": "allow",
                "permissionDecisionReason": "Auto-approved by policy",
            }
        })
        assert output.hook_specific_output.permission_decision == "allow"

    def test_output_extra_fields(self):
        """Output models accept extra fields."""
        output = StopOutput.model_validate({
            "hookSpecificOutput": {
                "decision": "continue",
                "future_field": "future_value",
            }
        })
        assert output.hook_specific_output.future_field == "future_value"

    def test_pre_tool_use_output_defer(self):
        """PreToolUseOutput supports the new 'defer' decision (headless -p --resume)."""
        output = PreToolUseOutput.model_validate({
            "hookSpecificOutput": {
                "permissionDecision": "defer",
                "permissionDecisionReason": "Awaiting headless resume",
            }
        })
        assert output.hook_specific_output.permission_decision == "defer"

    def test_pre_tool_use_output_ask(self):
        """PreToolUseOutput supports the 'ask' decision."""
        output = PreToolUseOutput.model_validate({
            "hookSpecificOutput": {
                "permissionDecision": "ask",
            }
        })
        assert output.hook_specific_output.permission_decision == "ask"

    def test_permission_denied_output_default(self):
        """PermissionDeniedOutput defaults retry to False."""
        output = PermissionDeniedOutput.model_validate({
            "hookSpecificOutput": {}
        })
        assert output.hook_specific_output.retry is False

    def test_permission_denied_output_retry(self):
        """PermissionDeniedOutput can request retry."""
        output = PermissionDeniedOutput.model_validate({
            "hookSpecificOutput": {
                "retry": True,
            }
        })
        assert output.hook_specific_output.retry is True

    def test_permission_denied_output_extra_fields(self):
        """PermissionDeniedOutput accepts extra fields."""
        output = PermissionDeniedOutput.model_validate({
            "hookSpecificOutput": {
                "retry": True,
                "future_field": "value",
            }
        })
        assert output.hook_specific_output.future_field == "value"


# =============================================================================
# 7. HOOK_TYPE_MAP Registry Tests
# =============================================================================

class TestHookTypeMap:
    """Tests for the HOOK_TYPE_MAP registry."""

    def test_all_hooks_registered(self):
        """All 24 hook types are in the registry."""
        expected_hooks = {
            "PreToolUse",
            "PostToolUse",
            "PostToolUseFailure",
            "UserPromptSubmit",
            "SessionStart",
            "SessionEnd",
            "Stop",
            "SubagentStart",
            "SubagentStop",
            "PreCompact",
            "PermissionRequest",
            "Notification",
            "Setup",
            # New in v2.1.83 - v2.1.92
            "InstructionsLoaded",
            "PermissionDenied",
            "Elicitation",
            "ElicitationResult",
            "CwdChanged",
            "FileChanged",
            "TaskCreated",
            "TaskCompleted",
            "TeammateIdle",
            "WorktreeCreate",
            "WorktreeRemove",
        }
        assert set(HOOK_TYPE_MAP.keys()) == expected_hooks
        assert len(HOOK_TYPE_MAP) == 24

    def test_registry_values_are_classes(self):
        """All registry values are BaseHook subclasses."""
        for hook_name, hook_class in HOOK_TYPE_MAP.items():
            assert issubclass(hook_class, BaseHook), f"{hook_name} is not a BaseHook subclass"

    def test_registry_class_names_match_keys(self):
        """Registry keys match class names (minus 'Hook' suffix)."""
        for hook_name, hook_class in HOOK_TYPE_MAP.items():
            expected_class_name = f"{hook_name}Hook"
            assert hook_class.__name__ == expected_class_name


# =============================================================================
# 8. Serialization Round-Trip Tests
# =============================================================================

class TestSerialization:
    """Tests for JSON serialization/deserialization round-trips."""

    @pytest.mark.parametrize("hook_name", list(HOOK_TYPE_MAP.keys()))
    def test_round_trip_json(self, hook_name: str):
        """Hook can be serialized to JSON and back."""
        data = make_full_hook_data(hook_name)
        hook = parse_hook_event(data)

        # Serialize to JSON
        json_str = hook.model_dump_json()

        # Deserialize back
        hook_class = HOOK_TYPE_MAP[hook_name]
        restored = hook_class.model_validate_json(json_str)

        assert restored.hook_event_name == hook.hook_event_name
        assert restored.session_id == hook.session_id

    @pytest.mark.parametrize("hook_name", list(HOOK_TYPE_MAP.keys()))
    def test_round_trip_dict(self, hook_name: str):
        """Hook can be converted to dict and back."""
        data = make_full_hook_data(hook_name)
        hook = parse_hook_event(data)

        # To dict
        hook_dict = hook.model_dump()

        # From dict
        hook_class = HOOK_TYPE_MAP[hook_name]
        restored = hook_class.model_validate(hook_dict)

        assert restored.hook_event_name == hook.hook_event_name


# =============================================================================
# Run Configuration
# =============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])

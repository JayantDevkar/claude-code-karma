"""
Pytest fixtures for Claude Code models tests.

Provides sample data structures matching Claude Code's local storage format.
"""

import sys
from pathlib import Path

# Add parent directory (api/) to sys.path so config module can be imported
sys.path.insert(0, str(Path(__file__).parent.parent))

import json
from typing import Any, Dict

import pytest

# =============================================================================
# Sample Data Fixtures
# =============================================================================


@pytest.fixture
def sample_user_message_data() -> Dict[str, Any]:
    """Sample user message data from session JSONL."""
    return {
        "parentUuid": None,
        "isSidechain": False,
        "userType": "external",
        "cwd": "/Users/test/project",
        "sessionId": "test-session-uuid",
        "version": "2.1.1",
        "gitBranch": "main",
        "type": "user",
        "message": {"role": "user", "content": "Help me understand this code"},
        "uuid": "user-msg-uuid-001",
        "timestamp": "2026-01-08T13:03:26.654Z",
        "thinkingMetadata": {"level": "high", "disabled": False, "triggers": []},
        "todos": [],
    }


@pytest.fixture
def sample_assistant_message_data() -> Dict[str, Any]:
    """Sample assistant message data from session JSONL."""
    return {
        "parentUuid": "user-msg-uuid-001",
        "isSidechain": False,
        "cwd": "/Users/test/project",
        "sessionId": "test-session-uuid",
        "version": "2.1.1",
        "gitBranch": "main",
        "type": "assistant",
        "message": {
            "model": "claude-opus-4-5-20251101",
            "id": "msg_test123",
            "type": "message",
            "role": "assistant",
            "content": [
                {"type": "thinking", "thinking": "Let me analyze this...", "signature": "sig123"},
                {"type": "text", "text": "I can help you with that."},
                {
                    "type": "tool_use",
                    "id": "toolu_01ABC",
                    "name": "Read",
                    "input": {"file_path": "/test/file.py"},
                },
            ],
            "stop_reason": "tool_use",
            "usage": {
                "input_tokens": 100,
                "cache_creation_input_tokens": 50000,
                "cache_read_input_tokens": 10000,
                "output_tokens": 500,
                "service_tier": "standard",
            },
        },
        "uuid": "assistant-msg-uuid-001",
        "timestamp": "2026-01-08T13:03:30.123Z",
        "requestId": "req_test123",
    }


@pytest.fixture
def sample_file_history_snapshot_data() -> Dict[str, Any]:
    """Sample file history snapshot data from session JSONL."""
    return {
        "type": "file-history-snapshot",
        "messageId": "snapshot-msg-uuid-001",
        "snapshot": {
            "messageId": "snapshot-msg-uuid-001",
            "trackedFileBackups": {"/test/file.py": "abc123@v1"},
            "timestamp": "2026-01-08T13:03:26.669Z",
        },
        "isSnapshotUpdate": False,
        "uuid": "snapshot-uuid-001",
        "timestamp": "2026-01-08T13:03:26.669Z",
    }


@pytest.fixture
def sample_subagent_message_data() -> Dict[str, Any]:
    """Sample subagent message data with isSidechain=True."""
    return {
        "parentUuid": "parent-uuid-001",
        "isSidechain": True,
        "agentId": "a5793c3",
        "slug": "eager-puzzling-fairy",
        "cwd": "/Users/test/project",
        "sessionId": "test-session-uuid",
        "version": "2.1.1",
        "gitBranch": "feature/branch",
        "type": "user",
        "message": {"role": "user", "content": "Subagent task content"},
        "uuid": "subagent-msg-uuid-001",
        "timestamp": "2026-01-08T14:00:00.000Z",
        "thinkingMetadata": {"level": "high", "disabled": False, "triggers": []},
        "todos": [],
    }


@pytest.fixture
def sample_usage_data() -> Dict[str, Any]:
    """Sample token usage data."""
    return {
        "input_tokens": 100,
        "output_tokens": 500,
        "cache_creation_input_tokens": 50000,
        "cache_read_input_tokens": 10000,
        "service_tier": "standard",
    }


@pytest.fixture
def sample_todo_data() -> list:
    """Sample todo list data."""
    return [
        {
            "content": "Explore codebase structure",
            "status": "completed",
            "activeForm": "Exploring codebase",
        },
        {
            "content": "Initialize feature",
            "status": "in_progress",
            "activeForm": "Initializing feature",
        },
        {"content": "Write tests", "status": "pending", "activeForm": "Writing tests"},
    ]


# =============================================================================
# Temporary Directory Fixtures
# =============================================================================


@pytest.fixture
def temp_claude_dir(tmp_path: Path) -> Path:
    """Create a temporary ~/.claude structure for testing."""
    claude_dir = tmp_path / ".claude"
    projects_dir = claude_dir / "projects"
    debug_dir = claude_dir / "debug"
    file_history_dir = claude_dir / "file-history"
    todos_dir = claude_dir / "todos"

    # Create directories
    projects_dir.mkdir(parents=True)
    debug_dir.mkdir(parents=True)
    file_history_dir.mkdir(parents=True)
    todos_dir.mkdir(parents=True)

    return claude_dir


@pytest.fixture
def temp_project_dir(temp_claude_dir: Path) -> Path:
    """Create a temporary project directory."""
    # Encode path: /Users/test/myproject -> -Users-test-myproject
    project_dir = temp_claude_dir / "projects" / "-Users-test-myproject"
    project_dir.mkdir(parents=True)
    return project_dir


@pytest.fixture
def sample_session_jsonl(
    temp_project_dir: Path,
    sample_file_history_snapshot_data: Dict[str, Any],
    sample_user_message_data: Dict[str, Any],
    sample_assistant_message_data: Dict[str, Any],
) -> Path:
    """Create a sample session JSONL file with test data."""
    session_uuid = "test-session-uuid"
    jsonl_path = temp_project_dir / f"{session_uuid}.jsonl"

    # Write sample messages
    with open(jsonl_path, "w") as f:
        f.write(json.dumps(sample_file_history_snapshot_data) + "\n")
        f.write(json.dumps(sample_user_message_data) + "\n")
        f.write(json.dumps(sample_assistant_message_data) + "\n")

    return jsonl_path


@pytest.fixture
def sample_session_with_subagents(
    temp_project_dir: Path,
    sample_session_jsonl: Path,
    sample_subagent_message_data: Dict[str, Any],
) -> Path:
    """Create a session with subagents directory."""
    session_uuid = "test-session-uuid"
    session_dir = temp_project_dir / session_uuid
    subagents_dir = session_dir / "subagents"
    subagents_dir.mkdir(parents=True)

    # Create a subagent file
    agent_jsonl = subagents_dir / "agent-a5793c3.jsonl"
    with open(agent_jsonl, "w") as f:
        f.write(json.dumps(sample_subagent_message_data) + "\n")

    return sample_session_jsonl


@pytest.fixture
def sample_session_with_tool_results(
    temp_project_dir: Path,
    sample_session_jsonl: Path,
) -> Path:
    """Create a session with tool-results directory."""
    session_uuid = "test-session-uuid"
    session_dir = temp_project_dir / session_uuid
    tool_results_dir = session_dir / "tool-results"
    tool_results_dir.mkdir(parents=True)

    # Create a tool result file
    tool_result = tool_results_dir / "toolu_01ABC.txt"
    tool_result.write_text("Sample tool output content")

    return sample_session_jsonl


@pytest.fixture
def sample_todos_file(temp_claude_dir: Path, sample_todo_data: list) -> Path:
    """Create a sample todos JSON file."""
    todos_dir = temp_claude_dir / "todos"
    todo_file = todos_dir / "test-session-uuid-agent-test-session-uuid.json"

    with open(todo_file, "w") as f:
        json.dump(sample_todo_data, f)

    return todo_file


@pytest.fixture
def sample_debug_log(temp_claude_dir: Path) -> Path:
    """Create a sample debug log file."""
    debug_dir = temp_claude_dir / "debug"
    debug_file = debug_dir / "test-session-uuid.txt"

    debug_content = """2026-01-08T13:02:04.118Z [DEBUG] Watching for changes in setting files...
2026-01-08T13:02:04.125Z [DEBUG] [init] configureGlobalMTLS starting
2026-01-08T13:02:04.136Z [DEBUG] Applying permission update: Adding 3 allow rule(s)...
"""
    debug_file.write_text(debug_content)

    return debug_file


# =============================================================================
# Windows Path Fixtures
# =============================================================================


@pytest.fixture
def temp_windows_project_dir(temp_claude_dir: Path) -> Path:
    """Create a temporary Windows-encoded project directory (C--Users-test-myproject)."""
    project_dir = temp_claude_dir / "projects" / "C--Users-test-myproject"
    project_dir.mkdir(parents=True)
    return project_dir


@pytest.fixture
def sample_windows_session_jsonl(temp_windows_project_dir: Path) -> Path:
    """Create a session JSONL file with Windows-style cwd (backslashes)."""
    session_file = temp_windows_project_dir / "win-session-uuid.jsonl"
    session_file.write_text(
        json.dumps(
            {
                "cwd": "C:\\Users\\test\\myproject",
                "type": "user",
                "sessionId": "win-session-uuid",
                "message": {"role": "user", "content": "Hello from Windows"},
                "uuid": "win-msg-001",
                "timestamp": "2026-01-08T13:00:00.000Z",
            }
        )
        + "\n"
    )
    return session_file


@pytest.fixture
def sample_file_history(temp_claude_dir: Path) -> Path:
    """Create a sample file history directory."""
    file_history_dir = temp_claude_dir / "file-history" / "test-session-uuid"
    file_history_dir.mkdir(parents=True)

    # Create a backup file
    backup_file = file_history_dir / "abc123@v1"
    backup_file.write_text("Original file content before edit")

    return file_history_dir


@pytest.fixture
def standalone_agent_jsonl(
    temp_project_dir: Path,
    sample_user_message_data: Dict[str, Any],
    sample_assistant_message_data: Dict[str, Any],
) -> Path:
    """Create a standalone agent JSONL file."""
    agent_path = temp_project_dir / "agent-b1234ef.jsonl"

    # Modify messages to not be sidechain (standalone agent)
    user_msg = sample_user_message_data.copy()
    user_msg["isSidechain"] = False

    asst_msg = sample_assistant_message_data.copy()
    asst_msg["isSidechain"] = False

    with open(agent_path, "w") as f:
        f.write(json.dumps(user_msg) + "\n")
        f.write(json.dumps(asst_msg) + "\n")

    return agent_path


@pytest.fixture
def temp_git_repo(tmp_path: Path) -> Path:
    """Create a temporary git repository for testing."""
    import subprocess

    repo_dir = tmp_path / "test-repo"
    repo_dir.mkdir()

    # Initialize git repo
    subprocess.run(["git", "init"], cwd=repo_dir, check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "test@test.com"],
        cwd=repo_dir,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test"],
        cwd=repo_dir,
        check=True,
        capture_output=True,
    )

    # Create initial commit so repo is fully initialized
    (repo_dir / "README.md").write_text("# Test Repo")
    subprocess.run(["git", "add", "."], cwd=repo_dir, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "Initial commit"],
        cwd=repo_dir,
        check=True,
        capture_output=True,
    )

    return repo_dir


# =============================================================================
# Plan Fixtures
# =============================================================================


@pytest.fixture
def temp_plans_dir(temp_claude_dir: Path) -> Path:
    """Create a temporary plans directory in ~/.claude/plans/."""
    plans_dir = temp_claude_dir / "plans"
    plans_dir.mkdir(parents=True)
    return plans_dir


@pytest.fixture
def temp_karma_dir(tmp_path: Path) -> Path:
    """Create a temporary ~/.claude_karma directory for testing."""
    karma_dir = tmp_path / ".claude_karma"
    karma_dir.mkdir(parents=True)

    # Create subdirectories
    (karma_dir / "plan-annotations").mkdir()
    (karma_dir / "plan-decisions").mkdir()
    (karma_dir / "live-sessions").mkdir()

    return karma_dir


@pytest.fixture
def sample_plan_content() -> str:
    """Sample plan markdown content."""
    return """# Implement User Authentication

## Overview

Add user authentication to the application using JWT tokens.

## Steps

1. Create User model with email/password fields
2. Add login/register API endpoints
3. Implement JWT token generation
4. Add middleware for protected routes
5. Write tests for auth flows

## Technical Details

- Use bcrypt for password hashing
- JWT expiry: 24 hours
- Refresh tokens: 7 days
"""


@pytest.fixture
def sample_plan_file(temp_plans_dir: Path, sample_plan_content: str) -> Path:
    """Create a sample plan markdown file."""
    plan_path = temp_plans_dir / "test-plan-slug.md"
    plan_path.write_text(sample_plan_content)
    return plan_path


@pytest.fixture
def sample_annotation_data() -> Dict[str, Any]:
    """Sample annotation data for testing."""
    return {
        "id": "ann-uuid-001",
        "type": "REPLACEMENT",
        "original_text": "Use bcrypt for password hashing",
        "new_text": "Use argon2 for password hashing (more secure)",
        "comment": None,
        "created": "2026-01-24T10:00:00",
        "creator": "reviewer",
        "line_start": 15,
        "line_end": 15,
    }


@pytest.fixture
def sample_decision_data() -> Dict[str, Any]:
    """Sample decision data for testing."""
    return {
        "id": "dec-uuid-001",
        "type": "APPROVED",
        "feedback": "Looks good!",
        "created": "2026-01-24T11:00:00",
        "creator": "reviewer",
        "annotation_ids": [],
    }


@pytest.fixture
def sample_hook_event_exitplanmode() -> Dict[str, Any]:
    """Sample PermissionRequest hook event for ExitPlanMode."""
    return {
        "hook_event_name": "PermissionRequest",
        "session_id": "test-session-uuid",
        "transcript_path": "/Users/test/.claude/projects/-test/session.jsonl",
        "cwd": "/Users/test/project",
        "permission_mode": "plan",
        "tool_name": "ExitPlanMode",
        "tool_input": {
            "plan_path": "~/.claude/plans/test-plan-slug.md",
        },
    }


@pytest.fixture
def sample_hook_event_other_tool() -> Dict[str, Any]:
    """Sample PermissionRequest hook event for a non-ExitPlanMode tool."""
    return {
        "hook_event_name": "PermissionRequest",
        "session_id": "test-session-uuid",
        "transcript_path": "/Users/test/.claude/projects/-test/session.jsonl",
        "cwd": "/Users/test/project",
        "permission_mode": "default",
        "tool_name": "Write",
        "tool_input": {
            "file_path": "/Users/test/project/file.py",
            "content": "print('hello')",
        },
    }

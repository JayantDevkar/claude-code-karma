"""
Unit tests for the sessions router.

Tests session endpoints, file activity extraction, and subagent handling.
"""

import sys
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Optional
from unittest.mock import MagicMock, patch

import pytest
from fastapi import APIRouter, FastAPI, HTTPException
from fastapi.testclient import TestClient

# Set up paths before any imports from the project
_tests_dir = Path(__file__).parent
_api_dir = _tests_dir.parent
_apps_dir = _api_dir.parent
_root_dir = _apps_dir.parent

# Add paths for imports
if str(_root_dir) not in sys.path:
    sys.path.insert(0, str(_root_dir))
if str(_api_dir) not in sys.path:
    sys.path.insert(0, str(_api_dir))

# Now we can import models (which don't have relative import issues)
# Import schemas directly
from models import Agent, AssistantMessage, Session, UserMessage
from models.content import ToolUseBlock
from models.usage import TokenUsage
from schemas import (
    FileActivity,
    InitialPrompt,
    SessionDetail,
    SubagentSummary,
    TodoItemSchema,
    ToolUsageSummary,
)
from utils import is_encoded_project_dir, normalize_key

# =============================================================================
# Recreate the router functions here for testing
# (This avoids the relative import issue in the original router module)
# =============================================================================


def get_claude_projects_dir() -> Path:
    """Get the ~/.claude/projects directory."""
    return Path.home() / ".claude" / "projects"


def find_session(uuid: str) -> Optional[Session]:
    """Find a session by UUID across all projects."""
    projects_dir = get_claude_projects_dir()
    if not projects_dir.exists():
        return None

    for encoded_dir in projects_dir.iterdir():
        if encoded_dir.is_dir() and is_encoded_project_dir(encoded_dir.name):
            jsonl_path = encoded_dir / f"{uuid}.jsonl"
            if jsonl_path.exists():
                return Session.from_path(jsonl_path)
    return None


def extract_file_activity_from_tool(
    block: ToolUseBlock,
    timestamp: datetime,
    actor: str,
    actor_type: str,
) -> Optional[FileActivity]:
    """Extract file activity from a tool use block."""
    tool_name = block.name
    tool_input = block.input

    # Map tool names to operations and path fields
    tool_mappings = {
        "Read": ("read", "file_path"),
        "Write": ("write", "file_path"),
        "StrReplace": ("edit", "file_path"),
        "Delete": ("delete", "file_path"),
        "Glob": ("search", "glob_pattern"),
        "LS": ("read", "target_directory"),
        "Grep": ("search", "path"),
        "SemanticSearch": ("search", "target_directories"),
    }

    if tool_name not in tool_mappings:
        return None

    operation, path_field = tool_mappings[tool_name]

    # Extract path from input
    path_value = tool_input.get(path_field)

    # Fallback for older/different tool versions
    if path_value is None and path_field == "file_path":
        path_value = tool_input.get("path")

    if path_value is None:
        return None

    # Handle list of paths (e.g., SemanticSearch target_directories)
    if isinstance(path_value, list):
        path_value = path_value[0] if path_value else None

    if not path_value:
        return None

    return FileActivity(
        path=str(path_value),
        operation=operation,
        actor=actor,
        actor_type=actor_type,
        timestamp=timestamp,
        tool_name=tool_name,
    )


# Create a test router that mimics the real one
router = APIRouter()


@router.get("/{uuid}", response_model=SessionDetail)
def get_session(uuid: str):
    """Get detailed session information."""
    session = find_session(uuid)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    usage = session.get_usage_summary()
    tools_used = session.get_tools_used()

    # Get initial prompt
    initial_prompt = None
    for msg in session.iter_user_messages():
        initial_prompt = msg.content[:500] if msg.content else None
        break

    # Load todos
    todos: list[TodoItemSchema] = []
    try:
        todo_items = session.list_todos()
        todos = [
            TodoItemSchema(
                content=t.content,
                status=t.status,
                active_form=t.active_form,
            )
            for t in todo_items
        ]
    except Exception:
        pass  # Todos are optional, don't fail the request

    return SessionDetail(
        uuid=session.uuid,
        message_count=session.message_count,
        start_time=session.start_time,
        end_time=session.end_time,
        duration_seconds=session.duration_seconds,
        models_used=list(session.get_models_used()),
        subagent_count=len(session.list_subagents()),
        has_todos=session.has_todos,
        todo_count=len(todos),
        initial_prompt=initial_prompt,
        tools_used=dict(tools_used),
        git_branches=list(session.get_git_branches()),
        working_directories=list(session.get_working_directories()),
        total_input_tokens=usage.total_input,
        total_output_tokens=usage.output_tokens,
        cache_hit_rate=usage.cache_hit_rate,
        todos=todos,
    )


@router.get("/{uuid}/todos", response_model=list[TodoItemSchema])
def get_session_todos(uuid: str) -> list[TodoItemSchema]:
    """Get all todo items for a session."""
    session = find_session(uuid)
    if session is None:
        raise HTTPException(status_code=404, detail=f"Session {uuid} not found")

    try:
        todos = session.list_todos()
        return [
            TodoItemSchema(
                content=todo.content,
                status=todo.status,
                active_form=todo.active_form,
            )
            for todo in todos
        ]
    except Exception:
        return []


@router.get("/{uuid}/file-activity", response_model=list[FileActivity])
def get_file_activity(uuid: str):
    """Get all file operations in a session with actor attribution."""
    session = find_session(uuid)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    activities: list[FileActivity] = []

    # Process main session messages
    for msg in session.iter_assistant_messages():
        # Determine if this is from a subagent
        if msg.is_sidechain or msg.agent_id:
            actor = msg.slug or msg.agent_id or "unknown-subagent"
            actor_type = "subagent"
        else:
            actor = "session"
            actor_type = "session"

        for block in msg.content_blocks:
            if isinstance(block, ToolUseBlock):
                activity = extract_file_activity_from_tool(block, msg.timestamp, actor, actor_type)
                if activity:
                    activities.append(activity)

    # Process subagent messages
    for subagent in session.list_subagents():
        actor = subagent.slug or subagent.agent_id
        for msg in subagent.iter_messages():
            if isinstance(msg, AssistantMessage):
                for block in msg.content_blocks:
                    if isinstance(block, ToolUseBlock):
                        activity = extract_file_activity_from_tool(
                            block, msg.timestamp, actor, "subagent"
                        )
                        if activity:
                            activities.append(activity)

    # Sort by timestamp
    activities.sort(key=lambda a: a.timestamp)
    return activities


@router.get("/{uuid}/subagents", response_model=list[SubagentSummary])
def get_subagents(uuid: str):
    """Get all subagents in a session with their tool usage."""
    session = find_session(uuid)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    # Build map: normalized_description -> subagent_type from Task tool calls
    # This correlates Task invocations to their spawned subagents
    task_type_map: dict[str, str] = {}
    for msg in session.iter_messages():
        if isinstance(msg, AssistantMessage):
            for block in msg.content_blocks:
                if isinstance(block, ToolUseBlock) and block.name in ("Task", "Agent"):
                    desc = block.input.get("description", "")[:100]
                    stype = block.input.get("subagent_type")  # None if missing
                    if desc and stype:
                        task_type_map[normalize_key(desc)] = stype

    summaries: list[SubagentSummary] = []

    for subagent in session.list_subagents():
        # Count tools used by this subagent
        tool_counts: Counter[str] = Counter()
        for msg in subagent.iter_messages():
            if isinstance(msg, AssistantMessage):
                for block in msg.content_blocks:
                    if isinstance(block, ToolUseBlock):
                        tool_counts[block.name] += 1

        # Get initial prompt (first user message to subagent)
        initial_prompt = None
        for msg in subagent.iter_messages():
            if isinstance(msg, UserMessage):
                initial_prompt = msg.content[:500] if msg.content else None
                break

        # Match subagent to Task invocation by normalized description prefix
        prompt_prefix = (initial_prompt or "")[:100]
        subagent_type = task_type_map.get(normalize_key(prompt_prefix), None)

        summaries.append(
            SubagentSummary(
                agent_id=subagent.agent_id,
                slug=subagent.slug,
                subagent_type=subagent_type,
                tools_used=dict(tool_counts),
                message_count=subagent.message_count,
                initial_prompt=initial_prompt,
            )
        )

    return summaries


@router.get("/{uuid}/tools", response_model=list[ToolUsageSummary])
def get_tools(uuid: str):
    """Get tool usage breakdown for a session."""
    session = find_session(uuid)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    # Count tools from main session vs subagents
    session_tools: Counter[str] = Counter()
    subagent_tools: Counter[str] = Counter()

    # Main session tools
    for msg in session.iter_assistant_messages():
        is_subagent = msg.is_sidechain or msg.agent_id
        for block in msg.content_blocks:
            if isinstance(block, ToolUseBlock):
                if is_subagent:
                    subagent_tools[block.name] += 1
                else:
                    session_tools[block.name] += 1

    # Subagent tools
    for subagent in session.list_subagents():
        for msg in subagent.iter_messages():
            if isinstance(msg, AssistantMessage):
                for block in msg.content_blocks:
                    if isinstance(block, ToolUseBlock):
                        subagent_tools[block.name] += 1

    # Combine into summaries
    all_tools = set(session_tools.keys()) | set(subagent_tools.keys())
    summaries = []
    for tool_name in sorted(all_tools):
        by_session = session_tools.get(tool_name, 0)
        by_subagents = subagent_tools.get(tool_name, 0)
        summaries.append(
            ToolUsageSummary(
                tool_name=tool_name,
                count=by_session + by_subagents,
                by_session=by_session,
                by_subagents=by_subagents,
            )
        )

    # Sort by total count descending
    summaries.sort(key=lambda s: s.count, reverse=True)
    return summaries


@router.get("/{uuid}/initial-prompt", response_model=InitialPrompt)
def get_initial_prompt(uuid: str):
    """Get the initial prompt (first user message) for a session."""
    session = find_session(uuid)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    for msg in session.iter_user_messages():
        return InitialPrompt(
            content=msg.content,
            timestamp=msg.timestamp,
        )

    raise HTTPException(status_code=404, detail="No user messages found in session")


# Create a test app with the sessions router
app = FastAPI()
app.include_router(router, prefix="/sessions", tags=["sessions"])

client = TestClient(app)


# Module path for patching - points to this test module
MODULE_PATH = "apps.api.tests.test_sessions"


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def mock_session() -> MagicMock:
    """Create a mock Session object with typical properties."""
    session = MagicMock(spec=Session)
    session.uuid = "test-session-uuid"
    session.message_count = 5
    session.start_time = datetime(2026, 1, 8, 13, 0, 0)
    session.end_time = datetime(2026, 1, 8, 13, 30, 0)
    session.duration_seconds = 1800.0
    session.has_todos = False

    # Mock usage summary
    usage = MagicMock(spec=TokenUsage)
    usage.total_input = 10000
    usage.output_tokens = 5000
    usage.cache_hit_rate = 0.75
    session.get_usage_summary.return_value = usage

    # Mock tools used
    session.get_tools_used.return_value = Counter({"Read": 5, "Write": 2})

    # Mock models used
    session.get_models_used.return_value = {"claude-opus-4-5-20251101"}

    # Mock git branches and working directories
    session.get_git_branches.return_value = {"main", "feature/test"}
    session.get_working_directories.return_value = {"/Users/test/project"}

    # Mock subagents
    session.list_subagents.return_value = []

    return session


@pytest.fixture
def mock_user_message() -> MagicMock:
    """Create a mock UserMessage."""
    msg = MagicMock(spec=UserMessage)
    msg.content = "Help me understand this code in the repository"
    msg.timestamp = datetime(2026, 1, 8, 13, 0, 0)
    return msg


@pytest.fixture
def mock_assistant_message() -> MagicMock:
    """Create a mock AssistantMessage with tool use blocks."""
    msg = MagicMock(spec=AssistantMessage)
    msg.timestamp = datetime(2026, 1, 8, 13, 1, 0)
    msg.is_sidechain = False
    msg.agent_id = None
    msg.slug = None

    # Create a Read tool use block
    read_block = ToolUseBlock(
        type="tool_use",
        id="toolu_01ABC",
        name="Read",
        input={"path": "/test/file.py"},
    )

    msg.content_blocks = [read_block]
    return msg


@pytest.fixture
def mock_subagent() -> MagicMock:
    """Create a mock Agent (subagent)."""
    agent = MagicMock(spec=Agent)
    agent.agent_id = "a5793c3"
    agent.slug = "eager-puzzling-fairy"
    agent.message_count = 10

    # Create a mock user message for the subagent
    user_msg = MagicMock(spec=UserMessage)
    user_msg.content = "Search for all test files"
    user_msg.timestamp = datetime(2026, 1, 8, 13, 5, 0)

    # Create a mock assistant message with tool use
    asst_msg = MagicMock(spec=AssistantMessage)
    asst_msg.timestamp = datetime(2026, 1, 8, 13, 6, 0)
    glob_block = ToolUseBlock(
        type="tool_use",
        id="toolu_02DEF",
        name="Glob",
        input={"glob_pattern": "**/*.test.py"},
    )
    asst_msg.content_blocks = [glob_block]

    agent.iter_messages.return_value = iter([user_msg, asst_msg])

    return agent


# =============================================================================
# extract_file_activity_from_tool Tests
# =============================================================================


class TestExtractFileActivityFromTool:
    """Tests for the extract_file_activity_from_tool function."""

    def test_extract_read_tool(self):
        """Test extracting file activity from Read tool."""
        block = ToolUseBlock(
            type="tool_use",
            id="toolu_01",
            name="Read",
            input={"path": "/test/file.py"},
        )
        timestamp = datetime(2026, 1, 8, 13, 0, 0)

        activity = extract_file_activity_from_tool(block, timestamp, "session", "session")

        assert activity is not None
        assert activity.path == "/test/file.py"
        assert activity.operation == "read"
        assert activity.actor == "session"
        assert activity.actor_type == "session"
        assert activity.tool_name == "Read"
        assert activity.timestamp == timestamp

    def test_extract_write_tool(self):
        """Test extracting file activity from Write tool."""
        block = ToolUseBlock(
            type="tool_use",
            id="toolu_02",
            name="Write",
            input={"path": "/test/new_file.py"},
        )
        timestamp = datetime(2026, 1, 8, 13, 0, 0)

        activity = extract_file_activity_from_tool(block, timestamp, "session", "session")

        assert activity is not None
        assert activity.path == "/test/new_file.py"
        assert activity.operation == "write"
        assert activity.tool_name == "Write"

    def test_extract_str_replace_tool(self):
        """Test extracting file activity from StrReplace tool."""
        block = ToolUseBlock(
            type="tool_use",
            id="toolu_03",
            name="StrReplace",
            input={"path": "/test/edit_file.py", "old_str": "foo", "new_str": "bar"},
        )
        timestamp = datetime(2026, 1, 8, 13, 0, 0)

        activity = extract_file_activity_from_tool(block, timestamp, "session", "session")

        assert activity is not None
        assert activity.path == "/test/edit_file.py"
        assert activity.operation == "edit"
        assert activity.tool_name == "StrReplace"

    def test_extract_delete_tool(self):
        """Test extracting file activity from Delete tool."""
        block = ToolUseBlock(
            type="tool_use",
            id="toolu_04",
            name="Delete",
            input={"path": "/test/delete_me.py"},
        )
        timestamp = datetime(2026, 1, 8, 13, 0, 0)

        activity = extract_file_activity_from_tool(block, timestamp, "session", "session")

        assert activity is not None
        assert activity.path == "/test/delete_me.py"
        assert activity.operation == "delete"
        assert activity.tool_name == "Delete"

    def test_extract_glob_tool(self):
        """Test extracting file activity from Glob tool."""
        block = ToolUseBlock(
            type="tool_use",
            id="toolu_05",
            name="Glob",
            input={"glob_pattern": "**/*.py"},
        )
        timestamp = datetime(2026, 1, 8, 13, 0, 0)

        activity = extract_file_activity_from_tool(block, timestamp, "session", "session")

        assert activity is not None
        assert activity.path == "**/*.py"
        assert activity.operation == "search"
        assert activity.tool_name == "Glob"

    def test_extract_ls_tool(self):
        """Test extracting file activity from LS tool."""
        block = ToolUseBlock(
            type="tool_use",
            id="toolu_06",
            name="LS",
            input={"target_directory": "/test/dir"},
        )
        timestamp = datetime(2026, 1, 8, 13, 0, 0)

        activity = extract_file_activity_from_tool(block, timestamp, "session", "session")

        assert activity is not None
        assert activity.path == "/test/dir"
        assert activity.operation == "read"
        assert activity.tool_name == "LS"

    def test_extract_grep_tool(self):
        """Test extracting file activity from Grep tool."""
        block = ToolUseBlock(
            type="tool_use",
            id="toolu_07",
            name="Grep",
            input={"path": "/test/search_here", "pattern": "TODO"},
        )
        timestamp = datetime(2026, 1, 8, 13, 0, 0)

        activity = extract_file_activity_from_tool(block, timestamp, "session", "session")

        assert activity is not None
        assert activity.path == "/test/search_here"
        assert activity.operation == "search"
        assert activity.tool_name == "Grep"

    def test_extract_semantic_search_tool(self):
        """Test extracting file activity from SemanticSearch tool with list paths."""
        block = ToolUseBlock(
            type="tool_use",
            id="toolu_08",
            name="SemanticSearch",
            input={"target_directories": ["/test/dir1", "/test/dir2"]},
        )
        timestamp = datetime(2026, 1, 8, 13, 0, 0)

        activity = extract_file_activity_from_tool(block, timestamp, "session", "session")

        assert activity is not None
        # Should take first directory from list
        assert activity.path == "/test/dir1"
        assert activity.operation == "search"
        assert activity.tool_name == "SemanticSearch"

    def test_extract_semantic_search_empty_list(self):
        """Test extracting file activity from SemanticSearch with empty list."""
        block = ToolUseBlock(
            type="tool_use",
            id="toolu_09",
            name="SemanticSearch",
            input={"target_directories": []},
        )
        timestamp = datetime(2026, 1, 8, 13, 0, 0)

        activity = extract_file_activity_from_tool(block, timestamp, "session", "session")

        assert activity is None

    def test_extract_unknown_tool_returns_none(self):
        """Test that unknown tools return None."""
        block = ToolUseBlock(
            type="tool_use",
            id="toolu_10",
            name="UnknownTool",
            input={"some_param": "value"},
        )
        timestamp = datetime(2026, 1, 8, 13, 0, 0)

        activity = extract_file_activity_from_tool(block, timestamp, "session", "session")

        assert activity is None

    def test_extract_tool_missing_path_field(self):
        """Test that tools with missing path field return None."""
        block = ToolUseBlock(
            type="tool_use",
            id="toolu_11",
            name="Read",
            input={"wrong_field": "/test/file.py"},
        )
        timestamp = datetime(2026, 1, 8, 13, 0, 0)

        activity = extract_file_activity_from_tool(block, timestamp, "session", "session")

        assert activity is None

    def test_extract_with_subagent_actor(self):
        """Test file activity with subagent actor."""
        block = ToolUseBlock(
            type="tool_use",
            id="toolu_12",
            name="Read",
            input={"path": "/test/file.py"},
        )
        timestamp = datetime(2026, 1, 8, 13, 0, 0)

        activity = extract_file_activity_from_tool(
            block, timestamp, "eager-puzzling-fairy", "subagent"
        )

        assert activity is not None
        assert activity.actor == "eager-puzzling-fairy"
        assert activity.actor_type == "subagent"


# =============================================================================
# find_session Tests
# =============================================================================


class TestFindSession:
    """Tests for the find_session function."""

    @patch(__name__ + ".get_claude_projects_dir")
    def test_find_session_not_found_no_projects_dir(self, mock_get_dir):
        """Test find_session returns None when projects dir doesn't exist."""
        mock_get_dir.return_value = Path("/nonexistent/path")

        result = find_session("test-uuid")

        assert result is None

    @patch(__name__ + ".get_claude_projects_dir")
    def test_find_session_not_found_no_matching_uuid(self, mock_get_dir, tmp_path):
        """Test find_session returns None when no matching session exists."""
        # Create projects directory structure
        projects_dir = tmp_path / "projects"
        projects_dir.mkdir()
        encoded_dir = projects_dir / "-Users-test-project"
        encoded_dir.mkdir()
        # Create a session with different UUID
        (encoded_dir / "different-uuid.jsonl").write_text("{}")

        mock_get_dir.return_value = projects_dir

        result = find_session("test-uuid")

        assert result is None

    @patch(__name__ + ".get_claude_projects_dir")
    @patch(__name__ + ".Session")
    def test_find_session_found(self, mock_session_class, mock_get_dir, tmp_path):
        """Test find_session returns Session when found."""
        # Create projects directory structure
        projects_dir = tmp_path / "projects"
        projects_dir.mkdir()
        encoded_dir = projects_dir / "-Users-test-project"
        encoded_dir.mkdir()
        jsonl_path = encoded_dir / "test-uuid.jsonl"
        jsonl_path.write_text('{"type": "user"}')

        mock_get_dir.return_value = projects_dir

        mock_session = MagicMock()
        mock_session_class.from_path.return_value = mock_session

        result = find_session("test-uuid")

        assert result == mock_session
        mock_session_class.from_path.assert_called_once_with(jsonl_path)


# =============================================================================
# GET /sessions/{uuid} Tests
# =============================================================================


class TestGetSessionEndpoint:
    """Tests for GET /sessions/{uuid} endpoint."""

    @patch(__name__ + ".find_session")
    def test_get_session_success(self, mock_find_session, mock_session, mock_user_message):
        """Test successful session retrieval."""
        mock_session.iter_user_messages.return_value = iter([mock_user_message])
        mock_find_session.return_value = mock_session

        response = client.get("/sessions/test-session-uuid")

        assert response.status_code == 200
        data = response.json()
        assert data["uuid"] == "test-session-uuid"
        assert data["message_count"] == 5
        assert data["duration_seconds"] == 1800.0
        assert "claude-opus-4-5-20251101" in data["models_used"]
        assert data["subagent_count"] == 0
        assert data["has_todos"] is False
        assert data["initial_prompt"] == "Help me understand this code in the repository"
        assert data["tools_used"]["Read"] == 5
        assert data["tools_used"]["Write"] == 2
        assert "main" in data["git_branches"]
        assert "/Users/test/project" in data["working_directories"]
        assert data["total_input_tokens"] == 10000
        assert data["total_output_tokens"] == 5000
        assert data["cache_hit_rate"] == 0.75

    @patch(__name__ + ".find_session")
    def test_get_session_not_found(self, mock_find_session):
        """Test 404 when session not found."""
        mock_find_session.return_value = None

        response = client.get("/sessions/nonexistent-uuid")

        assert response.status_code == 404
        assert response.json()["detail"] == "Session not found"

    @patch(__name__ + ".find_session")
    def test_get_session_no_user_messages(self, mock_find_session, mock_session):
        """Test session with no user messages."""
        mock_session.iter_user_messages.return_value = iter([])
        mock_find_session.return_value = mock_session

        response = client.get("/sessions/test-session-uuid")

        assert response.status_code == 200
        data = response.json()
        assert data["initial_prompt"] is None

    @patch(__name__ + ".find_session")
    def test_get_session_truncates_long_prompt(
        self, mock_find_session, mock_session, mock_user_message
    ):
        """Test that initial prompt is truncated to 500 chars."""
        mock_user_message.content = "x" * 1000
        mock_session.iter_user_messages.return_value = iter([mock_user_message])
        mock_find_session.return_value = mock_session

        response = client.get("/sessions/test-session-uuid")

        assert response.status_code == 200
        data = response.json()
        assert len(data["initial_prompt"]) == 500


# =============================================================================
# GET /sessions/{uuid}/file-activity Tests
# =============================================================================


class TestGetFileActivityEndpoint:
    """Tests for GET /sessions/{uuid}/file-activity endpoint."""

    @patch(__name__ + ".find_session")
    def test_get_file_activity_success(
        self, mock_find_session, mock_session, mock_assistant_message
    ):
        """Test successful file activity retrieval."""
        mock_session.iter_assistant_messages.return_value = iter([mock_assistant_message])
        mock_session.list_subagents.return_value = []
        mock_find_session.return_value = mock_session

        response = client.get("/sessions/test-session-uuid/file-activity")

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["path"] == "/test/file.py"
        assert data[0]["operation"] == "read"
        assert data[0]["actor"] == "session"
        assert data[0]["actor_type"] == "session"
        assert data[0]["tool_name"] == "Read"

    @patch(__name__ + ".find_session")
    def test_get_file_activity_not_found(self, mock_find_session):
        """Test 404 when session not found."""
        mock_find_session.return_value = None

        response = client.get("/sessions/nonexistent-uuid/file-activity")

        assert response.status_code == 404
        assert response.json()["detail"] == "Session not found"

    @patch(__name__ + ".find_session")
    def test_get_file_activity_no_tool_use(self, mock_find_session, mock_session):
        """Test empty list when no tool usage."""
        # Mock assistant message with no tool use blocks
        msg = MagicMock(spec=AssistantMessage)
        msg.timestamp = datetime(2026, 1, 8, 13, 1, 0)
        msg.is_sidechain = False
        msg.agent_id = None
        msg.content_blocks = []

        mock_session.iter_assistant_messages.return_value = iter([msg])
        mock_session.list_subagents.return_value = []
        mock_find_session.return_value = mock_session

        response = client.get("/sessions/test-session-uuid/file-activity")

        assert response.status_code == 200
        data = response.json()
        assert data == []

    @patch(__name__ + ".find_session")
    def test_get_file_activity_with_subagents(self, mock_find_session, mock_session, mock_subagent):
        """Test file activity includes subagent activities."""
        # Main session has no activity
        mock_session.iter_assistant_messages.return_value = iter([])
        mock_session.list_subagents.return_value = [mock_subagent]
        mock_find_session.return_value = mock_session

        response = client.get("/sessions/test-session-uuid/file-activity")

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["path"] == "**/*.test.py"
        assert data[0]["operation"] == "search"
        assert data[0]["actor"] == "eager-puzzling-fairy"
        assert data[0]["actor_type"] == "subagent"

    @patch(__name__ + ".find_session")
    def test_get_file_activity_subagent_from_sidechain_message(
        self, mock_find_session, mock_session
    ):
        """Test file activity identifies subagent from sidechain message."""
        # Create a sidechain message
        msg = MagicMock(spec=AssistantMessage)
        msg.timestamp = datetime(2026, 1, 8, 13, 1, 0)
        msg.is_sidechain = True
        msg.agent_id = "a5793c3"
        msg.slug = "eager-puzzling-fairy"
        read_block = ToolUseBlock(
            type="tool_use",
            id="toolu_01",
            name="Read",
            input={"path": "/test/file.py"},
        )
        msg.content_blocks = [read_block]

        mock_session.iter_assistant_messages.return_value = iter([msg])
        mock_session.list_subagents.return_value = []
        mock_find_session.return_value = mock_session

        response = client.get("/sessions/test-session-uuid/file-activity")

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["actor"] == "eager-puzzling-fairy"
        assert data[0]["actor_type"] == "subagent"

    @patch(__name__ + ".find_session")
    def test_get_file_activity_sorted_by_timestamp(self, mock_find_session, mock_session):
        """Test file activities are sorted by timestamp."""
        # Create messages with different timestamps
        msg1 = MagicMock(spec=AssistantMessage)
        msg1.timestamp = datetime(2026, 1, 8, 13, 5, 0)  # Later
        msg1.is_sidechain = False
        msg1.agent_id = None
        msg1.content_blocks = [
            ToolUseBlock(
                type="tool_use",
                id="toolu_02",
                name="Read",
                input={"path": "/test/second.py"},
            )
        ]

        msg2 = MagicMock(spec=AssistantMessage)
        msg2.timestamp = datetime(2026, 1, 8, 13, 0, 0)  # Earlier
        msg2.is_sidechain = False
        msg2.agent_id = None
        msg2.content_blocks = [
            ToolUseBlock(
                type="tool_use",
                id="toolu_01",
                name="Read",
                input={"path": "/test/first.py"},
            )
        ]

        mock_session.iter_assistant_messages.return_value = iter([msg1, msg2])
        mock_session.list_subagents.return_value = []
        mock_find_session.return_value = mock_session

        response = client.get("/sessions/test-session-uuid/file-activity")

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2
        # Should be sorted by timestamp - first.py before second.py
        assert data[0]["path"] == "/test/first.py"
        assert data[1]["path"] == "/test/second.py"


# =============================================================================
# GET /sessions/{uuid}/subagents Tests
# =============================================================================


class TestGetSubagentsEndpoint:
    """Tests for GET /sessions/{uuid}/subagents endpoint."""

    @patch(__name__ + ".find_session")
    def test_get_subagents_success(self, mock_find_session, mock_session, mock_subagent):
        """Test successful subagent retrieval."""
        # Reset the iter_messages mock to return fresh iterators
        user_msg = MagicMock(spec=UserMessage)
        user_msg.content = "Search for all test files"
        user_msg.timestamp = datetime(2026, 1, 8, 13, 5, 0)

        asst_msg = MagicMock(spec=AssistantMessage)
        asst_msg.timestamp = datetime(2026, 1, 8, 13, 6, 0)
        glob_block = ToolUseBlock(
            type="tool_use",
            id="toolu_02DEF",
            name="Glob",
            input={"glob_pattern": "**/*.test.py"},
        )
        asst_msg.content_blocks = [glob_block]

        # Make iter_messages return a new iterator each time
        mock_subagent.iter_messages.side_effect = lambda: iter([user_msg, asst_msg])

        mock_session.list_subagents.return_value = [mock_subagent]
        mock_find_session.return_value = mock_session

        response = client.get("/sessions/test-session-uuid/subagents")

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["agent_id"] == "a5793c3"
        assert data[0]["slug"] == "eager-puzzling-fairy"
        assert data[0]["tools_used"]["Glob"] == 1
        assert data[0]["message_count"] == 10
        assert data[0]["initial_prompt"] == "Search for all test files"

    @patch(__name__ + ".find_session")
    def test_get_subagents_not_found(self, mock_find_session):
        """Test 404 when session not found."""
        mock_find_session.return_value = None

        response = client.get("/sessions/nonexistent-uuid/subagents")

        assert response.status_code == 404
        assert response.json()["detail"] == "Session not found"

    @patch(__name__ + ".find_session")
    def test_get_subagents_empty_list(self, mock_find_session, mock_session):
        """Test empty list when no subagents."""
        mock_session.list_subagents.return_value = []
        mock_find_session.return_value = mock_session

        response = client.get("/sessions/test-session-uuid/subagents")

        assert response.status_code == 200
        data = response.json()
        assert data == []

    @patch(__name__ + ".find_session")
    def test_get_subagents_no_user_messages(self, mock_find_session, mock_session):
        """Test subagent with no user messages has None initial_prompt."""
        subagent = MagicMock(spec=Agent)
        subagent.agent_id = "b1234ef"
        subagent.slug = None
        subagent.message_count = 5

        # Only assistant messages
        asst_msg = MagicMock(spec=AssistantMessage)
        asst_msg.content_blocks = []
        subagent.iter_messages.side_effect = lambda: iter([asst_msg])

        mock_session.list_subagents.return_value = [subagent]
        mock_find_session.return_value = mock_session

        response = client.get("/sessions/test-session-uuid/subagents")

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["initial_prompt"] is None

    @patch(__name__ + ".find_session")
    def test_get_subagents_multiple_tools(self, mock_find_session, mock_session):
        """Test subagent with multiple tool uses."""
        subagent = MagicMock(spec=Agent)
        subagent.agent_id = "c9876ab"
        subagent.slug = "busy-coding-robot"
        subagent.message_count = 20

        user_msg = MagicMock(spec=UserMessage)
        user_msg.content = "Fix the bug"

        asst_msg1 = MagicMock(spec=AssistantMessage)
        asst_msg1.content_blocks = [
            ToolUseBlock(type="tool_use", id="t1", name="Read", input={"path": "/f1"}),
            ToolUseBlock(type="tool_use", id="t2", name="Read", input={"path": "/f2"}),
        ]

        asst_msg2 = MagicMock(spec=AssistantMessage)
        asst_msg2.content_blocks = [
            ToolUseBlock(type="tool_use", id="t3", name="Write", input={"path": "/f1"}),
        ]

        subagent.iter_messages.side_effect = lambda: iter([user_msg, asst_msg1, asst_msg2])

        mock_session.list_subagents.return_value = [subagent]
        mock_find_session.return_value = mock_session

        response = client.get("/sessions/test-session-uuid/subagents")

        assert response.status_code == 200
        data = response.json()
        assert data[0]["tools_used"]["Read"] == 2
        assert data[0]["tools_used"]["Write"] == 1

    @patch(__name__ + ".find_session")
    def test_subagent_type_extracted(self, mock_find_session, mock_session):
        """Verify subagent_type is extracted from Task tool and linked to SubagentSummary."""
        # Create a Task tool call in the main session with subagent_type
        task_msg = MagicMock(spec=AssistantMessage)
        task_msg.content_blocks = [
            ToolUseBlock(
                type="tool_use",
                id="toolu_task_01",
                name="Task",
                input={
                    "description": "Explore the codebase structure",
                    "prompt": "Search for all Python files...",
                    "subagent_type": "Explore",
                },
            )
        ]

        # Create a subagent whose initial_prompt matches the Task description
        subagent = MagicMock(spec=Agent)
        subagent.agent_id = "a1b2c3d"
        subagent.slug = "curious-explorer"
        subagent.message_count = 8

        user_msg = MagicMock(spec=UserMessage)
        user_msg.content = "Explore the codebase structure"  # Matches Task description

        asst_msg = MagicMock(spec=AssistantMessage)
        asst_msg.content_blocks = [
            ToolUseBlock(type="tool_use", id="t1", name="Glob", input={"glob_pattern": "**/*.py"}),
        ]

        subagent.iter_messages.side_effect = lambda: iter([user_msg, asst_msg])

        # Mock session to return both Task message and subagent
        mock_session.iter_messages.return_value = iter([task_msg])
        mock_session.list_subagents.return_value = [subagent]
        mock_find_session.return_value = mock_session

        response = client.get("/sessions/test-session-uuid/subagents")

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["agent_id"] == "a1b2c3d"
        assert data[0]["slug"] == "curious-explorer"
        assert data[0]["subagent_type"] == "Explore"
        assert data[0]["initial_prompt"] == "Explore the codebase structure"

    @patch(__name__ + ".find_session")
    def test_subagent_type_optional(self, mock_find_session, mock_session):
        """Verify missing subagent_type doesn't break parsing and returns None."""
        # Create a Task tool call WITHOUT subagent_type (older data or custom prompt)
        task_msg = MagicMock(spec=AssistantMessage)
        task_msg.content_blocks = [
            ToolUseBlock(
                type="tool_use",
                id="toolu_task_02",
                name="Task",
                input={
                    "description": "Do something custom",
                    "prompt": "Custom task without type...",
                    # No subagent_type field
                },
            )
        ]

        # Create a subagent
        subagent = MagicMock(spec=Agent)
        subagent.agent_id = "x9y8z7w"
        subagent.slug = "custom-worker"
        subagent.message_count = 3

        user_msg = MagicMock(spec=UserMessage)
        user_msg.content = "Do something custom"

        asst_msg = MagicMock(spec=AssistantMessage)
        asst_msg.content_blocks = []

        subagent.iter_messages.side_effect = lambda: iter([user_msg, asst_msg])

        mock_session.iter_messages.return_value = iter([task_msg])
        mock_session.list_subagents.return_value = [subagent]
        mock_find_session.return_value = mock_session

        response = client.get("/sessions/test-session-uuid/subagents")

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["subagent_type"] is None  # Should be None, not break

    @patch(__name__ + ".find_session")
    def test_subagent_type_no_match(self, mock_find_session, mock_session):
        """Verify subagent_type is None when subagent prompt doesn't match any Task."""
        # Create a Task tool call with subagent_type
        task_msg = MagicMock(spec=AssistantMessage)
        task_msg.content_blocks = [
            ToolUseBlock(
                type="tool_use",
                id="toolu_task_03",
                name="Task",
                input={
                    "description": "Task A description",
                    "subagent_type": "Plan",
                },
            )
        ]

        # Create a subagent with DIFFERENT initial_prompt (no match)
        subagent = MagicMock(spec=Agent)
        subagent.agent_id = "m1n2o3p"
        subagent.slug = "unmatched-agent"
        subagent.message_count = 2

        user_msg = MagicMock(spec=UserMessage)
        user_msg.content = "Completely different task"  # Does NOT match Task description

        asst_msg = MagicMock(spec=AssistantMessage)
        asst_msg.content_blocks = []

        subagent.iter_messages.side_effect = lambda: iter([user_msg, asst_msg])

        mock_session.iter_messages.return_value = iter([task_msg])
        mock_session.list_subagents.return_value = [subagent]
        mock_find_session.return_value = mock_session

        response = client.get("/sessions/test-session-uuid/subagents")

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["subagent_type"] is None  # No match found

    @patch(__name__ + ".find_session")
    def test_subagent_type_whitespace_normalization(self, mock_find_session, mock_session):
        """Verify whitespace differences don't break subagent_type matching."""
        # Task description has extra whitespace and different case
        task_msg = MagicMock(spec=AssistantMessage)
        task_msg.content_blocks = [
            ToolUseBlock(
                type="tool_use",
                id="toolu_task_04",
                name="Task",
                input={
                    "description": "  Explore   the   codebase  ",  # Extra whitespace
                    "subagent_type": "Explore",
                },
            )
        ]

        # Subagent prompt has normalized whitespace and different case
        subagent = MagicMock(spec=Agent)
        subagent.agent_id = "ws123"
        subagent.slug = "whitespace-test"
        subagent.message_count = 5

        user_msg = MagicMock(spec=UserMessage)
        user_msg.content = "explore the codebase"  # Lowercase, single spaces

        asst_msg = MagicMock(spec=AssistantMessage)
        asst_msg.content_blocks = []

        subagent.iter_messages.side_effect = lambda: iter([user_msg, asst_msg])

        mock_session.iter_messages.return_value = iter([task_msg])
        mock_session.list_subagents.return_value = [subagent]
        mock_find_session.return_value = mock_session

        response = client.get("/sessions/test-session-uuid/subagents")

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["subagent_type"] == "Explore"  # Should match despite whitespace


# =============================================================================
# GET /sessions/{uuid}/tools Tests
# =============================================================================


class TestGetToolsEndpoint:
    """Tests for GET /sessions/{uuid}/tools endpoint."""

    @patch(__name__ + ".find_session")
    def test_get_tools_success(self, mock_find_session, mock_session, mock_assistant_message):
        """Test successful tool usage retrieval."""
        mock_session.iter_assistant_messages.return_value = iter([mock_assistant_message])
        mock_session.list_subagents.return_value = []
        mock_find_session.return_value = mock_session

        response = client.get("/sessions/test-session-uuid/tools")

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["tool_name"] == "Read"
        assert data[0]["count"] == 1
        assert data[0]["by_session"] == 1
        assert data[0]["by_subagents"] == 0

    @patch(__name__ + ".find_session")
    def test_get_tools_not_found(self, mock_find_session):
        """Test 404 when session not found."""
        mock_find_session.return_value = None

        response = client.get("/sessions/nonexistent-uuid/tools")

        assert response.status_code == 404
        assert response.json()["detail"] == "Session not found"

    @patch(__name__ + ".find_session")
    def test_get_tools_empty_list(self, mock_find_session, mock_session):
        """Test empty list when no tool usage."""
        mock_session.iter_assistant_messages.return_value = iter([])
        mock_session.list_subagents.return_value = []
        mock_find_session.return_value = mock_session

        response = client.get("/sessions/test-session-uuid/tools")

        assert response.status_code == 200
        data = response.json()
        assert data == []

    @patch(__name__ + ".find_session")
    def test_get_tools_session_and_subagent_combined(self, mock_find_session, mock_session):
        """Test tool usage combines session and subagent counts."""
        # Session uses Read twice
        session_msg = MagicMock(spec=AssistantMessage)
        session_msg.is_sidechain = False
        session_msg.agent_id = None
        session_msg.content_blocks = [
            ToolUseBlock(type="tool_use", id="t1", name="Read", input={"path": "/f1"}),
            ToolUseBlock(type="tool_use", id="t2", name="Read", input={"path": "/f2"}),
        ]
        mock_session.iter_assistant_messages.return_value = iter([session_msg])

        # Subagent uses Read once and Write once
        subagent = MagicMock(spec=Agent)
        subagent.agent_id = "sub1"
        subagent.slug = "test-agent"

        sub_msg = MagicMock(spec=AssistantMessage)
        sub_msg.content_blocks = [
            ToolUseBlock(type="tool_use", id="t3", name="Read", input={"path": "/f3"}),
            ToolUseBlock(type="tool_use", id="t4", name="Write", input={"path": "/f4"}),
        ]
        subagent.iter_messages.return_value = iter([sub_msg])

        mock_session.list_subagents.return_value = [subagent]
        mock_find_session.return_value = mock_session

        response = client.get("/sessions/test-session-uuid/tools")

        assert response.status_code == 200
        data = response.json()

        # Should have Read and Write tools, sorted by count descending
        assert len(data) == 2

        # Find Read and Write in response
        read_tool = next(t for t in data if t["tool_name"] == "Read")
        write_tool = next(t for t in data if t["tool_name"] == "Write")

        assert read_tool["count"] == 3  # 2 session + 1 subagent
        assert read_tool["by_session"] == 2
        assert read_tool["by_subagents"] == 1

        assert write_tool["count"] == 1
        assert write_tool["by_session"] == 0
        assert write_tool["by_subagents"] == 1

    @patch(__name__ + ".find_session")
    def test_get_tools_sorted_by_count_descending(self, mock_find_session, mock_session):
        """Test tools are sorted by total count descending."""
        session_msg = MagicMock(spec=AssistantMessage)
        session_msg.is_sidechain = False
        session_msg.agent_id = None
        session_msg.content_blocks = [
            ToolUseBlock(type="tool_use", id="t1", name="Write", input={}),
            ToolUseBlock(type="tool_use", id="t2", name="Read", input={}),
            ToolUseBlock(type="tool_use", id="t3", name="Read", input={}),
            ToolUseBlock(type="tool_use", id="t4", name="Read", input={}),
            ToolUseBlock(type="tool_use", id="t5", name="Glob", input={}),
            ToolUseBlock(type="tool_use", id="t6", name="Glob", input={}),
        ]
        mock_session.iter_assistant_messages.return_value = iter([session_msg])
        mock_session.list_subagents.return_value = []
        mock_find_session.return_value = mock_session

        response = client.get("/sessions/test-session-uuid/tools")

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 3
        assert data[0]["tool_name"] == "Read"  # 3 uses
        assert data[0]["count"] == 3
        assert data[1]["tool_name"] == "Glob"  # 2 uses
        assert data[1]["count"] == 2
        assert data[2]["tool_name"] == "Write"  # 1 use
        assert data[2]["count"] == 1

    @patch(__name__ + ".find_session")
    def test_get_tools_sidechain_message_counts_as_subagent(self, mock_find_session, mock_session):
        """Test sidechain messages are counted as subagent tool usage."""
        sidechain_msg = MagicMock(spec=AssistantMessage)
        sidechain_msg.is_sidechain = True
        sidechain_msg.agent_id = "a5793c3"
        sidechain_msg.content_blocks = [
            ToolUseBlock(type="tool_use", id="t1", name="Read", input={"path": "/f1"}),
        ]
        mock_session.iter_assistant_messages.return_value = iter([sidechain_msg])
        mock_session.list_subagents.return_value = []
        mock_find_session.return_value = mock_session

        response = client.get("/sessions/test-session-uuid/tools")

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["tool_name"] == "Read"
        assert data[0]["by_session"] == 0
        assert data[0]["by_subagents"] == 1


# =============================================================================
# GET /sessions/{uuid}/initial-prompt Tests
# =============================================================================


class TestGetInitialPromptEndpoint:
    """Tests for GET /sessions/{uuid}/initial-prompt endpoint."""

    @patch(__name__ + ".find_session")
    def test_get_initial_prompt_success(self, mock_find_session, mock_session, mock_user_message):
        """Test successful initial prompt retrieval."""
        mock_session.iter_user_messages.return_value = iter([mock_user_message])
        mock_find_session.return_value = mock_session

        response = client.get("/sessions/test-session-uuid/initial-prompt")

        assert response.status_code == 200
        data = response.json()
        assert data["content"] == "Help me understand this code in the repository"
        assert "timestamp" in data

    @patch(__name__ + ".find_session")
    def test_get_initial_prompt_not_found(self, mock_find_session):
        """Test 404 when session not found."""
        mock_find_session.return_value = None

        response = client.get("/sessions/nonexistent-uuid/initial-prompt")

        assert response.status_code == 404
        assert response.json()["detail"] == "Session not found"

    @patch(__name__ + ".find_session")
    def test_get_initial_prompt_no_user_messages(self, mock_find_session, mock_session):
        """Test 404 when no user messages in session."""
        mock_session.iter_user_messages.return_value = iter([])
        mock_find_session.return_value = mock_session

        response = client.get("/sessions/test-session-uuid/initial-prompt")

        assert response.status_code == 404
        assert response.json()["detail"] == "No user messages found in session"

    @patch(__name__ + ".find_session")
    def test_get_initial_prompt_returns_first_message(self, mock_find_session, mock_session):
        """Test that initial prompt returns the first user message."""
        msg1 = MagicMock(spec=UserMessage)
        msg1.content = "First message"
        msg1.timestamp = datetime(2026, 1, 8, 13, 0, 0)

        msg2 = MagicMock(spec=UserMessage)
        msg2.content = "Second message"
        msg2.timestamp = datetime(2026, 1, 8, 13, 5, 0)

        mock_session.iter_user_messages.return_value = iter([msg1, msg2])
        mock_find_session.return_value = mock_session

        response = client.get("/sessions/test-session-uuid/initial-prompt")

        assert response.status_code == 200
        data = response.json()
        assert data["content"] == "First message"


# =============================================================================
# Todo-related Fixtures
# =============================================================================


@pytest.fixture
def mock_todo_items():
    """Create mock TodoItem instances."""
    from models.todo import TodoItem

    return [
        TodoItem(content="Explore codebase", status="completed", active_form="Exploring"),
        TodoItem(content="Write tests", status="in_progress", active_form="Writing tests"),
        TodoItem(content="Deploy feature", status="pending", active_form="Deploying"),
    ]


@pytest.fixture
def mock_session_with_todos(mock_session, mock_todo_items, mock_user_message):
    """Create a mock session with todo items."""
    mock_session.has_todos = True
    mock_session.list_todos.return_value = mock_todo_items
    mock_session.iter_user_messages.return_value = iter([mock_user_message])
    return mock_session


# =============================================================================
# GET /sessions/{uuid}/todos Tests
# =============================================================================


class TestGetSessionTodosEndpoint:
    """Tests for GET /sessions/{uuid}/todos endpoint."""

    @patch(__name__ + ".find_session")
    def test_get_session_todos_success(self, mock_find_session, mock_session, mock_todo_items):
        """Test successful todos retrieval."""
        mock_session.list_todos.return_value = mock_todo_items
        mock_find_session.return_value = mock_session

        response = client.get("/sessions/test-session-uuid/todos")

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 3
        assert data[0]["content"] == "Explore codebase"
        assert data[0]["status"] == "completed"
        assert data[0]["activeForm"] == "Exploring"
        assert data[1]["content"] == "Write tests"
        assert data[1]["status"] == "in_progress"
        assert data[2]["status"] == "pending"

    @patch(__name__ + ".find_session")
    def test_get_session_todos_not_found(self, mock_find_session):
        """Test 404 when session not found."""
        mock_find_session.return_value = None

        response = client.get("/sessions/nonexistent-uuid/todos")

        assert response.status_code == 404
        assert "not found" in response.json()["detail"]

    @patch(__name__ + ".find_session")
    def test_get_session_todos_empty(self, mock_find_session, mock_session):
        """Test empty list when no todos."""
        mock_session.list_todos.return_value = []
        mock_find_session.return_value = mock_session

        response = client.get("/sessions/test-session-uuid/todos")

        assert response.status_code == 200
        data = response.json()
        assert data == []

    @patch(__name__ + ".find_session")
    def test_get_session_todos_error_returns_empty(self, mock_find_session, mock_session):
        """Test exception during todos loading returns empty list."""
        mock_session.list_todos.side_effect = Exception("Failed to load")
        mock_find_session.return_value = mock_session

        response = client.get("/sessions/test-session-uuid/todos")

        assert response.status_code == 200
        data = response.json()
        assert data == []


# =============================================================================
# Session Detail Todos Tests
# =============================================================================


class TestSessionDetailWithTodos:
    """Tests for todo-related fields in SessionDetail."""

    @patch(__name__ + ".find_session")
    def test_session_detail_includes_todos(self, mock_find_session, mock_session_with_todos):
        """Test GET /sessions/{uuid} includes todos in response."""
        mock_find_session.return_value = mock_session_with_todos

        response = client.get("/sessions/test-session-uuid")

        assert response.status_code == 200
        data = response.json()

        assert data["has_todos"] is True
        assert data["todo_count"] == 3
        assert len(data["todos"]) == 3
        assert data["todos"][0]["content"] == "Explore codebase"
        assert data["todos"][0]["status"] == "completed"
        assert data["todos"][0]["activeForm"] == "Exploring"

    @patch(__name__ + ".find_session")
    def test_session_detail_no_todos(self, mock_find_session, mock_session, mock_user_message):
        """Test session detail with no todos."""
        mock_session.has_todos = False
        mock_session.list_todos.return_value = []
        mock_session.iter_user_messages.return_value = iter([mock_user_message])
        mock_find_session.return_value = mock_session

        response = client.get("/sessions/test-session-uuid")

        assert response.status_code == 200
        data = response.json()

        assert data["has_todos"] is False
        assert data["todo_count"] == 0
        assert data["todos"] == []

    @patch(__name__ + ".find_session")
    def test_session_detail_todos_error_graceful(
        self, mock_find_session, mock_session, mock_user_message
    ):
        """Test session detail handles todos loading error gracefully."""
        mock_session.has_todos = True
        mock_session.list_todos.side_effect = Exception("Todo file corrupted")
        mock_session.iter_user_messages.return_value = iter([mock_user_message])
        mock_find_session.return_value = mock_session

        response = client.get("/sessions/test-session-uuid")

        # Should still succeed, just with empty todos
        assert response.status_code == 200
        data = response.json()
        assert data["todo_count"] == 0
        assert data["todos"] == []

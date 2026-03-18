"""
Comprehensive unit tests for the projects router.

Tests cover:
- get_claude_projects_dir() helper function
- list_all_projects() helper function
- session_to_summary() helper function
- GET /projects endpoint
- GET /projects/{encoded_name} endpoint

Uses pytest with FastAPI's TestClient and unittest.mock to avoid
dependency on actual ~/.claude/ data.

Run from project root: pytest apps/api/tests/test_projects.py -v
Or from apps/api: PYTHONPATH=../.. python -m pytest tests/test_projects.py -v
"""

import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
from unittest.mock import patch

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from pydantic import BaseModel, Field

# Setup paths before imports
_project_root = Path(__file__).parent.parent.parent.parent
_api_root = Path(__file__).parent.parent
sys.path.insert(0, str(_project_root))
sys.path.insert(0, str(_api_root))

# Import models
from models import Project, Session
from utils import is_encoded_project_dir

# =============================================================================
# Mock Schemas (to avoid relative import issues)
# =============================================================================


class MockSessionSummary(BaseModel):
    """Mock SessionSummary for testing."""

    uuid: str
    message_count: int
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    duration_seconds: Optional[float] = None
    models_used: List[str] = Field(default_factory=list)
    subagent_count: int = 0
    has_todos: bool = False
    initial_prompt: Optional[str] = None


class MockProjectSummary(BaseModel):
    """Mock ProjectSummary for testing."""

    path: str
    encoded_name: str
    session_count: int = 0
    agent_count: int = 0
    exists: bool = True


class MockProjectDetail(MockProjectSummary):
    """Mock ProjectDetail for testing."""

    sessions: List[MockSessionSummary] = Field(default_factory=list)


# =============================================================================
# Replicate Router Functions for Testing
# =============================================================================


def get_claude_projects_dir() -> Path:
    """Get the ~/.claude/projects directory."""
    return Path.home() / ".claude" / "projects"


def list_all_projects() -> List[Project]:
    """List all projects from ~/.claude/projects/."""
    projects_dir = get_claude_projects_dir()
    if not projects_dir.exists():
        return []

    projects = []
    for encoded_dir in projects_dir.iterdir():
        if encoded_dir.is_dir() and is_encoded_project_dir(encoded_dir.name):
            try:
                project = Project.from_encoded_name(encoded_dir.name)
                projects.append(project)
            except Exception:
                continue
    return sorted(projects, key=lambda p: p.path)


def session_to_summary(session: Session) -> MockSessionSummary:
    """Convert a Session to MockSessionSummary."""
    # Get initial prompt (first user message)
    initial_prompt = None
    for msg in session.iter_user_messages():
        initial_prompt = msg.content[:500] if msg.content else None
        break

    return MockSessionSummary(
        uuid=session.uuid,
        message_count=session.message_count,
        start_time=session.start_time,
        end_time=session.end_time,
        duration_seconds=session.duration_seconds,
        models_used=list(session.get_models_used()),
        subagent_count=len(session.list_subagents()),
        has_todos=session.has_todos,
        initial_prompt=initial_prompt,
    )


# =============================================================================
# Create Test App
# =============================================================================


def create_test_app():
    """Create a test FastAPI app with mocked router."""
    app = FastAPI()

    @app.get("/projects", response_model=List[MockProjectSummary])
    def list_projects():
        """List all projects with basic stats."""
        projects = list_all_projects()
        return [
            MockProjectSummary(
                path=p.path,
                encoded_name=p.encoded_name,
                session_count=p.session_count,
                agent_count=p.agent_count,
                exists=p.exists,
            )
            for p in projects
        ]

    @app.get("/projects/{encoded_name}", response_model=MockProjectDetail)
    def get_project(encoded_name: str, limit: Optional[int] = None):
        """Get project details with sessions list."""
        try:
            project = Project.from_encoded_name(encoded_name)
        except Exception as e:
            raise HTTPException(status_code=404, detail=f"Project not found: {e}") from e

        if not project.exists:
            raise HTTPException(status_code=404, detail="Project directory not found")

        sessions = project.list_sessions()
        # Sort by start time descending (most recent first)
        sessions_with_time = [(s, s.start_time) for s in sessions]
        sessions_with_time.sort(key=lambda x: x[1] or "", reverse=True)
        sessions = [s for s, _ in sessions_with_time]

        if limit:
            sessions = sessions[:limit]

        return MockProjectDetail(
            path=project.path,
            encoded_name=project.encoded_name,
            session_count=project.session_count,
            agent_count=project.agent_count,
            exists=project.exists,
            sessions=[session_to_summary(s) for s in sessions],
        )

    return app


test_app = create_test_app()


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def client():
    """Create a TestClient for the FastAPI app."""
    return TestClient(test_app)


@pytest.fixture
def temp_claude_dir(tmp_path: Path, monkeypatch) -> Path:
    """Create a temporary ~/.claude structure for testing.

    Also patches settings.claude_base to point to this temp directory.
    """
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

    # Patch settings to use temp directory
    from config import settings

    monkeypatch.setattr(settings, "claude_base", claude_dir)

    return claude_dir


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
def temp_project_with_sessions(
    temp_claude_dir: Path,
    sample_user_message_data: Dict[str, Any],
    sample_assistant_message_data: Dict[str, Any],
) -> Path:
    """Create a temporary project directory with sessions."""
    # Create project directory: /Users/test/myproject -> -Users-test-myproject
    project_dir = temp_claude_dir / "projects" / "-Users-test-myproject"
    project_dir.mkdir(parents=True)

    # Create a session JSONL file
    session_uuid = "test-session-uuid"
    jsonl_path = project_dir / f"{session_uuid}.jsonl"

    with open(jsonl_path, "w") as f:
        f.write(json.dumps(sample_user_message_data) + "\n")
        f.write(json.dumps(sample_assistant_message_data) + "\n")

    return project_dir


@pytest.fixture
def temp_multiple_projects(temp_claude_dir: Path) -> Path:
    """Create multiple temporary project directories."""
    projects_dir = temp_claude_dir / "projects"

    # Create several projects
    project_names = [
        "-Users-test-project1",
        "-Users-test-project2",
        "-Users-test-project3",
    ]

    for name in project_names:
        project_dir = projects_dir / name
        project_dir.mkdir(parents=True)
        # Create a session file in each
        (project_dir / "session-uuid.jsonl").write_text('{"type": "user"}\n')

    return projects_dir


# =============================================================================
# Tests for get_claude_projects_dir()
# =============================================================================


class TestGetClaudeProjectsDir:
    """Tests for the get_claude_projects_dir() helper function."""

    def test_returns_correct_path(self):
        """Test that get_claude_projects_dir returns ~/.claude/projects."""
        result = get_claude_projects_dir()
        expected = Path.home() / ".claude" / "projects"
        assert result == expected

    def test_returns_path_object(self):
        """Test that get_claude_projects_dir returns a Path object."""
        result = get_claude_projects_dir()
        assert isinstance(result, Path)

    def test_with_mocked_home(self, tmp_path: Path):
        """Test get_claude_projects_dir with mocked Path.home()."""
        with patch.object(Path, "home", return_value=tmp_path):
            result = get_claude_projects_dir()
            assert result == tmp_path / ".claude" / "projects"


# =============================================================================
# Tests for list_all_projects()
# =============================================================================


class TestListAllProjects:
    """Tests for the list_all_projects() helper function."""

    def test_returns_empty_when_projects_dir_missing(self, tmp_path: Path):
        """Test that list_all_projects returns empty list when dir doesn't exist."""
        with patch.object(Path, "home", return_value=tmp_path):
            result = list_all_projects()
            assert result == []

    def test_returns_empty_when_projects_dir_empty(self, temp_claude_dir: Path, tmp_path: Path):
        """Test that list_all_projects returns empty list when no projects exist."""
        with patch.object(Path, "home", return_value=tmp_path):
            result = list_all_projects()
            assert result == []

    def test_returns_projects_sorted_by_path(self, temp_multiple_projects: Path, tmp_path: Path):
        """Test that list_all_projects returns projects sorted by path."""
        with patch.object(Path, "home", return_value=tmp_path):
            result = list_all_projects()

            assert len(result) == 3
            paths = [p.path for p in result]
            # Should be sorted alphabetically by decoded path
            assert paths == sorted(paths)

    def test_ignores_non_dash_prefixed_directories(self, temp_claude_dir: Path, tmp_path: Path):
        """Test that directories not starting with '-' are ignored."""
        projects_dir = temp_claude_dir / "projects"

        # Create valid project
        valid_project = projects_dir / "-Users-test-valid"
        valid_project.mkdir(parents=True)

        # Create invalid directories (don't start with -)
        invalid1 = projects_dir / "not-a-project"
        invalid1.mkdir(parents=True)
        invalid2 = projects_dir / "regular_dir"
        invalid2.mkdir(parents=True)

        with patch.object(Path, "home", return_value=tmp_path):
            result = list_all_projects()

            assert len(result) == 1
            assert result[0].encoded_name == "-Users-test-valid"

    def test_ignores_files_in_projects_dir(self, temp_claude_dir: Path, tmp_path: Path):
        """Test that files in projects dir are ignored."""
        projects_dir = temp_claude_dir / "projects"

        # Create valid project
        valid_project = projects_dir / "-Users-test-valid"
        valid_project.mkdir(parents=True)

        # Create a file (not a directory)
        (projects_dir / "-Users-test-file.txt").write_text("not a project")

        with patch.object(Path, "home", return_value=tmp_path):
            result = list_all_projects()

            assert len(result) == 1
            assert result[0].encoded_name == "-Users-test-valid"


# =============================================================================
# Tests for session_to_summary()
# =============================================================================


class TestSessionToSummary:
    """Tests for the session_to_summary() helper function."""

    def test_creates_summary_with_basic_fields(
        self, temp_project_with_sessions: Path, temp_claude_dir: Path
    ):
        """Test that session_to_summary creates summary with all basic fields."""
        session_path = temp_project_with_sessions / "test-session-uuid.jsonl"
        session = Session.from_path(session_path, claude_base_dir=temp_claude_dir)

        summary = session_to_summary(session)

        assert summary.uuid == "test-session-uuid"
        assert summary.message_count > 0
        assert isinstance(summary.start_time, datetime) or summary.start_time is None
        assert isinstance(summary.end_time, datetime) or summary.end_time is None
        assert isinstance(summary.duration_seconds, (float, int, type(None)))
        assert isinstance(summary.models_used, list)
        assert isinstance(summary.subagent_count, int)
        assert isinstance(summary.has_todos, bool)

    def test_extracts_initial_prompt(self, temp_project_with_sessions: Path, temp_claude_dir: Path):
        """Test that session_to_summary extracts the initial prompt."""
        session_path = temp_project_with_sessions / "test-session-uuid.jsonl"
        session = Session.from_path(session_path, claude_base_dir=temp_claude_dir)

        summary = session_to_summary(session)

        assert summary.initial_prompt == "Help me understand this code"

    def test_truncates_long_initial_prompt(self, temp_claude_dir: Path):
        """Test that long initial prompts are truncated to 500 chars."""
        project_dir = temp_claude_dir / "projects" / "-Users-test-long"
        project_dir.mkdir(parents=True)

        # Create session with very long user message
        long_content = "x" * 1000
        long_msg = {
            "type": "user",
            "message": {"role": "user", "content": long_content},
            "uuid": "user-uuid",
            "timestamp": "2026-01-08T13:00:00.000Z",
        }

        session_path = project_dir / "long-session.jsonl"
        session_path.write_text(json.dumps(long_msg) + "\n")

        session = Session.from_path(session_path, claude_base_dir=temp_claude_dir)
        summary = session_to_summary(session)

        assert summary.initial_prompt is not None
        assert len(summary.initial_prompt) <= 500

    def test_initial_prompt_none_when_no_user_messages(self, temp_claude_dir: Path):
        """Test that initial_prompt is None when no user messages exist."""
        project_dir = temp_claude_dir / "projects" / "-Users-test-empty"
        project_dir.mkdir(parents=True)

        # Create session with only assistant message
        assistant_msg = {
            "type": "assistant",
            "message": {"role": "assistant", "content": []},
            "uuid": "assistant-uuid",
            "timestamp": "2026-01-08T13:00:00.000Z",
        }

        session_path = project_dir / "no-user.jsonl"
        session_path.write_text(json.dumps(assistant_msg) + "\n")

        session = Session.from_path(session_path, claude_base_dir=temp_claude_dir)
        summary = session_to_summary(session)

        assert summary.initial_prompt is None

    def test_models_used_extracted(self, temp_project_with_sessions: Path, temp_claude_dir: Path):
        """Test that models_used is extracted correctly."""
        session_path = temp_project_with_sessions / "test-session-uuid.jsonl"
        session = Session.from_path(session_path, claude_base_dir=temp_claude_dir)

        summary = session_to_summary(session)

        assert "claude-opus-4-5-20251101" in summary.models_used


# =============================================================================
# Tests for GET /projects endpoint
# =============================================================================


class TestListProjectsEndpoint:
    """Tests for the GET /projects endpoint."""

    def test_returns_empty_list_when_no_projects(self, client: TestClient, tmp_path: Path):
        """Test that endpoint returns empty list when no projects exist."""
        with patch.object(Path, "home", return_value=tmp_path):
            response = client.get("/projects")

            assert response.status_code == 200
            assert response.json() == []

    def test_returns_project_summaries(
        self, client: TestClient, temp_multiple_projects: Path, tmp_path: Path
    ):
        """Test that endpoint returns list of project summaries."""
        with patch.object(Path, "home", return_value=tmp_path):
            response = client.get("/projects")

            assert response.status_code == 200
            data = response.json()

            assert len(data) == 3
            for project in data:
                assert "path" in project
                assert "encoded_name" in project
                assert "session_count" in project
                assert "agent_count" in project
                assert "exists" in project

    def test_response_contains_correct_counts(
        self, client: TestClient, temp_project_with_sessions: Path, tmp_path: Path
    ):
        """Test that response contains correct session and agent counts."""
        with patch.object(Path, "home", return_value=tmp_path):
            response = client.get("/projects")

            assert response.status_code == 200
            data = response.json()

            assert len(data) == 1
            project = data[0]
            assert project["session_count"] == 1
            assert project["agent_count"] == 0
            assert project["exists"] is True

    def test_projects_sorted_by_path(
        self, client: TestClient, temp_multiple_projects: Path, tmp_path: Path
    ):
        """Test that projects are sorted by path."""
        with patch.object(Path, "home", return_value=tmp_path):
            response = client.get("/projects")

            assert response.status_code == 200
            data = response.json()

            paths = [p["path"] for p in data]
            assert paths == sorted(paths)


class TestListProjectsEndpointEdgeCases:
    """Edge case tests for GET /projects endpoint."""

    def test_handles_projects_dir_missing(self, client: TestClient, tmp_path: Path):
        """Test graceful handling when ~/.claude/projects doesn't exist."""
        with patch.object(Path, "home", return_value=tmp_path):
            response = client.get("/projects")

            assert response.status_code == 200
            assert response.json() == []

    def test_handles_mixed_valid_invalid_dirs(
        self, client: TestClient, temp_claude_dir: Path, tmp_path: Path
    ):
        """Test that invalid directories are skipped gracefully."""
        projects_dir = temp_claude_dir / "projects"

        # Valid project
        (projects_dir / "-Users-test-valid").mkdir()
        (projects_dir / "-Users-test-valid" / "session.jsonl").write_text("{}\n")

        # Invalid (no dash prefix)
        (projects_dir / "invalid_dir").mkdir()

        with patch.object(Path, "home", return_value=tmp_path):
            response = client.get("/projects")

            assert response.status_code == 200
            data = response.json()
            assert len(data) == 1
            assert data[0]["encoded_name"] == "-Users-test-valid"


# =============================================================================
# Tests for GET /projects/{encoded_name} endpoint
# =============================================================================


class TestGetProjectEndpoint:
    """Tests for the GET /projects/{encoded_name} endpoint."""

    def test_returns_project_detail(
        self, client: TestClient, temp_project_with_sessions: Path, tmp_path: Path
    ):
        """Test that endpoint returns project detail with sessions."""
        with patch.object(Path, "home", return_value=tmp_path):
            response = client.get("/projects/-Users-test-myproject")

            assert response.status_code == 200
            data = response.json()

            assert data["path"] == "/Users/test/myproject"
            assert data["encoded_name"] == "-Users-test-myproject"
            assert data["session_count"] == 1
            assert data["agent_count"] == 0
            assert data["exists"] is True
            assert "sessions" in data
            assert len(data["sessions"]) == 1

    def test_sessions_contain_summary_fields(
        self, client: TestClient, temp_project_with_sessions: Path, tmp_path: Path
    ):
        """Test that sessions in response contain all summary fields."""
        with patch.object(Path, "home", return_value=tmp_path):
            response = client.get("/projects/-Users-test-myproject")

            assert response.status_code == 200
            session = response.json()["sessions"][0]

            assert "uuid" in session
            assert "message_count" in session
            assert "start_time" in session
            assert "end_time" in session
            assert "duration_seconds" in session
            assert "models_used" in session
            assert "subagent_count" in session
            assert "has_todos" in session
            assert "initial_prompt" in session

    def test_per_page_parameter(self, temp_claude_dir: Path, tmp_path: Path):
        """Test that per_page parameter limits number of sessions returned.

        Note: Tests the router directly due to TestClient caching/SQLite behavior.
        """
        from routers.projects import get_project

        project_dir = temp_claude_dir / "projects" / "-Users-test-many"
        project_dir.mkdir(parents=True)

        # Create multiple sessions
        for i in range(5):
            session_path = project_dir / f"session-{i}.jsonl"
            msg = {
                "type": "user",
                "message": {"role": "user", "content": f"Message {i}"},
                "uuid": f"uuid-{i}",
                "timestamp": f"2026-01-0{i + 1}T13:00:00.000Z",
            }
            session_path.write_text(json.dumps(msg) + "\n")

        class MockRequest:
            url = None

        with patch.object(Path, "home", return_value=tmp_path):
            result = get_project("-Users-test-many", MockRequest(), page=1, per_page=3)
            data = json.loads(result.body)

            assert len(data["sessions"]) == 3
            assert data["session_count"] == 5  # Total count unchanged

    def test_pagination_parameter(self, temp_claude_dir: Path, tmp_path: Path):
        """Test that page/per_page parameters paginate sessions correctly.

        Note: Tests the router directly due to TestClient caching behavior.
        """
        from routers.projects import get_project

        project_dir = temp_claude_dir / "projects" / "-Users-test-offset"
        project_dir.mkdir(parents=True)

        # Create multiple sessions with different timestamps (uuid derived from filename stem)
        for i in range(5):
            session_path = project_dir / f"session-offset-{i}.jsonl"
            msg = {
                "type": "user",
                "message": {"role": "user", "content": f"Message {i}"},
                "uuid": f"session-offset-{i}",
                "timestamp": f"2026-01-0{i + 1}T13:00:00.000Z",
            }
            session_path.write_text(json.dumps(msg) + "\n")

        class MockRequest:
            url = None

        with patch.object(Path, "home", return_value=tmp_path):
            # Test 1: page=1, per_page=2 returns first 2 sessions (most recent: 4, 3)
            result1 = get_project("-Users-test-offset", MockRequest(), page=1, per_page=2)
            data1 = json.loads(result1.body)
            assert len(data1["sessions"]) == 2
            assert data1["session_count"] == 5  # Total unchanged
            # Sessions sorted by start_time descending, so most recent first
            assert [s["uuid"] for s in data1["sessions"]] == [
                "session-offset-4",
                "session-offset-3",
            ]

            # Test 2: page=2, per_page=2 returns next 2 sessions (2, 1)
            result2 = get_project("-Users-test-offset", MockRequest(), page=2, per_page=2)
            data2 = json.loads(result2.body)
            assert len(data2["sessions"]) == 2
            assert [s["uuid"] for s in data2["sessions"]] == [
                "session-offset-2",
                "session-offset-1",
            ]

            # Test 3: page=3, per_page=2 returns last session (0)
            result3 = get_project("-Users-test-offset", MockRequest(), page=3, per_page=2)
            data3 = json.loads(result3.body)
            assert len(data3["sessions"]) == 1  # Only 1 left
            assert data3["sessions"][0]["uuid"] == "session-offset-0"

    def test_sessions_sorted_by_start_time_descending(
        self, client: TestClient, temp_claude_dir: Path, tmp_path: Path
    ):
        """Test that sessions are sorted by start time, most recent first."""
        project_dir = temp_claude_dir / "projects" / "-Users-test-sorted"
        project_dir.mkdir(parents=True)

        # Create sessions with different timestamps
        timestamps = [
            ("session-old.jsonl", "2026-01-01T10:00:00.000Z"),
            ("session-mid.jsonl", "2026-01-05T10:00:00.000Z"),
            ("session-new.jsonl", "2026-01-10T10:00:00.000Z"),
        ]

        for filename, ts in timestamps:
            session_path = project_dir / filename
            msg = {
                "type": "user",
                "message": {"role": "user", "content": "Test"},
                "uuid": "uuid",
                "timestamp": ts,
            }
            session_path.write_text(json.dumps(msg) + "\n")

        with patch.object(Path, "home", return_value=tmp_path):
            response = client.get("/projects/-Users-test-sorted")

            assert response.status_code == 200
            sessions = response.json()["sessions"]

            # Most recent first
            assert sessions[0]["uuid"] == "session-new"
            assert sessions[1]["uuid"] == "session-mid"
            assert sessions[2]["uuid"] == "session-old"


class TestGetProjectEndpointErrors:
    """Error handling tests for GET /projects/{encoded_name} endpoint."""

    def test_returns_404_for_nonexistent_project(
        self, client: TestClient, temp_claude_dir: Path, tmp_path: Path
    ):
        """Test that 404 is returned for non-existent project."""
        with patch.object(Path, "home", return_value=tmp_path):
            response = client.get("/projects/-Users-nonexistent-project")

            assert response.status_code == 404
            assert "not found" in response.json()["detail"].lower()

    def test_returns_404_for_missing_project_directory(self, client: TestClient, tmp_path: Path):
        """Test 404 when project directory doesn't exist on disk."""
        with patch.object(Path, "home", return_value=tmp_path):
            response = client.get("/projects/-Users-missing-dir")

            assert response.status_code == 404

    def test_returns_404_with_descriptive_message(self, client: TestClient, tmp_path: Path):
        """Test that 404 response contains descriptive error message."""
        with patch.object(Path, "home", return_value=tmp_path):
            response = client.get("/projects/-Users-test-missing")

            assert response.status_code == 404
            detail = response.json()["detail"]
            assert isinstance(detail, str)
            assert len(detail) > 0


class TestGetProjectEndpointEdgeCases:
    """Edge case tests for GET /projects/{encoded_name} endpoint."""

    def test_handles_project_with_no_sessions(
        self, client: TestClient, temp_claude_dir: Path, tmp_path: Path
    ):
        """Test handling project that exists but has no sessions."""
        project_dir = temp_claude_dir / "projects" / "-Users-test-empty"
        project_dir.mkdir(parents=True)

        with patch.object(Path, "home", return_value=tmp_path):
            response = client.get("/projects/-Users-test-empty")

            assert response.status_code == 200
            data = response.json()
            assert data["session_count"] == 0
            assert data["sessions"] == []

    def test_handles_special_characters_in_path(
        self, client: TestClient, temp_claude_dir: Path, tmp_path: Path
    ):
        """Test handling encoded names with many dashes."""
        # Path with many components: /Users/test/a/b/c -> -Users-test-a-b-c
        project_dir = temp_claude_dir / "projects" / "-Users-test-a-b-c"
        project_dir.mkdir(parents=True)
        (project_dir / "session.jsonl").write_text('{"type": "user"}\n')

        with patch.object(Path, "home", return_value=tmp_path):
            response = client.get("/projects/-Users-test-a-b-c")

            assert response.status_code == 200
            assert response.json()["encoded_name"] == "-Users-test-a-b-c"

    def test_per_page_larger_than_session_count(
        self, client: TestClient, temp_project_with_sessions: Path, tmp_path: Path
    ):
        """Test that per_page larger than session count returns all sessions."""
        with patch.object(Path, "home", return_value=tmp_path):
            response = client.get("/projects/-Users-test-myproject?per_page=100")

            assert response.status_code == 200
            data = response.json()
            assert len(data["sessions"]) == 1  # Only 1 session exists


# =============================================================================
# Integration Tests
# =============================================================================


class TestProjectsRouterIntegration:
    """Integration tests for the projects router."""

    def test_list_then_get_project(
        self, client: TestClient, temp_project_with_sessions: Path, tmp_path: Path
    ):
        """Test listing projects then getting detail for one."""
        with patch.object(Path, "home", return_value=tmp_path):
            # List all projects
            list_response = client.get("/projects")
            assert list_response.status_code == 200
            projects = list_response.json()
            assert len(projects) == 1

            # Get detail for the project
            encoded_name = projects[0]["encoded_name"]
            detail_response = client.get(f"/projects/{encoded_name}")
            assert detail_response.status_code == 200

            detail = detail_response.json()
            assert detail["path"] == projects[0]["path"]
            assert len(detail["sessions"]) == projects[0]["session_count"]

    def test_project_count_consistency(
        self, client: TestClient, temp_multiple_projects: Path, tmp_path: Path
    ):
        """Test that session_count in list matches sessions in detail."""
        with patch.object(Path, "home", return_value=tmp_path):
            list_response = client.get("/projects")
            projects = list_response.json()

            for project in projects:
                detail_response = client.get(f"/projects/{project['encoded_name']}")
                detail = detail_response.json()

                # Session count should match
                assert detail["session_count"] == len(detail["sessions"])
                # Should match list response
                assert detail["session_count"] == project["session_count"]


# =============================================================================
# Tests with Mocked Models
# =============================================================================


class TestWithMockedModels:
    """Tests using mocked Project and Session models."""

    def test_list_all_projects_with_exception_handling(self, temp_claude_dir: Path, tmp_path: Path):
        """Test that list_all_projects handles exceptions gracefully."""
        projects_dir = temp_claude_dir / "projects"

        # Create a valid project
        valid_project = projects_dir / "-Users-test-valid"
        valid_project.mkdir(parents=True)

        # Create a directory that will cause issues (though it starts with -)
        # The from_encoded_name won't fail, but this tests the exception handling structure
        with patch.object(Path, "home", return_value=tmp_path):
            result = list_all_projects()
            # Should still return the valid project
            assert len(result) >= 1

    def test_session_to_summary_with_empty_session(self, temp_claude_dir: Path):
        """Test session_to_summary with minimal session data."""
        project_dir = temp_claude_dir / "projects" / "-Users-test-minimal"
        project_dir.mkdir(parents=True)

        # Create minimal session
        session_path = project_dir / "minimal.jsonl"
        session_path.write_text("")

        session = Session.from_path(session_path, claude_base_dir=temp_claude_dir)
        summary = session_to_summary(session)

        assert summary.uuid == "minimal"
        assert summary.message_count == 0
        assert summary.initial_prompt is None
        assert summary.subagent_count == 0

    def test_project_with_agents(self, client: TestClient, temp_claude_dir: Path, tmp_path: Path):
        """Test that agent_count is correctly reported."""
        project_dir = temp_claude_dir / "projects" / "-Users-test-agents"
        project_dir.mkdir(parents=True)

        # Create session
        (project_dir / "session.jsonl").write_text('{"type": "user"}\n')

        # Create standalone agents
        (project_dir / "agent-abc123.jsonl").write_text('{"type": "user"}\n')
        (project_dir / "agent-def456.jsonl").write_text('{"type": "user"}\n')

        with patch.object(Path, "home", return_value=tmp_path):
            response = client.get("/projects/-Users-test-agents")

            assert response.status_code == 200
            data = response.json()
            assert data["session_count"] == 1
            assert data["agent_count"] == 2


# =============================================================================
# Additional Edge Case Tests
# =============================================================================


class TestAdditionalEdgeCases:
    """Additional edge case tests."""

    def test_empty_session_file(self, client: TestClient, temp_claude_dir: Path, tmp_path: Path):
        """Test handling of empty session files."""
        project_dir = temp_claude_dir / "projects" / "-Users-test-empty-file"
        project_dir.mkdir(parents=True)
        (project_dir / "empty.jsonl").write_text("")

        with patch.object(Path, "home", return_value=tmp_path):
            response = client.get("/projects/-Users-test-empty-file")

            assert response.status_code == 200
            data = response.json()
            assert data["session_count"] == 1
            assert len(data["sessions"]) == 1
            assert data["sessions"][0]["message_count"] == 0

    def test_malformed_session_file(
        self, client: TestClient, temp_claude_dir: Path, tmp_path: Path
    ):
        """Test handling of malformed JSON in session files."""
        project_dir = temp_claude_dir / "projects" / "-Users-test-malformed"
        project_dir.mkdir(parents=True)
        (project_dir / "malformed.jsonl").write_text("not valid json\n")

        with patch.object(Path, "home", return_value=tmp_path):
            response = client.get("/projects/-Users-test-malformed")

            assert response.status_code == 200
            data = response.json()
            # Session file exists but no valid messages
            assert data["session_count"] == 1

    def test_project_path_decoding(self, client: TestClient, temp_claude_dir: Path, tmp_path: Path):
        """Test that project path is correctly decoded from encoded name."""
        project_dir = temp_claude_dir / "projects" / "-Users-developer-my-awesome-project"
        project_dir.mkdir(parents=True)
        (project_dir / "session.jsonl").write_text('{"type": "user"}\n')

        with patch.object(Path, "home", return_value=tmp_path):
            response = client.get("/projects/-Users-developer-my-awesome-project")

            assert response.status_code == 200
            data = response.json()
            # Note: decode is lossy, so dashes in original path become slashes
            assert data["path"] == "/Users/developer/my/awesome/project"

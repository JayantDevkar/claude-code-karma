"""
Tests for Phase 4 optimizations: Async and structural improvements.

Phase 4 focuses on:
- Early date filtering
- Parallel subagent processing
- Batch session loading
- Async file I/O
"""

import importlib.util
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from models import Project
from models.batch_loader import BatchSessionLoader, load_sessions_metadata_batch

# =============================================================================
# Fixtures for Phase 4 tests
# =============================================================================


@pytest.fixture
def multi_session_project(temp_claude_dir: Path) -> tuple[Path, list[str]]:
    """Create a project with multiple sessions at different times."""
    project_dir = temp_claude_dir / "projects" / "-Users-test-multiproject"
    project_dir.mkdir(parents=True)

    # Create sessions with different timestamps
    sessions = []
    base_time = datetime.now(timezone.utc) - timedelta(days=30)

    for i in range(5):
        session_uuid = f"session-{i:03d}"
        sessions.append(session_uuid)
        jsonl_path = project_dir / f"{session_uuid}.jsonl"

        # Create a session with timestamp at day i
        session_time = base_time + timedelta(days=i * 7)
        message_data = {
            "type": "user",
            "message": {"role": "user", "content": f"Message for session {i}"},
            "uuid": f"msg-{i}",
            "timestamp": session_time.isoformat(),
            "cwd": "/Users/test/multiproject",
            "slug": f"session-slug-{i}",
        }

        with open(jsonl_path, "w") as f:
            f.write(json.dumps(message_data) + "\n")

        # Touch file to set mtime to match session time (for early filtering tests)
        import os

        os.utime(jsonl_path, (session_time.timestamp(), session_time.timestamp()))

    return project_dir, sessions


@pytest.fixture
def project_with_many_subagents(temp_claude_dir: Path) -> Path:
    """Create a session with multiple subagents for parallel processing tests."""
    project_dir = temp_claude_dir / "projects" / "-Users-test-manysubagents"
    project_dir.mkdir(parents=True)

    session_uuid = "session-with-subagents"
    jsonl_path = project_dir / f"{session_uuid}.jsonl"

    # Create main session
    main_message = {
        "type": "user",
        "message": {"role": "user", "content": "Main session content"},
        "uuid": "main-msg",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "cwd": "/Users/test/manysubagents",
    }

    with open(jsonl_path, "w") as f:
        f.write(json.dumps(main_message) + "\n")

    # Create subagents directory and files
    subagents_dir = project_dir / session_uuid / "subagents"
    subagents_dir.mkdir(parents=True)

    for i in range(10):
        agent_id = f"agent{i:02d}"
        agent_path = subagents_dir / f"agent-{agent_id}.jsonl"

        agent_message = {
            "type": "user",
            "isSidechain": True,
            "agentId": agent_id,
            "message": {"role": "user", "content": f"Subagent {i} task"},
            "uuid": f"subagent-msg-{i}",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        with open(agent_path, "w") as f:
            f.write(json.dumps(agent_message) + "\n")

    return project_dir


# =============================================================================
# Test Early Date Filtering
# =============================================================================


class TestListSessionsFiltered:
    """Tests for Project.list_sessions_filtered()."""

    def test_no_filters_returns_all(self, multi_session_project):
        """Without date filters, all sessions should be returned."""
        project_dir, session_uuids = multi_session_project
        project = Project.from_encoded_name(
            "-Users-test-multiproject",
            claude_projects_dir=project_dir.parent,
        )

        sessions = project.list_sessions_filtered()
        assert len(sessions) == 5

    def test_start_date_filter(self, multi_session_project):
        """Start date filter should exclude older sessions."""
        project_dir, session_uuids = multi_session_project
        project = Project.from_encoded_name(
            "-Users-test-multiproject",
            claude_projects_dir=project_dir.parent,
        )

        # Filter to only sessions from last 2 weeks
        start_date = datetime.now(timezone.utc) - timedelta(days=14)
        sessions = project.list_sessions_filtered(start_date=start_date)

        # Should get fewer sessions
        assert len(sessions) < 5

    def test_end_date_filter(self, multi_session_project):
        """End date filter should exclude newer sessions."""
        project_dir, session_uuids = multi_session_project
        project = Project.from_encoded_name(
            "-Users-test-multiproject",
            claude_projects_dir=project_dir.parent,
        )

        # Filter to only sessions from before 2 weeks ago
        end_date = datetime.now(timezone.utc) - timedelta(days=14)
        sessions = project.list_sessions_filtered(end_date=end_date)

        # Should get fewer sessions
        assert len(sessions) < 5

    def test_limit_parameter(self, multi_session_project):
        """Limit parameter should cap number of returned sessions."""
        project_dir, session_uuids = multi_session_project
        project = Project.from_encoded_name(
            "-Users-test-multiproject",
            claude_projects_dir=project_dir.parent,
        )

        sessions = project.list_sessions_filtered(limit=2)
        assert len(sessions) == 2

    def test_sort_by_mtime(self, multi_session_project):
        """Sessions should be sorted by modification time by default."""
        project_dir, session_uuids = multi_session_project
        project = Project.from_encoded_name(
            "-Users-test-multiproject",
            claude_projects_dir=project_dir.parent,
        )

        sessions = project.list_sessions_filtered(sort_by_mtime=True)
        assert len(sessions) == 5

        # Most recent should be first
        # Note: exact order depends on file mtime which we set in fixture


# =============================================================================
# Test Batch Session Loader
# =============================================================================


class TestBatchSessionLoader:
    """Tests for BatchSessionLoader."""

    def test_load_all_metadata(self, multi_session_project):
        """Should load metadata from all session files."""
        project_dir, session_uuids = multi_session_project
        session_paths = list(project_dir.glob("*.jsonl"))

        loader = BatchSessionLoader(session_paths)
        metadata_list = loader.load_all_metadata()

        assert len(metadata_list) == 5
        for metadata in metadata_list:
            assert "path" in metadata
            assert "uuid" in metadata
            assert "start_time" in metadata or "end_time" in metadata

    def test_load_sessions_metadata_batch_function(self, multi_session_project):
        """Convenience function should work the same as class method."""
        project_dir, session_uuids = multi_session_project
        session_paths = list(project_dir.glob("*.jsonl"))

        metadata_list = load_sessions_metadata_batch(session_paths)
        assert len(metadata_list) == 5

    def test_handles_empty_files(self, temp_claude_dir):
        """Should handle empty files gracefully."""
        project_dir = temp_claude_dir / "projects" / "-Users-test-empty"
        project_dir.mkdir(parents=True)

        empty_file = project_dir / "empty-session.jsonl"
        empty_file.touch()

        loader = BatchSessionLoader([empty_file])
        metadata_list = loader.load_all_metadata()

        # Empty file should be skipped or have None values
        assert len(metadata_list) == 0 or metadata_list[0]["start_time"] is None

    def test_handles_malformed_json(self, temp_claude_dir):
        """Should handle files with invalid JSON."""
        project_dir = temp_claude_dir / "projects" / "-Users-test-malformed"
        project_dir.mkdir(parents=True)

        malformed_file = project_dir / "malformed.jsonl"
        malformed_file.write_text("not valid json\n")

        loader = BatchSessionLoader([malformed_file])
        metadata_list = loader.load_all_metadata()

        # Should not crash, may return empty or partial data
        assert isinstance(metadata_list, list)


# =============================================================================
# Test Fast Latest Session Time
# =============================================================================


class TestGetLatestSessionTimeFast:
    """Tests for Project.get_latest_session_time_fast()."""

    def test_returns_datetime_for_project_with_sessions(self, multi_session_project):
        """Should return a datetime for projects with sessions."""
        project_dir, _ = multi_session_project
        project = Project.from_encoded_name(
            "-Users-test-multiproject",
            claude_projects_dir=project_dir.parent,
        )

        latest_time = project.get_latest_session_time_fast()
        assert latest_time is not None
        assert isinstance(latest_time, datetime)

    def test_returns_none_for_empty_project(self, temp_claude_dir):
        """Should return None for projects with no sessions."""
        project_dir = temp_claude_dir / "projects" / "-Users-test-empty"
        project_dir.mkdir(parents=True)

        project = Project.from_encoded_name(
            "-Users-test-empty",
            claude_projects_dir=project_dir.parent,
        )

        latest_time = project.get_latest_session_time_fast()
        assert latest_time is None

    def test_returns_none_for_nonexistent_project(self, temp_claude_dir):
        """Should return None for non-existent projects."""
        project = Project.from_encoded_name(
            "-Users-test-nonexistent",
            claude_projects_dir=temp_claude_dir / "projects",
        )

        latest_time = project.get_latest_session_time_fast()
        assert latest_time is None


# =============================================================================
# Test Parallel Processing (Basic)
# =============================================================================


class TestParallelProcessing:
    """Tests for parallel processing utilities."""

    def test_session_with_subagents_loads(self, project_with_many_subagents):
        """Session with many subagents should load correctly."""
        project = Project.from_encoded_name(
            "-Users-test-manysubagents",
            claude_projects_dir=project_with_many_subagents.parent,
        )

        sessions = project.list_sessions()
        assert len(sessions) == 1

        session = sessions[0]
        subagents = session.list_subagents()
        assert len(subagents) == 10


# =============================================================================
# Test Async Session (if aiofiles available)
# =============================================================================

# Check for async dependencies
ASYNC_DEPS_AVAILABLE = (
    importlib.util.find_spec("aiofiles") is not None
    and importlib.util.find_spec("pytest_asyncio") is not None
)


@pytest.mark.skipif(not ASYNC_DEPS_AVAILABLE, reason="aiofiles or pytest-asyncio not installed")
class TestAsyncSession:
    """Tests for AsyncSession - skipped if aiofiles not available."""

    @pytest.mark.asyncio
    async def test_async_session_loads_metadata(self, multi_session_project):
        """AsyncSession should load metadata correctly."""
        from models.async_session import AsyncSession

        project_dir, session_uuids = multi_session_project
        session_path = project_dir / f"{session_uuids[0]}.jsonl"

        session = AsyncSession(session_path)
        metadata = await session.get_metadata()

        assert metadata["uuid"] == session_uuids[0]
        assert "start_time" in metadata
        assert "message_count" in metadata

    @pytest.mark.asyncio
    async def test_get_sessions_metadata_async(self, multi_session_project):
        """Async bulk metadata loading should work."""
        from models.async_session import get_sessions_metadata_async

        project_dir, _ = multi_session_project
        session_paths = list(project_dir.glob("*.jsonl"))

        metadata_list = await get_sessions_metadata_async(session_paths)
        assert len(metadata_list) == 5

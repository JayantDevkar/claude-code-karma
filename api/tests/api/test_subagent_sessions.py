"""
API tests for subagent sessions endpoints.

Tests cover:
- GET /{encoded_name}/{session_uuid}/agents/{agent_id}/tasks endpoint
"""

import json

# Import the FastAPI app
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

api_path = Path(__file__).parent.parent.parent
sys.path.insert(0, str(api_path))

from main import app


@pytest.fixture
def client():
    """Create a test client for the FastAPI app."""
    return TestClient(app)


@pytest.fixture
def setup_subagent_with_tasks(tmp_path, monkeypatch):
    """
    Create a temporary project structure with a subagent that has tasks.

    Returns a dict with encoded_name, session_uuid, and agent_id.
    """
    # Create temp ~/.claude structure
    claude_dir = tmp_path / ".claude"
    projects_dir = claude_dir / "projects"
    encoded_name = "-Users-test-myproject"
    project_dir = projects_dir / encoded_name
    project_dir.mkdir(parents=True)

    # Create session JSONL
    session_uuid = "test-session-12345"
    session_jsonl = project_dir / f"{session_uuid}.jsonl"

    session_msg = {
        "type": "user",
        "message": {"role": "user", "content": "Test session"},
        "uuid": "session-msg-1",
        "timestamp": "2026-01-08T13:00:00.000Z",
        "slug": "test-session-slug",
    }
    with open(session_jsonl, "w") as f:
        f.write(json.dumps(session_msg) + "\n")

    # Create subagent directory and file
    subagents_dir = project_dir / session_uuid / "subagents"
    subagents_dir.mkdir(parents=True)

    agent_id = "abc1234"
    agent_jsonl = subagents_dir / f"agent-{agent_id}.jsonl"

    # Create JSONL with TaskCreate and TaskUpdate events
    messages = [
        # User prompt
        {
            "type": "user",
            "isSidechain": True,
            "agentId": agent_id,
            "slug": "test-session-slug",
            "message": {"role": "user", "content": "Work on feature"},
            "uuid": "agent-msg-1",
            "timestamp": "2026-01-08T14:00:00.000Z",
        },
        # TaskCreate
        {
            "type": "assistant",
            "isSidechain": True,
            "agentId": agent_id,
            "message": {
                "role": "assistant",
                "content": [
                    {
                        "type": "tool_use",
                        "id": "toolu_task_1",
                        "name": "TaskCreate",
                        "input": {
                            "subject": "Research API",
                            "description": "Explore the API structure",
                            "activeForm": "Researching API",
                        },
                    },
                    {
                        "type": "tool_use",
                        "id": "toolu_task_2",
                        "name": "TaskCreate",
                        "input": {
                            "subject": "Implement endpoint",
                            "description": "Add the new endpoint",
                        },
                    },
                ],
            },
            "uuid": "agent-msg-2",
            "timestamp": "2026-01-08T14:01:00.000Z",
        },
        # TaskUpdate
        {
            "type": "assistant",
            "isSidechain": True,
            "agentId": agent_id,
            "message": {
                "role": "assistant",
                "content": [
                    {
                        "type": "tool_use",
                        "id": "toolu_update_1",
                        "name": "TaskUpdate",
                        "input": {
                            "taskId": "1",
                            "status": "completed",
                        },
                    },
                ],
            },
            "uuid": "agent-msg-3",
            "timestamp": "2026-01-08T14:02:00.000Z",
        },
    ]

    with open(agent_jsonl, "w") as f:
        for msg in messages:
            f.write(json.dumps(msg) + "\n")

    # Monkeypatch the claude_base directory (projects_dir is derived from it)
    from config import settings

    monkeypatch.setattr(settings, "claude_base", claude_dir)

    return {
        "encoded_name": encoded_name,
        "session_uuid": session_uuid,
        "agent_id": agent_id,
    }


class TestGetSubagentTasks:
    """Tests for GET /{encoded_name}/{session_uuid}/subagents/{agent_id}/tasks endpoint."""

    def test_get_subagent_tasks_returns_tasks(self, client, setup_subagent_with_tasks):
        """Test that tasks endpoint returns tasks for a subagent."""
        data = setup_subagent_with_tasks
        url = (
            f"/agents/{data['encoded_name']}/{data['session_uuid']}/agents/{data['agent_id']}/tasks"
        )

        response = client.get(url)

        assert response.status_code == 200
        tasks = response.json()
        assert len(tasks) == 2

        # First task should be completed (TaskUpdate applied)
        task_1 = next(t for t in tasks if t["id"] == "1")
        assert task_1["subject"] == "Research API"
        assert task_1["description"] == "Explore the API structure"
        assert task_1["status"] == "completed"
        assert task_1["active_form"] == "Researching API"

        # Second task should still be pending
        task_2 = next(t for t in tasks if t["id"] == "2")
        assert task_2["subject"] == "Implement endpoint"
        assert task_2["status"] == "pending"

    def test_get_subagent_tasks_returns_404_for_missing_subagent(
        self, client, setup_subagent_with_tasks
    ):
        """Test that 404 is returned for a non-existent subagent."""
        data = setup_subagent_with_tasks
        url = f"/agents/{data['encoded_name']}/{data['session_uuid']}/agents/nonexistent/tasks"

        response = client.get(url)

        assert response.status_code == 404

    def test_get_subagent_tasks_returns_404_for_missing_session(
        self, client, setup_subagent_with_tasks
    ):
        """Test that 404 is returned for a non-existent session."""
        data = setup_subagent_with_tasks
        url = f"/agents/{data['encoded_name']}/nonexistent-session/agents/{data['agent_id']}/tasks"

        response = client.get(url)

        assert response.status_code == 404

    def test_get_subagent_tasks_returns_empty_list_when_no_tasks(
        self, client, tmp_path, monkeypatch
    ):
        """Test that empty list is returned when subagent has no tasks."""
        # Create temp structure with no task events
        claude_dir = tmp_path / ".claude"
        projects_dir = claude_dir / "projects"
        encoded_name = "-Users-test-notasks"
        project_dir = projects_dir / encoded_name
        project_dir.mkdir(parents=True)

        session_uuid = "no-tasks-session"
        session_jsonl = project_dir / f"{session_uuid}.jsonl"
        with open(session_jsonl, "w") as f:
            f.write(
                json.dumps(
                    {
                        "type": "user",
                        "message": {"role": "user", "content": "test"},
                        "uuid": "msg-1",
                        "timestamp": "2026-01-08T13:00:00.000Z",
                    }
                )
                + "\n"
            )

        # Create subagent with no task events
        subagents_dir = project_dir / session_uuid / "subagents"
        subagents_dir.mkdir(parents=True)
        agent_id = "notasks"
        agent_jsonl = subagents_dir / f"agent-{agent_id}.jsonl"
        with open(agent_jsonl, "w") as f:
            f.write(
                json.dumps(
                    {
                        "type": "user",
                        "isSidechain": True,
                        "agentId": agent_id,
                        "message": {"role": "user", "content": "test"},
                        "uuid": "agent-msg-1",
                        "timestamp": "2026-01-08T14:00:00.000Z",
                    }
                )
                + "\n"
            )

        # Monkeypatch the claude_base directory (projects_dir is derived from it)
        from config import settings

        monkeypatch.setattr(settings, "claude_base", claude_dir)

        url = f"/agents/{encoded_name}/{session_uuid}/agents/{agent_id}/tasks"
        response = client.get(url)

        assert response.status_code == 200
        assert response.json() == []

    def test_get_subagent_tasks_has_cache_headers(self, client, setup_subagent_with_tasks):
        """Test that response includes cache control headers."""
        data = setup_subagent_with_tasks
        url = (
            f"/agents/{data['encoded_name']}/{data['session_uuid']}/agents/{data['agent_id']}/tasks"
        )

        response = client.get(url)

        assert response.status_code == 200
        assert "cache-control" in response.headers
        # Should have private caching
        assert "private" in response.headers["cache-control"]

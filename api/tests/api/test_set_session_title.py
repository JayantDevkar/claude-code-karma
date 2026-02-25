"""
Tests for POST /sessions/{uuid}/title endpoint.
"""

import json

import pytest
from fastapi.testclient import TestClient

from main import app
from services.session_title_cache import title_cache


@pytest.fixture
def client():
    """Create test client."""
    return TestClient(app)


@pytest.fixture
def sample_session_for_title(mock_claude_base):
    """Create a sample session for testing title setting."""
    # Create project directory
    project_dir = mock_claude_base / "projects" / "-Users-test-myproject"
    project_dir.mkdir(parents=True, exist_ok=True)

    # Create session JSONL
    session_uuid = "test-title-session-uuid"
    session_file = project_dir / f"{session_uuid}.jsonl"

    session_data = [
        {
            "type": "user",
            "uuid": "msg-1",
            "timestamp": "2024-01-01T10:00:00Z",
            "message": {"role": "user", "content": "Test message"},
        },
        {
            "type": "assistant",
            "uuid": "msg-2",
            "timestamp": "2024-01-01T10:01:00Z",
            "message": {
                "role": "assistant",
                "content": [{"type": "text", "text": "Response"}],
            },
        },
    ]

    with open(session_file, "w") as f:
        for entry in session_data:
            f.write(json.dumps(entry) + "\n")

    # Clear singleton cache so tests don't leak state to each other
    title_cache._project_data.pop("-Users-test-myproject", None)
    disk_cache = title_cache._cache_path("-Users-test-myproject")
    if disk_cache.is_file():
        disk_cache.unlink()

    return session_uuid, "-Users-test-myproject"


class TestSetSessionTitle:
    """Tests for POST /sessions/{uuid}/title endpoint."""

    def test_set_title_success(self, client, sample_session_for_title):
        """Test setting a title successfully."""
        session_uuid, encoded_name = sample_session_for_title
        new_title = "My New Session Title"

        response = client.post(
            f"/sessions/{session_uuid}/title",
            json={"title": new_title},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert data["uuid"] == session_uuid
        assert data["title"] == new_title

        # Verify title was cached
        cached_titles = title_cache.get_titles(encoded_name, session_uuid)
        assert new_title in cached_titles

    def test_set_title_prepends_to_existing(self, client, sample_session_for_title):
        """Test that new titles are prepended to existing ones."""
        session_uuid, encoded_name = sample_session_for_title

        # Set first title
        client.post(
            f"/sessions/{session_uuid}/title",
            json={"title": "First Title"},
        )

        # Set second title
        response = client.post(
            f"/sessions/{session_uuid}/title",
            json={"title": "Second Title"},
        )

        assert response.status_code == 200

        # Verify both titles exist with second one first
        cached_titles = title_cache.get_titles(encoded_name, session_uuid)
        assert cached_titles[0] == "Second Title"
        assert "First Title" in cached_titles

    def test_set_title_session_not_found(self, client):
        """Test setting title for non-existent session."""
        response = client.post(
            "/sessions/non-existent-uuid/title",
            json={"title": "Test Title"},
        )

        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()

    def test_set_title_duplicate_not_added(self, client, sample_session_for_title):
        """Test that duplicate titles are not added multiple times."""
        session_uuid, encoded_name = sample_session_for_title
        title = "Same Title"

        # Set title twice
        client.post(f"/sessions/{session_uuid}/title", json={"title": title})
        client.post(f"/sessions/{session_uuid}/title", json={"title": title})

        # Verify only one instance exists
        cached_titles = title_cache.get_titles(encoded_name, session_uuid)
        assert cached_titles.count(title) == 1

    def test_set_title_empty_string(self, client, sample_session_for_title):
        """Test setting an empty title."""
        session_uuid, encoded_name = sample_session_for_title

        response = client.post(
            f"/sessions/{session_uuid}/title",
            json={"title": ""},
        )

        # Empty title should still be accepted
        assert response.status_code == 200

    def test_set_title_special_characters(self, client, sample_session_for_title):
        """Test setting title with special characters."""
        session_uuid, encoded_name = sample_session_for_title
        special_title = "Title with émojis 🎉 and special chars: <>&"

        response = client.post(
            f"/sessions/{session_uuid}/title",
            json={"title": special_title},
        )

        assert response.status_code == 200
        cached_titles = title_cache.get_titles(encoded_name, session_uuid)
        assert special_title in cached_titles

    def test_set_title_long_title(self, client, sample_session_for_title):
        """Test setting a very long title."""
        session_uuid, encoded_name = sample_session_for_title
        long_title = "A" * 1000  # 1000 character title

        response = client.post(
            f"/sessions/{session_uuid}/title",
            json={"title": long_title},
        )

        assert response.status_code == 200
        cached_titles = title_cache.get_titles(encoded_name, session_uuid)
        assert long_title in cached_titles

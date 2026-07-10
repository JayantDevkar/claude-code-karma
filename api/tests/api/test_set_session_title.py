"""
Tests for POST /sessions/{uuid}/title endpoint.
"""

import json
from pathlib import Path
from unittest.mock import patch

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


class TestSetSessionTitleOutbox:
    """Tests for Syncthing outbox write in POST /sessions/{uuid}/title."""

    @pytest.fixture
    def mock_karma_base(self, tmp_path):
        """Create a fake karma_base directory with sync-config.json."""
        karma_dir = tmp_path / ".claude_karma"
        karma_dir.mkdir()
        return karma_dir

    @pytest.fixture
    def setup_sync_config(self, mock_karma_base):
        """Write a sync-config.json with a test user_id."""
        config = {"user_id": "test-user-123", "device_name": "test-device"}
        (mock_karma_base / "sync-config.json").write_text(
            json.dumps(config), encoding="utf-8"
        )
        return "test-user-123"

    @pytest.fixture
    def setup_outbox(self, mock_karma_base, setup_sync_config):
        """Create the outbox directory for a test project."""
        user_id = setup_sync_config
        encoded_name = "-Users-test-myproject"
        outbox_dir = mock_karma_base / "remote-sessions" / user_id / encoded_name
        outbox_dir.mkdir(parents=True)
        return outbox_dir

    def test_writes_to_outbox_titles_json(
        self, client, sample_session_for_title, mock_karma_base, setup_outbox
    ):
        """When sync-config exists and outbox dir exists, title is written to outbox titles.json."""
        session_uuid, encoded_name = sample_session_for_title
        outbox_dir = setup_outbox
        new_title = "Outbox Title Test"

        from config import Settings

        with patch.object(
            Settings, "karma_base", new_callable=lambda: property(lambda self: mock_karma_base)
        ):
            response = client.post(
                f"/sessions/{session_uuid}/title",
                json={"title": new_title},
            )

        assert response.status_code == 200

        # Verify titles.json was written in the outbox
        titles_path = outbox_dir / "titles.json"
        assert titles_path.is_file(), "titles.json should have been created in outbox"

        data = json.loads(titles_path.read_text(encoding="utf-8"))
        assert data["version"] == 1
        assert session_uuid in data["titles"]
        assert data["titles"][session_uuid]["title"] == new_title
        assert data["titles"][session_uuid]["source"] == "hook"

    def test_skips_when_no_sync_config(
        self, client, sample_session_for_title, mock_karma_base
    ):
        """No error when sync-config.json doesn't exist."""
        session_uuid, _encoded_name = sample_session_for_title

        # mock_karma_base exists but has no sync-config.json
        from config import Settings

        with patch.object(
            Settings, "karma_base", new_callable=lambda: property(lambda self: mock_karma_base)
        ):
            response = client.post(
                f"/sessions/{session_uuid}/title",
                json={"title": "No Config Title"},
            )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"

    def test_skips_when_outbox_missing(
        self, client, sample_session_for_title, mock_karma_base, setup_sync_config
    ):
        """No error when outbox directory doesn't exist (sync-config exists but no outbox dir)."""
        session_uuid, _encoded_name = sample_session_for_title

        # sync-config.json exists but no remote-sessions dir
        from config import Settings

        with patch.object(
            Settings, "karma_base", new_callable=lambda: property(lambda self: mock_karma_base)
        ):
            response = client.post(
                f"/sessions/{session_uuid}/title",
                json={"title": "No Outbox Title"},
            )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"

        # Verify no titles.json was created anywhere
        remote_dir = mock_karma_base / "remote-sessions"
        if remote_dir.exists():
            titles_files = list(remote_dir.rglob("titles.json"))
            assert len(titles_files) == 0, "No titles.json should be created when outbox is missing"

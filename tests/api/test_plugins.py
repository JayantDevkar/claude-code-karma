"""
Unit tests for the plugins router API endpoints.

Tests cover:
- GET /plugins - List all installed plugins
- GET /plugins/stats - Get plugin statistics
- GET /plugins/{plugin_name} - Get specific plugin details
- Error handling (404 for missing plugins)
- Empty state handling
"""

import sys
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

# Set up paths before any imports from the project
_tests_dir = Path(__file__).parent
_api_dir = _tests_dir.parent.parent
_root_dir = _api_dir.parent

if str(_root_dir) not in sys.path:
    sys.path.insert(0, str(_root_dir))
if str(_api_dir) not in sys.path:
    sys.path.insert(0, str(_api_dir))

from models import InstalledPlugins, PluginInstallation
from routers import plugins

# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def app():
    """Create a FastAPI app with the plugins router."""
    test_app = FastAPI()
    test_app.include_router(plugins.router, prefix="/plugins")
    return test_app


@pytest.fixture
def client(app):
    """Create a test client for the app."""
    return TestClient(app)


@pytest.fixture
def sample_plugins_data():
    """Sample plugins data matching Claude Code format."""
    return {
        "version": 2,
        "plugins": {
            "github@claude-plugins-official": [
                {
                    "scope": "user",
                    "installPath": "/Users/test/.claude/plugins/github",
                    "version": "e30768372b41",
                    "installedAt": "2026-01-03T01:14:29.419Z",
                    "lastUpdated": "2026-01-21T09:41:35.704Z",
                }
            ],
            "playwright@claude-plugins-official": [
                {
                    "scope": "user",
                    "installPath": "/Users/test/.claude/plugins/playwright",
                    "version": "abc123def",
                    "installedAt": "2026-01-10T00:00:00.000Z",
                    "lastUpdated": "2026-01-15T12:00:00.000Z",
                },
                {
                    "scope": "project",
                    "installPath": "/Users/test/project/.claude/plugins/playwright",
                    "version": "abc123def",
                    "installedAt": "2026-01-12T00:00:00.000Z",
                    "lastUpdated": "2026-01-12T00:00:00.000Z",
                },
            ],
        },
    }


@pytest.fixture
def sample_installed_plugins(sample_plugins_data):
    """Create InstalledPlugins model from sample data."""
    # Parse datetime strings
    for _plugin_name, installations in sample_plugins_data["plugins"].items():
        for inst in installations:
            inst["installedAt"] = datetime.fromisoformat(inst["installedAt"].replace("Z", "+00:00"))
            inst["lastUpdated"] = datetime.fromisoformat(inst["lastUpdated"].replace("Z", "+00:00"))
    return InstalledPlugins.model_validate(sample_plugins_data)


@pytest.fixture
def mock_plugins_file(tmp_path: Path):
    """Create a mock plugins file that exists."""
    plugins_file = tmp_path / "installed_plugins.json"
    plugins_file.write_text("{}")  # Create empty file so it exists
    return plugins_file


# =============================================================================
# Test List Plugins Endpoint
# =============================================================================


class TestListPlugins:
    """Tests for GET /plugins endpoint."""

    def test_list_plugins_returns_overview(self, client, sample_installed_plugins):
        """Test that list_plugins returns PluginsOverview."""
        with patch("routers.plugins.load_installed_plugins") as mock_load:
            mock_load.return_value = sample_installed_plugins

            response = client.get("/plugins")

            assert response.status_code == 200
            data = response.json()
            assert "version" in data
            assert "total_plugins" in data
            assert "total_installations" in data
            assert "plugins" in data

    def test_list_plugins_counts(self, client, sample_installed_plugins, mock_plugins_file):
        """Test that counts are correct."""
        with (
            patch("routers.plugins.get_plugins_file", return_value=mock_plugins_file),
            patch("routers.plugins.load_installed_plugins") as mock_load,
        ):
            mock_load.return_value = sample_installed_plugins

            response = client.get("/plugins")

            data = response.json()
            assert data["version"] == 2
            assert data["total_plugins"] == 2
            assert data["total_installations"] == 3  # 1 + 2

    def test_list_plugins_summaries(self, client, sample_installed_plugins, mock_plugins_file):
        """Test that plugin summaries are correct."""
        with (
            patch("routers.plugins.get_plugins_file", return_value=mock_plugins_file),
            patch("routers.plugins.load_installed_plugins") as mock_load,
        ):
            mock_load.return_value = sample_installed_plugins

            response = client.get("/plugins")

            data = response.json()
            plugins_list = data["plugins"]
            assert len(plugins_list) == 2

            # Find github plugin
            github = next(p for p in plugins_list if p["name"] == "github@claude-plugins-official")
            assert github["installation_count"] == 1
            assert "user" in github["scopes"]

            # Find playwright plugin
            playwright = next(
                p for p in plugins_list if p["name"] == "playwright@claude-plugins-official"
            )
            assert playwright["installation_count"] == 2
            assert "user" in playwright["scopes"]
            assert "project" in playwright["scopes"]

    def test_list_plugins_empty_when_no_file(self, client, tmp_path):
        """Test that empty response when no plugins file."""
        with patch("routers.plugins.get_plugins_file") as mock_get:
            mock_get.return_value = tmp_path / "nonexistent.json"
            with patch("routers.plugins.load_installed_plugins") as mock_load:
                mock_load.return_value = None

                response = client.get("/plugins")

                assert response.status_code == 200
                data = response.json()
                assert data["total_plugins"] == 0
                assert data["total_installations"] == 0
                assert data["plugins"] == []


# =============================================================================
# Test Plugin Stats Endpoint
# =============================================================================


class TestPluginStats:
    """Tests for GET /plugins/stats endpoint."""

    def test_stats_returns_aggregates(self, client, sample_installed_plugins):
        """Test that stats returns correct aggregates."""
        with patch("routers.plugins.load_installed_plugins") as mock_load:
            mock_load.return_value = sample_installed_plugins

            response = client.get("/plugins/stats")

            assert response.status_code == 200
            data = response.json()
            assert data["total_plugins"] == 2
            assert data["total_installations"] == 3
            assert data["version"] == 2

    def test_stats_by_scope(self, client, sample_installed_plugins):
        """Test that by_scope counts are correct."""
        with patch("routers.plugins.load_installed_plugins") as mock_load:
            mock_load.return_value = sample_installed_plugins

            response = client.get("/plugins/stats")

            data = response.json()
            assert "by_scope" in data
            assert data["by_scope"]["user"] == 2  # github + playwright user
            assert data["by_scope"]["project"] == 1  # playwright project

    def test_stats_timestamps(self, client, sample_installed_plugins):
        """Test that oldest/newest install timestamps are included."""
        with patch("routers.plugins.load_installed_plugins") as mock_load:
            mock_load.return_value = sample_installed_plugins

            response = client.get("/plugins/stats")

            data = response.json()
            assert "oldest_install" in data
            assert "newest_install" in data
            assert data["oldest_install"] is not None
            assert data["newest_install"] is not None

    def test_stats_empty_when_no_plugins(self, client):
        """Test stats response when no plugins installed."""
        with patch("routers.plugins.load_installed_plugins") as mock_load:
            mock_load.return_value = None

            response = client.get("/plugins/stats")

            assert response.status_code == 200
            data = response.json()
            assert data["total_plugins"] == 0
            assert data["total_installations"] == 0
            assert data["by_scope"] == {}
            assert data["oldest_install"] is None
            assert data["newest_install"] is None


# =============================================================================
# Test Get Plugin Detail Endpoint
# =============================================================================


class TestGetPluginDetail:
    """Tests for GET /plugins/{plugin_name} endpoint."""

    def test_get_plugin_returns_detail(self, client, sample_installed_plugins):
        """Test that get_plugin returns plugin detail."""
        with patch("routers.plugins.load_installed_plugins") as mock_load:
            mock_load.return_value = sample_installed_plugins

            response = client.get("/plugins/github@claude-plugins-official")

            assert response.status_code == 200
            data = response.json()
            assert data["name"] == "github@claude-plugins-official"
            assert "installations" in data
            assert len(data["installations"]) == 1

    def test_get_plugin_installations(self, client, sample_installed_plugins):
        """Test that installations are returned correctly."""
        with patch("routers.plugins.load_installed_plugins") as mock_load:
            mock_load.return_value = sample_installed_plugins

            response = client.get("/plugins/playwright@claude-plugins-official")

            data = response.json()
            assert len(data["installations"]) == 2

            # Check first installation
            user_inst = next(i for i in data["installations"] if i["scope"] == "user")
            assert user_inst["plugin_name"] == "playwright@claude-plugins-official"
            assert user_inst["version"] == "abc123def"

    def test_get_plugin_not_found(self, client, sample_installed_plugins):
        """Test 404 when plugin not found."""
        with patch("routers.plugins.load_installed_plugins") as mock_load:
            mock_load.return_value = sample_installed_plugins

            response = client.get("/plugins/nonexistent-plugin")

            assert response.status_code == 404
            assert "not found" in response.json()["detail"].lower()

    def test_get_plugin_no_plugins_file(self, client):
        """Test 404 when no plugins file exists."""
        with patch("routers.plugins.load_installed_plugins") as mock_load:
            mock_load.return_value = None

            response = client.get("/plugins/any-plugin")

            assert response.status_code == 404

    def test_get_plugin_url_encoded_name(self, client, sample_installed_plugins):
        """Test that URL-encoded plugin names work."""
        with patch("routers.plugins.load_installed_plugins") as mock_load:
            mock_load.return_value = sample_installed_plugins

            # URL encode @ as %40
            response = client.get("/plugins/github%40claude-plugins-official")

            assert response.status_code == 200
            data = response.json()
            assert data["name"] == "github@claude-plugins-official"


# =============================================================================
# Test Converter Functions
# =============================================================================


class TestConverterFunctions:
    """Tests for router converter functions."""

    def test_installation_to_schema(self):
        """Test installation_to_schema converter."""
        now = datetime.now(timezone.utc)
        installation = PluginInstallation(
            scope="user",
            installPath="/path/to/plugin",
            version="v1.0.0",
            installedAt=now,
            lastUpdated=now,
        )

        schema = plugins.installation_to_schema("test-plugin", installation)

        assert schema.plugin_name == "test-plugin"
        assert schema.scope == "user"
        assert schema.install_path == "/path/to/plugin"
        assert schema.version == "v1.0.0"
        assert schema.installed_at == now
        assert schema.last_updated == now

    def test_plugin_to_summary(self):
        """Test plugin_to_summary converter."""
        now = datetime.now(timezone.utc)
        installations = [
            PluginInstallation(
                scope="user",
                installPath="/path1",
                version="v1",
                installedAt=now,
                lastUpdated=now,
            ),
            PluginInstallation(
                scope="project",
                installPath="/path2",
                version="v2",
                installedAt=now,
                lastUpdated=now,
            ),
        ]

        summary = plugins.plugin_to_summary("test-plugin", installations)

        assert summary.name == "test-plugin"
        assert summary.installation_count == 2
        assert set(summary.scopes) == {"user", "project"}

    def test_plugin_to_detail(self):
        """Test plugin_to_detail converter."""
        now = datetime.now(timezone.utc)
        installations = [
            PluginInstallation(
                scope="user",
                installPath="/path",
                version="v1",
                installedAt=now,
                lastUpdated=now,
            )
        ]

        detail = plugins.plugin_to_detail("test-plugin", installations)

        assert detail.name == "test-plugin"
        assert len(detail.installations) == 1
        assert detail.installations[0].plugin_name == "test-plugin"

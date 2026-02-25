"""
Unit tests for Plugin model and plugin loading functions.

Tests cover:
- PluginInstallation instantiation
- Field aliases: installPath, installedAt, lastUpdated
- InstalledPlugins container
- Properties: plugin_count, total_installations
- Methods: list_all_installations, get_plugin, has_plugin
- Immutability (frozen=True)
- from_path() loading
- load_installed_plugins() convenience function
- Error handling (missing file, invalid JSON)
"""

import json
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import pytest
from pydantic import ValidationError

from models import (
    InstalledPlugins,
    PluginInstallation,
    get_plugins_file,
    load_installed_plugins,
)


class TestPluginInstallationInstantiation:
    """Tests for PluginInstallation instantiation."""

    def test_instantiation_with_all_fields(self):
        """Test PluginInstallation with all required fields."""
        now = datetime.now(timezone.utc)
        installation = PluginInstallation(
            scope="user",
            installPath="/path/to/plugin",
            version="abc123",
            installedAt=now,
            lastUpdated=now,
        )
        assert installation.scope == "user"
        assert installation.install_path == "/path/to/plugin"
        assert installation.version == "abc123"
        assert installation.installed_at == now
        assert installation.last_updated == now

    def test_instantiation_with_snake_case_fields(self):
        """Test PluginInstallation with snake_case field names."""
        now = datetime.now(timezone.utc)
        installation = PluginInstallation(
            scope="project",
            install_path="/another/path",
            version="def456",
            installed_at=now,
            last_updated=now,
        )
        assert installation.install_path == "/another/path"
        assert installation.installed_at == now
        assert installation.last_updated == now

    def test_missing_required_field_raises_error(self):
        """Test that missing required fields raise ValidationError."""
        now = datetime.now(timezone.utc)
        with pytest.raises(ValidationError):
            PluginInstallation(
                scope="user",
                # Missing installPath
                version="abc123",
                installedAt=now,
                lastUpdated=now,
            )


class TestPluginInstallationFieldAliases:
    """Tests for field aliases: installPath, installedAt, lastUpdated."""

    def test_install_path_alias(self):
        """Test that installPath alias works."""
        now = datetime.now(timezone.utc)
        installation = PluginInstallation(
            scope="user",
            installPath="/path/to/plugin",
            version="v1",
            installedAt=now,
            lastUpdated=now,
        )
        assert installation.install_path == "/path/to/plugin"

    def test_installed_at_alias(self):
        """Test that installedAt alias works."""
        now = datetime.now(timezone.utc)
        installation = PluginInstallation(
            scope="user",
            installPath="/path",
            version="v1",
            installedAt=now,
            lastUpdated=now,
        )
        assert installation.installed_at == now

    def test_last_updated_alias(self):
        """Test that lastUpdated alias works."""
        now = datetime.now(timezone.utc)
        installation = PluginInstallation(
            scope="user",
            installPath="/path",
            version="v1",
            installedAt=now,
            lastUpdated=now,
        )
        assert installation.last_updated == now

    def test_model_validate_with_aliases(self):
        """Test model_validate with aliased field names in dict."""
        now_str = "2026-01-20T10:00:00+00:00"
        data = {
            "scope": "user",
            "installPath": "/path/to/plugin",
            "version": "e30768372b41",
            "installedAt": datetime.fromisoformat(now_str),
            "lastUpdated": datetime.fromisoformat(now_str),
        }
        installation = PluginInstallation.model_validate(data)
        assert installation.install_path == "/path/to/plugin"

    def test_model_dump_with_alias(self):
        """Test that model_dump outputs with alias when by_alias=True."""
        now = datetime.now(timezone.utc)
        installation = PluginInstallation(
            scope="user",
            install_path="/path",
            version="v1",
            installed_at=now,
            last_updated=now,
        )
        dumped = installation.model_dump(by_alias=True)
        assert "installPath" in dumped
        assert "installedAt" in dumped
        assert "lastUpdated" in dumped


class TestPluginInstallationProperties:
    """Tests for PluginInstallation computed properties."""

    def test_is_user_scoped(self):
        """Test is_user_scoped property."""
        now = datetime.now(timezone.utc)
        user_install = PluginInstallation(
            scope="user",
            installPath="/path",
            version="v1",
            installedAt=now,
            lastUpdated=now,
        )
        project_install = PluginInstallation(
            scope="project",
            installPath="/path",
            version="v1",
            installedAt=now,
            lastUpdated=now,
        )
        assert user_install.is_user_scoped is True
        assert project_install.is_user_scoped is False

    def test_is_project_scoped(self):
        """Test is_project_scoped property."""
        now = datetime.now(timezone.utc)
        user_install = PluginInstallation(
            scope="user",
            installPath="/path",
            version="v1",
            installedAt=now,
            lastUpdated=now,
        )
        project_install = PluginInstallation(
            scope="project",
            installPath="/path",
            version="v1",
            installedAt=now,
            lastUpdated=now,
        )
        assert user_install.is_project_scoped is False
        assert project_install.is_project_scoped is True


class TestPluginInstallationImmutability:
    """Tests for PluginInstallation immutability (frozen=True)."""

    def test_cannot_modify_scope(self):
        """Test that scope field cannot be modified after creation."""
        now = datetime.now(timezone.utc)
        installation = PluginInstallation(
            scope="user",
            installPath="/path",
            version="v1",
            installedAt=now,
            lastUpdated=now,
        )
        with pytest.raises(ValidationError):
            installation.scope = "project"

    def test_cannot_modify_version(self):
        """Test that version field cannot be modified after creation."""
        now = datetime.now(timezone.utc)
        installation = PluginInstallation(
            scope="user",
            installPath="/path",
            version="v1",
            installedAt=now,
            lastUpdated=now,
        )
        with pytest.raises(ValidationError):
            installation.version = "v2"


class TestInstalledPluginsInstantiation:
    """Tests for InstalledPlugins container instantiation."""

    def test_instantiation_with_version_and_plugins(self):
        """Test InstalledPlugins with version and plugins dict."""
        now = datetime.now(timezone.utc)
        installation = PluginInstallation(
            scope="user",
            installPath="/path",
            version="v1",
            installedAt=now,
            lastUpdated=now,
        )
        installed = InstalledPlugins(
            version=2,
            plugins={"github@claude-plugins-official": [installation]},
        )
        assert installed.version == 2
        assert "github@claude-plugins-official" in installed.plugins

    def test_empty_plugins_dict(self):
        """Test InstalledPlugins with empty plugins dict."""
        installed = InstalledPlugins(version=2, plugins={})
        assert installed.plugin_count == 0
        assert installed.total_installations == 0


class TestInstalledPluginsProperties:
    """Tests for InstalledPlugins computed properties."""

    def test_plugin_count(self):
        """Test plugin_count property returns unique plugin count."""
        now = datetime.now(timezone.utc)
        installation = PluginInstallation(
            scope="user",
            installPath="/path",
            version="v1",
            installedAt=now,
            lastUpdated=now,
        )
        installed = InstalledPlugins(
            version=2,
            plugins={
                "plugin-a": [installation],
                "plugin-b": [installation, installation],
            },
        )
        assert installed.plugin_count == 2

    def test_total_installations(self):
        """Test total_installations sums all installations."""
        now = datetime.now(timezone.utc)
        installation = PluginInstallation(
            scope="user",
            installPath="/path",
            version="v1",
            installedAt=now,
            lastUpdated=now,
        )
        installed = InstalledPlugins(
            version=2,
            plugins={
                "plugin-a": [installation],
                "plugin-b": [installation, installation],
            },
        )
        assert installed.total_installations == 3


class TestInstalledPluginsMethods:
    """Tests for InstalledPlugins methods."""

    def test_list_all_installations(self):
        """Test list_all_installations returns tuples sorted by plugin name."""
        now = datetime.now(timezone.utc)
        inst_a = PluginInstallation(
            scope="user",
            installPath="/path/a",
            version="v1",
            installedAt=now,
            lastUpdated=now,
        )
        inst_b = PluginInstallation(
            scope="project",
            installPath="/path/b",
            version="v2",
            installedAt=now,
            lastUpdated=now,
        )
        installed = InstalledPlugins(
            version=2,
            plugins={
                "z-plugin": [inst_a],
                "a-plugin": [inst_b],
            },
        )

        all_installations = installed.list_all_installations()

        assert len(all_installations) == 2
        # Should be sorted by plugin name
        assert all_installations[0][0] == "a-plugin"
        assert all_installations[1][0] == "z-plugin"
        # Each item is (plugin_name, installation) tuple
        assert all_installations[0][1] == inst_b
        assert all_installations[1][1] == inst_a

    def test_get_plugin_returns_installations(self):
        """Test get_plugin returns list of installations for existing plugin."""
        now = datetime.now(timezone.utc)
        installation = PluginInstallation(
            scope="user",
            installPath="/path",
            version="v1",
            installedAt=now,
            lastUpdated=now,
        )
        installed = InstalledPlugins(
            version=2,
            plugins={"my-plugin": [installation]},
        )

        result = installed.get_plugin("my-plugin")

        assert result is not None
        assert len(result) == 1
        assert result[0] == installation

    def test_get_plugin_returns_none_for_missing(self):
        """Test get_plugin returns None for non-existent plugin."""
        installed = InstalledPlugins(version=2, plugins={})

        result = installed.get_plugin("nonexistent")

        assert result is None

    def test_has_plugin_true(self):
        """Test has_plugin returns True for existing plugin."""
        now = datetime.now(timezone.utc)
        installation = PluginInstallation(
            scope="user",
            installPath="/path",
            version="v1",
            installedAt=now,
            lastUpdated=now,
        )
        installed = InstalledPlugins(
            version=2,
            plugins={"my-plugin": [installation]},
        )

        assert installed.has_plugin("my-plugin") is True

    def test_has_plugin_false(self):
        """Test has_plugin returns False for non-existent plugin."""
        installed = InstalledPlugins(version=2, plugins={})

        assert installed.has_plugin("nonexistent") is False


class TestInstalledPluginsFromPath:
    """Tests for InstalledPlugins.from_path() classmethod."""

    def test_load_valid_plugins_file(self, tmp_path: Path):
        """Test loading a valid plugins JSON file."""
        plugins_file = tmp_path / "installed_plugins.json"
        plugins_data = {
            "version": 2,
            "plugins": {
                "github@claude-plugins-official": [
                    {
                        "scope": "user",
                        "installPath": "/path/to/github",
                        "version": "e30768372b41",
                        "installedAt": "2026-01-03T01:14:29.419Z",
                        "lastUpdated": "2026-01-21T09:41:35.704Z",
                    }
                ]
            },
        }
        plugins_file.write_text(json.dumps(plugins_data))

        installed = InstalledPlugins.from_path(plugins_file)

        assert installed is not None
        assert installed.version == 2
        assert installed.plugin_count == 1
        assert installed.has_plugin("github@claude-plugins-official")

        installs = installed.get_plugin("github@claude-plugins-official")
        assert len(installs) == 1
        assert installs[0].scope == "user"
        assert installs[0].version == "e30768372b41"

    def test_load_multiple_plugins(self, tmp_path: Path):
        """Test loading file with multiple plugins."""
        plugins_file = tmp_path / "installed_plugins.json"
        plugins_data = {
            "version": 2,
            "plugins": {
                "plugin-a": [
                    {
                        "scope": "user",
                        "installPath": "/path/a",
                        "version": "v1",
                        "installedAt": "2026-01-01T00:00:00Z",
                        "lastUpdated": "2026-01-01T00:00:00Z",
                    }
                ],
                "plugin-b": [
                    {
                        "scope": "user",
                        "installPath": "/path/b",
                        "version": "v1",
                        "installedAt": "2026-01-01T00:00:00Z",
                        "lastUpdated": "2026-01-01T00:00:00Z",
                    },
                    {
                        "scope": "project",
                        "installPath": "/path/b-project",
                        "version": "v2",
                        "installedAt": "2026-01-02T00:00:00Z",
                        "lastUpdated": "2026-01-02T00:00:00Z",
                    },
                ],
            },
        }
        plugins_file.write_text(json.dumps(plugins_data))

        installed = InstalledPlugins.from_path(plugins_file)

        assert installed is not None
        assert installed.plugin_count == 2
        assert installed.total_installations == 3

    def test_missing_file_returns_none(self, tmp_path: Path):
        """Test that missing file returns None."""
        nonexistent = tmp_path / "nonexistent.json"

        installed = InstalledPlugins.from_path(nonexistent)

        assert installed is None

    def test_invalid_json_returns_none(self, tmp_path: Path):
        """Test that invalid JSON returns None."""
        invalid_file = tmp_path / "invalid.json"
        invalid_file.write_text("not valid json {")

        installed = InstalledPlugins.from_path(invalid_file)

        assert installed is None

    def test_directory_path_returns_none(self, tmp_path: Path):
        """Test that passing a directory path returns None."""
        installed = InstalledPlugins.from_path(tmp_path)

        assert installed is None

    def test_empty_plugins_dict(self, tmp_path: Path):
        """Test loading file with empty plugins dict."""
        plugins_file = tmp_path / "installed_plugins.json"
        plugins_data = {"version": 2, "plugins": {}}
        plugins_file.write_text(json.dumps(plugins_data))

        installed = InstalledPlugins.from_path(plugins_file)

        assert installed is not None
        assert installed.plugin_count == 0
        assert installed.total_installations == 0


class TestGetPluginsFile:
    """Tests for get_plugins_file() function."""

    def test_returns_path_to_plugins_file(self):
        """Test that get_plugins_file returns correct path."""
        plugins_file = get_plugins_file()

        assert plugins_file.name == "installed_plugins.json"
        assert plugins_file.parent.name == "plugins"
        assert ".claude" in str(plugins_file)


class TestLoadInstalledPlugins:
    """Tests for load_installed_plugins() convenience function."""

    def test_returns_none_when_file_missing(self, tmp_path: Path):
        """Test that load_installed_plugins returns None when file doesn't exist."""
        import models.plugin as _plugin_mod

        # Clear the module-level cache so the mock is actually hit
        _plugin_mod._installed_plugins_cache = None
        _plugin_mod._installed_plugins_cache_time = None

        with patch("models.plugin.get_plugins_file") as mock_get:
            mock_get.return_value = tmp_path / "nonexistent.json"

            installed = load_installed_plugins()

            assert installed is None

        # Clear again so cached None doesn't leak to subsequent tests
        _plugin_mod._installed_plugins_cache = None
        _plugin_mod._installed_plugins_cache_time = None

    def test_loads_plugins_from_standard_location(self, tmp_path: Path):
        """Test loading plugins from the standard location."""
        import models.plugin as _plugin_mod

        # Clear the module-level cache so the mock is actually hit
        _plugin_mod._installed_plugins_cache = None
        _plugin_mod._installed_plugins_cache_time = None

        plugins_file = tmp_path / "installed_plugins.json"
        plugins_data = {
            "version": 2,
            "plugins": {
                "test-plugin": [
                    {
                        "scope": "user",
                        "installPath": "/path",
                        "version": "v1",
                        "installedAt": "2026-01-01T00:00:00Z",
                        "lastUpdated": "2026-01-01T00:00:00Z",
                    }
                ]
            },
        }
        plugins_file.write_text(json.dumps(plugins_data))

        with patch("models.plugin.get_plugins_file") as mock_get:
            mock_get.return_value = plugins_file

            installed = load_installed_plugins()

            assert installed is not None
            assert installed.plugin_count == 1

        # Clear cache after test
        _plugin_mod._installed_plugins_cache = None
        _plugin_mod._installed_plugins_cache_time = None

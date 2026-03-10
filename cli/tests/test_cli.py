"""Tests for CLI commands."""

import json
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest
from click.testing import CliRunner

from karma.main import cli
from karma.config import SyncConfig


@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture
def init_config(tmp_path, monkeypatch):
    """Initialize a config for testing."""
    config_path = tmp_path / "sync-config.json"
    monkeypatch.setattr("karma.config.SYNC_CONFIG_PATH", config_path)
    monkeypatch.setattr("karma.config.KARMA_BASE", tmp_path)
    monkeypatch.setattr("karma.main.KARMA_BASE", tmp_path)
    return config_path


class TestInitCommand:
    def test_init_creates_config(self, runner, init_config):
        result = runner.invoke(cli, ["init", "--user-id", "alice"])
        assert result.exit_code == 0
        assert "Initialized as 'alice'" in result.output
        assert init_config.exists()


class TestTeamCommands:
    def test_team_create(self, runner, init_config, mock_db):
        runner.invoke(cli, ["init", "--user-id", "alice"])
        result = runner.invoke(cli, ["team", "create", "alpha"])
        assert result.exit_code == 0
        assert "Created team 'alpha'" in result.output

        # Verify in DB
        row = mock_db.execute("SELECT * FROM sync_teams WHERE name = 'alpha'").fetchone()
        assert row is not None
        assert row["backend"] == "syncthing"

        # Verify event logged
        ev = mock_db.execute("SELECT * FROM sync_events WHERE event_type = 'team_created'").fetchone()
        assert ev is not None

    def test_team_create_duplicate(self, runner, init_config, mock_db):
        runner.invoke(cli, ["init", "--user-id", "alice"])
        runner.invoke(cli, ["team", "create", "alpha"])
        result = runner.invoke(cli, ["team", "create", "alpha"])
        assert result.exit_code != 0
        assert "already exists" in result.output

    def test_team_add_member(self, runner, init_config, mock_db):
        runner.invoke(cli, ["init", "--user-id", "alice"])
        runner.invoke(cli, ["team", "create", "alpha"])
        result = runner.invoke(cli, ["team", "add", "bob", "BOB-DEVICE-ID", "--team", "alpha"])
        assert result.exit_code == 0
        assert "Added team member 'bob'" in result.output

        # Verify in DB
        row = mock_db.execute(
            "SELECT * FROM sync_members WHERE team_name = 'alpha' AND name = 'bob'"
        ).fetchone()
        assert row is not None
        assert row["device_id"] == "BOB-DEVICE-ID"

    def test_team_list(self, runner, init_config, mock_db):
        runner.invoke(cli, ["init", "--user-id", "alice"])
        runner.invoke(cli, ["team", "create", "alpha"])
        result = runner.invoke(cli, ["team", "list"])
        assert result.exit_code == 0
        assert "alpha" in result.output

    def test_team_list_empty(self, runner, init_config, mock_db):
        runner.invoke(cli, ["init", "--user-id", "alice"])
        result = runner.invoke(cli, ["team", "list"])
        assert result.exit_code == 0
        assert "No teams" in result.output

    def test_team_remove_member(self, runner, init_config, mock_db):
        runner.invoke(cli, ["init", "--user-id", "alice"])
        runner.invoke(cli, ["team", "create", "alpha"])
        runner.invoke(cli, ["team", "add", "bob", "BOB-DEVICE-ID", "--team", "alpha"])
        result = runner.invoke(cli, ["team", "remove", "bob", "--team", "alpha"])
        assert result.exit_code == 0
        assert "Removed 'bob' from team 'alpha'" in result.output

        # Verify removed from DB
        row = mock_db.execute(
            "SELECT * FROM sync_members WHERE team_name = 'alpha' AND name = 'bob'"
        ).fetchone()
        assert row is None

    def test_team_remove_member_not_found(self, runner, init_config, mock_db):
        runner.invoke(cli, ["init", "--user-id", "alice"])
        runner.invoke(cli, ["team", "create", "alpha"])
        result = runner.invoke(cli, ["team", "remove", "bob", "--team", "alpha"])
        assert result.exit_code != 0
        assert "not found" in result.output

    def test_team_leave(self, runner, init_config, mock_db):
        runner.invoke(cli, ["init", "--user-id", "alice"])
        runner.invoke(cli, ["team", "create", "alpha"])
        runner.invoke(cli, ["team", "add", "bob", "DEV-BOB", "--team", "alpha"])
        result = runner.invoke(cli, ["team", "leave", "alpha"])
        assert result.exit_code == 0
        assert "Left team 'alpha'" in result.output

        # Verify cascade
        assert mock_db.execute("SELECT * FROM sync_teams WHERE name = 'alpha'").fetchone() is None
        assert mock_db.execute("SELECT * FROM sync_members WHERE team_name = 'alpha'").fetchone() is None


class TestProjectCommands:
    def test_project_add(self, runner, init_config, mock_db, tmp_path):
        runner.invoke(cli, ["init", "--user-id", "alice"])
        runner.invoke(cli, ["team", "create", "alpha"])

        project_path = tmp_path / "test-project"
        project_path.mkdir(parents=True)

        result = runner.invoke(
            cli, ["project", "add", "test-project", "--path", str(project_path), "--team", "alpha"]
        )
        assert result.exit_code == 0
        assert "Added project 'test-project'" in result.output

        # Verify in DB
        row = mock_db.execute(
            "SELECT * FROM sync_team_projects WHERE team_name = 'alpha'"
        ).fetchone()
        assert row is not None
        assert row["path"] == str(project_path)

    def test_project_add_team_not_found(self, runner, init_config, mock_db, tmp_path):
        runner.invoke(cli, ["init", "--user-id", "alice"])
        project_path = tmp_path / "test-project"
        project_path.mkdir(parents=True)

        result = runner.invoke(
            cli, ["project", "add", "test-project", "--path", str(project_path), "--team", "nope"]
        )
        assert result.exit_code != 0
        assert "not found" in result.output

    def test_project_list(self, runner, init_config, mock_db, tmp_path):
        runner.invoke(cli, ["init", "--user-id", "alice"])
        runner.invoke(cli, ["team", "create", "alpha"])

        project_path = tmp_path / "myapp"
        project_path.mkdir(parents=True)
        runner.invoke(
            cli, ["project", "add", "myapp", "--path", str(project_path), "--team", "alpha"]
        )

        result = runner.invoke(cli, ["project", "list"])
        assert result.exit_code == 0
        assert "myapp" in result.output
        assert "alpha" in result.output

    def test_project_list_empty(self, runner, init_config, mock_db):
        runner.invoke(cli, ["init", "--user-id", "alice"])
        result = runner.invoke(cli, ["project", "list"])
        assert result.exit_code == 0
        assert "No projects configured" in result.output

    def test_project_remove(self, runner, init_config, mock_db, tmp_path):
        runner.invoke(cli, ["init", "--user-id", "alice"])
        runner.invoke(cli, ["team", "create", "alpha"])

        project_path = tmp_path / "myapp"
        project_path.mkdir(parents=True)
        runner.invoke(
            cli, ["project", "add", "myapp", "--path", str(project_path), "--team", "alpha"]
        )

        result = runner.invoke(cli, ["project", "remove", "myapp", "--team", "alpha"])
        assert result.exit_code == 0
        assert "Removed project 'myapp'" in result.output

        # Verify removed from DB
        row = mock_db.execute(
            "SELECT * FROM sync_team_projects WHERE team_name = 'alpha'"
        ).fetchone()
        assert row is None

    def test_project_remove_not_found(self, runner, init_config, mock_db):
        runner.invoke(cli, ["init", "--user-id", "alice"])
        runner.invoke(cli, ["team", "create", "alpha"])
        result = runner.invoke(cli, ["project", "remove", "nope", "--team", "alpha"])
        assert result.exit_code != 0
        assert "not found" in result.output


class TestCorruptConfig:
    def test_load_corrupt_json(self, runner, init_config):
        init_config.write_text("{invalid json")
        result = runner.invoke(cli, ["project", "list"])
        assert result.exit_code != 0
        assert "Corrupt config" in result.output

    def test_load_invalid_schema(self, runner, init_config):
        init_config.write_text('{"bad_field": true}')
        result = runner.invoke(cli, ["project", "list"])
        assert result.exit_code != 0
        assert "Corrupt config" in result.output


class TestLsCommand:
    def test_ls_no_remote_dir(self, runner, init_config):
        result = runner.invoke(cli, ["ls"])
        assert result.exit_code == 0
        assert "No remote sessions" in result.output


class TestStatusCommand:
    def test_status_with_teams(self, runner, init_config, mock_db):
        runner.invoke(cli, ["init", "--user-id", "alice"])
        runner.invoke(cli, ["team", "create", "alpha"])
        result = runner.invoke(cli, ["status"])
        assert result.exit_code == 0
        assert "alice" in result.output
        assert "alpha" in result.output

    def test_status_no_teams(self, runner, init_config, mock_db):
        runner.invoke(cli, ["init", "--user-id", "alice"])
        result = runner.invoke(cli, ["status"])
        assert result.exit_code == 0
        assert "No teams configured" in result.output

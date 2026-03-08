"""Integration test: full team/project lifecycle with SQLite."""

import json

import pytest
from click.testing import CliRunner

from karma.main import cli


@pytest.fixture
def full_setup(tmp_path, monkeypatch, mock_db):
    """Set up a complete test environment."""
    config_path = tmp_path / "sync-config.json"
    monkeypatch.setattr("karma.config.SYNC_CONFIG_PATH", config_path)
    monkeypatch.setattr("karma.config.KARMA_BASE", tmp_path)
    monkeypatch.setattr("karma.main.KARMA_BASE", tmp_path)

    return {
        "tmp": tmp_path,
        "config_path": config_path,
        "db": mock_db,
    }


class TestFullSyncFlow:
    def test_init_and_team_project_flow(self, full_setup):
        runner = CliRunner()
        tmp = full_setup["tmp"]

        # Step 1: Init
        result = runner.invoke(cli, ["init", "--user-id", "alice"])
        assert result.exit_code == 0
        assert "Initialized as 'alice'" in result.output

        # Step 2: Create team
        result = runner.invoke(cli, ["team", "create", "beta"])
        assert result.exit_code == 0

        # Step 3: Add project (path must be absolute)
        project_path = tmp / "test-project"
        project_path.mkdir()
        result = runner.invoke(cli, [
            "project", "add", "test-project",
            "--path", str(project_path),
            "--team", "beta",
        ])
        assert result.exit_code == 0
        assert "Added project 'test-project'" in result.output

        # Verify in DB
        row = full_setup["db"].execute(
            "SELECT * FROM sync_team_projects WHERE team_name = 'beta'"
        ).fetchone()
        assert row is not None

    def test_team_management_flow(self, full_setup):
        runner = CliRunner()

        # Init
        runner.invoke(cli, ["init", "--user-id", "owner"])

        # Create team
        result = runner.invoke(cli, ["team", "create", "alpha"])
        assert result.exit_code == 0

        # Add team members
        result = runner.invoke(cli, ["team", "add", "alice", "ALICE-DEVICE-ID", "--team", "alpha"])
        assert result.exit_code == 0

        result = runner.invoke(cli, ["team", "add", "bob", "BOB-DEVICE-ID", "--team", "alpha"])
        assert result.exit_code == 0

        # List team
        result = runner.invoke(cli, ["team", "list"])
        assert "alice" in result.output
        assert "bob" in result.output

        # Remove member
        result = runner.invoke(cli, ["team", "remove", "alice", "--team", "alpha"])
        assert result.exit_code == 0

        # Verify alice is gone from DB
        row = full_setup["db"].execute(
            "SELECT * FROM sync_members WHERE team_name = 'alpha' AND name = 'alice'"
        ).fetchone()
        assert row is None

        # Bob still there
        row = full_setup["db"].execute(
            "SELECT * FROM sync_members WHERE team_name = 'alpha' AND name = 'bob'"
        ).fetchone()
        assert row is not None

    def test_project_lifecycle(self, full_setup):
        runner = CliRunner()
        tmp = full_setup["tmp"]

        # Init
        runner.invoke(cli, ["init", "--user-id", "alice"])

        # Create team
        runner.invoke(cli, ["team", "create", "beta"])

        # Add project
        project_path = tmp / "my-app"
        project_path.mkdir()
        result = runner.invoke(cli, [
            "project", "add", "my-app",
            "--path", str(project_path),
            "--team", "beta",
        ])
        assert result.exit_code == 0

        # List projects
        result = runner.invoke(cli, ["project", "list"])
        assert "my-app" in result.output

        # Remove project
        result = runner.invoke(cli, ["project", "remove", "my-app", "--team", "beta"])
        assert result.exit_code == 0
        assert "Removed project 'my-app'" in result.output

        # Verify gone from DB
        row = full_setup["db"].execute(
            "SELECT * FROM sync_team_projects WHERE team_name = 'beta'"
        ).fetchone()
        assert row is None

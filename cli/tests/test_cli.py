"""Tests for CLI commands."""


import pytest
from click.testing import CliRunner

from karma.main import cli


@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture
def init_config(tmp_path, monkeypatch):
    """Initialize a config for testing."""
    config_path = tmp_path / "sync-config.json"
    monkeypatch.setattr("karma.config.SYNC_CONFIG_PATH", config_path)
    monkeypatch.setattr("karma.config.KARMA_BASE", tmp_path)
    return config_path


class TestInitCommand:
    def test_init_creates_config(self, runner, init_config):
        result = runner.invoke(cli, ["init", "--user-id", "alice"])
        assert result.exit_code == 0
        assert "Initialized as 'alice'" in result.output
        assert init_config.exists()


class TestProjectCommands:
    def test_project_add(self, runner, init_config, tmp_path):
        # Init first
        runner.invoke(cli, ["init", "--user-id", "alice"])

        # Use an absolute path for the project
        project_path = tmp_path / "test-project"
        project_path.mkdir(parents=True)

        result = runner.invoke(
            cli, ["project", "add", "test-project", "--path", str(project_path)]
        )
        assert result.exit_code == 0
        assert "Added project 'test-project'" in result.output

    def test_project_list(self, runner, init_config):
        runner.invoke(cli, ["init", "--user-id", "alice"])
        result = runner.invoke(cli, ["project", "list"])
        assert result.exit_code == 0


class TestTeamCommands:
    def test_team_add(self, runner, init_config):
        runner.invoke(cli, ["init", "--user-id", "alice"])
        result = runner.invoke(cli, ["team", "add", "bob", "k51testkey123"])
        assert result.exit_code == 0
        assert "Added team member 'bob'" in result.output

    def test_team_list(self, runner, init_config):
        runner.invoke(cli, ["init", "--user-id", "alice"])
        result = runner.invoke(cli, ["team", "list"])
        assert result.exit_code == 0

    def test_team_remove(self, runner, init_config):
        runner.invoke(cli, ["init", "--user-id", "alice"])
        runner.invoke(cli, ["team", "add", "bob", "k51testkey123"])
        result = runner.invoke(cli, ["team", "remove", "bob"])
        assert result.exit_code == 0
        assert "Removed team member 'bob'" in result.output

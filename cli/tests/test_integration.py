"""Integration test: full sync -> pull flow with mocked IPFS."""

import json

import pytest
from click.testing import CliRunner

from karma.main import cli


@pytest.fixture
def full_setup(tmp_path, monkeypatch):
    """Set up a complete test environment."""
    # Config paths
    config_path = tmp_path / "sync-config.json"
    monkeypatch.setattr("karma.config.SYNC_CONFIG_PATH", config_path)
    monkeypatch.setattr("karma.config.KARMA_BASE", tmp_path)

    # Create fake Claude project directory
    claude_project = tmp_path / ".claude" / "projects" / "-test-project"
    claude_project.mkdir(parents=True)
    (claude_project / "session-001.jsonl").write_text('{"type":"user"}\n')
    (claude_project / "session-002.jsonl").write_text('{"type":"user"}\n')

    return {
        "tmp": tmp_path,
        "config_path": config_path,
        "claude_project": claude_project,
    }


class TestFullSyncFlow:
    def test_init_add_project_sync(self, full_setup):
        runner = CliRunner()

        # Step 1: Init
        result = runner.invoke(cli, ["init", "--user-id", "alice"])
        assert result.exit_code == 0
        assert "Initialized as 'alice'" in result.output

        # Step 2: Add project (path must be absolute)
        result = runner.invoke(cli, [
            "project", "add", "test-project",
            "--path", str(full_setup["claude_project"]),
        ])
        assert result.exit_code == 0
        assert "Added project 'test-project'" in result.output

        # Verify config was updated
        config = json.loads(full_setup["config_path"].read_text())
        assert "test-project" in config["projects"]

    def test_team_management_flow(self, full_setup):
        runner = CliRunner()

        # Init
        runner.invoke(cli, ["init", "--user-id", "owner"])

        # Add team members
        result = runner.invoke(cli, ["team", "add", "alice", "k51alice123"])
        assert result.exit_code == 0

        result = runner.invoke(cli, ["team", "add", "bob", "k51bob456"])
        assert result.exit_code == 0

        # List team
        result = runner.invoke(cli, ["team", "list"])
        assert "alice" in result.output
        assert "bob" in result.output

        # Remove member
        result = runner.invoke(cli, ["team", "remove", "alice"])
        assert result.exit_code == 0

        # Verify alice is gone
        config = json.loads(full_setup["config_path"].read_text())
        assert "alice" not in config["team"]
        assert "bob" in config["team"]

    def test_project_lifecycle(self, full_setup):
        runner = CliRunner()

        # Init
        runner.invoke(cli, ["init", "--user-id", "alice"])

        # Add project
        result = runner.invoke(cli, [
            "project", "add", "my-app",
            "--path", "/Users/alice/my-app",
        ])
        assert result.exit_code == 0

        # List projects
        result = runner.invoke(cli, ["project", "list"])
        assert "my-app" in result.output
        assert "never synced" in result.output

        # Remove project
        result = runner.invoke(cli, ["project", "remove", "my-app"])
        assert result.exit_code == 0
        assert "Removed project 'my-app'" in result.output

        # Verify gone
        config = json.loads(full_setup["config_path"].read_text())
        assert "my-app" not in config["projects"]

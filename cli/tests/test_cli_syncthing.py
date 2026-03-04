"""Tests for Syncthing CLI commands."""

from unittest.mock import patch, MagicMock
from click.testing import CliRunner

import pytest

from karma.main import cli


@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture
def mock_config(tmp_path, monkeypatch):
    config_path = tmp_path / "sync-config.json"
    monkeypatch.setattr("karma.config.SYNC_CONFIG_PATH", config_path)
    monkeypatch.setattr("karma.config.KARMA_BASE", tmp_path)
    return config_path


class TestInitWithBackend:
    def test_init_default_no_backend_flag(self, runner, mock_config):
        result = runner.invoke(cli, ["init", "--user-id", "alice"])
        assert result.exit_code == 0
        assert "alice" in result.output

    @patch("karma.syncthing.SyncthingClient")
    def test_init_syncthing_backend(self, mock_st_cls, runner, mock_config):
        mock_st = MagicMock()
        mock_st.is_running.return_value = True
        mock_st.get_device_id.return_value = "AAAA-BBBB-CCCC"
        mock_st_cls.return_value = mock_st

        result = runner.invoke(cli, ["init", "--user-id", "alice", "--backend", "syncthing"])
        assert result.exit_code == 0
        assert "AAAA-BBBB-CCCC" in result.output

    @patch("karma.syncthing.SyncthingClient")
    def test_init_syncthing_not_running(self, mock_st_cls, runner, mock_config):
        mock_st = MagicMock()
        mock_st.is_running.return_value = False
        mock_st_cls.return_value = mock_st

        result = runner.invoke(cli, ["init", "--user-id", "alice", "--backend", "syncthing"])
        assert result.exit_code != 0
        assert "not running" in result.output.lower() or "not running" in str(result.exception or "").lower()


class TestTeamCreate:
    def test_team_create_syncthing(self, runner, mock_config):
        runner.invoke(cli, ["init", "--user-id", "alice"])
        result = runner.invoke(cli, ["team", "create", "beta", "--backend", "syncthing"])
        assert result.exit_code == 0
        assert "beta" in result.output

    def test_team_create_ipfs(self, runner, mock_config):
        runner.invoke(cli, ["init", "--user-id", "alice"])
        result = runner.invoke(cli, ["team", "create", "alpha", "--backend", "ipfs"])
        assert result.exit_code == 0
        assert "alpha" in result.output

    def test_team_create_requires_init(self, runner, mock_config):
        result = runner.invoke(cli, ["team", "create", "beta", "--backend", "syncthing"])
        assert result.exit_code != 0


class TestTeamAddSyncthing:
    def test_team_add_device_id(self, runner, mock_config):
        runner.invoke(cli, ["init", "--user-id", "alice"])
        runner.invoke(cli, ["team", "create", "beta", "--backend", "syncthing"])
        result = runner.invoke(cli, ["team", "add", "bob", "DEVICEID123", "--team", "beta"])
        assert result.exit_code == 0
        assert "bob" in result.output


class TestProjectAddWithTeam:
    def test_project_add_to_team(self, runner, mock_config, tmp_path):
        runner.invoke(cli, ["init", "--user-id", "alice"])
        runner.invoke(cli, ["team", "create", "beta", "--backend", "syncthing"])
        project_path = tmp_path / "test-project"
        project_path.mkdir()
        result = runner.invoke(cli, [
            "project", "add", "app", "--path", str(project_path), "--team", "beta"
        ])
        assert result.exit_code == 0
        assert "app" in result.output

    def test_project_add_to_nonexistent_team(self, runner, mock_config, tmp_path):
        runner.invoke(cli, ["init", "--user-id", "alice"])
        project_path = tmp_path / "test-project"
        project_path.mkdir()
        result = runner.invoke(cli, [
            "project", "add", "app", "--path", str(project_path), "--team", "nope"
        ])
        assert result.exit_code != 0


class TestProjectRemoveWithTeam:
    def test_project_remove_from_team(self, runner, mock_config, tmp_path):
        runner.invoke(cli, ["init", "--user-id", "alice"])
        runner.invoke(cli, ["team", "create", "beta", "--backend", "syncthing"])
        project_path = tmp_path / "test-project"
        project_path.mkdir()
        runner.invoke(cli, [
            "project", "add", "app", "--path", str(project_path), "--team", "beta"
        ])
        result = runner.invoke(cli, ["project", "remove", "app", "--team", "beta"])
        assert result.exit_code == 0
        assert "app" in result.output

    def test_project_remove_from_nonexistent_team(self, runner, mock_config):
        runner.invoke(cli, ["init", "--user-id", "alice"])
        result = runner.invoke(cli, ["project", "remove", "app", "--team", "nope"])
        assert result.exit_code != 0

    def test_project_remove_nonexistent_from_team(self, runner, mock_config):
        runner.invoke(cli, ["init", "--user-id", "alice"])
        runner.invoke(cli, ["team", "create", "beta", "--backend", "syncthing"])
        result = runner.invoke(cli, ["project", "remove", "missing", "--team", "beta"])
        assert result.exit_code != 0


class TestTeamMemberRemove:
    def test_remove_syncthing_member(self, runner, mock_config):
        runner.invoke(cli, ["init", "--user-id", "alice"])
        runner.invoke(cli, ["team", "create", "beta", "--backend", "syncthing"])
        runner.invoke(cli, ["team", "add", "bob", "DEVICEID123", "--team", "beta"])
        result = runner.invoke(cli, ["team", "remove", "bob", "--team", "beta"])
        assert result.exit_code == 0
        assert "bob" in result.output

    def test_remove_nonexistent_member_from_team(self, runner, mock_config):
        runner.invoke(cli, ["init", "--user-id", "alice"])
        runner.invoke(cli, ["team", "create", "beta", "--backend", "syncthing"])
        result = runner.invoke(cli, ["team", "remove", "ghost", "--team", "beta"])
        assert result.exit_code != 0


class TestWatchCommand:
    def test_watch_requires_init(self, runner, mock_config):
        result = runner.invoke(cli, ["watch", "--team", "beta"])
        assert result.exit_code != 0

    def test_watch_requires_syncthing_team(self, runner, mock_config):
        runner.invoke(cli, ["init", "--user-id", "alice"])
        result = runner.invoke(cli, ["watch", "--team", "nonexistent"])
        assert result.exit_code != 0

    @patch("karma.watcher.SessionWatcher")
    def test_watch_starts_and_stops_on_interrupt(self, mock_watcher_cls, runner, mock_config, tmp_path):
        runner.invoke(cli, ["init", "--user-id", "alice"])
        runner.invoke(cli, ["team", "create", "beta", "--backend", "syncthing"])
        project_path = tmp_path / "test-project"
        project_path.mkdir()
        runner.invoke(cli, [
            "project", "add", "app", "--path", str(project_path), "--team", "beta"
        ])

        # Create the claude dir that watch() checks for
        from karma.sync import encode_project_path
        encoded = encode_project_path(str(project_path))
        claude_dir = tmp_path / ".claude" / "projects" / encoded
        claude_dir.mkdir(parents=True)

        mock_watcher = MagicMock()
        mock_watcher_cls.return_value = mock_watcher

        # Patch Path.home to point to tmp_path so watch finds claude_dir
        # and patch time.sleep to raise KeyboardInterrupt
        with patch("karma.main.Path.home", return_value=tmp_path), \
             patch("time.sleep", side_effect=KeyboardInterrupt()):
            result = runner.invoke(cli, ["watch", "--team", "beta"])

        # Should have created and stopped the watcher
        mock_watcher_cls.assert_called_once()
        mock_watcher.start.assert_called_once()
        mock_watcher.stop.assert_called()


class TestStatusCommand:
    def test_status_no_teams(self, runner, mock_config):
        runner.invoke(cli, ["init", "--user-id", "alice"])
        result = runner.invoke(cli, ["status"])
        assert result.exit_code == 0
        assert "No teams" in result.output

    def test_status_shows_teams(self, runner, mock_config):
        runner.invoke(cli, ["init", "--user-id", "alice"])
        runner.invoke(cli, ["team", "create", "beta", "--backend", "syncthing"])
        result = runner.invoke(cli, ["status"])
        assert result.exit_code == 0
        assert "beta" in result.output
        assert "syncthing" in result.output.lower()

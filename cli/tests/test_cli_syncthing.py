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
    monkeypatch.setattr("karma.main.KARMA_BASE", tmp_path)
    return config_path


@pytest.fixture(autouse=True)
def _isolate_syncthing(monkeypatch):
    """Prevent init from detecting real Syncthing unless test explicitly mocks it."""
    monkeypatch.setattr("karma.syncthing.read_local_api_key", lambda: None)


class TestInit:
    def test_init_no_syncthing(self, runner, mock_config):
        result = runner.invoke(cli, ["init", "--user-id", "alice"])
        assert result.exit_code == 0
        assert "alice" in result.output

    @patch("karma.syncthing.read_local_api_key", return_value="test-key")
    @patch("karma.syncthing.SyncthingClient")
    def test_init_with_syncthing_running(self, mock_st_cls, mock_key, runner, mock_config):
        mock_st = MagicMock()
        mock_st.is_running.return_value = True
        mock_st.get_device_id.return_value = "AAAA-BBBB-CCCC"
        mock_st_cls.return_value = mock_st

        result = runner.invoke(cli, ["init", "--user-id", "alice"])
        assert result.exit_code == 0
        assert "AAAA-BBBB-CCCC" in result.output

    @patch("karma.syncthing.read_local_api_key", return_value="test-key")
    @patch("karma.syncthing.SyncthingClient")
    def test_init_syncthing_not_running(self, mock_st_cls, mock_key, runner, mock_config):
        mock_st = MagicMock()
        mock_st.is_running.return_value = False
        mock_st_cls.return_value = mock_st

        result = runner.invoke(cli, ["init", "--user-id", "alice"])
        assert result.exit_code == 0
        assert "not detected" in result.output.lower()


class TestTeamCreate:
    def test_team_create_syncthing(self, runner, mock_config, mock_db):
        runner.invoke(cli, ["init", "--user-id", "alice"])
        result = runner.invoke(cli, ["team", "create", "beta"])
        assert result.exit_code == 0
        assert "beta" in result.output

    def test_team_create_requires_init(self, runner, mock_config):
        result = runner.invoke(cli, ["team", "create", "beta"])
        assert result.exit_code != 0


class TestTeamAddSyncthing:
    @patch("karma.syncthing.SyncthingClient")
    def test_team_add_device_id(self, mock_st_cls, runner, mock_config, mock_db):
        runner.invoke(cli, ["init", "--user-id", "alice"])
        runner.invoke(cli, ["team", "create", "beta"])
        result = runner.invoke(cli, ["team", "add", "bob", "DEVICEID123", "--team", "beta"])
        assert result.exit_code == 0
        assert "bob" in result.output


class TestProjectAddWithTeam:
    def test_project_add_to_team(self, runner, mock_config, mock_db, tmp_path):
        runner.invoke(cli, ["init", "--user-id", "alice"])
        runner.invoke(cli, ["team", "create", "beta"])
        project_path = tmp_path / "test-project"
        project_path.mkdir()
        result = runner.invoke(cli, [
            "project", "add", "app", "--path", str(project_path), "--team", "beta"
        ])
        assert result.exit_code == 0
        assert "app" in result.output

    def test_project_add_to_nonexistent_team(self, runner, mock_config, mock_db, tmp_path):
        runner.invoke(cli, ["init", "--user-id", "alice"])
        project_path = tmp_path / "test-project"
        project_path.mkdir()
        result = runner.invoke(cli, [
            "project", "add", "app", "--path", str(project_path), "--team", "nope"
        ])
        assert result.exit_code != 0


class TestProjectRemoveWithTeam:
    def test_project_remove_from_team(self, runner, mock_config, mock_db, tmp_path):
        runner.invoke(cli, ["init", "--user-id", "alice"])
        runner.invoke(cli, ["team", "create", "beta"])
        project_path = tmp_path / "test-project"
        project_path.mkdir()
        runner.invoke(cli, [
            "project", "add", "app", "--path", str(project_path), "--team", "beta"
        ])
        result = runner.invoke(cli, ["project", "remove", "test-project", "--team", "beta"])
        assert result.exit_code == 0

    def test_project_remove_from_nonexistent_team(self, runner, mock_config, mock_db):
        runner.invoke(cli, ["init", "--user-id", "alice"])
        result = runner.invoke(cli, ["project", "remove", "app", "--team", "nope"])
        assert result.exit_code != 0

    def test_project_remove_nonexistent_from_team(self, runner, mock_config, mock_db):
        runner.invoke(cli, ["init", "--user-id", "alice"])
        runner.invoke(cli, ["team", "create", "beta"])
        result = runner.invoke(cli, ["project", "remove", "missing", "--team", "beta"])
        assert result.exit_code != 0


class TestTeamMemberRemove:
    @patch("karma.syncthing.SyncthingClient")
    def test_remove_syncthing_member(self, mock_st_cls, runner, mock_config, mock_db):
        runner.invoke(cli, ["init", "--user-id", "alice"])
        runner.invoke(cli, ["team", "create", "beta"])
        runner.invoke(cli, ["team", "add", "bob", "DEVICEID123", "--team", "beta"])
        result = runner.invoke(cli, ["team", "remove", "bob", "--team", "beta"])
        assert result.exit_code == 0
        assert "bob" in result.output

    def test_remove_nonexistent_member_from_team(self, runner, mock_config, mock_db):
        runner.invoke(cli, ["init", "--user-id", "alice"])
        runner.invoke(cli, ["team", "create", "beta"])
        result = runner.invoke(cli, ["team", "remove", "ghost", "--team", "beta"])
        assert result.exit_code != 0


class TestWatchCommand:
    def test_watch_requires_init(self, runner, mock_config):
        result = runner.invoke(cli, ["watch", "--team", "beta"])
        assert result.exit_code != 0

    def test_watch_requires_syncthing_team(self, runner, mock_config, mock_db):
        runner.invoke(cli, ["init", "--user-id", "alice"])
        result = runner.invoke(cli, ["watch", "--team", "nonexistent"])
        assert result.exit_code != 0

    @patch("karma.watcher.SessionWatcher")
    def test_watch_starts_and_stops_on_interrupt(self, mock_watcher_cls, runner, mock_config, mock_db, tmp_path):
        runner.invoke(cli, ["init", "--user-id", "alice"])
        runner.invoke(cli, ["team", "create", "beta"])
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

        with patch("karma.main.Path.home", return_value=tmp_path), \
             patch("time.sleep", side_effect=KeyboardInterrupt()):
            result = runner.invoke(cli, ["watch", "--team", "beta"])

        mock_watcher_cls.assert_called_once()
        mock_watcher.start.assert_called_once()
        mock_watcher.stop.assert_called()


class TestAcceptCommand:
    def test_accept_requires_init(self, runner, mock_config):
        result = runner.invoke(cli, ["accept"])
        assert result.exit_code != 0

    @patch("karma.syncthing.read_local_api_key", return_value="test-key")
    @patch("karma.syncthing.SyncthingClient")
    def test_accept_no_pending(self, mock_st_cls, mock_key, runner, mock_config, mock_db):
        mock_st = MagicMock()
        mock_st.is_running.return_value = True
        mock_st.get_device_id.return_value = "MY-DEVICE-ID"
        mock_st.get_pending_folders.return_value = {}
        mock_st_cls.return_value = mock_st

        runner.invoke(cli, ["init", "--user-id", "alice"])
        result = runner.invoke(cli, ["accept"])
        assert result.exit_code == 0
        assert "No pending" in result.output

    @patch("karma.syncthing.read_local_api_key", return_value="test-key")
    @patch("karma.syncthing.SyncthingClient")
    def test_accept_from_known_member(self, mock_st_cls, mock_key, runner, mock_config, mock_db, tmp_path):
        mock_st = MagicMock()
        mock_st.is_running.return_value = True
        mock_st.get_device_id.return_value = "MY-DEVICE-ID"
        mock_st.get_pending_folders.return_value = {}
        mock_st.get_folders.return_value = []
        mock_st.find_folder_by_path.return_value = None
        mock_st_cls.return_value = mock_st

        runner.invoke(cli, ["init", "--user-id", "alice"])
        runner.invoke(cli, ["team", "create", "beta"])
        runner.invoke(cli, ["team", "add", "bob", "BOB-DEVICE-ID-FULL", "--team", "beta"])
        project_path = tmp_path / "myapp"
        project_path.mkdir()
        runner.invoke(cli, [
            "project", "add", "myapp", "--path", str(project_path), "--team", "beta"
        ])

        # Now set up the pending folder for the accept call
        mock_st.get_pending_folders.return_value = {
            "karma-out-bob-myapp": {
                "offeredBy": {
                    "BOB-DEVICE-ID-FULL": {"time": "2026-03-05T03:45:06Z"}
                }
            }
        }

        result = runner.invoke(cli, ["accept"])
        assert result.exit_code == 0
        assert "Accepted" in result.output or "bob" in result.output.lower()

    @patch("karma.syncthing.read_local_api_key", return_value="test-key")
    @patch("karma.syncthing.SyncthingClient")
    def test_accept_skips_unknown_device(self, mock_st_cls, mock_key, runner, mock_config, mock_db):
        mock_st = MagicMock()
        mock_st.is_running.return_value = True
        mock_st.get_device_id.return_value = "MY-DEVICE-ID"
        mock_st.get_pending_folders.return_value = {}
        mock_st.get_folders.return_value = []
        mock_st_cls.return_value = mock_st

        runner.invoke(cli, ["init", "--user-id", "alice"])
        runner.invoke(cli, ["team", "create", "beta"])

        mock_st.get_pending_folders.return_value = {
            "karma-evil-folder": {
                "offeredBy": {"UNKNOWN-DEVICE-XYZ": {"time": "2026-03-05T00:00:00Z"}}
            }
        }

        result = runner.invoke(cli, ["accept"])
        assert result.exit_code == 0
        assert "unknown device" in result.output.lower()
        mock_st.add_folder.assert_not_called()

    @patch("karma.syncthing.read_local_api_key", return_value="test-key")
    @patch("karma.syncthing.SyncthingClient")
    def test_accept_skips_non_karma_prefix(self, mock_st_cls, mock_key, runner, mock_config, mock_db):
        mock_st = MagicMock()
        mock_st.is_running.return_value = True
        mock_st.get_device_id.return_value = "MY-DEVICE-ID"
        mock_st.get_pending_folders.return_value = {}
        mock_st.get_folders.return_value = []
        mock_st_cls.return_value = mock_st

        runner.invoke(cli, ["init", "--user-id", "alice"])
        runner.invoke(cli, ["team", "create", "beta"])
        runner.invoke(cli, ["team", "add", "bob", "BOB-DEVICE-ID", "--team", "beta"])

        mock_st.get_pending_folders.return_value = {
            "suspicious-folder": {
                "offeredBy": {"BOB-DEVICE-ID": {"time": "2026-03-05T00:00:00Z"}}
            }
        }

        result = runner.invoke(cli, ["accept"])
        assert result.exit_code == 0
        assert "non-karma" in result.output.lower()
        mock_st.add_folder.assert_not_called()

    @patch("karma.syncthing.read_local_api_key", return_value="test-key")
    @patch("karma.syncthing.SyncthingClient")
    def test_accept_replaces_empty_existing_folder(self, mock_st_cls, mock_key, runner, mock_config, mock_db, tmp_path):
        mock_st = MagicMock()
        mock_st.is_running.return_value = True
        mock_st.get_device_id.return_value = "MY-DEVICE-ID"
        mock_st.get_pending_folders.return_value = {}
        mock_st.get_folders.return_value = []
        mock_st_cls.return_value = mock_st

        runner.invoke(cli, ["init", "--user-id", "alice"])
        runner.invoke(cli, ["team", "create", "beta"])
        runner.invoke(cli, ["team", "add", "bob", "BOB-DEVICE-ID", "--team", "beta"])
        project_path = tmp_path / "myapp"
        project_path.mkdir()
        runner.invoke(cli, [
            "project", "add", "myapp", "--path", str(project_path), "--team", "beta"
        ])

        mock_st.get_pending_folders.return_value = {
            "karma-out-bob-myapp": {
                "offeredBy": {"BOB-DEVICE-ID": {"time": "2026-03-05T00:00:00Z"}}
            }
        }
        mock_st.find_folder_by_path.return_value = {"id": "karma-out-bob-old", "path": "/tmp/inbox"}

        result = runner.invoke(cli, ["accept"])
        assert result.exit_code == 0
        assert "Replacing" in result.output
        mock_st.remove_folder.assert_called_once_with("karma-out-bob-old")


class TestWorktreeDiscoveryIntegration:
    def test_watch_discovers_worktree_dirs(self, tmp_path):
        """karma watch should find worktree dirs and pass them to packager."""
        from karma.worktree_discovery import find_worktree_dirs

        projects_dir = tmp_path / ".claude" / "projects"
        main = projects_dir / "-Users-jay-GitHub-karma"
        wt = projects_dir / "-Users-jay-GitHub-karma--claude-worktrees-feat-a"
        main.mkdir(parents=True)
        wt.mkdir(parents=True)
        (main / "s1.jsonl").write_text('{"type":"user"}\n')
        (wt / "s2.jsonl").write_text('{"type":"user"}\n')

        dirs = find_worktree_dirs("-Users-jay-GitHub-karma", projects_dir)
        assert len(dirs) == 1
        assert dirs[0] == wt


class TestEndToEndWorktreeSync:
    def test_full_worktree_package_pipeline(self, tmp_path):
        """End-to-end: discover worktrees, package, verify manifest."""
        from karma.packager import SessionPackager
        from karma.worktree_discovery import find_worktree_dirs
        import json

        projects_dir = tmp_path / "projects"

        main = projects_dir / "-Users-jay-karma"
        main.mkdir(parents=True)
        (main / "main-session.jsonl").write_text(
            '{"type":"user","message":{"role":"user","content":"main work"}}\n'
        )

        wt1 = projects_dir / "-Users-jay-karma--claude-worktrees-feat-auth"
        wt1.mkdir(parents=True)
        (wt1 / "auth-session.jsonl").write_text(
            '{"type":"user","message":{"role":"user","content":"auth feature"}}\n'
        )
        (wt1 / "auth-session" / "subagents").mkdir(parents=True)
        (wt1 / "auth-session" / "subagents" / "agent-a1.jsonl").write_text('{"type":"agent"}\n')

        wt2 = projects_dir / "-Users-jay-karma--claude-worktrees-fix-bug"
        wt2.mkdir(parents=True)
        (wt2 / "bug-session.jsonl").write_text(
            '{"type":"user","message":{"role":"user","content":"bug fix"}}\n'
        )

        wt_dirs = find_worktree_dirs("-Users-jay-karma", projects_dir)
        assert len(wt_dirs) == 2

        staging = tmp_path / "outbox"
        packager = SessionPackager(
            project_dir=main,
            user_id="jay",
            machine_id="mac",
            extra_dirs=wt_dirs,
        )
        manifest = packager.package(staging_dir=staging)

        assert manifest.session_count == 3
        uuids = {s.uuid for s in manifest.sessions}
        assert uuids == {"main-session", "auth-session", "bug-session"}

        by_uuid = {s.uuid: s for s in manifest.sessions}
        assert by_uuid["main-session"].worktree_name is None
        assert by_uuid["auth-session"].worktree_name == "feat-auth"
        assert by_uuid["bug-session"].worktree_name == "fix-bug"

        assert (staging / "sessions" / "auth-session.jsonl").exists()
        assert (staging / "sessions" / "auth-session" / "subagents" / "agent-a1.jsonl").exists()
        assert (staging / "sessions" / "bug-session.jsonl").exists()

        manifest_json = json.loads((staging / "manifest.json").read_text())
        wt_entries = [s for s in manifest_json["sessions"] if s["worktree_name"]]
        assert len(wt_entries) == 2


class TestStatusCommand:
    def test_status_no_teams(self, runner, mock_config, mock_db):
        runner.invoke(cli, ["init", "--user-id", "alice"])
        result = runner.invoke(cli, ["status"])
        assert result.exit_code == 0
        assert "No teams" in result.output

    def test_status_shows_teams(self, runner, mock_config, mock_db):
        runner.invoke(cli, ["init", "--user-id", "alice"])
        runner.invoke(cli, ["team", "create", "beta"])
        result = runner.invoke(cli, ["status"])
        assert result.exit_code == 0
        assert "beta" in result.output

    def test_status_shows_worktree_counts(self, runner, mock_config, mock_db, tmp_path):
        """karma status should show worktree session counts."""
        runner.invoke(cli, ["init", "--user-id", "jay"])
        runner.invoke(cli, ["team", "create", "beta"])
        project_path = tmp_path / "karma-project"
        project_path.mkdir()
        runner.invoke(cli, [
            "project", "add", "karma", "--path", str(project_path), "--team", "beta"
        ])

        from karma.sync import encode_project_path
        encoded = encode_project_path(str(project_path))
        projects_dir = tmp_path / ".claude" / "projects"
        main_dir = projects_dir / encoded
        main_dir.mkdir(parents=True)
        (main_dir / "s1.jsonl").write_text('{"type":"user"}\n')
        (main_dir / "s2.jsonl").write_text('{"type":"user"}\n')

        wt_dir = projects_dir / f"{encoded}--claude-worktrees-feat-x"
        wt_dir.mkdir(parents=True)
        (wt_dir / "s3.jsonl").write_text('{"type":"user"}\n')

        with patch("karma.main.Path.home", return_value=tmp_path):
            result = runner.invoke(cli, ["status"])

        assert result.exit_code == 0
        assert "worktree" in result.output.lower()
        assert "3" in result.output

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


class TestAcceptCommand:
    def test_accept_requires_init(self, runner, mock_config):
        result = runner.invoke(cli, ["accept"])
        assert result.exit_code != 0

    @patch("karma.syncthing.SyncthingClient")
    def test_accept_no_pending(self, mock_st_cls, runner, mock_config):
        mock_st = MagicMock()
        mock_st.is_running.return_value = True
        mock_st.get_device_id.return_value = "MY-DEVICE-ID"
        mock_st.get_pending_folders.return_value = {}
        mock_st_cls.return_value = mock_st

        runner.invoke(cli, ["init", "--user-id", "alice", "--backend", "syncthing"])
        result = runner.invoke(cli, ["accept"])
        assert result.exit_code == 0
        assert "No pending" in result.output

    @patch("karma.syncthing.SyncthingClient")
    def test_accept_from_known_member(self, mock_st_cls, runner, mock_config, tmp_path):
        mock_st = MagicMock()
        mock_st.is_running.return_value = True
        mock_st.get_device_id.return_value = "MY-DEVICE-ID"
        mock_st.get_pending_folders.return_value = {}
        mock_st.find_folder_by_path.return_value = None
        mock_st_cls.return_value = mock_st

        # Setup: init + team + member + project
        runner.invoke(cli, ["init", "--user-id", "alice", "--backend", "syncthing"])
        runner.invoke(cli, ["team", "create", "beta", "--backend", "syncthing"])
        runner.invoke(cli, ["team", "add", "bob", "BOB-DEVICE-ID-FULL", "--team", "beta"])
        project_path = tmp_path / "myapp"
        project_path.mkdir()
        runner.invoke(cli, [
            "project", "add", "myapp", "--path", str(project_path), "--team", "beta"
        ])

        # Now set up the pending folder for the accept call
        mock_st.get_pending_folders.return_value = {
            "karma-beta-myapp": {
                "offeredBy": {
                    "BOB-DEVICE-ID-FULL": {"time": "2026-03-05T03:45:06Z"}
                }
            }
        }

        result = runner.invoke(cli, ["accept"])
        assert result.exit_code == 0
        assert "Accepted" in result.output
        assert "bob" in result.output

    @patch("karma.syncthing.SyncthingClient")
    def test_accept_skips_unknown_device(self, mock_st_cls, runner, mock_config):
        mock_st = MagicMock()
        mock_st.is_running.return_value = True
        mock_st.get_device_id.return_value = "MY-DEVICE-ID"
        mock_st.get_pending_folders.return_value = {}
        mock_st_cls.return_value = mock_st

        runner.invoke(cli, ["init", "--user-id", "alice", "--backend", "syncthing"])
        runner.invoke(cli, ["team", "create", "beta", "--backend", "syncthing"])

        mock_st.get_pending_folders.return_value = {
            "karma-evil-folder": {
                "offeredBy": {"UNKNOWN-DEVICE-XYZ": {"time": "2026-03-05T00:00:00Z"}}
            }
        }

        result = runner.invoke(cli, ["accept"])
        assert result.exit_code == 0
        assert "unknown device" in result.output.lower()
        mock_st.add_folder.assert_not_called()

    @patch("karma.syncthing.SyncthingClient")
    def test_accept_skips_non_karma_prefix(self, mock_st_cls, runner, mock_config):
        mock_st = MagicMock()
        mock_st.is_running.return_value = True
        mock_st.get_device_id.return_value = "MY-DEVICE-ID"
        mock_st.get_pending_folders.return_value = {}
        mock_st_cls.return_value = mock_st

        runner.invoke(cli, ["init", "--user-id", "alice", "--backend", "syncthing"])
        runner.invoke(cli, ["team", "create", "beta", "--backend", "syncthing"])
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

    @patch("karma.syncthing.SyncthingClient")
    def test_accept_replaces_empty_existing_folder(self, mock_st_cls, runner, mock_config, tmp_path):
        mock_st = MagicMock()
        mock_st.is_running.return_value = True
        mock_st.get_device_id.return_value = "MY-DEVICE-ID"
        mock_st.get_pending_folders.return_value = {}
        mock_st_cls.return_value = mock_st

        runner.invoke(cli, ["init", "--user-id", "alice", "--backend", "syncthing"])
        runner.invoke(cli, ["team", "create", "beta", "--backend", "syncthing"])
        runner.invoke(cli, ["team", "add", "bob", "BOB-DEVICE-ID", "--team", "beta"])
        project_path = tmp_path / "myapp"
        project_path.mkdir()
        runner.invoke(cli, [
            "project", "add", "myapp", "--path", str(project_path), "--team", "beta"
        ])

        mock_st.get_pending_folders.return_value = {
            "karma-beta-myapp": {
                "offeredBy": {"BOB-DEVICE-ID": {"time": "2026-03-05T00:00:00Z"}}
            }
        }
        # Simulate existing pre-created folder at same path
        mock_st.find_folder_by_path.return_value = {"id": "karma-out-bob-myapp", "path": "/tmp/inbox"}

        result = runner.invoke(cli, ["accept"])
        assert result.exit_code == 0
        assert "Replacing" in result.output
        mock_st.remove_folder.assert_called_once_with("karma-out-bob-myapp")


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

        # Main project
        main = projects_dir / "-Users-jay-karma"
        main.mkdir(parents=True)
        (main / "main-session.jsonl").write_text(
            '{"type":"user","message":{"role":"user","content":"main work"}}\n'
        )

        # Worktree 1
        wt1 = projects_dir / "-Users-jay-karma--claude-worktrees-feat-auth"
        wt1.mkdir(parents=True)
        (wt1 / "auth-session.jsonl").write_text(
            '{"type":"user","message":{"role":"user","content":"auth feature"}}\n'
        )
        # With subagent
        (wt1 / "auth-session" / "subagents").mkdir(parents=True)
        (wt1 / "auth-session" / "subagents" / "agent-a1.jsonl").write_text('{"type":"agent"}\n')

        # Worktree 2
        wt2 = projects_dir / "-Users-jay-karma--claude-worktrees-fix-bug"
        wt2.mkdir(parents=True)
        (wt2 / "bug-session.jsonl").write_text(
            '{"type":"user","message":{"role":"user","content":"bug fix"}}\n'
        )

        # Discover
        wt_dirs = find_worktree_dirs("-Users-jay-karma", projects_dir)
        assert len(wt_dirs) == 2

        # Package
        staging = tmp_path / "outbox"
        packager = SessionPackager(
            project_dir=main,
            user_id="jay",
            machine_id="mac",
            extra_dirs=wt_dirs,
        )
        manifest = packager.package(staging_dir=staging)

        # Verify manifest
        assert manifest.session_count == 3
        uuids = {s.uuid for s in manifest.sessions}
        assert uuids == {"main-session", "auth-session", "bug-session"}

        # Verify worktree tagging
        by_uuid = {s.uuid: s for s in manifest.sessions}
        assert by_uuid["main-session"].worktree_name is None
        assert by_uuid["auth-session"].worktree_name == "feat-auth"
        assert by_uuid["bug-session"].worktree_name == "fix-bug"

        # Verify files on disk
        assert (staging / "sessions" / "auth-session.jsonl").exists()
        assert (staging / "sessions" / "auth-session" / "subagents" / "agent-a1.jsonl").exists()
        assert (staging / "sessions" / "bug-session.jsonl").exists()

        # Verify manifest JSON
        manifest_json = json.loads((staging / "manifest.json").read_text())
        wt_entries = [s for s in manifest_json["sessions"] if s["worktree_name"]]
        assert len(wt_entries) == 2


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

    def test_status_shows_worktree_counts(self, runner, mock_config, tmp_path):
        """karma status should show worktree session counts."""
        runner.invoke(cli, ["init", "--user-id", "jay"])
        runner.invoke(cli, ["team", "create", "beta", "--backend", "syncthing"])
        project_path = tmp_path / "karma-project"
        project_path.mkdir()
        runner.invoke(cli, [
            "project", "add", "karma", "--path", str(project_path), "--team", "beta"
        ])

        # Create fake project dir with sessions
        from karma.sync import encode_project_path
        encoded = encode_project_path(str(project_path))
        projects_dir = tmp_path / ".claude" / "projects"
        main_dir = projects_dir / encoded
        main_dir.mkdir(parents=True)
        (main_dir / "s1.jsonl").write_text('{"type":"user"}\n')
        (main_dir / "s2.jsonl").write_text('{"type":"user"}\n')

        # Create worktree dir
        wt_dir = projects_dir / f"{encoded}--claude-worktrees-feat-x"
        wt_dir.mkdir(parents=True)
        (wt_dir / "s3.jsonl").write_text('{"type":"user"}\n')

        with patch("karma.main.Path.home", return_value=tmp_path):
            result = runner.invoke(cli, ["status"])

        assert result.exit_code == 0
        assert "worktree" in result.output.lower()
        assert "3" in result.output  # total = 2 local + 1 worktree

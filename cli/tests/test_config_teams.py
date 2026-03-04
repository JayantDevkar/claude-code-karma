"""Tests for per-team config model."""

import pytest
from karma.config import (
    SyncConfig,
    TeamConfig,
    ProjectConfig,
    SyncthingSettings,
    TeamMemberSyncthing,
)


class TestTeamConfig:
    def test_create_syncthing_team(self):
        team = TeamConfig(
            backend="syncthing",
            owner_device_id="XXXXXXX-XXXXXXX",
            projects={
                "acme": ProjectConfig(path="/Users/alice/acme", encoded_name="-Users-alice-acme")
            },
        )
        assert team.backend == "syncthing"
        assert "acme" in team.projects

    def test_create_ipfs_team(self):
        team = TeamConfig(
            backend="ipfs",
            owner_ipns_key="k51abc",
            projects={},
        )
        assert team.backend == "ipfs"
        assert team.owner_ipns_key == "k51abc"

    def test_invalid_backend_rejected(self):
        with pytest.raises(Exception):
            TeamConfig(backend="dropbox", projects={})


class TestSyncthingSettings:
    def test_defaults(self):
        s = SyncthingSettings()
        assert s.api_url == "http://127.0.0.1:8384"
        assert s.api_key is None
        assert s.device_id is None

    def test_custom_values(self):
        s = SyncthingSettings(api_url="http://localhost:9999", api_key="abc123")
        assert s.api_url == "http://localhost:9999"
        assert s.api_key == "abc123"


class TestSyncConfigWithTeams:
    def test_config_has_teams(self):
        config = SyncConfig(user_id="alice")
        assert config.teams == {}

    def test_config_has_syncthing_settings(self):
        config = SyncConfig(
            user_id="alice",
            syncthing=SyncthingSettings(api_key="test"),
        )
        assert config.syncthing.api_key == "test"

    def test_backward_compat_projects_still_work(self):
        """Old flat projects dict is still accessible for IPFS-only setups."""
        config = SyncConfig(
            user_id="alice",
            projects={
                "acme": ProjectConfig(path="/foo", encoded_name="-foo")
            },
        )
        assert "acme" in config.projects

    def test_team_members_property(self):
        """Unified members view combines ipfs_members and syncthing_members."""
        team = TeamConfig(
            backend="syncthing",
            syncthing_members={"bob": TeamMemberSyncthing(syncthing_device_id="DEVICE123")},
        )
        assert "bob" in team.members

    def test_save_and_load_with_teams(self, tmp_path, monkeypatch):
        config_path = tmp_path / "sync-config.json"
        monkeypatch.setattr("karma.config.SYNC_CONFIG_PATH", config_path)
        monkeypatch.setattr("karma.config.KARMA_BASE", tmp_path)

        config = SyncConfig(
            user_id="alice",
            machine_id="test-mac",
            teams={
                "beta": TeamConfig(
                    backend="syncthing",
                    owner_device_id="YYYY",
                    projects={
                        "startup": ProjectConfig(path="/startup", encoded_name="-startup")
                    },
                )
            },
            syncthing=SyncthingSettings(api_url="http://127.0.0.1:8384", api_key="key123"),
        )
        config.save()

        loaded = SyncConfig.load()
        assert loaded is not None
        assert "beta" in loaded.teams
        assert loaded.teams["beta"].backend == "syncthing"
        assert loaded.syncthing.api_key == "key123"

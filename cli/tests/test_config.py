"""Tests for sync configuration."""


import pytest

from karma.config import SyncConfig, ProjectConfig


class TestSyncConfig:
    def test_create_with_defaults(self):
        config = SyncConfig(user_id="alice")
        assert config.user_id == "alice"
        assert config.machine_id  # auto-generated hostname
        assert config.projects == {}
        assert config.team == {}
        assert config.ipfs_api == "http://127.0.0.1:5001"

    def test_save_and_load(self, tmp_path, monkeypatch):
        config_path = tmp_path / "sync-config.json"
        monkeypatch.setattr("karma.config.SYNC_CONFIG_PATH", config_path)
        monkeypatch.setattr("karma.config.KARMA_BASE", tmp_path)

        config = SyncConfig(user_id="bob", machine_id="test-machine")
        config.save()

        assert config_path.exists()
        loaded = SyncConfig.load()
        assert loaded is not None
        assert loaded.user_id == "bob"
        assert loaded.machine_id == "test-machine"

    def test_load_returns_none_when_missing(self, tmp_path, monkeypatch):
        monkeypatch.setattr("karma.config.SYNC_CONFIG_PATH", tmp_path / "nope.json")
        assert SyncConfig.load() is None

    def test_project_config_frozen(self):
        pc = ProjectConfig(path="/foo", encoded_name="-foo")
        with pytest.raises(Exception):
            pc.path = "/bar"


class TestProjectConfig:
    def test_create(self):
        pc = ProjectConfig(path="/Users/alice/acme", encoded_name="-Users-alice-acme")
        assert pc.last_sync_cid is None
        assert pc.last_sync_at is None

"""Tests for sync configuration (identity-only)."""

import pytest

from karma.config import SyncConfig, SyncthingSettings


class TestSyncConfig:
    def test_create_with_defaults(self):
        config = SyncConfig(user_id="alice")
        assert config.user_id == "alice"
        assert config.machine_id  # auto-generated hostname

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

    def test_frozen(self):
        config = SyncConfig(user_id="alice")
        with pytest.raises(Exception):
            config.user_id = "bob"

    def test_syncthing_settings_preserved(self, tmp_path, monkeypatch):
        config_path = tmp_path / "sync-config.json"
        monkeypatch.setattr("karma.config.SYNC_CONFIG_PATH", config_path)
        monkeypatch.setattr("karma.config.KARMA_BASE", tmp_path)

        config = SyncConfig(
            user_id="alice",
            machine_id="mac",
            syncthing=SyncthingSettings(api_key="key123", device_id="DEV-1"),
        )
        config.save()

        loaded = SyncConfig.load()
        assert loaded.syncthing.api_key == "key123"
        assert loaded.syncthing.device_id == "DEV-1"


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

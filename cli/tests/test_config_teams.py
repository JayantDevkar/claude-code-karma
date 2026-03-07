"""Tests for SyncConfig with syncthing settings (identity-only model)."""

from karma.config import SyncConfig, SyncthingSettings


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


class TestSyncConfigWithSyncthing:
    def test_config_has_syncthing_settings(self):
        config = SyncConfig(
            user_id="alice",
            syncthing=SyncthingSettings(api_key="test"),
        )
        assert config.syncthing.api_key == "test"

    def test_save_and_load_with_syncthing(self, tmp_path, monkeypatch):
        config_path = tmp_path / "sync-config.json"
        monkeypatch.setattr("karma.config.SYNC_CONFIG_PATH", config_path)
        monkeypatch.setattr("karma.config.KARMA_BASE", tmp_path)

        config = SyncConfig(
            user_id="alice",
            machine_id="test-mac",
            syncthing=SyncthingSettings(api_url="http://127.0.0.1:8384", api_key="key123"),
        )
        config.save()

        loaded = SyncConfig.load()
        assert loaded is not None
        assert loaded.syncthing.api_key == "key123"

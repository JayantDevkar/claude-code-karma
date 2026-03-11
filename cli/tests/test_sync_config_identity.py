"""Tests for machine_tag and member_tag derivation in SyncConfig."""

import pytest


def test_machine_tag_from_hostname():
    """machine_tag should be sanitized hostname: lowercase, alphanumeric + hyphens."""
    from karma.config import _sanitize_machine_tag

    assert _sanitize_machine_tag("Jayants-Mac-Mini") == "jayants-mac-mini"
    assert _sanitize_machine_tag("MacBook Pro") == "macbook-pro"
    assert _sanitize_machine_tag("DESKTOP_PC.local") == "desktop-pc-local"
    assert _sanitize_machine_tag("my--weird---host") == "my-weird-host"  # collapse multi-hyphens
    assert _sanitize_machine_tag("") == "unknown"


def test_member_tag_computed():
    """member_tag should be user_id.machine_tag."""
    from karma.config import SyncConfig

    config = SyncConfig(user_id="jayant", machine_id="Jayants-Mac-Mini")
    assert config.member_tag == "jayant.jayants-mac-mini"


def test_member_tag_with_custom_machine_tag():
    """If machine_tag is explicitly set, it overrides auto-derivation."""
    from karma.config import SyncConfig

    config = SyncConfig(user_id="jayant", machine_id="Jayants-Mac-Mini", machine_tag="mbp")
    assert config.member_tag == "jayant.mbp"


def test_user_id_cannot_contain_dot():
    """user_id with dots should be rejected (dot is the member_tag separator)."""
    from karma.config import SyncConfig

    with pytest.raises(ValueError, match="user_id"):
        SyncConfig(user_id="jay.ant", machine_id="test")


def test_machine_tag_no_double_dash():
    """machine_tag must not contain -- (folder ID delimiter)."""
    from karma.config import _sanitize_machine_tag

    result = _sanitize_machine_tag("my--host")
    assert "--" not in result


def test_config_roundtrip_with_member_tag(tmp_path):
    """Save and load preserves machine_tag and member_tag."""
    import json

    config_path = tmp_path / "sync-config.json"
    data = {
        "user_id": "jayant",
        "machine_id": "Jayants-Mac-Mini",
        "machine_tag": "mac-mini",
        "syncthing": {"device_id": "ABC", "api_key": "key", "api_url": "http://localhost:8384"},
    }
    config_path.write_text(json.dumps(data))

    from karma.config import SyncConfig
    config = SyncConfig(**json.loads(config_path.read_text()))
    assert config.member_tag == "jayant.mac-mini"

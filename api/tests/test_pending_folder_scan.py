"""Tests for pending folder scan in phase_team_discovery."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from services.sync.reconciliation_service import ReconciliationService
from services.sync.metadata_service import MetadataService


@pytest.fixture
def meta_base(tmp_path):
    base = tmp_path / "metadata-folders"
    base.mkdir()
    return base


@pytest.fixture
def metadata(meta_base):
    return MetadataService(meta_base)


@pytest.fixture
def syncthing_client():
    client = AsyncMock()
    client.get_pending_folders = AsyncMock(return_value={
        "karma-meta--new-team": {
            "offeredBy": {
                "DEVICE-BOB": {"time": "2026-03-20T00:00:00Z", "label": "karma-meta--new-team"}
            }
        }
    })
    return client


@pytest.fixture
def reconciliation(metadata, syncthing_client):
    folders = AsyncMock()
    # No configured folders
    folders.get_configured_folders = AsyncMock(return_value=[])
    folders._client = syncthing_client
    return ReconciliationService(
        teams=MagicMock(),
        members=MagicMock(),
        projects=MagicMock(),
        subs=MagicMock(),
        events=MagicMock(),
        devices=AsyncMock(),
        folders=folders,
        metadata=metadata,
        my_member_tag="alice.mac-mini",
        my_device_id="DEVICE-ALICE",
    )


@pytest.mark.asyncio
async def test_phase_team_discovery_accepts_pending_metadata_folders(reconciliation, syncthing_client):
    """phase_team_discovery should auto-accept pending karma-meta--* folders."""
    reconciliation.teams.get = MagicMock(return_value=None)

    conn = MagicMock()
    with patch("services.sync.reconciliation_service.ReconciliationService.phase_team_discovery",
               wraps=reconciliation.phase_team_discovery):
        await reconciliation.phase_team_discovery(conn)

    # Should have tried to accept the pending folder
    syncthing_client.put_config_folder.assert_called_once()
    call_args = syncthing_client.put_config_folder.call_args[0][0]
    assert call_args["id"] == "karma-meta--new-team"

    # Should have dismissed the pending folder after accepting
    syncthing_client.dismiss_pending_folder.assert_called_once_with(
        "karma-meta--new-team", "DEVICE-BOB"
    )


@pytest.mark.asyncio
async def test_phase_team_discovery_skips_already_configured(reconciliation, syncthing_client):
    """phase_team_discovery should NOT re-accept a folder already in Syncthing config."""
    # Folder already configured
    reconciliation.folders.get_configured_folders = AsyncMock(return_value=[
        {"id": "karma-meta--new-team", "path": "/tmp/meta"}
    ])
    reconciliation.teams.get = MagicMock(return_value=MagicMock())  # Team exists

    conn = MagicMock()
    await reconciliation.phase_team_discovery(conn)

    # Should NOT have tried to accept since it's already configured
    syncthing_client.put_config_folder.assert_not_called()


@pytest.mark.asyncio
async def test_phase_team_discovery_skips_non_meta_pending(reconciliation, syncthing_client):
    """phase_team_discovery should ignore non-karma-meta pending folders."""
    syncthing_client.get_pending_folders = AsyncMock(return_value={
        "karma-out--bob.macbook--some-project": {
            "offeredBy": {"DEVICE-BOB": {"time": "2026-03-20T00:00:00Z"}}
        }
    })

    reconciliation.teams.get = MagicMock(return_value=None)
    conn = MagicMock()
    await reconciliation.phase_team_discovery(conn)

    syncthing_client.put_config_folder.assert_not_called()

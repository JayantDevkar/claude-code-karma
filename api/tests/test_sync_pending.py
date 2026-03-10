"""Tests for pending folder endpoints and SyncthingProxy.get_pending_folders_for_ui."""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).parent.parent))

from services.syncthing_proxy import SyncthingProxy


class TestGetPendingFoldersForUI:
    def test_returns_pending_from_known_members(self):
        mock_client = MagicMock()
        mock_client.get_pending_folders.return_value = {
            "karma-out--alice--myapp": {
                "offeredBy": {"ALICE-DEVICE-ID": {"time": "2026-03-06T00:00:00Z"}}
            }
        }

        proxy = SyncthingProxy.__new__(SyncthingProxy)
        proxy._client = mock_client

        result = proxy.get_pending_folders_for_ui(
            known_devices={"ALICE-DEVICE-ID": ("alice", "my-team")}
        )

        assert len(result) == 1
        assert result[0]["folder_id"] == "karma-out--alice--myapp"
        assert result[0]["from_member"] == "alice"
        assert result[0]["from_team"] == "my-team"
        assert result[0]["from_device"] == "ALICE-DEVICE-ID"
        assert result[0]["offered_at"] == "2026-03-06T00:00:00Z"

    def test_filters_unknown_devices(self):
        mock_client = MagicMock()
        mock_client.get_pending_folders.return_value = {
            "karma-evil": {
                "offeredBy": {"UNKNOWN-DEVICE": {"time": "2026-03-06T00:00:00Z"}}
            }
        }

        proxy = SyncthingProxy.__new__(SyncthingProxy)
        proxy._client = mock_client

        result = proxy.get_pending_folders_for_ui(known_devices={})
        assert len(result) == 0

    def test_filters_non_karma_prefix(self):
        mock_client = MagicMock()
        mock_client.get_pending_folders.return_value = {
            "photos-backup": {
                "offeredBy": {"ALICE-ID": {"time": "2026-03-06T00:00:00Z"}}
            }
        }

        proxy = SyncthingProxy.__new__(SyncthingProxy)
        proxy._client = mock_client

        result = proxy.get_pending_folders_for_ui(
            known_devices={"ALICE-ID": ("alice", "team")}
        )
        assert len(result) == 0

    def test_multiple_offers_from_multiple_members(self):
        mock_client = MagicMock()
        mock_client.get_pending_folders.return_value = {
            "karma-proj-a": {
                "offeredBy": {
                    "ALICE-ID": {"time": "2026-03-06T01:00:00Z"},
                    "BOB-ID": {"time": "2026-03-06T02:00:00Z"},
                }
            },
            "karma-proj-b": {
                "offeredBy": {
                    "ALICE-ID": {"time": "2026-03-06T03:00:00Z"},
                }
            },
        }

        proxy = SyncthingProxy.__new__(SyncthingProxy)
        proxy._client = mock_client

        result = proxy.get_pending_folders_for_ui(
            known_devices={
                "ALICE-ID": ("alice", "team-a"),
                "BOB-ID": ("bob", "team-a"),
            }
        )
        assert len(result) == 3

    def test_empty_pending(self):
        mock_client = MagicMock()
        mock_client.get_pending_folders.return_value = {}

        proxy = SyncthingProxy.__new__(SyncthingProxy)
        proxy._client = mock_client

        result = proxy.get_pending_folders_for_ui(
            known_devices={"ALICE-ID": ("alice", "team")}
        )
        assert len(result) == 0

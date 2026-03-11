"""Tests for subscription checking in auto_share_folders / ensure_inbox_folders."""

import json
from pathlib import Path

import pytest

from services.sync_metadata import read_all_member_states


class TestSubscriptionCheck:
    def test_read_member_subscriptions(self, tmp_path):
        """Should read subscriptions from member metadata files."""
        meta_dir = tmp_path / "metadata-folders" / "acme"
        members_dir = meta_dir / "members"
        members_dir.mkdir(parents=True)

        # Ayush has unsubscribed from one project
        (members_dir / "ayush.ayush-mac.json").write_text(json.dumps({
            "member_tag": "ayush.ayush-mac",
            "user_id": "ayush",
            "device_id": "AYUSH-DID",
            "subscriptions": {
                "jayantdevkar-claude-karma": False,
                "jayantdevkar-other-project": True,
            },
        }))

        # Bob is fully subscribed
        (members_dir / "bob.bob-pc.json").write_text(json.dumps({
            "member_tag": "bob.bob-pc",
            "user_id": "bob",
            "device_id": "BOB-DID",
            "subscriptions": {
                "jayantdevkar-claude-karma": True,
            },
        }))

        states = read_all_member_states(meta_dir)
        assert len(states) == 2

        # Build subscriptions dict keyed by device_id
        member_subs = {}
        for state in states:
            device = state.get("device_id", "")
            subs = state.get("subscriptions", {})
            member_subs[device] = subs

        assert member_subs["AYUSH-DID"]["jayantdevkar-claude-karma"] is False
        assert member_subs["AYUSH-DID"]["jayantdevkar-other-project"] is True
        assert member_subs["BOB-DID"]["jayantdevkar-claude-karma"] is True

    def test_ensure_inbox_skips_unsubscribed_member(self, tmp_path):
        """ensure_inbox_folders should skip inbox creation for unsubscribed members."""
        from unittest.mock import AsyncMock, MagicMock
        import asyncio

        proxy = MagicMock()
        # add_folder should NOT be called for the unsubscribed member
        proxy.add_folder = AsyncMock()
        proxy.update_folder_devices = AsyncMock(side_effect=ValueError("not found"))

        config = MagicMock()
        config.syncthing.device_id = "MY-DID"

        members = [
            {"name": "ayush", "device_id": "AYUSH-DID", "member_tag": "ayush.ayush-mac"},
            {"name": "bob", "device_id": "BOB-DID", "member_tag": "bob.bob-pc"},
        ]

        # Ayush unsubscribed from this project
        member_subscriptions = {
            "AYUSH-DID": {"jayantdevkar-claude-karma": False},
            "BOB-DID": {"jayantdevkar-claude-karma": True},
        }

        from services.sync_folders import ensure_inbox_folders

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr("karma.config.KARMA_BASE", tmp_path)

            result = asyncio.get_event_loop().run_until_complete(
                ensure_inbox_folders(
                    proxy, config, members, "jayantdevkar-claude-karma",
                    "jayantdevkar-claude-karma",
                    member_subscriptions=member_subscriptions,
                )
            )

        # Only bob's inbox should be created (1), ayush skipped
        assert result["inboxes"] == 1

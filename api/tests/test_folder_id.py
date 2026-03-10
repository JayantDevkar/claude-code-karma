"""Tests for services.folder_id — double-dash delimited folder IDs."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from services.folder_id import (
    HANDSHAKE_PREFIX,
    KARMA_PREFIX,
    OUTBOX_PREFIX,
    build_handshake_id,
    build_outbox_id,
    is_handshake_folder,
    is_karma_folder,
    is_outbox_folder,
    parse_handshake_id,
    parse_outbox_id,
)


class TestBuildOutboxId:
    def test_simple(self):
        assert build_outbox_id("alice", "myapp") == "karma-out--alice--myapp"

    def test_hyphenated_username(self):
        assert build_outbox_id("ayush-mini", "claude-code-karma") == (
            "karma-out--ayush-mini--claude-code-karma"
        )

    def test_git_identity_suffix(self):
        assert build_outbox_id("alice", "jayantdevkar-claude-code-karma") == (
            "karma-out--alice--jayantdevkar-claude-code-karma"
        )

    def test_rejects_double_dash_in_username(self):
        with pytest.raises(ValueError, match="must not contain '--'"):
            build_outbox_id("bad--name", "suffix")

    def test_rejects_double_dash_in_suffix(self):
        with pytest.raises(ValueError, match="must not contain '--'"):
            build_outbox_id("alice", "bad--suffix")

    def test_rejects_empty_username(self):
        with pytest.raises(ValueError, match="must not be empty"):
            build_outbox_id("", "suffix")

    def test_rejects_empty_suffix(self):
        with pytest.raises(ValueError, match="must not be empty"):
            build_outbox_id("alice", "")


class TestBuildHandshakeId:
    def test_simple(self):
        assert build_handshake_id("alice", "my-team") == "karma-join--alice--my-team"

    def test_hyphenated_both(self):
        assert build_handshake_id("ayush-mini", "cool-team") == (
            "karma-join--ayush-mini--cool-team"
        )

    def test_rejects_double_dash(self):
        with pytest.raises(ValueError):
            build_handshake_id("alice", "bad--team")


class TestParseOutboxId:
    def test_simple(self):
        assert parse_outbox_id("karma-out--alice--myapp") == ("alice", "myapp")

    def test_hyphenated_username(self):
        assert parse_outbox_id("karma-out--ayush-mini--claude-code-karma") == (
            "ayush-mini",
            "claude-code-karma",
        )

    def test_roundtrip(self):
        """build → parse roundtrip."""
        fid = build_outbox_id("ayush-mini", "claude-code-karma")
        assert parse_outbox_id(fid) == ("ayush-mini", "claude-code-karma")

    def test_rejects_wrong_prefix(self):
        assert parse_outbox_id("karma-join--alice--team") is None

    def test_rejects_no_prefix(self):
        assert parse_outbox_id("random-folder") is None

    def test_rejects_old_format(self):
        """Old single-dash format should NOT parse."""
        assert parse_outbox_id("karma-out-alice-myapp") is None

    def test_rejects_single_part(self):
        assert parse_outbox_id("karma-out--aliceonly") is None

    def test_rejects_empty_username(self):
        assert parse_outbox_id("karma-out----suffix") is None

    def test_rejects_three_parts(self):
        """Extra -- in the value creates 3 parts → reject."""
        assert parse_outbox_id("karma-out--alice--some--extra") is None


class TestParseHandshakeId:
    def test_simple(self):
        assert parse_handshake_id("karma-join--alice--team-a") == ("alice", "team-a")

    def test_roundtrip(self):
        fid = build_handshake_id("ayush-mini", "cool-team")
        assert parse_handshake_id(fid) == ("ayush-mini", "cool-team")

    def test_rejects_wrong_prefix(self):
        assert parse_handshake_id("karma-out--alice--myapp") is None

    def test_rejects_old_format(self):
        assert parse_handshake_id("karma-join-alice-team") is None


class TestPredicates:
    def test_is_karma_folder(self):
        assert is_karma_folder("karma-out--alice--x") is True
        assert is_karma_folder("karma-join--bob--y") is True
        assert is_karma_folder("karma-something") is True
        assert is_karma_folder("photos-backup") is False

    def test_is_outbox_folder(self):
        assert is_outbox_folder("karma-out--alice--x") is True
        assert is_outbox_folder("karma-out-old-format") is False
        assert is_outbox_folder("karma-join--bob--y") is False

    def test_is_handshake_folder(self):
        assert is_handshake_folder("karma-join--alice--team") is True
        assert is_handshake_folder("karma-join-old-format") is False
        assert is_handshake_folder("karma-out--alice--x") is False


class TestPrefixConstants:
    def test_outbox_prefix(self):
        assert OUTBOX_PREFIX == "karma-out--"

    def test_handshake_prefix(self):
        assert HANDSHAKE_PREFIX == "karma-join--"

    def test_karma_prefix(self):
        assert KARMA_PREFIX == "karma-"

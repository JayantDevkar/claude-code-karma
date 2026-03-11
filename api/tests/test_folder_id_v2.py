"""Tests for folder_id.py v2 — member_tag in folder IDs."""

import pytest
from services.folder_id import (
    build_outbox_id,
    build_handshake_id,
    parse_outbox_id,
    parse_handshake_id,
    parse_member_tag,
)


class TestBuildWithMemberTag:
    def test_outbox_with_member_tag(self):
        fid = build_outbox_id("jayant.mac-mini", "jayantdevkar-claude-karma")
        assert fid == "karma-out--jayant.mac-mini--jayantdevkar-claude-karma"

    def test_handshake_with_member_tag(self):
        fid = build_handshake_id("jayant.mac-mini", "acme")
        assert fid == "karma-join--jayant.mac-mini--acme"

    def test_two_devices_produce_different_outbox_ids(self):
        fid1 = build_outbox_id("jayant.mac-mini", "proj")
        fid2 = build_outbox_id("jayant.mbp", "proj")
        assert fid1 != fid2


class TestParseWithMemberTag:
    def test_parse_outbox_returns_member_tag(self):
        result = parse_outbox_id("karma-out--jayant.mac-mini--proj-suffix")
        assert result == ("jayant.mac-mini", "proj-suffix")

    def test_parse_handshake_returns_member_tag(self):
        result = parse_handshake_id("karma-join--ayush.ayush-mac--acme")
        assert result == ("ayush.ayush-mac", "acme")


class TestParseMemberTag:
    def test_parse_valid_member_tag(self):
        user_id, machine_tag = parse_member_tag("jayant.mac-mini")
        assert user_id == "jayant"
        assert machine_tag == "mac-mini"

    def test_parse_no_dot_returns_bare_name(self):
        """Legacy format without machine_tag — treat as user_id only."""
        user_id, machine_tag = parse_member_tag("jayant")
        assert user_id == "jayant"
        assert machine_tag is None

    def test_parse_multiple_dots_splits_on_first(self):
        user_id, machine_tag = parse_member_tag("jayant.mac.mini")
        assert user_id == "jayant"
        assert machine_tag == "mac.mini"

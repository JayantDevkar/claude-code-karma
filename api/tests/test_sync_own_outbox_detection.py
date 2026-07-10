"""Tests for own-outbox detection in pending folder classification.

Reproduces the bug where the leader stores a sanitized hostname (e.g.,
"jayants-mac-mini") instead of the correct member_tag ("jay-mac-mini.
jayants-mac-mini-local"). The joiner's _is_own_outbox check then fails
to recognize the folder as its own outbox, causing it to be misclassified
as "sessions" instead of "outbox" and merged with the leader's real outbox
(device_count=2).

Note: ``build_own_names`` was originally in ``services.sync_identity_match``
(deleted as dead v3 code).  The function is inlined here so the test
remains self-contained.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).parent.parent))

# Domain suffixes commonly stripped by Syncthing device name sanitization.
_HOSTNAME_SUFFIXES = (".local", ".lan", ".home", ".internal", ".localdomain")


def _sanitize_hostname(raw: str) -> str:
    """Strip domain suffix and lowercase."""
    lower = raw.strip().lower()
    for suffix in _HOSTNAME_SUFFIXES:
        if lower.endswith(suffix):
            return lower[: -len(suffix)]
    return lower


def build_own_names(
    user_id: Optional[str],
    machine_id: Optional[str],
    machine_tag: Optional[str],
    member_tag: Optional[str],
) -> set[str]:
    """Build the set of all name variants that identify this machine."""
    names: set[str] = set()
    if user_id:
        names.add(user_id)
    if machine_id:
        names.add(machine_id)
        names.add(_sanitize_hostname(machine_id))
    if machine_tag:
        names.add(machine_tag)
    if member_tag:
        names.add(member_tag)
    return names


class TestBuildOwnNames:
    """Test that build_own_names produces all reasonable identity variants."""

    def test_includes_user_id(self):
        names = build_own_names("jay-mac-mini", "Jayants-Mac-mini.local", "jayants-mac-mini-local", "jay-mac-mini.jayants-mac-mini-local")
        assert "jay-mac-mini" in names

    def test_includes_machine_id(self):
        names = build_own_names("jay-mac-mini", "Jayants-Mac-mini.local", "jayants-mac-mini-local", "jay-mac-mini.jayants-mac-mini-local")
        assert "Jayants-Mac-mini.local" in names

    def test_includes_member_tag(self):
        names = build_own_names("jay-mac-mini", "Jayants-Mac-mini.local", "jayants-mac-mini-local", "jay-mac-mini.jayants-mac-mini-local")
        assert "jay-mac-mini.jayants-mac-mini-local" in names

    def test_includes_machine_tag(self):
        names = build_own_names("jay-mac-mini", "Jayants-Mac-mini.local", "jayants-mac-mini-local", "jay-mac-mini.jayants-mac-mini-local")
        assert "jayants-mac-mini-local" in names

    def test_includes_sanitized_hostname(self):
        """The exact scenario that caused the bug: leader used sanitized
        hostname 'jayants-mac-mini' (stripped .local suffix) as the
        folder owner tag.
        """
        names = build_own_names("jay-mac-mini", "Jayants-Mac-mini.local", "jayants-mac-mini-local", "jay-mac-mini.jayants-mac-mini-local")
        assert "jayants-mac-mini" in names

    def test_sanitizes_common_suffixes(self):
        """All common hostname suffixes should be stripped."""
        for hostname in [
            "my-mac.local",
            "my-mac.lan",
            "my-mac.home",
            "my-mac.internal",
            "my-mac.localdomain",
        ]:
            names = build_own_names("user", hostname, "my-mac-local", "user.my-mac-local")
            assert "my-mac" in names, f"Failed for hostname {hostname}"

    def test_lowercases_sanitized_hostname(self):
        names = build_own_names("user", "MyMac.local", "mymac-local", "user.mymac-local")
        assert "mymac" in names

    def test_handles_none_values(self):
        names = build_own_names(None, None, None, None)
        assert len(names) == 0

    def test_handles_partial_none(self):
        names = build_own_names("user", None, None, "user")
        assert "user" in names
        assert len(names) == 1

    def test_no_suffix_hostname(self):
        """Hostname without a known suffix should still be included lowercase."""
        names = build_own_names("user", "myhost", "myhost", "user.myhost")
        assert "myhost" in names


class TestIsOwnOutbox:
    """Integration test: own_names recognizes folders created with hostname fallback."""

    def test_recognizes_sanitized_hostname_folder(self):
        """Reproduce the exact bug: leader creates karma-out--jayants-mac-mini--suffix
        but joiner's member_tag is jay-mac-mini.jayants-mac-mini-local."""
        from services.syncthing.folder_manager import parse_outbox_id

        # Leader created inbox with sanitized hostname
        folder_id = "karma-out--jayants-mac-mini--the-non-expert-humanassaince"
        parsed = parse_outbox_id(folder_id)
        assert parsed is not None
        owner, _ = parsed

        # Joiner's identity
        names = build_own_names(
            user_id="jay-mac-mini",
            machine_id="Jayants-Mac-mini.local",
            machine_tag="jayants-mac-mini-local",
            member_tag="jay-mac-mini.jayants-mac-mini-local",
        )

        # This was the bug — "jayants-mac-mini" was NOT in own_names
        assert owner in names, (
            f"Sanitized hostname '{owner}' not recognized as own. "
            f"own_names={names}"
        )

"""Own-identity matching for sync folder classification.

Builds the set of all reasonable name variants that could identify THIS
machine in a Syncthing folder ID.  Covers the case where a remote leader
used a sanitized hostname (e.g., "jayants-mac-mini") instead of the
correct member_tag ("jay-mac-mini.jayants-mac-mini-local") when creating
inbox folders.
"""

from __future__ import annotations

from typing import Optional

# Domain suffixes commonly stripped by Syncthing device name sanitization.
# Must match the list in sync_devices._sanitize_device_name.
_HOSTNAME_SUFFIXES = (".local", ".lan", ".home", ".internal", ".localdomain")


def _sanitize_hostname(raw: str) -> str:
    """Strip domain suffix and lowercase — mirrors sync_devices._sanitize_device_name."""
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
    """Build the set of all name variants that identify this machine.

    Returns identifiers that could appear as the owner in a
    ``karma-out--{owner}--{suffix}`` folder ID, covering:
    - user_id (e.g., "jay-mac-mini")
    - machine_id / raw hostname (e.g., "Jayants-Mac-mini.local")
    - machine_tag (e.g., "jayants-mac-mini-local")
    - member_tag (e.g., "jay-mac-mini.jayants-mac-mini-local")
    - sanitized hostname — hostname with domain suffix stripped and
      lowercased (e.g., "jayants-mac-mini").  This is the fallback
      identity a remote leader may use when accepting a device before
      handshake/metadata syncs.
    """
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

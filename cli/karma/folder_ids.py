"""Shared folder ID parsing utilities for karma Syncthing folder IDs.

Re-exports the canonical implementations from ``api/services/folder_id``.
The CLI-only ``compute_proj_suffix()`` is defined locally.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

# Add API to path for services.folder_id
_API_PATH = Path(__file__).parent.parent.parent / "api"
if str(_API_PATH) not in sys.path:
    sys.path.insert(0, str(_API_PATH))

from services.folder_id import (  # noqa: E402, F401
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


def compute_proj_suffix(
    git_identity: Optional[str], path: Optional[str], encoded: str
) -> str:
    """Compute the project suffix used in Syncthing folder IDs.

    Priority:
    1. ``git_identity`` (e.g. ``jayantdevkar/my-repo``) with ``/`` → ``-``
    2. Last component of ``path`` (e.g. ``my-repo`` from ``/Users/me/my-repo``)
    3. ``encoded`` project name as fallback
    """
    if git_identity:
        return git_identity.replace("/", "-")
    return Path(path).name if path else encoded

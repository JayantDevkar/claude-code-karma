"""SharedProject domain model.

A SharedProject represents a git repository that has been shared within a Team
via Syncthing. The folder_suffix is derived from the git_identity and used to
construct Syncthing folder IDs.
"""
from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

from domain.team import InvalidTransitionError


def derive_folder_suffix(git_identity: str) -> str:
    """Derive a Syncthing-safe folder suffix from a git identity string.

    Rules:
      - Strip trailing ".git"
      - Replace all "/" with "-"

    Examples:
      "user/repo.git"                          → "user-repo"
      "https://github.com/user/repo.git"       → "https:-github.com-user-repo"
      "org/team/repo"                          → "org-team-repo"
    """
    suffix = git_identity
    if suffix.endswith(".git"):
        suffix = suffix[:-4]
    suffix = suffix.replace("/", "-")
    return suffix


class SharedProjectStatus(str, Enum):
    SHARED = "shared"
    REMOVED = "removed"


class SharedProject(BaseModel):
    """Immutable domain model representing a project shared within a team."""

    model_config = ConfigDict(frozen=True)

    team_name: str
    git_identity: str
    encoded_name: Optional[str] = None
    folder_suffix: str
    status: SharedProjectStatus = SharedProjectStatus.SHARED
    shared_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )

    # ------------------------------------------------------------------
    # State transitions
    # ------------------------------------------------------------------

    def remove(self) -> "SharedProject":
        """Transition SHARED → REMOVED.

        Raises:
            InvalidTransitionError: if already REMOVED.
        """
        if self.status == SharedProjectStatus.REMOVED:
            raise InvalidTransitionError(
                f"Project '{self.git_identity}' is already removed."
            )
        return self.model_copy(update={"status": SharedProjectStatus.REMOVED})

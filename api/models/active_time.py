"""Active time: the sum of gaps between messages, with each idle gap capped."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

# Idle gaps between messages count toward active duration only up to this cap
ACTIVE_IDLE_CAP_SECONDS = 30 * 60


class ActiveTimeAccumulator:
    """Feed message timestamps in file order; `seconds` is the active time so far."""

    def __init__(self) -> None:
        self.seconds = 0.0
        self._latest: Optional[datetime] = None  # active time only moves forward

    def add(self, timestamp: Optional[datetime]) -> None:
        if timestamp is None:
            return
        if self._latest is None:
            self._latest = timestamp
        elif timestamp > self._latest:
            gap = (timestamp - self._latest).total_seconds()
            self.seconds += min(gap, ACTIVE_IDLE_CAP_SECONDS)
            self._latest = timestamp

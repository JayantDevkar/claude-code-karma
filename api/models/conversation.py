"""
ConversationEntity Protocol - unified interface for Session and Agent.

This protocol defines the common interface shared by Session and Agent models,
enabling code reuse in routers and collectors that work with either type.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Iterator, Optional, Protocol, runtime_checkable

if TYPE_CHECKING:
    from .message import Message
    from .usage import TokenUsage


@runtime_checkable
class ConversationEntity(Protocol):
    """
    Protocol for conversation-like entities (Session, Agent).

    Both Session and Agent satisfy this protocol, enabling unified
    handling in data collection and API endpoints.
    """

    @property
    def jsonl_path(self) -> Path:
        """Path to the JSONL file containing messages."""
        ...

    def iter_messages(self) -> Iterator["Message"]:
        """Iterate over messages lazily."""
        ...

    @property
    def message_count(self) -> int:
        """Total message count."""
        ...

    @property
    def start_time(self) -> Optional[datetime]:
        """Timestamp of first message."""
        ...

    @property
    def end_time(self) -> Optional[datetime]:
        """Timestamp of last message."""
        ...

    def get_usage_summary(self) -> "TokenUsage":
        """Aggregated token usage."""
        ...


def is_session(entity: ConversationEntity) -> bool:
    """
    Type guard for Session entities.

    Args:
        entity: A ConversationEntity to check

    Returns:
        True if the entity is a Session (has list_subagents method)
    """
    return hasattr(entity, "list_subagents")


def is_agent(entity: ConversationEntity) -> bool:
    """
    Type guard for Agent entities.

    Args:
        entity: A ConversationEntity to check

    Returns:
        True if the entity is an Agent (has is_subagent attribute)
    """
    return hasattr(entity, "is_subagent") and hasattr(entity, "agent_id")

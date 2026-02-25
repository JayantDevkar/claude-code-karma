"""
Session relationship models for tracking session chains.

Relationships:
- RESUMED_FROM: This session was resumed/continued from a parent session
- PROVIDED_CONTEXT_TO: This session's context was loaded by a child session
- FORKED_FROM: Future - session branched from a parent (different path)

These models are immutable value objects for representing session chains.
"""

from datetime import datetime
from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field


class RelationshipType(str, Enum):
    """Types of relationships between sessions."""

    RESUMED_FROM = "resumed_from"  # This session resumed from parent
    PROVIDED_CONTEXT_TO = "provided_context_to"  # This session provided context to child
    FORKED_FROM = "forked_from"  # Future: session branched from parent


class SessionRelationship(BaseModel):
    """
    Represents a directed relationship between two sessions.

    Immutable, lightweight value object for representing session chains.
    Direction is always source → target.

    Example:
        SessionA provided context to SessionB
        - source_uuid = SessionA
        - target_uuid = SessionB
        - relationship_type = PROVIDED_CONTEXT_TO

        SessionB resumed from SessionA
        - source_uuid = SessionA
        - target_uuid = SessionB
        - relationship_type = RESUMED_FROM
    """

    model_config = ConfigDict(frozen=True)

    source_uuid: str = Field(..., description="Source session UUID (parent/provider)")
    target_uuid: str = Field(..., description="Target session UUID (child/recipient)")
    relationship_type: RelationshipType = Field(..., description="Type of relationship")

    # Relationship metadata
    source_slug: Optional[str] = Field(None, description="Source session slug")
    target_slug: Optional[str] = Field(None, description="Target session slug")
    detected_via: str = Field(..., description="Detection method: 'leaf_uuid'")
    confidence: float = Field(
        ..., ge=0.0, le=1.0, description="Confidence score 0.0-1.0 based on detection method"
    )

    # Timing metadata for validation
    source_end_time: Optional[datetime] = Field(None, description="When source session ended")
    target_start_time: Optional[datetime] = Field(None, description="When target session started")


class SessionChainNode(BaseModel):
    """
    A node in a session chain, representing one session's position.

    Used for frontend display of session chains/families.
    The chain forms a tree structure rooted at the oldest ancestor.
    """

    model_config = ConfigDict(frozen=True)

    uuid: str = Field(..., description="Session UUID")
    slug: Optional[str] = Field(None, description="Session slug if available")
    start_time: Optional[datetime] = Field(None, description="Session start time")
    end_time: Optional[datetime] = Field(None, description="Session end time")
    is_current: bool = Field(False, description="True if this is the session being viewed")

    # Chain position
    chain_depth: int = Field(
        0, description="Depth in chain: 0=root ancestor, 1=child, 2=grandchild, etc."
    )
    parent_uuid: Optional[str] = Field(
        None, description="Parent session UUID in chain (None for root)"
    )
    children_uuids: List[str] = Field(
        default_factory=list, description="Child session UUIDs that resumed from this session"
    )

    # Session metadata for display
    was_compacted: bool = Field(False, description="True if session underwent context compaction")
    is_continuation_marker: bool = Field(
        False, description="True if session is a continuation marker (no real content)"
    )
    message_count: int = Field(0, description="Number of messages in session")
    initial_prompt: Optional[str] = Field(None, description="First user prompt (truncated)")

    # Resume detection metadata
    resume_detected_via: Optional[str] = Field(
        None, description="How resume was detected: 'leaf_uuid' or None"
    )


class SessionChain(BaseModel):
    """
    Complete session chain for a given session.

    Contains the full tree of related sessions from root ancestor
    to all leaf descendants.
    """

    model_config = ConfigDict(frozen=True)

    # The session this chain was built for
    current_session_uuid: str = Field(
        ..., description="UUID of the session this chain was requested for"
    )

    # All nodes in the chain, ordered by chain_depth then start_time
    nodes: List[SessionChainNode] = Field(
        default_factory=list, description="All sessions in the chain"
    )

    # Root of the chain (oldest ancestor)
    root_uuid: Optional[str] = Field(None, description="UUID of the root ancestor session")

    # Chain statistics
    total_sessions: int = Field(0, description="Total number of sessions in chain")
    max_depth: int = Field(0, description="Maximum chain depth (0 = single session)")
    total_compactions: int = Field(0, description="Total compaction events across all sessions")

    @property
    def is_single_session(self) -> bool:
        """True if chain contains only one session (no relationships)."""
        return len(self.nodes) <= 1

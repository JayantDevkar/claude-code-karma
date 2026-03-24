"""
Service for discovering and resolving session relationships.

This service layer keeps Session model clean while providing relationship logic.
Uses leaf_uuid matching (95% confidence) - direct reference in JSONL summaries.
"""

import logging
import time
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Dict, List, Optional, Set

from models.session import Session
from models.session_relationship import (
    RelationshipType,
    SessionChain,
    SessionChainNode,
    SessionRelationship,
)

if TYPE_CHECKING:
    from schemas import SessionChainInfoSummary

logger = logging.getLogger(__name__)

# Module-level resolver cache: keyed by project_dir, with TTL to avoid stale data
_resolver_cache: Dict[str, tuple["SessionRelationshipResolver", float]] = {}
_RESOLVER_TTL = 300  # 5 minutes


def get_resolver(project_dir: Path) -> "SessionRelationshipResolver":
    """Get or create a cached resolver for a project directory."""
    key = str(project_dir)
    now = time.monotonic()
    if key in _resolver_cache:
        resolver, created_at = _resolver_cache[key]
        if now - created_at < _RESOLVER_TTL:
            return resolver
    resolver = SessionRelationshipResolver(project_dir)
    _resolver_cache[key] = (resolver, now)
    return resolver


class SessionRelationshipResolver:
    """
    Discovers and resolves relationships between sessions.

    Detection method:
    1. leaf_uuid (95% confidence): Direct reference in JSONL summary messages

    Usage:
        resolver = SessionRelationshipResolver(project_dir)
        relationships = resolver.find_relationships(session)
        chain = resolver.build_chain(session_uuid)
    """

    # Confidence scores by detection method
    CONFIDENCE_LEAF_UUID = 0.95

    def __init__(self, project_dir: Path):
        """
        Initialize resolver for a project directory.

        Args:
            project_dir: Path to the project's session directory
                        (e.g., ~/.claude/projects/-Users-me-repo/)
        """
        self.project_dir = project_dir
        self._session_cache: Dict[str, Session] = {}
        self._uuid_to_session_map: Optional[Dict[str, str]] = None

        self._leaf_uuid_children_map: Optional[Dict[str, List[str]]] = None
        self._relationships_cache: Dict[str, List[SessionRelationship]] = {}

    def _get_session(self, uuid: str) -> Optional[Session]:
        """Load session with caching."""
        if uuid not in self._session_cache:
            jsonl_path = self.project_dir / f"{uuid}.jsonl"
            if jsonl_path.exists():
                try:
                    self._session_cache[uuid] = Session.from_path(jsonl_path)
                except Exception as e:
                    logger.warning(f"Failed to load session {uuid}: {e}")
                    return None
            else:
                return None
        return self._session_cache[uuid]

    def _build_uuid_to_session_map(self) -> Dict[str, str]:
        """
        Build a map of message UUIDs to session UUIDs.

        Optimized: only indexes message UUIDs that are referenced as leaf_uuid
        targets by other sessions, rather than indexing every message.
        """
        if self._uuid_to_session_map is not None:
            return self._uuid_to_session_map

        self._uuid_to_session_map = {}

        # First pass: collect all leaf_uuid targets we need to resolve
        target_uuids: Set[str] = set()
        for jsonl_path in self.project_dir.glob("*.jsonl"):
            if jsonl_path.name.startswith("agent-"):
                continue
            try:
                session = self._get_session(jsonl_path.stem)
                if session and session.project_context_leaf_uuids:
                    target_uuids.update(session.project_context_leaf_uuids)
            except Exception:
                continue

        if not target_uuids:
            return self._uuid_to_session_map

        # Second pass: scan messages only to find target UUIDs
        remaining = set(target_uuids)
        for jsonl_path in self.project_dir.glob("*.jsonl"):
            if not remaining:
                break
            if jsonl_path.name.startswith("agent-"):
                continue
            session_uuid = jsonl_path.stem
            try:
                session = self._get_session(session_uuid)
                if not session:
                    continue
                for msg in session.iter_messages():
                    msg_uuid = getattr(msg, "uuid", None)
                    if msg_uuid and msg_uuid in remaining:
                        self._uuid_to_session_map[msg_uuid] = session_uuid
                        remaining.discard(msg_uuid)
                        if not remaining:
                            break
            except Exception:
                continue

        return self._uuid_to_session_map

    def _build_leaf_uuid_children_map(self) -> Dict[str, List[str]]:
        """
        Build reverse index: parent_session_uuid -> [child_session_uuids].

        Scans all sessions' project_context_leaf_uuids to find which sessions
        resumed from which. This enables discovering children of a session
        even when starting BFS from the parent.
        """
        if self._leaf_uuid_children_map is not None:
            return self._leaf_uuid_children_map

        self._leaf_uuid_children_map = {}
        uuid_map = self._build_uuid_to_session_map()

        for jsonl_path in self.project_dir.glob("*.jsonl"):
            if jsonl_path.name.startswith("agent-"):
                continue
            child_uuid = jsonl_path.stem
            try:
                child = self._get_session(child_uuid)
                if not child or not child.project_context_leaf_uuids:
                    continue
                for leaf_uuid in child.project_context_leaf_uuids:
                    parent_session_uuid = uuid_map.get(leaf_uuid)
                    if parent_session_uuid and parent_session_uuid != child_uuid:
                        if parent_session_uuid not in self._leaf_uuid_children_map:
                            self._leaf_uuid_children_map[parent_session_uuid] = []
                        if child_uuid not in self._leaf_uuid_children_map[parent_session_uuid]:
                            self._leaf_uuid_children_map[parent_session_uuid].append(child_uuid)
            except Exception as e:
                logger.debug(f"Error scanning session {child_uuid} for leaf_uuids: {e}")
                continue

        return self._leaf_uuid_children_map

    def _find_session_by_message_uuid(self, message_uuid: str) -> Optional[Session]:
        """Find session containing a specific message UUID."""
        uuid_map = self._build_uuid_to_session_map()
        session_uuid = uuid_map.get(message_uuid)

        if session_uuid:
            return self._get_session(session_uuid)
        return None

    def find_relationships(self, session: Session) -> List[SessionRelationship]:
        """
        Find all relationships for a given session.

        Returns both inbound (this session resumed FROM) and outbound
        (this session PROVIDED CONTEXT TO) relationships.

        Detection method:
        1. leaf_uuid (95%): Direct reference in JSONL summary messages

        Args:
            session: The session to find relationships for

        Returns:
            List of SessionRelationship objects with confidence scores
        """
        if session.uuid in self._relationships_cache:
            return self._relationships_cache[session.uuid]

        relationships: List[SessionRelationship] = []
        seen_pairs: Set[tuple] = set()  # Avoid duplicate relationships

        # Check if this session loaded context from previous sessions
        # This is the most reliable method (direct leaf_uuid reference)
        if session.project_context_leaf_uuids:
            for leaf_uuid in session.project_context_leaf_uuids:
                parent = self._find_session_by_message_uuid(leaf_uuid)
                if parent and parent.uuid != session.uuid:
                    pair_key = (parent.uuid, session.uuid, RelationshipType.PROVIDED_CONTEXT_TO)
                    if pair_key not in seen_pairs:
                        seen_pairs.add(pair_key)
                        relationships.append(
                            SessionRelationship(
                                source_uuid=parent.uuid,
                                target_uuid=session.uuid,
                                relationship_type=RelationshipType.PROVIDED_CONTEXT_TO,
                                source_slug=parent.slug,
                                target_slug=session.slug,
                                detected_via="leaf_uuid",
                                confidence=self.CONFIDENCE_LEAF_UUID,
                                source_end_time=parent.end_time,
                                target_start_time=session.start_time,
                            )
                        )

        self._relationships_cache[session.uuid] = relationships
        return relationships

    def find_all_related_sessions(self, session_uuid: str) -> Set[str]:
        """
        Find all session UUIDs related to a given session (ancestors + descendants).

        Uses BFS traversal of leaf_uuid relationships.
        """
        session = self._get_session(session_uuid)
        if not session:
            return set()

        related: Set[str] = {session_uuid}

        # Add children discovered via reverse leaf_uuid index
        children_map = self._build_leaf_uuid_children_map()
        for child_uuid in children_map.get(session_uuid, []):
            related.add(child_uuid)

        # BFS for leaf_uuid relationships (may find additional cross-slug links)
        to_process: List[str] = list(related)
        processed: Set[str] = set()

        while to_process:
            current_uuid = to_process.pop(0)
            if current_uuid in processed:
                continue
            processed.add(current_uuid)

            current = self._get_session(current_uuid)
            if not current:
                continue

            # Add children via reverse leaf_uuid index
            for child_uuid in children_map.get(current_uuid, []):
                if child_uuid not in related:
                    related.add(child_uuid)
                    to_process.append(child_uuid)

            # Find relationships for current session
            relationships = self.find_relationships(current)

            for rel in relationships:
                # Add related sessions to processing queue
                if rel.source_uuid not in related:
                    related.add(rel.source_uuid)
                    to_process.append(rel.source_uuid)
                if rel.target_uuid not in related:
                    related.add(rel.target_uuid)
                    to_process.append(rel.target_uuid)

        return related

    def build_chain(self, session_uuid: str) -> SessionChain:
        """
        Build the full session chain for a given session.

        Returns ordered tree from root ancestor to leaf descendants.

        Args:
            session_uuid: UUID of the session to build chain for

        Returns:
            SessionChain containing all related sessions
        """
        # Find all related sessions
        related_uuids = self.find_all_related_sessions(session_uuid)

        if not related_uuids:
            return SessionChain(
                current_session_uuid=session_uuid,
                nodes=[],
                total_sessions=0,
                max_depth=0,
                total_compactions=0,
            )

        # Build relationship map
        parent_of: Dict[str, str] = {}  # child -> parent
        children_of: Dict[str, List[str]] = {}  # parent -> [children]

        for uuid in related_uuids:
            session = self._get_session(uuid)
            if not session:
                continue

            relationships = self.find_relationships(session)

            for rel in relationships:
                if rel.relationship_type in (
                    RelationshipType.PROVIDED_CONTEXT_TO,
                    RelationshipType.RESUMED_FROM,
                ):
                    # source is parent, target is child
                    parent_of[rel.target_uuid] = rel.source_uuid
                    if rel.source_uuid not in children_of:
                        children_of[rel.source_uuid] = []
                    if rel.target_uuid not in children_of[rel.source_uuid]:
                        children_of[rel.source_uuid].append(rel.target_uuid)

        # Find root (session with no parent)
        root_uuid: Optional[str] = None
        for uuid in related_uuids:
            if uuid not in parent_of:
                root_uuid = uuid
                break

        if root_uuid is None:
            # Fallback: use the requested session as root
            root_uuid = session_uuid

        # Build nodes with depth using BFS
        nodes: List[SessionChainNode] = []
        total_compactions = 0
        max_depth = 0

        to_visit: List[tuple] = [(root_uuid, 0)]  # (uuid, depth)
        visited: Set[str] = set()

        while to_visit:
            current_uuid, depth = to_visit.pop(0)
            if current_uuid in visited:
                continue
            visited.add(current_uuid)

            session = self._get_session(current_uuid)
            if not session:
                continue

            max_depth = max(max_depth, depth)
            if session.was_compacted:
                total_compactions += session.compaction_summary_count

            # Get initial prompt from first user message
            initial_prompt = None
            for msg in session.iter_user_messages():
                if msg.content:
                    from utils import extract_prompt_from_content
                    prompt = extract_prompt_from_content(msg.content)
                    if prompt:
                        initial_prompt = prompt[:200]
                        break

            node = SessionChainNode(
                uuid=session.uuid,
                slug=session.slug,
                start_time=session.start_time,
                end_time=session.end_time,
                is_current=(session.uuid == session_uuid),
                chain_depth=depth,
                parent_uuid=parent_of.get(session.uuid),
                children_uuids=children_of.get(session.uuid, []),
                was_compacted=session.was_compacted,
                is_continuation_marker=session.is_continuation_marker,
                message_count=session.message_count,
                initial_prompt=initial_prompt,
            )
            nodes.append(node)

            # Add children to visit queue
            for child_uuid in children_of.get(current_uuid, []):
                if child_uuid not in visited:
                    to_visit.append((child_uuid, depth + 1))

        # Sort by depth, then start_time
        nodes.sort(key=lambda n: (n.chain_depth, n.start_time or datetime.min))

        return SessionChain(
            current_session_uuid=session_uuid,
            nodes=nodes,
            root_uuid=root_uuid,
            total_sessions=len(nodes),
            max_depth=max_depth,
            total_compactions=total_compactions,
        )

    def get_chain_info_for_all_sessions(
        self, sessions: List[Session], conn=None
    ) -> Dict[str, "SessionChainInfoSummary"]:
        """
        Build lightweight chain info for all sessions (for list views).

        When a DB connection is provided, uses the efficient DB-backed query
        that combines leaf_uuid + slug matching with overlap filtering.
        Falls back to slug-only grouping when no DB connection is available.

        Args:
            sessions: List of sessions to analyze
            conn: Optional sqlite3 connection for DB-backed chain detection

        Returns:
            Dict mapping session UUID to SessionChainInfoSummary
        """
        from schemas import SessionChainInfoSummary

        # Fast path: use DB-backed query if available
        if conn is not None and sessions:
            try:
                from db.queries import query_chain_info_for_project

                # Get project from first session's path
                # All sessions in a call share the same project
                first_path = str(self.project_dir)
                # Extract encoded project name from path
                import os

                project_encoded = os.path.basename(first_path.rstrip("/"))

                db_info = query_chain_info_for_project(conn, project_encoded)
                chain_info_map: Dict[str, SessionChainInfoSummary] = {}
                for uuid, info in db_info.items():
                    chain_info_map[uuid] = SessionChainInfoSummary(
                        chain_id=info["chain_id"],
                        position=info["position"],
                        total=info["total"],
                        is_root=info["is_root"],
                        is_latest=info["is_latest"],
                    )
                return chain_info_map
            except Exception:
                logger.debug("DB-backed chain info failed, falling back to slug-only")

        # Fallback: leaf_uuid-based grouping
        chain_info_map = {}
        # Build parent relationships from leaf_uuids
        parent_of: Dict[str, str] = {}  # child -> parent
        for session in sessions:
            if session.project_context_leaf_uuids:
                for leaf_uuid in session.project_context_leaf_uuids:
                    parent = self._find_session_by_message_uuid(leaf_uuid)
                    if parent and parent.uuid != session.uuid:
                        parent_of[session.uuid] = parent.uuid
                        break

        # Build chains from parent relationships
        # Find roots (sessions with no parent)
        _all_uuids = {s.uuid for s in sessions}  # noqa: F841
        children_of: Dict[str, List[str]] = {}
        for child, parent in parent_of.items():
            if parent not in children_of:
                children_of[parent] = []
            children_of[parent].append(child)

        roots = [s.uuid for s in sessions if s.uuid not in parent_of and s.uuid in children_of]

        for root_uuid in roots:
            # Walk chain from root
            chain: List[str] = []
            current = root_uuid
            visited: Set[str] = set()
            while current and current not in visited:
                visited.add(current)
                chain.append(current)
                kids = children_of.get(current, [])
                current = kids[0] if kids else None

            if len(chain) < 2:
                continue

            chain_id = root_uuid[:8]
            for idx, uuid in enumerate(chain):
                from schemas import SessionChainInfoSummary

                chain_info_map[uuid] = SessionChainInfoSummary(
                    chain_id=chain_id,
                    position=idx,
                    total=len(chain),
                    is_root=idx == 0,
                    is_latest=idx == len(chain) - 1,
                )

        return chain_info_map

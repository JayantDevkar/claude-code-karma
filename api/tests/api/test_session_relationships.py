"""
Unit tests for session relationship and chain detection.

Tests leaf_uuid-based chain detection (slug-based detection removed).
"""

import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

# Set up paths before any imports from the project
_tests_dir = Path(__file__).parent
_api_dir = _tests_dir.parent.parent
_root_dir = _api_dir.parent

if str(_root_dir) not in sys.path:
    sys.path.insert(0, str(_root_dir))
if str(_api_dir) not in sys.path:
    sys.path.insert(0, str(_api_dir))

from models.session import Session
from models.session_relationship import RelationshipType
from services.session_relationships import SessionRelationshipResolver


def create_test_session_jsonl(
    session_uuid: str,
    slug: str,
    start_time: datetime,
    end_time: datetime,
    project_context_leaf_uuids: list[str] | None = None,
) -> str:
    """Create JSONL content for a test session."""
    lines = []

    # File history snapshot (always first)
    lines.append(
        json.dumps(
            {
                "type": "file-history-snapshot",
                "messageId": f"fhs-{session_uuid[:8]}",
                "snapshot": {
                    "messageId": f"fhs-{session_uuid[:8]}",
                    "trackedFileBackups": {},
                    "timestamp": start_time.isoformat(),
                },
                "isSnapshotUpdate": False,
            }
        )
    )

    # Add summary messages with leaf UUIDs if provided (simulates resumed session)
    if project_context_leaf_uuids:
        for leaf_uuid in project_context_leaf_uuids:
            lines.append(
                json.dumps(
                    {
                        "type": "summary",
                        "summary": "Previous session context...",
                        "leafUuid": leaf_uuid,
                    }
                )
            )

    # User message
    user_msg_uuid = f"user-{session_uuid[:8]}"
    lines.append(
        json.dumps(
            {
                "type": "user",
                "uuid": user_msg_uuid,
                "sessionId": session_uuid,
                "slug": slug,
                "content": "Test user message",
                "timestamp": start_time.isoformat(),
                "cwd": "/test/project",
            }
        )
    )

    # Assistant message
    lines.append(
        json.dumps(
            {
                "type": "assistant",
                "uuid": f"asst-{session_uuid[:8]}",
                "sessionId": session_uuid,
                "slug": slug,
                "message": {
                    "role": "assistant",
                    "content": [{"type": "text", "text": "Test response"}],
                },
                "timestamp": end_time.isoformat(),
            }
        )
    )

    return "\n".join(lines)


class TestLeafUuidBasedChainDetection:
    """Test leaf_uuid-based session chain detection."""

    def test_sessions_linked_by_leaf_uuid_are_chained(self, tmp_path: Path):
        """Sessions linked by leaf_uuid should be detected as related."""
        project_dir = tmp_path / "test-project"
        project_dir.mkdir()

        base_time = datetime(2026, 1, 22, 6, 0, 0)

        # Create 3 sessions chained via leaf_uuid
        # Use UUIDs with distinct 8-char prefixes so message UUIDs are unique
        uuid1 = "aaaaaaaa-1111-0000-0000-000000000001"
        uuid2 = "bbbbbbbb-2222-0000-0000-000000000002"
        uuid3 = "cccccccc-3333-0000-0000-000000000003"

        (project_dir / f"{uuid1}.jsonl").write_text(
            create_test_session_jsonl(uuid1, "slug-a", base_time, base_time + timedelta(hours=1))
        )
        (project_dir / f"{uuid2}.jsonl").write_text(
            create_test_session_jsonl(
                uuid2,
                "slug-b",
                base_time + timedelta(hours=2),
                base_time + timedelta(hours=3),
                project_context_leaf_uuids=[f"user-{uuid1[:8]}"],
            )
        )
        (project_dir / f"{uuid3}.jsonl").write_text(
            create_test_session_jsonl(
                uuid3,
                "slug-c",
                base_time + timedelta(hours=4),
                base_time + timedelta(hours=5),
                project_context_leaf_uuids=[f"user-{uuid2[:8]}"],
            )
        )

        resolver = SessionRelationshipResolver(project_dir)
        session2 = Session.from_path(project_dir / f"{uuid2}.jsonl")
        relationships = resolver.find_relationships(session2)

        # Should find parent relationship (uuid1 -> uuid2) via leaf_uuid
        assert len(relationships) == 1
        rel = relationships[0]
        assert rel.source_uuid == uuid1
        assert rel.target_uuid == uuid2
        assert rel.relationship_type == RelationshipType.PROVIDED_CONTEXT_TO
        assert rel.detected_via == "leaf_uuid"
        assert rel.confidence == 0.95

    def test_sessions_without_leaf_uuid_not_chained(self, tmp_path: Path):
        """Sessions without leaf_uuid links should not be related, even with same slug."""
        project_dir = tmp_path / "test-project"
        project_dir.mkdir()

        base_time = datetime(2026, 1, 22, 6, 0, 0)

        # Same slug but no leaf_uuid links
        (project_dir / "session-1.jsonl").write_text(
            create_test_session_jsonl(
                "session-1", "same-slug", base_time, base_time + timedelta(hours=1)
            )
        )
        (project_dir / "session-2.jsonl").write_text(
            create_test_session_jsonl(
                "session-2",
                "same-slug",
                base_time + timedelta(hours=2),
                base_time + timedelta(hours=3),
            )
        )

        resolver = SessionRelationshipResolver(project_dir)
        session1 = Session.from_path(project_dir / "session-1.jsonl")
        relationships = resolver.find_relationships(session1)

        assert len(relationships) == 0

    def test_single_session_no_relationships(self, tmp_path: Path):
        """A single session should have no relationships."""
        project_dir = tmp_path / "test-project"
        project_dir.mkdir()

        base_time = datetime(2026, 1, 22, 6, 0, 0)
        (project_dir / "session-1.jsonl").write_text(
            create_test_session_jsonl(
                "session-1", "unique-slug", base_time, base_time + timedelta(hours=1)
            )
        )

        resolver = SessionRelationshipResolver(project_dir)
        session = Session.from_path(project_dir / "session-1.jsonl")
        relationships = resolver.find_relationships(session)

        assert len(relationships) == 0

    def test_build_chain_via_leaf_uuid(self, tmp_path: Path):
        """build_chain should include all sessions linked by leaf_uuid."""
        project_dir = tmp_path / "test-project"
        project_dir.mkdir()

        base_time = datetime(2026, 1, 22, 6, 0, 0)

        (project_dir / "uuid-a.jsonl").write_text(
            create_test_session_jsonl("uuid-a", "slug-1", base_time, base_time + timedelta(hours=1))
        )
        (project_dir / "uuid-b.jsonl").write_text(
            create_test_session_jsonl(
                "uuid-b",
                "slug-2",
                base_time + timedelta(hours=2),
                base_time + timedelta(hours=3),
                project_context_leaf_uuids=[f"user-{'uuid-a'[:8]}"],
            )
        )
        (project_dir / "uuid-c.jsonl").write_text(
            create_test_session_jsonl(
                "uuid-c",
                "slug-3",
                base_time + timedelta(hours=4),
                base_time + timedelta(hours=5),
                project_context_leaf_uuids=[f"user-{'uuid-b'[:8]}"],
            )
        )

        resolver = SessionRelationshipResolver(project_dir)
        chain = resolver.build_chain("uuid-b")

        assert chain.total_sessions == 3
        assert chain.root_uuid == "uuid-a"
        assert chain.current_session_uuid == "uuid-b"

        node_a = next((n for n in chain.nodes if n.uuid == "uuid-a"), None)
        node_b = next((n for n in chain.nodes if n.uuid == "uuid-b"), None)
        node_c = next((n for n in chain.nodes if n.uuid == "uuid-c"), None)

        assert node_a is not None and node_a.chain_depth == 0
        assert node_b is not None and node_b.chain_depth == 1
        assert node_c is not None and node_c.chain_depth == 2


class TestLeafUuidConfidence:
    """Test leaf_uuid confidence values."""

    def test_leaf_uuid_confidence(self, tmp_path: Path):
        """leaf_uuid detection should have 0.95 confidence."""
        resolver = SessionRelationshipResolver(tmp_path)
        assert resolver.CONFIDENCE_LEAF_UUID == 0.95


class TestFindAllRelatedSessions:
    """Test find_all_related_sessions via leaf_uuid links."""

    def test_finds_all_leaf_uuid_linked_sessions(self, tmp_path: Path):
        """Should find all sessions linked by leaf_uuid chain."""
        project_dir = tmp_path / "test-project"
        project_dir.mkdir()

        base_time = datetime(2026, 1, 22, 6, 0, 0)

        # Create 4 sessions chained via leaf_uuid
        (project_dir / "session-0.jsonl").write_text(
            create_test_session_jsonl(
                "session-0", "slug-0", base_time, base_time + timedelta(hours=1)
            )
        )
        for i in range(1, 4):
            start = base_time + timedelta(hours=i * 2)
            (project_dir / f"session-{i}.jsonl").write_text(
                create_test_session_jsonl(
                    f"session-{i}",
                    f"slug-{i}",
                    start,
                    start + timedelta(hours=1),
                    project_context_leaf_uuids=["user-session-"],  # "session-N"[:8] = "session-"
                )
            )

        # Fix: the leaf_uuid must match the PARENT's user msg uuid
        # "session-0"[:8] = "session-", so user msg uuid = "user-session-"
        # All children reference "user-session-" which maps to whichever session-N is found first
        # Let's use distinct UUIDs instead
        # Recreate with proper UUIDs
        import shutil

        shutil.rmtree(project_dir)
        project_dir.mkdir()

        uuids = ["sess-aa00", "sess-bb00", "sess-cc00", "sess-dd00"]
        (project_dir / f"{uuids[0]}.jsonl").write_text(
            create_test_session_jsonl(uuids[0], "slug-0", base_time, base_time + timedelta(hours=1))
        )
        for i in range(1, 4):
            parent_msg = f"user-{uuids[i - 1][:8]}"
            start = base_time + timedelta(hours=i * 2)
            (project_dir / f"{uuids[i]}.jsonl").write_text(
                create_test_session_jsonl(
                    uuids[i],
                    f"slug-{i}",
                    start,
                    start + timedelta(hours=1),
                    project_context_leaf_uuids=[parent_msg],
                )
            )

        resolver = SessionRelationshipResolver(project_dir)
        related = resolver.find_all_related_sessions(uuids[1])

        assert len(related) == 4
        assert all(u in related for u in uuids)


class TestUuidMapCaching:
    """Test that UUID map is properly cached."""

    def test_uuid_map_built_once(self, tmp_path: Path):
        """UUID map should be built once and cached."""
        project_dir = tmp_path / "test-project"
        project_dir.mkdir()

        base_time = datetime(2026, 1, 22, 6, 0, 0)
        (project_dir / "session-1.jsonl").write_text(
            create_test_session_jsonl(
                "session-1", "test-slug", base_time, base_time + timedelta(hours=1)
            )
        )

        resolver = SessionRelationshipResolver(project_dir)

        # First call builds the map
        map1 = resolver._build_uuid_to_session_map()

        # Second call should use cached map
        map2 = resolver._build_uuid_to_session_map()

        assert map1 is map2
        assert resolver._uuid_to_session_map is not None


class TestGetChainInfoForAllSessions:
    """Test get_chain_info_for_all_sessions method for list views."""

    def test_returns_chain_info_for_chained_sessions(self, tmp_path: Path):
        """Should return chain info for sessions linked by leaf_uuid."""
        project_dir = tmp_path / "test-project"
        project_dir.mkdir()

        base_time = datetime(2026, 1, 22, 6, 0, 0)

        # Create 3 sessions chained via leaf_uuid
        (project_dir / "sess-aa00.jsonl").write_text(
            create_test_session_jsonl(
                "sess-aa00", "slug-a", base_time, base_time + timedelta(hours=1)
            )
        )
        (project_dir / "sess-bb00.jsonl").write_text(
            create_test_session_jsonl(
                "sess-bb00",
                "slug-b",
                base_time + timedelta(hours=2),
                base_time + timedelta(hours=3),
                project_context_leaf_uuids=[f"user-{'sess-aa00'[:8]}"],
            )
        )
        (project_dir / "sess-cc00.jsonl").write_text(
            create_test_session_jsonl(
                "sess-cc00",
                "slug-c",
                base_time + timedelta(hours=4),
                base_time + timedelta(hours=5),
                project_context_leaf_uuids=[f"user-{'sess-bb00'[:8]}"],
            )
        )

        sessions = [
            Session.from_path(project_dir / f"{u}.jsonl")
            for u in ["sess-aa00", "sess-bb00", "sess-cc00"]
        ]

        resolver = SessionRelationshipResolver(project_dir)
        chain_info_map = resolver.get_chain_info_for_all_sessions(sessions)

        # All 3 sessions should have chain info
        assert len(chain_info_map) == 3

        # Check root
        info1 = chain_info_map["sess-aa00"]
        assert info1.position == 0
        assert info1.total == 3
        assert info1.is_root is True
        assert info1.is_latest is False

        # Check middle
        info2 = chain_info_map["sess-bb00"]
        assert info2.position == 1
        assert info2.is_root is False
        assert info2.is_latest is False

        # Check latest
        info3 = chain_info_map["sess-cc00"]
        assert info3.position == 2
        assert info3.is_root is False
        assert info3.is_latest is True

    def test_excludes_single_sessions(self, tmp_path: Path):
        """Sessions without chains (single session with unique slug) should not be included."""
        project_dir = tmp_path / "test-project"
        project_dir.mkdir()

        base_time = datetime(2026, 1, 22, 6, 0, 0)
        (project_dir / "single-session.jsonl").write_text(
            create_test_session_jsonl(
                "single-session", "unique-slug", base_time, base_time + timedelta(hours=1)
            )
        )

        sessions = [Session.from_path(project_dir / "single-session.jsonl")]

        resolver = SessionRelationshipResolver(project_dir)
        chain_info_map = resolver.get_chain_info_for_all_sessions(sessions)

        # Single session should not have chain info
        assert len(chain_info_map) == 0

    def test_handles_mixed_chained_and_single_sessions(self, tmp_path: Path):
        """Should handle mix of chained and standalone sessions."""
        project_dir = tmp_path / "test-project"
        project_dir.mkdir()

        base_time = datetime(2026, 1, 22, 6, 0, 0)

        (project_dir / "chain-10.jsonl").write_text(
            create_test_session_jsonl(
                "chain-10", "slug-a", base_time, base_time + timedelta(hours=1)
            )
        )
        (project_dir / "chain-20.jsonl").write_text(
            create_test_session_jsonl(
                "chain-20",
                "slug-b",
                base_time + timedelta(hours=2),
                base_time + timedelta(hours=3),
                project_context_leaf_uuids=[f"user-{'chain-10'[:8]}"],
            )
        )
        (project_dir / "standalo.jsonl").write_text(
            create_test_session_jsonl(
                "standalo",
                "slug-c",
                base_time + timedelta(hours=4),
                base_time + timedelta(hours=5),
            )
        )

        sessions = [
            Session.from_path(project_dir / f"{u}.jsonl")
            for u in ["chain-10", "chain-20", "standalo"]
        ]

        resolver = SessionRelationshipResolver(project_dir)
        chain_info_map = resolver.get_chain_info_for_all_sessions(sessions)

        # Only chained sessions should have chain info
        assert len(chain_info_map) == 2
        assert "chain-10" in chain_info_map
        assert "chain-20" in chain_info_map
        assert "standalo" not in chain_info_map


class TestLeafUuidChainDetection:
    """Test leaf_uuid-based parent session detection."""

    def test_child_finds_parent_via_leaf_uuid(self, tmp_path: Path):
        """Child session with project_context_leaf_uuids should find parent."""
        project_dir = tmp_path / "test-project"
        project_dir.mkdir()

        base_time = datetime(2026, 1, 22, 6, 0, 0)

        # Create parent session - note the user message UUID format from helper
        (project_dir / "parent-uuid.jsonl").write_text(
            create_test_session_jsonl(
                "parent-uuid", "slug-alpha", base_time, base_time + timedelta(hours=1)
            )
        )

        # Create child session that references parent's user message UUID
        # The helper creates user msg with uuid "user-{session_uuid[:8]}"
        parent_msg_uuid = f"user-{'parent-uuid'[:8]}"  # "user-parent-u"

        (project_dir / "child-uuid.jsonl").write_text(
            create_test_session_jsonl(
                "child-uuid",
                "slug-beta",  # DIFFERENT slug!
                base_time + timedelta(hours=2),
                base_time + timedelta(hours=3),
                project_context_leaf_uuids=[parent_msg_uuid],
            )
        )

        resolver = SessionRelationshipResolver(project_dir)
        child_session = Session.from_path(project_dir / "child-uuid.jsonl")
        relationships = resolver.find_relationships(child_session)

        assert len(relationships) == 1
        rel = relationships[0]
        assert rel.source_uuid == "parent-uuid"
        assert rel.target_uuid == "child-uuid"
        assert rel.detected_via == "leaf_uuid"
        assert rel.confidence == 0.95

    def test_cross_slug_chain_detected_via_leaf_uuid(self, tmp_path: Path):
        """Sessions with DIFFERENT slugs should be chained if linked by leaf_uuid."""
        project_dir = tmp_path / "test-project"
        project_dir.mkdir()

        base_time = datetime(2026, 1, 22, 6, 0, 0)

        # Use UUIDs with distinct 8-char prefixes to avoid message UUID collisions
        uuid_a = "cross-aa0"
        uuid_b = "cross-bb0"

        (project_dir / f"{uuid_a}.jsonl").write_text(
            create_test_session_jsonl(
                uuid_a, "rippling-cooking-reef", base_time, base_time + timedelta(hours=1)
            )
        )

        parent_msg_uuid = f"user-{uuid_a[:8]}"
        (project_dir / f"{uuid_b}.jsonl").write_text(
            create_test_session_jsonl(
                uuid_b,
                "imperative-strolling-torvalds",  # Different slug!
                base_time + timedelta(hours=2),
                base_time + timedelta(hours=3),
                project_context_leaf_uuids=[parent_msg_uuid],
            )
        )

        resolver = SessionRelationshipResolver(project_dir)
        chain = resolver.build_chain(uuid_b)

        assert chain.total_sessions == 2
        assert chain.root_uuid == uuid_a
        node_a = next(n for n in chain.nodes if n.uuid == uuid_a)
        node_b = next(n for n in chain.nodes if n.uuid == uuid_b)
        assert node_a.chain_depth == 0
        assert node_b.chain_depth == 1

    def test_null_leaf_uuid_no_parent(self, tmp_path: Path):
        """Session with null/empty project_context_leaf_uuids has no parent."""
        project_dir = tmp_path / "test-project"
        project_dir.mkdir()

        base_time = datetime(2026, 1, 22, 6, 0, 0)
        (project_dir / "orphan.jsonl").write_text(
            create_test_session_jsonl(
                "orphan", "some-slug", base_time, base_time + timedelta(hours=1)
            )
        )

        resolver = SessionRelationshipResolver(project_dir)
        session = Session.from_path(project_dir / "orphan.jsonl")
        relationships = resolver.find_relationships(session)

        assert len(relationships) == 0


class TestDeepChain:
    """Test deep session chains (5+ sessions)."""

    def test_deep_chain_5_sessions(self, tmp_path: Path):
        """Chain of 5 sessions linked by leaf_uuid should be fully discovered."""
        project_dir = tmp_path / "test-project"
        project_dir.mkdir()

        base_time = datetime(2026, 1, 22, 6, 0, 0)
        uuids = [f"deep-{i}" for i in range(5)]

        # First session has no parent
        (project_dir / f"{uuids[0]}.jsonl").write_text(
            create_test_session_jsonl(
                uuids[0], f"slug-{0}", base_time, base_time + timedelta(hours=1)
            )
        )

        # Each subsequent session references the previous one's user message
        for i in range(1, 5):
            parent_msg_uuid = f"user-{uuids[i - 1][:8]}"
            start = base_time + timedelta(hours=i * 2)
            (project_dir / f"{uuids[i]}.jsonl").write_text(
                create_test_session_jsonl(
                    uuids[i],
                    f"slug-{i}",  # Each has different slug
                    start,
                    start + timedelta(hours=1),
                    project_context_leaf_uuids=[parent_msg_uuid],
                )
            )

        resolver = SessionRelationshipResolver(project_dir)
        chain = resolver.build_chain(uuids[2])  # Start from middle

        assert chain.total_sessions == 5
        assert chain.root_uuid == uuids[0]
        assert chain.max_depth == 4

        for i, uuid in enumerate(uuids):
            node = next(n for n in chain.nodes if n.uuid == uuid)
            assert node.chain_depth == i

    def test_circular_reference_protection(self, tmp_path: Path):
        """Circular leaf_uuid references should not cause infinite loop."""
        project_dir = tmp_path / "test-project"
        project_dir.mkdir()

        base_time = datetime(2026, 1, 22, 6, 0, 0)

        # Session A references B's message, B references A's message (circular)
        # "circ-aaa"[:8] = "circ-aaa", "circ-bbb"[:8] = "circ-bbb"
        (project_dir / "circ-aaa.jsonl").write_text(
            create_test_session_jsonl(
                "circ-aaa",
                "slug-a",
                base_time,
                base_time + timedelta(hours=1),
                project_context_leaf_uuids=["user-circ-bbb"],  # References B
            )
        )
        (project_dir / "circ-bbb.jsonl").write_text(
            create_test_session_jsonl(
                "circ-bbb",
                "slug-b",
                base_time + timedelta(hours=2),
                base_time + timedelta(hours=3),
                project_context_leaf_uuids=["user-circ-aaa"],  # References A
            )
        )

        resolver = SessionRelationshipResolver(project_dir)
        # Should not hang - circular protection should kick in
        chain = resolver.build_chain("circ-aaa")
        assert chain.total_sessions == 2  # Both sessions found


class TestRelationshipsCaching:
    """Test that find_relationships results are cached per session."""

    def test_find_relationships_cached(self, tmp_path: Path):
        """Calling find_relationships twice should return cached result."""
        project_dir = tmp_path / "test-project"
        project_dir.mkdir()

        base_time = datetime(2026, 1, 22, 6, 0, 0)
        (project_dir / "session-1.jsonl").write_text(
            create_test_session_jsonl(
                "session-1", "test-slug", base_time, base_time + timedelta(hours=1)
            )
        )

        resolver = SessionRelationshipResolver(project_dir)
        session = Session.from_path(project_dir / "session-1.jsonl")

        result1 = resolver.find_relationships(session)
        result2 = resolver.find_relationships(session)

        # Same object should be returned (cached)
        assert result1 is result2

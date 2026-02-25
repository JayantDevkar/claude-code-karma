"""
Unit tests for CompactionDetector.

Tests the detection of true compaction events (CompactBoundaryMessage)
and proper handling of session titles (SessionTitleMessage).

IMPORTANT: SessionTitleMessage (type: "summary") are NOT compaction events!
True compaction is indicated by CompactBoundaryMessage (type: "system",
subtype: "compact_boundary").
"""

import sys
from datetime import datetime
from pathlib import Path

# Set up paths before any imports from the project
_tests_dir = Path(__file__).parent
_api_dir = _tests_dir.parent

if str(_api_dir) not in sys.path:
    sys.path.insert(0, str(_api_dir))

from models.compaction_detector import (
    SESSION_END_PATTERNS,
    SESSION_END_THRESHOLD,
    CompactionDetector,
)
from models.message import (
    AssistantMessage,
    CompactBoundaryMessage,
    SessionTitleMessage,
    UserMessage,
)

# Base timestamp for tests
BASE_TIME = datetime(2026, 1, 23, 12, 0, 0)


def make_user_message(content: str = "Test message") -> UserMessage:
    """Create a minimal UserMessage for testing."""
    return UserMessage(
        type="user",
        uuid="user-uuid-1",
        timestamp=BASE_TIME,
        content=content,
    )


def make_assistant_message(
    stop_reason: str | None = None,
    content_text: str = "Test response",
) -> AssistantMessage:
    """Create a minimal AssistantMessage for testing."""
    return AssistantMessage(
        type="assistant",
        uuid="assistant-uuid-1",
        timestamp=BASE_TIME,
        content_blocks=[],
        stop_reason=stop_reason,
    )


def make_session_title(
    summary: str = "Session title",
    leaf_uuid: str | None = None,
) -> SessionTitleMessage:
    """Create a SessionTitleMessage for testing (NOT compaction)."""
    return SessionTitleMessage(
        type="summary",
        summary=summary,
        leaf_uuid=leaf_uuid,
    )


def make_compact_boundary(
    trigger: str = "auto",
    pre_tokens: int = 150000,
) -> CompactBoundaryMessage:
    """Create a CompactBoundaryMessage for testing (TRUE compaction)."""
    return CompactBoundaryMessage(
        type="system",
        subtype="compact_boundary",
        uuid="compact-uuid-1",
        timestamp=BASE_TIME,
        content="Conversation compacted",
        trigger=trigger,
        pre_tokens=pre_tokens,
    )


# Backward compatibility alias
make_summary_message = make_session_title


class TestCompactionDetectorBasics:
    """Test basic detector functionality."""

    def test_no_messages_means_no_compaction(self):
        """Empty session is not compacted."""
        detector = CompactionDetector()

        assert detector.was_compacted is False
        assert detector.compaction_count == 0

    def test_no_compact_boundary_means_no_compaction(self):
        """Session without CompactBoundaryMessage is not compacted."""
        detector = CompactionDetector()
        detector.process(make_user_message())
        detector.process(make_assistant_message())

        assert detector.was_compacted is False
        assert detector.compaction_count == 0

    def test_tracks_conversation_start(self):
        """Detector tracks when conversation starts."""
        detector = CompactionDetector()

        # Before any user/assistant message
        assert detector.conversation_started is False

        detector.process(make_user_message())
        assert detector.conversation_started is True

    def test_tracks_conversation_start_with_assistant_first(self):
        """Conversation can start with assistant message."""
        detector = CompactionDetector()

        assert detector.conversation_started is False
        detector.process(make_assistant_message())
        assert detector.conversation_started is True


class TestSessionTitleNotCompaction:
    """
    Test that SessionTitleMessage (type: "summary") is NOT treated as compaction.

    This was the main bug - session titles were incorrectly detected as compaction.
    """

    def test_session_title_is_not_compaction(self):
        """SessionTitleMessage is NOT compaction, just session naming."""
        detector = CompactionDetector()

        detector.process(make_user_message())
        detector.process(make_assistant_message())
        detector.process(make_session_title("My Session Title"))

        # Session title should NOT trigger compaction
        assert detector.was_compacted is False
        assert detector.compaction_count == 0
        assert detector.session_titles == ["My Session Title"]

    def test_multiple_session_titles_not_compaction(self):
        """Multiple SessionTitleMessages are NOT compaction."""
        detector = CompactionDetector()

        detector.process(make_user_message())
        detector.process(make_assistant_message())
        detector.process(make_session_title("Title 1"))
        detector.process(make_session_title("Title 2"))
        detector.process(make_session_title("Title 3"))

        assert detector.was_compacted is False
        assert detector.compaction_count == 0
        assert len(detector.session_titles) == 3

    def test_session_title_mid_conversation_not_compaction(self):
        """Session title appearing mid-conversation is still NOT compaction."""
        detector = CompactionDetector()

        detector.process(make_user_message())
        detector.process(make_assistant_message())
        detector.process(make_session_title("Mid-session title"))
        detector.process(make_user_message())
        detector.process(make_assistant_message())

        assert detector.was_compacted is False
        assert detector.compaction_count == 0


class TestProjectContextDetection:
    """Test detection of project context summaries (from previous sessions)."""

    def test_session_title_before_conversation_is_project_context(self):
        """SessionTitleMessage before conversation is project context."""
        detector = CompactionDetector()

        # Session title first (before conversation)
        detector.process(make_session_title("Previous session context", "leaf-123"))

        # Then conversation starts
        detector.process(make_user_message())
        detector.process(make_assistant_message())

        assert detector.has_project_context is True
        assert detector.project_context_summaries == ["Previous session context"]
        assert detector.project_context_leaf_uuids == ["leaf-123"]
        assert detector.was_compacted is False

    def test_multiple_project_context_summaries(self):
        """Multiple session titles before conversation are all project context."""
        detector = CompactionDetector()

        detector.process(make_session_title("Context 1", "leaf-1"))
        detector.process(make_session_title("Context 2", "leaf-2"))
        detector.process(make_user_message())

        assert len(detector.project_context_summaries) == 2
        assert len(detector.project_context_leaf_uuids) == 2
        assert detector.was_compacted is False

    def test_project_context_with_null_leaf_uuid(self):
        """Project context with null leaf_uuid is still tracked."""
        detector = CompactionDetector()

        detector.process(make_session_title("Context without leaf", None))
        detector.process(make_user_message())

        assert detector.project_context_summaries == ["Context without leaf"]
        assert detector.project_context_leaf_uuids == []  # None not added


class TestTrueCompactionDetection:
    """Test detection of true compaction events (CompactBoundaryMessage)."""

    def test_compact_boundary_is_compaction(self):
        """CompactBoundaryMessage indicates true compaction."""
        detector = CompactionDetector()

        detector.process(make_user_message())
        detector.process(make_assistant_message())
        detector.process(make_compact_boundary(trigger="auto", pre_tokens=150000))

        assert detector.was_compacted is True
        assert detector.compaction_count == 1

    def test_manual_compaction(self):
        """Manual compaction via /compact command is detected."""
        detector = CompactionDetector()

        detector.process(make_user_message())
        detector.process(make_assistant_message())
        detector.process(make_compact_boundary(trigger="manual", pre_tokens=120000))

        assert detector.was_compacted is True
        assert detector.compaction_count == 1

    def test_multiple_compaction_events(self):
        """Multiple CompactBoundaryMessages = multiple compaction events."""
        detector = CompactionDetector()

        detector.process(make_user_message())
        detector.process(make_assistant_message())
        detector.process(make_compact_boundary(trigger="auto", pre_tokens=150000))
        detector.process(make_user_message())
        detector.process(make_assistant_message())
        detector.process(make_compact_boundary(trigger="auto", pre_tokens=155000))
        detector.process(make_user_message())
        detector.process(make_assistant_message())

        assert detector.was_compacted is True
        assert detector.compaction_count == 2

    def test_compaction_summaries_include_metadata(self):
        """Compaction summaries include trigger and token info."""
        detector = CompactionDetector()

        detector.process(make_user_message())
        detector.process(make_compact_boundary(trigger="auto", pre_tokens=150000))

        summaries = detector.compaction_summaries
        assert len(summaries) == 1
        assert "Conversation compacted" in summaries[0]
        assert "(auto)" in summaries[0]
        assert "150,000" in summaries[0]


class TestMixedScenarios:
    """Test complex scenarios with both compaction and session titles."""

    def test_session_title_plus_compaction(self):
        """Session with both session titles and compaction."""
        detector = CompactionDetector()

        # Conversation starts
        detector.process(make_user_message())
        detector.process(make_assistant_message())

        # Session gets named (NOT compaction)
        detector.process(make_session_title("My Session"))

        # Later, context fills up and compaction happens
        detector.process(make_user_message())
        detector.process(make_assistant_message())
        detector.process(make_compact_boundary(trigger="auto", pre_tokens=155000))

        # Continue after compaction
        detector.process(make_user_message())
        detector.process(make_assistant_message())

        assert detector.was_compacted is True
        assert detector.compaction_count == 1
        assert detector.session_titles == ["My Session"]

    def test_project_context_and_compaction(self):
        """Session with project context AND compaction."""
        detector = CompactionDetector()

        # Project context (before conversation)
        detector.process(make_session_title("Previous session context", "leaf-prev"))

        # Conversation starts
        detector.process(make_user_message())
        detector.process(make_assistant_message())

        # True compaction
        detector.process(make_compact_boundary())

        # More conversation
        detector.process(make_user_message())
        detector.process(make_assistant_message())

        assert detector.has_project_context is True
        assert detector.was_compacted is True
        assert detector.compaction_count == 1

    def test_project_context_session_title_and_compaction(self):
        """Session with project context, session title, AND compaction."""
        detector = CompactionDetector()

        # Project context
        detector.process(make_session_title("Previous session", "leaf-1"))

        # Conversation
        detector.process(make_user_message())
        detector.process(make_assistant_message())

        # Session naming
        detector.process(make_session_title("Current session title"))

        # Compaction
        detector.process(make_compact_boundary())

        # Continue
        detector.process(make_user_message())
        detector.process(make_assistant_message())

        assert detector.has_project_context is True
        assert detector.project_context_summaries == ["Previous session"]
        assert detector.session_titles == ["Current session title"]
        assert detector.was_compacted is True
        assert detector.compaction_count == 1


class TestCompactionDetails:
    """Test detailed compaction information."""

    def test_get_compaction_details(self):
        """get_compaction_details returns structured info."""
        detector = CompactionDetector()

        detector.process(make_user_message())
        detector.process(make_compact_boundary(trigger="auto", pre_tokens=150000))
        detector.process(make_user_message())
        detector.process(make_compact_boundary(trigger="manual", pre_tokens=160000))

        details = detector.get_compaction_details()
        assert len(details) == 2

        assert details[0]["trigger"] == "auto"
        assert details[0]["pre_tokens"] == 150000

        assert details[1]["trigger"] == "manual"
        assert details[1]["pre_tokens"] == 160000


class TestBackwardCompatibility:
    """Test backward compatibility with old tests/code."""

    def test_session_end_patterns_constant_exists(self):
        """SESSION_END_PATTERNS constant exists for backward compatibility."""
        assert SESSION_END_PATTERNS is not None
        assert isinstance(SESSION_END_PATTERNS, list)

    def test_session_end_threshold_constant_exists(self):
        """SESSION_END_THRESHOLD constant exists for backward compatibility."""
        assert SESSION_END_THRESHOLD == 3

    def test_session_end_summary_property(self):
        """session_end_summary returns last session title."""
        detector = CompactionDetector()

        detector.process(make_user_message())
        detector.process(make_assistant_message())
        detector.process(make_session_title("Final title"))

        assert detector.session_end_summary == "Final title"

    def test_session_end_summary_none_when_no_titles(self):
        """session_end_summary returns None when no session titles."""
        detector = CompactionDetector()

        detector.process(make_user_message())
        detector.process(make_assistant_message())

        assert detector.session_end_summary is None


class TestEdgeCases:
    """Test edge cases and boundary conditions."""

    def test_only_file_history_snapshots(self):
        """Session with only file snapshots has no compaction."""
        from models.message import FileHistorySnapshot

        detector = CompactionDetector()

        # File history snapshots don't start conversation
        detector.process(
            FileHistorySnapshot(
                type="file-history-snapshot",
                uuid="fhs-uuid-1",
                timestamp=BASE_TIME,
                message_id="fhs-1",
                snapshot={},
                is_snapshot_update=False,
            )
        )

        assert detector.conversation_started is False
        assert detector.was_compacted is False

    def test_empty_session_title(self):
        """Empty session title is still tracked."""
        detector = CompactionDetector()

        detector.process(make_session_title("", "leaf-1"))
        detector.process(make_user_message())

        # Empty summaries are not added to project_context_summaries
        assert detector.project_context_summaries == []
        assert detector.project_context_leaf_uuids == ["leaf-1"]

    def test_compact_boundary_without_metadata(self):
        """CompactBoundaryMessage works without trigger/pre_tokens."""
        detector = CompactionDetector()

        detector.process(make_user_message())
        detector.process(
            CompactBoundaryMessage(
                type="system",
                subtype="compact_boundary",
                uuid="compact-uuid",
                timestamp=BASE_TIME,
                content="Conversation compacted",
                trigger=None,
                pre_tokens=None,
            )
        )

        assert detector.was_compacted is True
        assert detector.compaction_count == 1
        summaries = detector.compaction_summaries
        assert len(summaries) == 1
        assert "Conversation compacted" in summaries[0]

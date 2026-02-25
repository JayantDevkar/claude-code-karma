"""
Unit tests for session search filter functionality.

Tests SearchScope, SessionStatus, date range filtering, and the updated
/sessions/all endpoint with new filter parameters.
"""

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

# Set up paths before any imports from the project
_tests_dir = Path(__file__).parent
_api_dir = _tests_dir.parent.parent
_root_dir = _api_dir.parent

# Add paths for imports
if str(_root_dir) not in sys.path:
    sys.path.insert(0, str(_root_dir))
if str(_api_dir) not in sys.path:
    sys.path.insert(0, str(_api_dir))

# Import from unified services module
from schemas import StatusFilterOption
from services.session_filter import (
    SearchScope,
    SessionFilter,
    SessionMetadata,
    SessionStatus,
    determine_session_status,
    filter_sessions_by_date,
)


# Test helper that wraps SessionFilter for backward compatibility with test signatures
def _matches_filters_metadata(
    meta: SessionMetadata,
    project_filter,
    branch_filter,
    search_lower,
    search_scope=SearchScope.BOTH,
    status_filter=SessionStatus.ALL,
    start_dt=None,
    end_dt=None,
) -> bool:
    """Test helper: wraps SessionFilter.matches_metadata() with legacy signature."""
    session_filter = SessionFilter(
        search=search_lower,
        search_scope=search_scope,
        status=status_filter,
        date_from=start_dt,
        date_to=end_dt,
        project_encoded_name=project_filter,
        branch=branch_filter,
    )
    session_filter._search_lower = search_lower
    return session_filter.matches_metadata(meta)


# Alias for backward compatibility
_determine_session_status = determine_session_status

# =============================================================================
# SearchScope Enum Tests
# =============================================================================


class TestSearchScope:
    """Tests for SearchScope enum."""

    def test_search_scope_values(self):
        """Test SearchScope has expected values."""
        assert SearchScope.BOTH.value == "both"
        assert SearchScope.TITLES.value == "titles"
        assert SearchScope.PROMPTS.value == "prompts"

    def test_search_scope_from_string(self):
        """Test SearchScope can be created from string."""
        assert SearchScope("both") == SearchScope.BOTH
        assert SearchScope("titles") == SearchScope.TITLES
        assert SearchScope("prompts") == SearchScope.PROMPTS


# =============================================================================
# SessionStatus Enum Tests
# =============================================================================


class TestSessionStatus:
    """Tests for SessionStatus enum."""

    def test_session_status_values(self):
        """Test SessionStatus has expected values."""
        assert SessionStatus.ALL.value == "all"
        assert SessionStatus.ACTIVE.value == "active"
        assert SessionStatus.COMPLETED.value == "completed"
        assert SessionStatus.ERROR.value == "error"

    def test_session_status_from_string(self):
        """Test SessionStatus can be created from string."""
        assert SessionStatus("all") == SessionStatus.ALL
        assert SessionStatus("active") == SessionStatus.ACTIVE
        assert SessionStatus("completed") == SessionStatus.COMPLETED
        assert SessionStatus("error") == SessionStatus.ERROR


# =============================================================================
# _determine_session_status Tests
# =============================================================================


class TestDetermineSessionStatus:
    """Tests for _determine_session_status helper function."""

    def test_no_start_time_returns_unknown(self):
        """Test session without start_time returns 'unknown'."""
        meta = SessionMetadata(
            uuid="test-uuid",
            encoded_name="-Users-test",
            project_path="/Users/test",
            message_count=10,
            start_time=None,
            end_time=None,
            slug="test-session",
            initial_prompt="test prompt",
            git_branch="main",
        )
        assert _determine_session_status(meta) == "unknown"

    def test_recent_activity_returns_active(self):
        """Test session with activity within 5 minutes returns 'active'."""
        now = datetime.now(timezone.utc)
        meta = SessionMetadata(
            uuid="test-uuid",
            encoded_name="-Users-test",
            project_path="/Users/test",
            message_count=10,
            start_time=now - timedelta(minutes=30),
            end_time=now - timedelta(seconds=60),  # 1 minute ago
            slug="test-session",
            initial_prompt="test prompt",
            git_branch="main",
        )
        assert _determine_session_status(meta) == "active"

    def test_old_activity_returns_completed(self):
        """Test session with activity older than 5 minutes returns 'completed'."""
        now = datetime.now(timezone.utc)
        meta = SessionMetadata(
            uuid="test-uuid",
            encoded_name="-Users-test",
            project_path="/Users/test",
            message_count=10,
            start_time=now - timedelta(hours=2),
            end_time=now - timedelta(hours=1),  # 1 hour ago
            slug="test-session",
            initial_prompt="test prompt",
            git_branch="main",
        )
        assert _determine_session_status(meta) == "completed"

    def test_no_end_time_returns_completed(self):
        """Test session without end_time returns 'completed'."""
        now = datetime.now(timezone.utc)
        meta = SessionMetadata(
            uuid="test-uuid",
            encoded_name="-Users-test",
            project_path="/Users/test",
            message_count=10,
            start_time=now - timedelta(hours=1),
            end_time=None,
            slug="test-session",
            initial_prompt="test prompt",
            git_branch="main",
        )
        assert _determine_session_status(meta) == "completed"

    def test_boundary_exactly_5_minutes(self):
        """Test session at exactly 5 minutes boundary."""
        now = datetime.now(timezone.utc)
        meta = SessionMetadata(
            uuid="test-uuid",
            encoded_name="-Users-test",
            project_path="/Users/test",
            message_count=10,
            start_time=now - timedelta(hours=1),
            end_time=now - timedelta(seconds=300),  # Exactly 5 minutes
            slug="test-session",
            initial_prompt="test prompt",
            git_branch="main",
        )
        # At exactly 300 seconds, should be completed (not < 300)
        assert _determine_session_status(meta) == "completed"


# =============================================================================
# _matches_filters_metadata Tests - Search Scope
# =============================================================================


class TestMatchesFiltersMetadataSearchScope:
    """Tests for search scope filtering in _matches_filters_metadata."""

    @pytest.fixture
    def sample_meta(self):
        """Create a sample SessionMetadata for testing."""
        return SessionMetadata(
            uuid="test-uuid",
            encoded_name="-Users-test",
            project_path="/Users/test/project",
            message_count=10,
            start_time=datetime.now(timezone.utc) - timedelta(hours=1),
            end_time=datetime.now(timezone.utc) - timedelta(minutes=10),
            slug="auth-feature",
            initial_prompt="implement authentication",
            git_branch="main",
            title="Authentication Feature Implementation",
        )

    def test_search_scope_both_matches_prompt(self, sample_meta):
        """Test scope=both matches prompt content."""
        assert (
            _matches_filters_metadata(
                sample_meta,
                project_filter=None,
                branch_filter=None,
                search_lower="authentication",
                search_scope=SearchScope.BOTH,
            )
            is True
        )

    def test_search_scope_both_matches_title(self, sample_meta):
        """Test scope=both matches title content."""
        assert (
            _matches_filters_metadata(
                sample_meta,
                project_filter=None,
                branch_filter=None,
                search_lower="feature",
                search_scope=SearchScope.BOTH,
            )
            is True
        )

    def test_search_scope_prompts_only_matches_prompt(self, sample_meta):
        """Test scope=prompts only matches prompt, not title."""
        assert (
            _matches_filters_metadata(
                sample_meta,
                project_filter=None,
                branch_filter=None,
                search_lower="authentication",
                search_scope=SearchScope.PROMPTS,
            )
            is True
        )

    def test_search_scope_prompts_only_no_match_title(self, sample_meta):
        """Test scope=prompts does not match title-only term."""
        # "Implementation" is only in title, not in prompt
        assert (
            _matches_filters_metadata(
                sample_meta,
                project_filter=None,
                branch_filter=None,
                search_lower="implementation",
                search_scope=SearchScope.PROMPTS,
            )
            is False
        )

    def test_search_scope_titles_only_matches_title(self, sample_meta):
        """Test scope=titles matches title content."""
        assert (
            _matches_filters_metadata(
                sample_meta,
                project_filter=None,
                branch_filter=None,
                search_lower="implementation",
                search_scope=SearchScope.TITLES,
            )
            is True
        )

    def test_search_scope_titles_only_no_match_prompt(self, sample_meta):
        """Test scope=titles does not match prompt-only term."""
        # "implement" is in prompt but "Implementation" is the title match
        # Let's use a term only in prompt
        sample_meta.title = "Something Else"
        assert (
            _matches_filters_metadata(
                sample_meta,
                project_filter=None,
                branch_filter=None,
                search_lower="authentication",
                search_scope=SearchScope.TITLES,
            )
            is False
        )

    def test_search_scope_case_insensitive(self, sample_meta):
        """Test search is case insensitive."""
        assert (
            _matches_filters_metadata(
                sample_meta,
                project_filter=None,
                branch_filter=None,
                search_lower="authentication",  # lowercase
                search_scope=SearchScope.BOTH,
            )
            is True
        )

    def test_search_matches_slug(self, sample_meta):
        """Test search matches slug in prompts scope."""
        assert (
            _matches_filters_metadata(
                sample_meta,
                project_filter=None,
                branch_filter=None,
                search_lower="auth",  # matches slug "auth-feature"
                search_scope=SearchScope.PROMPTS,
            )
            is True
        )

    def test_search_matches_path(self, sample_meta):
        """Test search matches project path in prompts scope."""
        assert (
            _matches_filters_metadata(
                sample_meta,
                project_filter=None,
                branch_filter=None,
                search_lower="project",  # matches path "/Users/test/project"
                search_scope=SearchScope.PROMPTS,
            )
            is True
        )


# =============================================================================
# _matches_filters_metadata Tests - Status Filter
# =============================================================================


class TestMatchesFiltersMetadataStatusFilter:
    """Tests for status filtering in _matches_filters_metadata."""

    @pytest.fixture
    def active_meta(self):
        """Create a session metadata that should be active."""
        now = datetime.now(timezone.utc)
        return SessionMetadata(
            uuid="active-uuid",
            encoded_name="-Users-test",
            project_path="/Users/test",
            message_count=10,
            start_time=now - timedelta(minutes=10),
            end_time=now - timedelta(seconds=30),  # 30 seconds ago - active
            slug="active-session",
            initial_prompt="test",
            git_branch="main",
        )

    @pytest.fixture
    def completed_meta(self):
        """Create a session metadata that should be completed."""
        now = datetime.now(timezone.utc)
        return SessionMetadata(
            uuid="completed-uuid",
            encoded_name="-Users-test",
            project_path="/Users/test",
            message_count=10,
            start_time=now - timedelta(hours=2),
            end_time=now - timedelta(hours=1),  # 1 hour ago - completed
            slug="completed-session",
            initial_prompt="test",
            git_branch="main",
        )

    def test_status_all_matches_everything(self, active_meta, completed_meta):
        """Test status=all matches both active and completed."""
        assert (
            _matches_filters_metadata(
                active_meta,
                project_filter=None,
                branch_filter=None,
                search_lower=None,
                status_filter=SessionStatus.ALL,
            )
            is True
        )

        assert (
            _matches_filters_metadata(
                completed_meta,
                project_filter=None,
                branch_filter=None,
                search_lower=None,
                status_filter=SessionStatus.ALL,
            )
            is True
        )

    def test_status_active_matches_active(self, active_meta):
        """Test status=active matches active sessions."""
        assert (
            _matches_filters_metadata(
                active_meta,
                project_filter=None,
                branch_filter=None,
                search_lower=None,
                status_filter=SessionStatus.ACTIVE,
            )
            is True
        )

    def test_status_active_rejects_completed(self, completed_meta):
        """Test status=active rejects completed sessions."""
        assert (
            _matches_filters_metadata(
                completed_meta,
                project_filter=None,
                branch_filter=None,
                search_lower=None,
                status_filter=SessionStatus.ACTIVE,
            )
            is False
        )

    def test_status_completed_matches_completed(self, completed_meta):
        """Test status=completed matches completed sessions."""
        assert (
            _matches_filters_metadata(
                completed_meta,
                project_filter=None,
                branch_filter=None,
                search_lower=None,
                status_filter=SessionStatus.COMPLETED,
            )
            is True
        )

    def test_status_completed_rejects_active(self, active_meta):
        """Test status=completed rejects active sessions."""
        assert (
            _matches_filters_metadata(
                active_meta,
                project_filter=None,
                branch_filter=None,
                search_lower=None,
                status_filter=SessionStatus.COMPLETED,
            )
            is False
        )


# =============================================================================
# _matches_filters_metadata Tests - Date Range Filter
# =============================================================================


class TestMatchesFiltersMetadataDateRange:
    """Tests for date range filtering in _matches_filters_metadata."""

    @pytest.fixture
    def meta_jan_15(self):
        """Create session metadata from Jan 15, 2026."""
        return SessionMetadata(
            uuid="jan15-uuid",
            encoded_name="-Users-test",
            project_path="/Users/test",
            message_count=10,
            start_time=datetime(2026, 1, 15, 12, 0, 0, tzinfo=timezone.utc),
            end_time=datetime(2026, 1, 15, 13, 0, 0, tzinfo=timezone.utc),
            slug="jan15-session",
            initial_prompt="test",
            git_branch="main",
        )

    def test_date_range_within_range(self, meta_jan_15):
        """Test session within date range passes."""
        start_dt = datetime(2026, 1, 10, 0, 0, 0, tzinfo=timezone.utc)
        end_dt = datetime(2026, 1, 20, 0, 0, 0, tzinfo=timezone.utc)

        assert (
            _matches_filters_metadata(
                meta_jan_15,
                project_filter=None,
                branch_filter=None,
                search_lower=None,
                start_dt=start_dt,
                end_dt=end_dt,
            )
            is True
        )

    def test_date_range_before_start(self, meta_jan_15):
        """Test session before start date is rejected."""
        start_dt = datetime(2026, 1, 20, 0, 0, 0, tzinfo=timezone.utc)  # After Jan 15

        assert (
            _matches_filters_metadata(
                meta_jan_15,
                project_filter=None,
                branch_filter=None,
                search_lower=None,
                start_dt=start_dt,
                end_dt=None,
            )
            is False
        )

    def test_date_range_after_end(self, meta_jan_15):
        """Test session after end date is rejected."""
        end_dt = datetime(2026, 1, 10, 0, 0, 0, tzinfo=timezone.utc)  # Before Jan 15

        assert (
            _matches_filters_metadata(
                meta_jan_15,
                project_filter=None,
                branch_filter=None,
                search_lower=None,
                start_dt=None,
                end_dt=end_dt,
            )
            is False
        )

    def test_date_range_start_only(self, meta_jan_15):
        """Test filtering with only start date."""
        start_dt = datetime(2026, 1, 10, 0, 0, 0, tzinfo=timezone.utc)

        assert (
            _matches_filters_metadata(
                meta_jan_15,
                project_filter=None,
                branch_filter=None,
                search_lower=None,
                start_dt=start_dt,
                end_dt=None,
            )
            is True
        )

    def test_date_range_end_only(self, meta_jan_15):
        """Test filtering with only end date."""
        end_dt = datetime(2026, 1, 20, 0, 0, 0, tzinfo=timezone.utc)

        assert (
            _matches_filters_metadata(
                meta_jan_15,
                project_filter=None,
                branch_filter=None,
                search_lower=None,
                start_dt=None,
                end_dt=end_dt,
            )
            is True
        )

    def test_date_range_no_session_start_time(self):
        """Test session without start_time is excluded by date range filters."""
        meta = SessionMetadata(
            uuid="no-time-uuid",
            encoded_name="-Users-test",
            project_path="/Users/test",
            message_count=10,
            start_time=None,
            end_time=None,
            slug="no-time-session",
            initial_prompt="test",
            git_branch="main",
        )
        start_dt = datetime(2026, 1, 10, 0, 0, 0, tzinfo=timezone.utc)
        end_dt = datetime(2026, 1, 20, 0, 0, 0, tzinfo=timezone.utc)

        # Sessions without start_time are excluded when date filtering is active
        # (they can't be meaningfully compared, so we exclude rather than include)
        assert (
            _matches_filters_metadata(
                meta,
                project_filter=None,
                branch_filter=None,
                search_lower=None,
                start_dt=start_dt,
                end_dt=end_dt,
            )
            is False
        )


# =============================================================================
# _matches_filters_metadata Tests - Combined Filters
# =============================================================================


class TestMatchesFiltersMetadataCombined:
    """Tests for combined filter application (AND logic)."""

    @pytest.fixture
    def sample_meta(self):
        """Create a sample SessionMetadata."""
        now = datetime.now(timezone.utc)
        return SessionMetadata(
            uuid="test-uuid",
            encoded_name="-Users-test-project",
            project_path="/Users/test/project",
            message_count=10,
            start_time=now - timedelta(hours=2),
            end_time=now - timedelta(hours=1),  # completed
            slug="auth-feature",
            initial_prompt="implement user authentication",
            git_branch="main",
            title="Auth Feature",
        )

    def test_combined_all_match(self, sample_meta):
        """Test session passes when all filters match."""
        assert (
            _matches_filters_metadata(
                sample_meta,
                project_filter="-Users-test-project",
                branch_filter="main",
                search_lower="auth",
                search_scope=SearchScope.BOTH,
                status_filter=SessionStatus.COMPLETED,
            )
            is True
        )

    def test_combined_project_fails(self, sample_meta):
        """Test session fails when project doesn't match."""
        assert (
            _matches_filters_metadata(
                sample_meta,
                project_filter="-Wrong-project",
                branch_filter="main",
                search_lower="auth",
                search_scope=SearchScope.BOTH,
                status_filter=SessionStatus.COMPLETED,
            )
            is False
        )

    def test_combined_branch_fails(self, sample_meta):
        """Test session fails when branch doesn't match."""
        assert (
            _matches_filters_metadata(
                sample_meta,
                project_filter="-Users-test-project",
                branch_filter="develop",  # doesn't match "main"
                search_lower="auth",
                search_scope=SearchScope.BOTH,
                status_filter=SessionStatus.COMPLETED,
            )
            is False
        )

    def test_combined_search_fails(self, sample_meta):
        """Test session fails when search doesn't match."""
        assert (
            _matches_filters_metadata(
                sample_meta,
                project_filter="-Users-test-project",
                branch_filter="main",
                search_lower="nonexistent",
                search_scope=SearchScope.BOTH,
                status_filter=SessionStatus.COMPLETED,
            )
            is False
        )

    def test_combined_status_fails(self, sample_meta):
        """Test session fails when status doesn't match."""
        assert (
            _matches_filters_metadata(
                sample_meta,
                project_filter="-Users-test-project",
                branch_filter="main",
                search_lower="auth",
                search_scope=SearchScope.BOTH,
                status_filter=SessionStatus.ACTIVE,  # sample_meta is completed
            )
            is False
        )


# =============================================================================
# StatusFilterOption Schema Tests
# =============================================================================


class TestStatusFilterOptionSchema:
    """Tests for StatusFilterOption schema."""

    def test_status_filter_option_creation(self):
        """Test creating StatusFilterOption."""
        option = StatusFilterOption(
            value="active",
            label="Active",
            count=5,
        )
        assert option.value == "active"
        assert option.label == "Active"
        assert option.count == 5

    def test_status_filter_option_serialization(self):
        """Test StatusFilterOption JSON serialization."""
        option = StatusFilterOption(
            value="completed",
            label="Completed",
            count=150,
        )
        data = option.model_dump()
        assert data == {
            "value": "completed",
            "label": "Completed",
            "count": 150,
        }


# =============================================================================
# SessionFilter Class Tests
# =============================================================================


class TestSessionFilterClass:
    """Tests for the unified SessionFilter class."""

    @pytest.fixture
    def sample_meta(self):
        """Create a sample SessionMetadata for testing."""
        now = datetime.now(timezone.utc)
        return SessionMetadata(
            uuid="test-uuid",
            encoded_name="-Users-test-project",
            project_path="/Users/test/project",
            message_count=10,
            start_time=now - timedelta(hours=2),
            end_time=now - timedelta(hours=1),  # completed
            slug="auth-feature",
            initial_prompt="implement user authentication",
            git_branch="main",
            title="Auth Feature",
        )

    def test_session_filter_no_filters(self, sample_meta):
        """Test SessionFilter with no filters matches everything."""
        sf = SessionFilter()
        assert sf.matches_metadata(sample_meta) is True

    def test_session_filter_search(self, sample_meta):
        """Test SessionFilter search matching."""
        sf = SessionFilter(search="auth")
        assert sf.matches_metadata(sample_meta) is True

        sf = SessionFilter(search="nonexistent")
        assert sf.matches_metadata(sample_meta) is False

    def test_session_filter_search_scope_titles_only(self, sample_meta):
        """Test SessionFilter with titles-only search scope."""
        # "auth" is in both title and prompt, so it matches
        sf = SessionFilter(search="auth", search_scope=SearchScope.TITLES)
        assert sf.matches_metadata(sample_meta) is True

        # "implement" is only in prompt, not title
        sample_meta.title = "Something Else"
        sf = SessionFilter(search="implement", search_scope=SearchScope.TITLES)
        assert sf.matches_metadata(sample_meta) is False

    def test_session_filter_search_scope_prompts_only(self, sample_meta):
        """Test SessionFilter with prompts-only search scope."""
        # "implement" is in prompt
        sf = SessionFilter(search="implement", search_scope=SearchScope.PROMPTS)
        assert sf.matches_metadata(sample_meta) is True

    def test_session_filter_project(self, sample_meta):
        """Test SessionFilter project filtering."""
        sf = SessionFilter(project_encoded_name="-Users-test-project")
        assert sf.matches_metadata(sample_meta) is True

        sf = SessionFilter(project_encoded_name="-Wrong-project")
        assert sf.matches_metadata(sample_meta) is False

    def test_session_filter_branch(self, sample_meta):
        """Test SessionFilter branch filtering."""
        sf = SessionFilter(branch="main")
        assert sf.matches_metadata(sample_meta) is True

        sf = SessionFilter(branch="develop")
        assert sf.matches_metadata(sample_meta) is False

    def test_session_filter_status(self, sample_meta):
        """Test SessionFilter status filtering."""
        sf = SessionFilter(status=SessionStatus.COMPLETED)
        assert sf.matches_metadata(sample_meta) is True

        sf = SessionFilter(status=SessionStatus.ACTIVE)
        assert sf.matches_metadata(sample_meta) is False

    def test_session_filter_date_range(self, sample_meta):
        """Test SessionFilter date range filtering."""
        now = datetime.now(timezone.utc)

        # Within range
        sf = SessionFilter(
            date_from=now - timedelta(days=1),
            date_to=now,
        )
        assert sf.matches_metadata(sample_meta) is True

        # Before start
        sf = SessionFilter(date_from=now - timedelta(hours=1))
        assert sf.matches_metadata(sample_meta) is False

        # After end
        sf = SessionFilter(date_to=now - timedelta(days=1))
        assert sf.matches_metadata(sample_meta) is False

    def test_session_filter_combined(self, sample_meta):
        """Test SessionFilter with multiple filters (AND logic)."""
        sf = SessionFilter(
            search="auth",
            project_encoded_name="-Users-test-project",
            branch="main",
            status=SessionStatus.COMPLETED,
        )
        assert sf.matches_metadata(sample_meta) is True

        # One filter fails
        sf = SessionFilter(
            search="auth",
            project_encoded_name="-Users-test-project",
            branch="develop",  # wrong branch
            status=SessionStatus.COMPLETED,
        )
        assert sf.matches_metadata(sample_meta) is False


class TestDetermineSessionStatusFunction:
    """Tests for the determine_session_status function."""

    def test_determine_session_status_unknown(self):
        """Test determine_session_status returns 'unknown' for missing start_time."""
        meta = SessionMetadata(
            uuid="test-uuid",
            encoded_name="-Users-test",
            project_path="/Users/test",
            message_count=10,
            start_time=None,
            end_time=None,
            slug="test-session",
            initial_prompt="test prompt",
            git_branch="main",
        )
        assert determine_session_status(meta) == "unknown"

    def test_determine_session_status_active(self):
        """Test determine_session_status returns 'active' for recent sessions."""
        now = datetime.now(timezone.utc)
        meta = SessionMetadata(
            uuid="test-uuid",
            encoded_name="-Users-test",
            project_path="/Users/test",
            message_count=10,
            start_time=now - timedelta(minutes=30),
            end_time=now - timedelta(seconds=60),  # 1 minute ago - active
            slug="test-session",
            initial_prompt="test prompt",
            git_branch="main",
        )
        assert determine_session_status(meta) == "active"

    def test_determine_session_status_completed(self):
        """Test determine_session_status returns 'completed' for old sessions."""
        now = datetime.now(timezone.utc)
        meta = SessionMetadata(
            uuid="test-uuid",
            encoded_name="-Users-test",
            project_path="/Users/test",
            message_count=10,
            start_time=now - timedelta(hours=2),
            end_time=now - timedelta(hours=1),  # 1 hour ago - completed
            slug="test-session",
            initial_prompt="test prompt",
            git_branch="main",
        )
        assert determine_session_status(meta) == "completed"


class TestFilterSessionsByDateFunction:
    """Tests for the filter_sessions_by_date utility function."""

    def test_filter_sessions_by_date_no_filters(self):
        """Test filter_sessions_by_date returns all sessions when no date filters."""

        # Create mock sessions with start_time attribute
        class MockSession:
            def __init__(self, start_time):
                self.start_time = start_time

        sessions = [
            MockSession(datetime(2026, 1, 10, tzinfo=timezone.utc)),
            MockSession(datetime(2026, 1, 15, tzinfo=timezone.utc)),
            MockSession(datetime(2026, 1, 20, tzinfo=timezone.utc)),
        ]

        result = filter_sessions_by_date(sessions, None, None)
        assert len(result) == 3

    def test_filter_sessions_by_date_with_range(self):
        """Test filter_sessions_by_date filters correctly with date range."""

        class MockSession:
            def __init__(self, start_time):
                self.start_time = start_time

        sessions = [
            MockSession(datetime(2026, 1, 10, tzinfo=timezone.utc)),
            MockSession(datetime(2026, 1, 15, tzinfo=timezone.utc)),
            MockSession(datetime(2026, 1, 20, tzinfo=timezone.utc)),
        ]

        # Filter to only Jan 12-18
        start_dt = datetime(2026, 1, 12, tzinfo=timezone.utc)
        end_dt = datetime(2026, 1, 18, tzinfo=timezone.utc)
        result = filter_sessions_by_date(sessions, start_dt, end_dt)

        assert len(result) == 1
        assert result[0].start_time.day == 15

    def test_filter_sessions_by_date_excludes_no_start_time(self):
        """Test filter_sessions_by_date excludes sessions without start_time."""

        class MockSession:
            def __init__(self, start_time):
                self.start_time = start_time

        sessions = [
            MockSession(datetime(2026, 1, 15, tzinfo=timezone.utc)),
            MockSession(None),  # No start_time
        ]

        start_dt = datetime(2026, 1, 10, tzinfo=timezone.utc)
        result = filter_sessions_by_date(sessions, start_dt, None)

        assert len(result) == 1
        assert result[0].start_time is not None

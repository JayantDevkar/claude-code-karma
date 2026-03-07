"""
Unified session filtering logic.

This module consolidates filter logic that was previously duplicated across:
- routers/sessions.py (_matches_filters, _matches_filters_metadata)
- routers/history.py (inline search filtering)
- routers/analytics.py (_filter_sessions_by_date)

The SessionFilter class provides a single, consistent interface for
filtering sessions by various criteria.
"""

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import TYPE_CHECKING, Optional

from utils import normalize_timezone

if TYPE_CHECKING:
    from models import Session


class SearchScope(str, Enum):
    """Search scope for session search."""

    BOTH = "both"
    TITLES = "titles"
    PROMPTS = "prompts"


class SessionStatus(str, Enum):
    """Status filter for session search."""

    ALL = "all"
    ACTIVE = "active"
    COMPLETED = "completed"
    ERROR = "error"


class SessionSource(str, Enum):
    """Source filter for session search."""

    ALL = "all"
    LOCAL = "local"
    REMOTE = "remote"


@dataclass
class SessionMetadata:
    """
    Lightweight session metadata for filtering without full JSONL parsing.

    Used to avoid N+1 query pattern where we'd load all Session objects
    across all projects before any filtering or pagination.
    """

    uuid: str
    encoded_name: str
    project_path: str
    message_count: int
    start_time: Optional[datetime]
    end_time: Optional[datetime]
    slug: Optional[str]
    initial_prompt: Optional[str]
    git_branch: Optional[str]
    # Session title/summary for display (from sessions-index.json summary field)
    title: Optional[str] = None
    session_titles: Optional[list] = None  # All session titles (from title cache)
    # Remote sync fields
    source: Optional[str] = None  # "local" or "remote" (None = local)
    remote_user_id: Optional[str] = None
    remote_machine_id: Optional[str] = None
    # Lazy session loader - only called when we need the full Session
    _session: Optional["Session"] = None

    def get_session(self) -> "Session":
        """Get the full Session object (lazy load)."""
        if self._session:
            return self._session
        # Import here to avoid circular imports
        from config import settings
        from models import Session

        # Construct from path
        projects_dir = settings.projects_dir
        jsonl_path = projects_dir / self.encoded_name / f"{self.uuid}.jsonl"
        return Session.from_path(jsonl_path)

    def get_git_branches(self) -> set:
        """Get git branches - from metadata if available, or from session."""
        if self.git_branch:
            return {self.git_branch}
        if self._session:
            return self._session.get_git_branches()
        # For index-loaded metadata without full session, return single branch
        return set()


# Active session threshold in seconds (5 minutes)
ACTIVE_THRESHOLD_SECONDS = 300


def determine_session_status(meta: SessionMetadata) -> str:
    """
    Determine session status from metadata.

    Status is based on time since last activity:
    - active: last activity within 5 minutes
    - completed: older than 5 minutes
    - error: would require checking session messages (future enhancement)

    Args:
        meta: SessionMetadata to check

    Returns:
        Status string: "active", "completed", or "unknown"
    """
    if not meta.start_time:
        return "unknown"

    now = datetime.now(timezone.utc)

    # Check recency of last activity
    if meta.end_time:
        age_seconds = (now - normalize_timezone(meta.end_time)).total_seconds()

        # Active: last activity within 5 minutes (300 seconds)
        if age_seconds < ACTIVE_THRESHOLD_SECONDS:
            return "active"
        # Completed: older than 5 minutes
        return "completed"

    return "completed"


@dataclass
class SessionFilter:
    """
    Unified session filter that consolidates filtering logic.

    Supports filtering by:
    - search: Text search in prompts, titles, slugs, paths (comma-separated tokens)
    - search_scope: Where to search (titles, prompts, or both)
    - status: Session status (active, completed, error, all)
    - date_from: Filter sessions starting after this time
    - date_to: Filter sessions starting before this time
    - project_encoded_name: Filter by project encoded name
    - branch: Filter by git branch

    All filters are optional; when None, that filter is not applied.
    Multiple filters are combined with AND logic.

    Search tokens use AND logic: all tokens must match for a session to be included.
    """

    search: Optional[str] = None
    search_scope: SearchScope = SearchScope.BOTH
    status: SessionStatus = SessionStatus.ALL
    source: SessionSource = SessionSource.ALL
    date_from: Optional[datetime] = None
    date_to: Optional[datetime] = None
    project_encoded_name: Optional[str] = None
    branch: Optional[str] = None

    def __post_init__(self):
        """Parse search into tokens (comma-separated) and normalize to lowercase."""
        self._search_tokens: list[str] = []
        if self.search:
            # Split on comma, strip whitespace, lowercase, remove empty
            self._search_tokens = [
                token.strip().lower() for token in self.search.split(",") if token.strip()
            ][:7]  # Max 7 tokens
        # Keep _search_lower for backward compatibility
        self._search_lower = self.search.lower() if self.search else None

    def _text_matches_all_tokens(self, text: str) -> bool:
        """Check if text contains ALL search tokens (AND logic)."""
        if not self._search_tokens:
            return True
        text_lower = text.lower()
        return all(token in text_lower for token in self._search_tokens)

    def matches(self, session: "Session", encoded_name: str, project_path: str) -> bool:
        """
        Check if a Session matches all filter criteria.

        Args:
            session: Full Session object to check
            encoded_name: Project encoded name
            project_path: Full project path

        Returns:
            True if session matches all filters
        """
        # Project filter
        if self.project_encoded_name and encoded_name != self.project_encoded_name:
            return False

        # Branch filter
        if self.branch and self.branch not in session.get_git_branches():
            return False

        # Search filter with token-based AND logic
        if self._search_tokens:
            # Build combined searchable text based on scope
            searchable_parts: list[str] = []

            # Check prompts (slug, path, initial_prompt)
            if self.search_scope in (SearchScope.BOTH, SearchScope.PROMPTS):
                if session.slug:
                    searchable_parts.append(session.slug)
                if project_path:
                    searchable_parts.append(project_path)
                # Get initial prompt (first user message)
                from utils import get_initial_prompt

                prompt = get_initial_prompt(session)
                if prompt:
                    searchable_parts.append(prompt)

            # Check titles
            if self.search_scope in (SearchScope.BOTH, SearchScope.TITLES):
                for title in session.session_titles or []:
                    searchable_parts.append(title)

            # Combine all searchable text and check ALL tokens match
            combined_text = " ".join(searchable_parts)
            if not self._text_matches_all_tokens(combined_text):
                return False

        # Date range filtering
        if self.date_from:
            if not session.start_time:
                return False
            if normalize_timezone(session.start_time) < normalize_timezone(self.date_from):
                return False

        if self.date_to:
            if not session.start_time:
                return False
            if normalize_timezone(session.start_time) > normalize_timezone(self.date_to):
                return False

        return True

    def matches_metadata(self, meta: SessionMetadata) -> bool:
        """
        Check if SessionMetadata matches all filter criteria.

        Optimized version that works with lightweight SessionMetadata
        instead of full Session objects. Use this for index-based filtering.

        Args:
            meta: Session metadata to check

        Returns:
            True if session matches all filters
        """
        # Project filter
        if self.project_encoded_name and meta.encoded_name != self.project_encoded_name:
            return False

        # Branch filter
        if self.branch:
            branches = meta.get_git_branches()
            if self.branch not in branches:
                return False

        # Source filter (local/remote)
        if self.source != SessionSource.ALL:
            meta_source = meta.source or "local"
            if meta_source != self.source.value:
                return False

        # Search filter with token-based AND logic
        if self._search_tokens:
            # Build combined searchable text based on scope
            searchable_parts: list[str] = []

            # Check prompts (slug, path, initial_prompt)
            if self.search_scope in (SearchScope.BOTH, SearchScope.PROMPTS):
                if meta.slug:
                    searchable_parts.append(meta.slug)
                if meta.project_path:
                    searchable_parts.append(meta.project_path)
                if meta.initial_prompt:
                    searchable_parts.append(meta.initial_prompt)

            # Check titles (from title cache — no JSONL loading needed)
            if self.search_scope in (SearchScope.BOTH, SearchScope.TITLES):
                if meta.session_titles:
                    for title in meta.session_titles:
                        searchable_parts.append(title)
                elif meta.title:
                    searchable_parts.append(meta.title)

            # Combine all searchable text and check ALL tokens match
            combined_text = " ".join(searchable_parts)
            if not self._text_matches_all_tokens(combined_text):
                return False

        # Status filter
        if self.status != SessionStatus.ALL:
            session_status = determine_session_status(meta)
            if session_status != self.status.value:
                return False

        # Date range filtering
        # Sessions without start_time are excluded when date filtering is active
        if self.date_from:
            if not meta.start_time:
                return False
            if normalize_timezone(meta.start_time) < normalize_timezone(self.date_from):
                return False

        if self.date_to:
            if not meta.start_time:
                return False
            if normalize_timezone(meta.start_time) > normalize_timezone(self.date_to):
                return False

        return True

    def matches_session_for_date(self, session: "Session") -> bool:
        """
        Check if a session matches date filters only.

        Simplified filter for analytics that only needs date range filtering.
        This is a lightweight check for already-loaded Session objects.

        Args:
            session: Session to check

        Returns:
            True if session falls within date range
        """
        if not self.date_from and not self.date_to:
            return True

        if not session.start_time:
            return False

        if self.date_from and session.start_time < self.date_from:
            return False

        if self.date_to and session.start_time > self.date_to:
            return False

        return True


def filter_sessions_by_date(
    sessions: list,
    start_date: Optional[datetime],
    end_date: Optional[datetime],
) -> list:
    """
    Filter sessions by date range.

    Convenience function that wraps SessionFilter for simple date filtering.
    Kept for backward compatibility with existing code.

    Note: For new code, prefer using Project.list_sessions_filtered() which
    applies early mtime-based filtering before loading sessions (Phase 4).

    Args:
        sessions: List of Session objects to filter
        start_date: Filter sessions starting after this time
        end_date: Filter sessions starting before this time

    Returns:
        Filtered list of sessions
    """
    if not start_date and not end_date:
        return sessions

    session_filter = SessionFilter(date_from=start_date, date_to=end_date)
    return [s for s in sessions if session_filter.matches_session_for_date(s)]

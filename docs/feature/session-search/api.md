# Session Search - API Implementation Tasks

**Feature:** Session Search with Filters
**Module:** `api/` submodule
**Related Design:** `docs/design/session-search-feature.md`

---

## Overview

Extend the existing `/sessions/all` endpoint to support additional search and filter capabilities:
- **Search scope:** Search in titles only, prompts only, or both
- **Status filter:** Active, completed, error sessions
- **Date range filter:** Filter by session start time

---

## Current Implementation Analysis

### Existing Endpoint
**File:** `api/routers/sessions.py:488-610`

```python
@router.get("/all", response_model=AllSessionsResponse)
def get_all_sessions(
    search: Optional[str] = None,      # Searches slug, initial_prompt, project_path
    project: Optional[str] = None,     # Filter by encoded project name
    branch: Optional[str] = None,      # Filter by git branch
    limit: int = 200,
    offset: int = 0,
) -> AllSessionsResponse
```

### What Already Exists (Reuse)

| Component | Location | Status |
|-----------|----------|--------|
| Timestamp parsing | `api/utils.py:15-45` | Ready to use |
| Timezone normalization | `api/utils.py:48-73` | Ready to use |
| Filter matching pattern | `api/routers/sessions.py:461-485` | Extend |
| Pagination with heapq | `api/routers/sessions.py:535-557` | No changes |
| Session index loading | `api/routers/sessions.py:489-530` | No changes |
| Caching decorator | `@cacheable()` | Already applied |

### Data Available in SessionMetadata

| Field | Source | Notes |
|-------|--------|-------|
| `uuid` | Index | Always available |
| `slug` | Index/Session | Lazy loaded if not in index |
| `initial_prompt` | Index (`first_prompt`) | Truncated to 500 chars |
| `start_time` | Index (`created`) | Available |
| `end_time` | Index (`modified`) | Available |
| `git_branch` | Index | Available |
| `session_titles` | Session only | Requires lazy load |

---

## Implementation Tasks

### Task 1: Add Search Scope Parameter

**Goal:** Allow searching only titles, only prompts, or both (default)

**File:** `api/routers/sessions.py`

**Changes:**

1. Add `scope` query parameter to endpoint:
```python
from enum import Enum

class SearchScope(str, Enum):
    BOTH = "both"
    TITLES = "titles"
    PROMPTS = "prompts"

@router.get("/all", response_model=AllSessionsResponse)
def get_all_sessions(
    # ... existing params ...
    scope: SearchScope = SearchScope.BOTH,  # NEW
) -> AllSessionsResponse:
```

2. Update `_matches_filters_metadata()` function:
```python
def _matches_filters_metadata(
    meta: SessionMetadata,
    project_filter: Optional[str],
    branch_filter: Optional[str],
    search_lower: Optional[str],
    search_scope: SearchScope = SearchScope.BOTH,  # NEW
) -> bool:
    # ... existing filters ...

    if search_lower:
        matches = False

        # Check prompts (existing behavior)
        if search_scope in (SearchScope.BOTH, SearchScope.PROMPTS):
            if meta.initial_prompt and search_lower in meta.initial_prompt.lower():
                matches = True
            # Also check slug for prompts scope (backward compat)
            if meta.slug and search_lower in meta.slug.lower():
                matches = True

        # Check titles (NEW)
        if search_scope in (SearchScope.BOTH, SearchScope.TITLES):
            if meta.title and search_lower in meta.title.lower():
                matches = True
            # Lazy load session_titles if needed
            if not matches and search_scope == SearchScope.TITLES:
                session = meta.get_session()
                titles = session.session_titles or []
                for title in titles:
                    if search_lower in title.lower():
                        matches = True
                        break

        if not matches:
            return False

    return True
```

3. Add `title` field to `SessionMetadata` dataclass:
```python
@dataclass
class SessionMetadata:
    # ... existing fields ...
    title: Optional[str] = None  # First session_title if available
```

**Performance consideration:** Title search requires lazy loading `session_titles` which means parsing the JSONL. Consider caching the first title in the session index in a future optimization.

---

### Task 2: Add Status Filter Parameter

**Goal:** Filter sessions by status (active, completed, error)

**File:** `api/routers/sessions.py`

**Changes:**

1. Define status enum:
```python
class SessionStatus(str, Enum):
    ALL = "all"
    ACTIVE = "active"
    COMPLETED = "completed"
    ERROR = "error"
```

2. Add status determination helper:
```python
def _determine_session_status(meta: SessionMetadata) -> str:
    """Determine session status from metadata."""
    from datetime import datetime, timezone

    if not meta.start_time:
        return "unknown"

    now = datetime.now(timezone.utc)

    # Check if session has error indicators
    # (would need to check last message or session metadata)

    # Check recency of last activity
    if meta.end_time:
        age_seconds = (now - normalize_timezone(meta.end_time)).total_seconds()

        # Active: last activity within 5 minutes
        if age_seconds < 300:
            return "active"
        # Completed: older than 5 minutes
        else:
            return "completed"

    return "completed"
```

3. Add to endpoint:
```python
@router.get("/all", response_model=AllSessionsResponse)
def get_all_sessions(
    # ... existing params ...
    status: SessionStatus = SessionStatus.ALL,  # NEW
) -> AllSessionsResponse:
```

4. Add to filter function:
```python
def _matches_filters_metadata(
    meta: SessionMetadata,
    # ... existing params ...
    status_filter: SessionStatus = SessionStatus.ALL,  # NEW
) -> bool:
    # ... existing filters ...

    if status_filter != SessionStatus.ALL:
        session_status = _determine_session_status(meta)
        if session_status != status_filter.value:
            return False

    return True
```

**Note:** Error status detection requires checking session messages for error indicators. This could be:
- A message with `stop_reason: "error"`
- An error in the last assistant message
- A flag in session metadata

For MVP, consider error as a subset of completed (sessions that ended with errors).

---

### Task 3: Add Date Range Filter Parameters

**Goal:** Filter sessions by start_time within a date range

**File:** `api/routers/sessions.py`

**Changes:**

1. Add timestamp parameters to endpoint:
```python
@router.get("/all", response_model=AllSessionsResponse)
def get_all_sessions(
    # ... existing params ...
    start_ts: Optional[int] = None,  # NEW - Unix timestamp in milliseconds
    end_ts: Optional[int] = None,    # NEW - Unix timestamp in milliseconds
) -> AllSessionsResponse:
```

2. Parse timestamps in endpoint body:
```python
from utils import parse_timestamp_range, normalize_timezone

def get_all_sessions(...):
    # Parse date range
    start_dt, end_dt = parse_timestamp_range(start_ts, end_ts)

    # Pass to filter
    filtered_sessions = [
        meta for meta in all_sessions
        if _matches_filters_metadata(
            meta, project, branch,
            search.lower() if search else None,
            scope, status, start_dt, end_dt  # Pass new params
        )
    ]
```

3. Add to filter function:
```python
def _matches_filters_metadata(
    meta: SessionMetadata,
    # ... existing params ...
    start_dt: Optional[datetime] = None,  # NEW
    end_dt: Optional[datetime] = None,    # NEW
) -> bool:
    # ... existing filters ...

    # Date range filtering
    if start_dt and meta.start_time:
        if normalize_timezone(meta.start_time) < normalize_timezone(start_dt):
            return False

    if end_dt and meta.start_time:
        if normalize_timezone(meta.start_time) > normalize_timezone(end_dt):
            return False

    return True
```

**Already exists:** `parse_timestamp_range()` in `api/utils.py:15-45`

---

### Task 4: Update Response Schema

**Goal:** Include filter metadata in response for frontend dropdowns

**File:** `api/schemas.py`

**Changes:**

1. Add filter option schemas:
```python
class StatusFilterOption(BaseModel):
    """Option for status filter dropdown."""
    value: str
    label: str
    count: int

class DateRangePreset(BaseModel):
    """Preset date range option."""
    value: str
    label: str
    start_ts: Optional[int]
    end_ts: Optional[int]
```

2. Extend `AllSessionsResponse`:
```python
class AllSessionsResponse(BaseModel):
    sessions: list[SessionWithContext]
    total: int
    page: int
    per_page: int
    total_pages: int
    projects: list[ProjectFilterOption]
    # NEW fields
    status_options: list[StatusFilterOption] = Field(default_factory=list)
    applied_filters: dict = Field(default_factory=dict)  # Echo back applied filters
```

3. Compute status counts in endpoint:
```python
def get_all_sessions(...):
    # After filtering, compute status distribution
    status_counts = {"active": 0, "completed": 0, "error": 0}
    for meta in all_sessions:  # Before filtering by status
        s = _determine_session_status(meta)
        if s in status_counts:
            status_counts[s] += 1

    status_options = [
        StatusFilterOption(value="all", label="All", count=len(all_sessions)),
        StatusFilterOption(value="active", label="Active", count=status_counts["active"]),
        StatusFilterOption(value="completed", label="Completed", count=status_counts["completed"]),
        StatusFilterOption(value="error", label="Error", count=status_counts["error"]),
    ]
```

---

### Task 5: Add Session Titles to Index (Optimization)

**Goal:** Cache first session title in index to avoid lazy loading for title search

**File:** `api/models/session_index.py`

**Changes:**

1. Add field to `SessionIndexEntry`:
```python
class SessionIndexEntry(BaseModel):
    # ... existing fields ...
    session_title: Optional[str] = None  # First AI-generated title
```

2. Update index building in `api/routers/sessions.py`:
```python
# When building index entry from Session
entry = SessionIndexEntry(
    session_id=session.uuid,
    first_prompt=get_initial_prompt(session, max_length=500),
    session_title=session.session_titles[0] if session.session_titles else None,  # NEW
    # ... other fields ...
)
```

3. Use in `SessionMetadata`:
```python
# In _build_metadata_from_index()
meta = SessionMetadata(
    uuid=entry.session_id,
    title=entry.session_title,  # Use indexed title
    # ... other fields ...
)
```

**Note:** This is an optimization task. Can be done after MVP if performance is acceptable.

---

## File Changes Summary

| File | Changes |
|------|---------|
| `api/routers/sessions.py` | Add params, extend filter function, compute status |
| `api/schemas.py` | Add StatusFilterOption, extend AllSessionsResponse |
| `api/models/session_index.py` | Add session_title field (optional optimization) |
| `api/utils.py` | No changes (reuse existing functions) |

---

## API Contract

### Updated Endpoint

```
GET /sessions/all?
  search=<string>           # Text search query
  &scope=both|titles|prompts  # Search scope (default: both)
  &project=<encoded_name>   # Filter by project
  &branch=<branch_name>     # Filter by git branch
  &status=all|active|completed|error  # Status filter (default: all)
  &start_ts=<unix_ms>       # Date range start (milliseconds)
  &end_ts=<unix_ms>         # Date range end (milliseconds)
  &limit=200                # Page size
  &offset=0                 # Pagination offset
```

### Response

```json
{
  "sessions": [...],
  "total": 156,
  "page": 1,
  "per_page": 200,
  "total_pages": 1,
  "projects": [...],
  "status_options": [
    {"value": "all", "label": "All", "count": 156},
    {"value": "active", "label": "Active", "count": 3},
    {"value": "completed", "label": "Completed", "count": 150},
    {"value": "error", "label": "Error", "count": 3}
  ],
  "applied_filters": {
    "search": "implement",
    "scope": "titles",
    "status": "active",
    "start_ts": 1706140800000,
    "end_ts": 1706745600000
  }
}
```

---

## Testing Requirements

### Unit Tests

**File:** `api/tests/test_sessions.py`

```python
def test_search_scope_titles_only():
    """Search should only match session titles when scope=titles."""
    pass

def test_search_scope_prompts_only():
    """Search should only match initial_prompt when scope=prompts."""
    pass

def test_search_scope_both():
    """Search should match both titles and prompts when scope=both."""
    pass

def test_status_filter_active():
    """Should only return sessions with recent activity."""
    pass

def test_status_filter_completed():
    """Should only return sessions without recent activity."""
    pass

def test_date_range_filter():
    """Should only return sessions within date range."""
    pass

def test_combined_filters():
    """Should correctly apply multiple filters with AND logic."""
    pass

def test_pagination_with_filters():
    """Pagination should work correctly with filters applied."""
    pass
```

### Integration Tests

```python
def test_api_search_endpoint_with_all_params():
    """Test full endpoint with all parameters."""
    response = client.get(
        "/sessions/all",
        params={
            "search": "auth",
            "scope": "titles",
            "status": "completed",
            "start_ts": 1706140800000,
            "end_ts": 1706745600000,
            "limit": 10,
        }
    )
    assert response.status_code == 200
    data = response.json()
    assert "status_options" in data
    assert "applied_filters" in data
```

---

## Performance Considerations

1. **Title search without index:** Requires lazy loading sessions. For large datasets (1000+ sessions), consider:
   - Adding `session_title` to index (Task 5)
   - Implementing search result caching
   - Using background indexing for titles

2. **Status computation:** `_determine_session_status()` is cheap (datetime comparison). No concerns.

3. **Date filtering:** Uses indexed `start_time`, very efficient.

4. **Cache invalidation:** The `@cacheable` decorator handles this. New filter params will create new cache keys.

---

## Dependencies

- No new Python packages required
- Uses existing `datetime`, `enum` from stdlib
- Uses existing `utils.py` functions

---

## Rollout Plan

1. **Phase 1:** Add date range filter (lowest risk, uses existing patterns)
2. **Phase 2:** Add status filter (requires status determination logic)
3. **Phase 3:** Add search scope (may require index optimization for performance)

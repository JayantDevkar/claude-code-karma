# Session Search Logic Issues

**Branch**: `feature/session-search`
**Date**: 2026-01-30
**Status**: Analysis Complete

---

## Overview

This document outlines observations and details regarding the session filtering implementation across two views in Claude Karma:

1. **Project Detail Page** (`/projects/[encoded_name]`)
2. **Global Sessions Page** (`/sessions`)

The session search feature was implemented in both locations with the goal of providing consistent filtering capabilities. However, analysis reveals inconsistencies in data sources, filtering logic, and code structure.

---

## Observed Discrepancy

When viewing the same project from different entry points:

| View          | Displayed Count                  | Example                                                               |
| ------------- | -------------------------------- | --------------------------------------------------------------------- |
| Project Page  | "366 of 368 sessions"            | `/projects/-Users-jayantdevkar-Documents-GitHub-claude-karma`         |
| Sessions Page | "Showing 1 - 50 of 344 sessions" | `/sessions?project=-Users-jayantdevkar-Documents-GitHub-claude-karma` |

**Difference**: 368 total sessions (project) vs 344 total sessions (global)

---

## Data Flow Analysis

### Project Detail Page

```
User visits /projects/[encoded_name]
    ↓
+page.server.ts calls GET /projects/{encoded_name}
    ↓
API returns Project object with ALL sessions
    ↓
project.sessions contains 368 sessions
    ↓
Client-side filtering in $derived (filteredSessions)
    ↓
Display: "366 of 368 sessions"
```

**API Endpoint**: `/projects/{encoded_name}`
**File**: `api/routers/projects.py`
**Session Loading**: `project.list_sessions()` → Full Session objects
**Empty Session Filter**: None applied

### Global Sessions Page

```
User visits /sessions
    ↓
+page.server.ts calls GET /sessions/all
    ↓
API uses sessions-index.json (optimized)
    ↓
Filters: message_count > 0
    ↓
Returns 344 sessions (paginated)
    ↓
Client-side + server-side filtering
    ↓
Display: "Showing 1 - 50 of 344 sessions"
```

**API Endpoint**: `/sessions/all`
**File**: `api/routers/sessions.py`
**Session Loading**: `SessionMetadata` from sessions-index.json
**Empty Session Filter**: `valid_entries = [e for e in index.entries if e.message_count > 0]`

---

## API Implementation Details

### `/projects/{encoded_name}` Endpoint

**Location**: `api/routers/projects.py` lines 166-213

```python
@router.get("/{encoded_name}")
def get_project(encoded_name: str, request: Request, limit: int | None = None):
    project = Project.from_encoded_name(encoded_name)
    sessions = project.list_sessions()
    # No filtering by message_count
    # All sessions returned regardless of content
```

**Session Count Property** (`api/models/project.py` line 453):

```python
@property
def session_count(self) -> int:
    return len(self.list_session_paths())  # Counts all *.jsonl files
```

### `/sessions/all` Endpoint

**Location**: `api/routers/sessions.py` lines 610-788

```python
@router.get("/all", response_model=AllSessionsResponse)
def get_all_sessions(...):
    all_sessions, project_options = _list_all_projects_with_sessions_optimized()
    # Uses sessions-index.json with message_count filter
```

**Optimized Loading** (`api/routers/sessions.py` lines 254-357):

```python
def _list_all_projects_with_sessions_optimized():
    index = project.load_sessions_index()
    if index and index.entries:
        valid_entries = [e for e in index.entries if e.message_count > 0]
        # Only sessions with messages are included
```

---

## Frontend Implementation Analysis

### File Locations

| Component     | Project Page                                         | Sessions Page                         |
| ------------- | ---------------------------------------------------- | ------------------------------------- |
| Route         | `src/routes/projects/[encoded_name]/+page.svelte`    | `src/routes/sessions/+page.svelte`    |
| Server Loader | `src/routes/projects/[encoded_name]/+page.server.ts` | `src/routes/sessions/+page.server.ts` |
| Lines of Code | 1,086 lines                                          | 1,374 lines                           |

### Shared Components Used

Both pages use the same filter UI components:

- `SessionSearchBar.svelte` - Search input with filter toggle
- `FiltersDropdown.svelte` - Desktop filter panel
- `FiltersBottomSheet.svelte` - Mobile filter panel
- `ActiveFilterChips.svelte` - Visual filter indicators

### Shared Utilities

**File**: `src/lib/search.ts`

```typescript
// Default filter state
export const DEFAULT_FILTERS: SearchFilters = {
	query: '',
	scope: 'both',
	status: 'all',
	dateRange: 'all',
	liveSubStatuses: [...ALL_LIVE_SUB_STATUSES]
};

// Utility functions
export function getFilterChips(filters: SearchFilters): FilterChip[];
export function hasActiveFilters(filters: SearchFilters): boolean;
export function getDateRangeTimestamps(range, customStart?, customEnd?);
```

---

## Code Duplication Analysis

### Duplicated Filtering Logic

#### Search Query Matching

**Project Page** (`+page.svelte` lines 527-553):

```typescript
if (filters.query.trim()) {
	const query = filters.query.toLowerCase().trim();
	sessions = sessions.filter((session) => {
		let matches = false;
		if (scopeSelection.prompts) {
			const matchSlug = session.slug?.toLowerCase().includes(query);
			const matchPrompt = session.initial_prompt?.toLowerCase().includes(query);
			const matchUuid = session.uuid.toLowerCase().includes(query);
			if (matchSlug || matchPrompt || matchUuid) matches = true;
		}
		if (scopeSelection.titles) {
			const matchTitle = session.session_titles?.some((t) => t.toLowerCase().includes(query));
			if (matchTitle) matches = true;
		}
		return matches;
	});
}
```

**Sessions Page** (`+page.svelte` lines 183-209):

```typescript
if (searchInput.trim()) {
	const query = searchInput.toLowerCase().trim();
	sessions = sessions.filter((session) => {
		let matches = false;
		if (scopeSelection.prompts) {
			const matchSlug = session.slug?.toLowerCase().includes(query);
			const matchPrompt = session.initial_prompt?.toLowerCase().includes(query);
			const matchUuid = session.uuid.toLowerCase().includes(query);
			if (matchSlug || matchPrompt || matchUuid) matches = true;
		}
		if (scopeSelection.titles) {
			const matchTitle = session.session_titles?.some((t) => t.toLowerCase().includes(query));
			if (matchTitle) matches = true;
		}
		return matches;
	});
}
```

#### Status Filtering

**Project Page** (`+page.svelte` lines 557-569):

```typescript
if (filters.status !== 'all') {
	if (filters.status === 'completed') {
		sessions = sessions.filter((session) => !getLiveSession(session.uuid));
	} else if (filters.status === 'live') {
		sessions = sessions.filter((session) => {
			const live = getLiveSession(session.uuid);
			if (!live) return false;
			return selectedLiveSubStatuses.includes(live.status as LiveSubStatus);
		});
	}
}
```

**Sessions Page** (`+page.svelte` lines 213-222):

```typescript
if (selectedStatus !== 'all') {
	if (selectedStatus === 'completed') {
		sessions = sessions.filter((session) => !getLiveSession(session));
	} else if (selectedStatus === 'live') {
		sessions = []; // Different behavior - hides all historical
	}
}
```

#### Date Range Filtering

**Project Page** (`+page.svelte` lines 573-587):

```typescript
const { start_ts, end_ts } = getDateRangeTimestamps(
	filters.dateRange,
	filters.customStart,
	filters.customEnd
);
if (start_ts) {
	sessions = sessions.filter((s) => s.start_time && new Date(s.start_time).getTime() >= start_ts);
}
if (end_ts) {
	sessions = sessions.filter((s) => s.start_time && new Date(s.start_time).getTime() <= end_ts);
}
```

**Sessions Page** (`+page.svelte` lines 225-235):

```typescript
const { start_ts, end_ts } = getDateRangeTimestamps(selectedDateRange);
if (start_ts) {
	sessions = sessions.filter((s) => s.start_time && new Date(s.start_time).getTime() >= start_ts);
}
if (end_ts) {
	sessions = sessions.filter((s) => s.start_time && new Date(s.start_time).getTime() <= end_ts);
}
```

### Duplicated State Management

**Project Page** (`+page.svelte` lines 308-313):

```typescript
let filters = $state<SearchFilters>({ ...DEFAULT_FILTERS });
let scopeSelection = $state<SearchScopeSelection>({ ...DEFAULT_SCOPE_SELECTION });
let selectedLiveSubStatuses = $state<LiveSubStatus[]>([...ALL_LIVE_SUB_STATUSES]);
let showFiltersDropdown = $state(false);
let isMobile = $state(false);
let selectedBranchFilters = $state<Set<string>>(new Set());
```

**Sessions Page** (`+page.svelte` lines 153-164):

```typescript
let searchInput = $state(data.filters.search || '');
let selectedProject = $state(data.filters.project || '');
let selectedBranch = $state(data.filters.branch || '');
let scopeSelection = $state<SearchScopeSelection>(
	apiToScopeSelection(data.filters.scope || 'both')
);
let selectedStatus = $state<SessionStatusFilter>(data.filters.status || 'all');
let selectedDateRange = $state<SearchDateRange>('all');
let selectedLiveSubStatuses = $state<LiveSubStatus[]>([...ALL_LIVE_SUB_STATUSES]);
let showFiltersDropdown = $state(false);
let isMobile = $state(false);
```

### Duplicated Event Handlers

Both files implement nearly identical handler functions:

| Handler                      | Project Page Lines | Sessions Page Lines |
| ---------------------------- | ------------------ | ------------------- |
| `handleSearchChange`         | 424-426            | 641-643             |
| `handleScopeSelectionChange` | 428-430            | 646-648             |
| `handleStatusChange`         | 432-434            | 658-660             |
| `handleDateRangeChange`      | 436-438            | 662-672             |
| `handleLiveSubStatusChange`  | 440-442            | 675-677             |
| `handleRemoveFilter`         | 444-450            | 680-702             |
| `handleClearAllFilters`      | 452-457            | 737-758             |

### Duplicated Live Session Logic

#### `getLiveSession()` Function

**Project Page** (`+page.svelte` lines 223-230):

```typescript
function getLiveSession(sessionUuid: string): LiveSessionSummary | null {
	const live = liveSessionsMap.get(sessionUuid);
	if (!live) return null;
	if (live.status === 'ended' && !shouldShowEndedStatus(live.updated_at)) {
		return null;
	}
	return live;
}
```

**Sessions Page** (`+page.svelte` lines 123-131):

```typescript
function getLiveSession(session: SessionWithContext): LiveSessionSummary | null {
	if (session.slug) {
		const bySlug = liveSessionMaps.bySlug.get(session.slug);
		if (bySlug) return bySlug;
	}
	return liveSessionMaps.bySessionId.get(session.uuid) || null;
}
```

**Note**: Different matching strategies - Project page uses UUID only, Sessions page tries slug first then UUID.

#### Recently Ended Sessions Logic

**Project Page** (`+page.svelte` lines 340-393):

```typescript
let recentlyEndedSessions = $derived.by(() => {
	if (filters.status === 'completed') return [];
	const allLive = Array.from(liveSessionsMap.values());
	let endedLive = allLive.filter(
		(s) => s.status === 'ended' && shouldShowEndedStatus(s.updated_at)
	);
	// Apply filters...
	// Match to historical sessions...
	// Sort by updated_at...
});
```

**Sessions Page** (`+page.svelte` lines 371-417):

```typescript
const recentlyEndedSessions = $derived.by(() => {
	if (selectedStatus === 'completed') return [];
	let endedLive = data.liveSessions.filter(
		(s) => s.status === 'ended' && shouldShowEndedStatus(s.updated_at)
	);
	// Apply filters...
	// Match to historical sessions...
	// Sort by updated_at...
});
```

#### Live Status Counts

**Project Page** (`+page.svelte` lines 317-333):

```typescript
let liveStatusCounts = $derived.by<LiveStatusCounts>(() => {
	const allLive = Array.from(liveSessionsMap.values());
	const liveSessions = allLive.filter(
		(s) => s.status !== 'ended' || shouldShowEndedStatus(s.updated_at)
	);
	return {
		total: liveSessions.length,
		starting: liveSessions.filter((s) => s.status === 'starting').length,
		active: liveSessions.filter((s) => s.status === 'active').length
		// ... identical for all statuses
	};
});
```

**Sessions Page** (`+page.svelte` lines 316-331):

```typescript
let liveStatusCounts = $derived.by<LiveStatusCounts>(() => {
	const liveSessions = data.liveSessions.filter(
		(s) => s.status !== 'ended' || shouldShowEndedStatus(s.updated_at)
	);
	return {
		total: liveSessions.length,
		starting: liveSessions.filter((s) => s.status === 'starting').length,
		active: liveSessions.filter((s) => s.status === 'active').length
		// ... identical for all statuses
	};
});
```

---

## Architectural Differences

### Filtering Strategy

| Aspect                | Project Page         | Sessions Page                    |
| --------------------- | -------------------- | -------------------------------- |
| Primary Strategy      | Client-side only     | Hybrid (server + client)         |
| Data Loading          | All sessions upfront | Paginated from server            |
| Pagination            | None                 | Server-side with limit/offset    |
| When Pagination Works | N/A                  | Only without client-side filters |

### Filter Persistence

| Filter Type           | Project Page      | Sessions Page             |
| --------------------- | ----------------- | ------------------------- |
| Search query          | Not in URL        | Not in URL                |
| Scope                 | Not in URL        | Not in URL                |
| Status                | Not in URL        | Not in URL                |
| Date range            | Not in URL        | In URL (start_ts, end_ts) |
| Project               | N/A               | In URL                    |
| Branch                | Not in URL        | In URL                    |
| Analytics time filter | In URL (separate) | N/A                       |

### Branch Filtering

| Aspect       | Project Page             | Sessions Page          |
| ------------ | ------------------------ | ---------------------- |
| UI Element   | Multi-select badge chips | Single-select dropdown |
| State Type   | `Set<string>`            | `string`               |
| Filter Logic | OR (any selected branch) | Exact match            |
| Clear Action | "Clear branches" button  | "All Branches" option  |

### Live Session Data Sources

| Aspect            | Project Page                    | Sessions Page                                       |
| ----------------- | ------------------------------- | --------------------------------------------------- |
| Polling Endpoint  | `/live-sessions/project/{name}` | `/live-sessions/active`                             |
| Polling Interval  | 2 seconds                       | Via LiveSessionsSection component                   |
| Data Storage      | `liveSessionsMap` (Map)         | `data.liveSessions` (Array) + `currentLiveSessions` |
| Matching Strategy | UUID lookup only                | Slug-first, then UUID                               |

---

## Behavioral Differences

### Status Filter: "Live" Behavior

**Project Page**:

- Filters `filteredSessions` to only show sessions with active live status
- Applies `selectedLiveSubStatuses` filter
- Still shows historical session cards (with live badge)

**Sessions Page**:

- Sets `sessions = []` when status is "live"
- Relies entirely on `LiveSessionsSection` component
- No historical session cards shown

### Deduplication Strategy

**Project Page**:

```typescript
// Excludes recently ended from main list
const recentlyEndedUuids = new Set(recentlyEndedSessions.map((pair) => pair.session.uuid));
sessions = sessions.filter((s) => !recentlyEndedUuids.has(s.uuid));
```

**Sessions Page**:

```typescript
// Excludes live sessions from historical list
const liveSessionIdentifiers = $derived.by(() => {
	const identifiers = new Set<string>();
	for (const ls of currentLiveSessions) {
		if (ls.status !== 'ended') {
			if (ls.slug) identifiers.add(ls.slug);
			if (ls.session_id) identifiers.add(ls.session_id);
		}
	}
	return identifiers;
});

const historicalSessions = $derived(
	data.sessions.filter((session) => {
		if (session.slug && liveSessionIdentifiers.has(session.slug)) return false;
		if (liveSessionIdentifiers.has(session.uuid)) return false;
		return true;
	})
);
```

---

## Count Display Differences

### Project Page

**Location**: Line 684-686

```svelte
<span class="text-xs text-[var(--text-muted)] font-mono">
	{filteredSessions.length} of {project.sessions?.length ?? 0} sessions
</span>
```

- Shows: filtered count / total count
- No pagination info

### Sessions Page

**Location**: Lines 1294-1307

```svelte
{#if hasClientSideFilters}
	Showing <span>{effectiveTotal.toLocaleString()}</span> filtered sessions
{:else}
	Showing <span>{showingStart}</span> - <span>{showingEnd}</span>
	of <span>{effectiveTotal.toLocaleString()}</span> sessions
{/if}
```

- Shows: range / total (when paginated)
- Shows: filtered count (when client filters active)

---

## API Filter Parameters

### `/sessions/all` Endpoint Parameters

| Parameter  | Type          | Default | Description                                   |
| ---------- | ------------- | ------- | --------------------------------------------- |
| `search`   | string        | null    | Text search term                              |
| `project`  | string        | null    | Project encoded name                          |
| `branch`   | string        | null    | Git branch name                               |
| `scope`    | SearchScope   | BOTH    | Search scope (BOTH, TITLES, PROMPTS)          |
| `status`   | SessionStatus | ALL     | Status filter (ALL, ACTIVE, COMPLETED, ERROR) |
| `start_ts` | int           | null    | Unix timestamp (ms) - start                   |
| `end_ts`   | int           | null    | Unix timestamp (ms) - end                     |
| `limit`    | int           | 200     | Page size                                     |
| `offset`   | int           | 0       | Pagination offset                             |

### `/projects/{encoded_name}` Endpoint Parameters

| Parameter | Type | Default | Description            |
| --------- | ---- | ------- | ---------------------- |
| `limit`   | int  | null    | Optional session limit |

**Note**: No filtering parameters available on project endpoint.

---

## Session Metadata Differences

### Project Page Session Object

**Type**: `SessionSummary` (from project.sessions)

```typescript
interface SessionSummary {
	uuid: string;
	slug: string | null;
	message_count: number;
	start_time: string;
	end_time: string | null;
	duration_seconds: number | null;
	models_used: string[];
	subagent_count: number;
	has_todos: boolean;
	initial_prompt: string | null;
	git_branches: string[];
	session_titles: string[];
	// ... additional fields
}
```

### Sessions Page Session Object

**Type**: `SessionWithContext` (from /sessions/all)

```typescript
interface SessionWithContext {
	uuid: string;
	slug: string | null;
	project_encoded_name: string;
	project_path: string;
	project_name: string;
	message_count: number;
	start_time: string;
	end_time: string | null;
	duration_seconds: number | null;
	models_used: string[]; // Often empty (optimization)
	subagent_count: number; // Often 0 (optimization)
	has_todos: boolean; // Often false (optimization)
	initial_prompt: string | null;
	git_branches: string[];
	session_titles: string[];
}
```

**Note**: `SessionWithContext` includes project context but may have less complete data due to optimization (avoiding full JSONL parsing).

---

## Summary of Duplicated Code

| Category               | Approximate Lines | Files Affected   |
| ---------------------- | ----------------- | ---------------- |
| Search query filtering | ~30 lines × 2     | Both route files |
| Scope-based filtering  | ~20 lines × 2     | Both route files |
| Status filtering       | ~15 lines × 2     | Both route files |
| Date range filtering   | ~15 lines × 2     | Both route files |
| Live session lookup    | ~10 lines × 2     | Both route files |
| Recently ended logic   | ~55 lines × 2     | Both route files |
| Live status counts     | ~20 lines × 2     | Both route files |
| Event handlers         | ~100 lines × 2    | Both route files |
| State declarations     | ~15 lines × 2     | Both route files |
| **Total Estimated**    | **~560 lines**    | 2 files          |

---

## File Reference

### Frontend Files

| File                                                 | Lines           | Purpose                      |
| ---------------------------------------------------- | --------------- | ---------------------------- |
| `src/routes/projects/[encoded_name]/+page.svelte`    | 1,086           | Project detail with sessions |
| `src/routes/projects/[encoded_name]/+page.server.ts` | 94              | Project data loader          |
| `src/routes/sessions/+page.svelte`                   | 1,374           | Global sessions view         |
| `src/routes/sessions/+page.server.ts`                | 96              | Sessions data loader         |
| `src/lib/search.ts`                                  | 329             | Shared filter utilities      |
| `src/lib/api-types.ts`                               | ~150 (relevant) | Type definitions             |
| `src/lib/components/FiltersDropdown.svelte`          | 409             | Filter panel component       |
| `src/lib/components/SessionSearchBar.svelte`         | 190             | Search input component       |
| `src/lib/components/ActiveFilterChips.svelte`        | 89              | Filter chips component       |

### API Files

| File                          | Lines  | Purpose             |
| ----------------------------- | ------ | ------------------- |
| `api/routers/sessions.py`     | 1,779  | Sessions endpoints  |
| `api/routers/projects.py`     | 325    | Projects endpoints  |
| `api/models/project.py`       | 564    | Project model       |
| `api/models/session.py`       | ~500   | Session model       |
| `api/models/session_index.py` | 114    | Session index model |
| `api/schemas.py`              | ~1,000 | Response schemas    |

---

_Document generated from codebase analysis on feature/session-search branch_

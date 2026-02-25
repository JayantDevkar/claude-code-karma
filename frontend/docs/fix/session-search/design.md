# Session Search UX Unification Design Doc

> **Branch**: `feature/session-search`
> **Date**: 2026-01-30
> **Status**: Draft

---

## 1. Overview

The session filtering/search feature was implemented across two views:

| View                 | Route                      | Purpose                          |
| -------------------- | -------------------------- | -------------------------------- |
| **Project Sessions** | `/projects/[encoded_name]` | Sessions within a single project |
| **Global Sessions**  | `/sessions`                | Sessions across all projects     |

This document analyzes UI/UX consistency between these views and provides recommendations for unification.

---

## 2. Current Architecture

### 2.1 Shared Components

Both pages correctly reuse these components:

```
src/lib/components/
├── SessionSearchBar.svelte      # Search input + filter toggle
├── FiltersDropdown.svelte       # Desktop filter panel
├── FiltersBottomSheet.svelte    # Mobile filter sheet
├── ActiveFilterChips.svelte     # Active filter badges
└── LiveSessionsSection.svelte   # Live sessions display
```

### 2.2 Page-Specific Components

| Component                  | Used In       | Purpose                    |
| -------------------------- | ------------- | -------------------------- |
| `SessionCard.svelte`       | Project page  | Card without project name  |
| `GlobalSessionCard.svelte` | Sessions page | Card with project + branch |
| `ActiveBranches.svelte`    | Project page  | Multi-select branch chips  |

### 2.3 Shared Utilities

```
src/lib/
├── search.ts              # Filter state, chips, date calculations
├── api-types.ts           # TypeScript interfaces
└── live-session-config.ts # Status colors & 45-min timeout
```

---

## 3. Observations

### 3.1 Consistency Strengths

| Aspect                   | Status        | Notes                          |
| ------------------------ | ------------- | ------------------------------ |
| Filter dropdown layout   | ✅ Consistent | Same sections, same order      |
| Filter chip styling      | ✅ Consistent | Same accent colors, pill shape |
| Live status indicators   | ✅ Consistent | Same colors, pulse animations  |
| "Recently Ended" section | ✅ Consistent | Same header, same 45-min logic |
| Mobile bottom sheet      | ✅ Consistent | Same layout, slide-up behavior |
| Keyboard shortcuts       | ✅ Consistent | Cmd+K focuses search on both   |

### 3.2 Inconsistencies Found

#### 3.2.1 Branch Filter Pattern

**Project Page** (`/projects/[encoded_name]`):

- Uses `ActiveBranches` component
- Multi-select checkbox chips inline below search
- OR logic: shows sessions matching ANY selected branch
- Visual: Interactive badges with pulse indicators for active branches

**Sessions Page** (`/sessions`):

- Uses custom dropdown button
- Single-select only
- Only appears when a project is selected
- Visual: Standard dropdown with chevron

```svelte
<!-- Project page: Multi-select chips -->
{#each [...selectedBranchFilters] as branch}
	<button onclick={() => handleBranchToggle(branch)}>
		<GitBranch size={10} />
		{branch}
		<X size={10} />
	</button>
{/each}

<!-- Sessions page: Single-select dropdown -->
<button onclick={() => (showBranchDropdown = !showBranchDropdown)}>
	<GitBranch size={12} />
	<span>Branch:</span>
	<span>{selectedBranch || 'All'}</span>
	<ChevronDown size={12} />
</button>
```

**Impact**: Users experience different interaction patterns for the same conceptual filter.

---

#### 3.2.2 Session Grouping

**Project Page**:

- Flat grid, no time-based grouping
- Sessions sorted by `start_time` descending
- Single grid: `grid-cols-1 md:grid-cols-2 lg:grid-cols-3`

**Sessions Page**:

- Time-based grouping: Today → Yesterday → This Week → This Month → Older
- View toggle: List (grouped) vs Grid (flat, 4 columns)
- Group headers with session counts

```svelte
<!-- Sessions page only -->
{#each groupedByDate as group}
  <h2>{group.label} ({group.sessions.length})</h2>
  <div class="grid ...">
    {#each group.sessions as session}
```

**Impact**: Different mental models for browsing sessions.

---

#### 3.2.3 Search Placeholder Text

```
Project:  "Search by title, prompt, slug, or ID..."
Sessions: "Search sessions..."
```

**Impact**: Minor, but the project page provides better guidance.

---

#### 3.2.4 Grid Spacing

| Page     | Recently Ended | Main Grid |
| -------- | -------------- | --------- |
| Project  | `gap-4`        | `gap-4`   |
| Sessions | `gap-3`        | `gap-3`   |

**Impact**: Subtle visual density difference.

---

#### 3.2.5 Section Header Semantics

| Page     | Recently Ended Header | Main Section Header |
| -------- | --------------------- | ------------------- |
| Project  | `<h3>`                | None                |
| Sessions | `<h2>`                | `<h2>`              |

**Impact**: Accessibility/semantic inconsistency.

---

#### 3.2.6 View Mode Toggle

**Project Page**: No view toggle (always grid)

**Sessions Page**: List/Grid toggle with localStorage persistence

```svelte
<!-- Sessions page only -->
<div class="flex items-center gap-1 p-0.5 bg-[var(--bg-muted)] rounded-[6px]">
	<button class={viewMode === 'list' ? 'active' : ''}>
		<LayoutList size={14} />
	</button>
	<button class={viewMode === 'grid' ? 'active' : ''}>
		<LayoutGrid size={14} />
	</button>
</div>
```

---

#### 3.2.7 Filter Chip Layout Flow

**Project Page**:

```
[Search Bar] [Filters Button]
[ActiveFilterChips: scope, status, date]
[Branch Chips: feature/x, main, ...]  ← Separate row
```

**Sessions Page**:

```
[Search Bar] [Filters] [Project ▾] [Branch ▾] [View Toggle] [Clear]
[ActiveFilterChips: scope, status, date]
[Project/Branch Badges]  ← Only when selected
```

---

#### 3.2.8 Card Content Differences

| Field        | `SessionCard`                      | `GlobalSessionCard`          |
| ------------ | ---------------------------------- | ---------------------------- |
| Project name | ❌ Not shown                       | ✅ Shown with folder icon    |
| Branch       | ✅ Conditional (`showBranch` prop) | ✅ Always shown if available |
| Chain info   | ✅ Uses UUID for chain sessions    | ❌ Not handled               |
| Compact mode | ❌ Not supported                   | ✅ Supported for grid view   |

---

## 4. Recommendations

### 4.1 Priority 1: Quick Fixes (Low Effort)

#### 4.1.1 Unify Search Placeholder

**Change**: Use descriptive placeholder on both pages.

```diff
// SessionSearchBar.svelte or page-level override
- placeholder="Search sessions..."
+ placeholder="Search by title, prompt, slug, or ID..."
```

**Files**:

- `src/routes/sessions/+page.svelte` (line ~903)

---

#### 4.1.2 Unify Grid Gap

**Change**: Standardize on `gap-3` for tighter, more modern feel.

```diff
// Project page
- <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
+ <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
```

**Files**:

- `src/routes/projects/[encoded_name]/+page.svelte` (lines ~797, ~812)

---

#### 4.1.3 Unify Section Header Semantics

**Change**: Use `<h2>` consistently for major sections.

```diff
// Project page Recently Ended
- <h3 class="text-sm font-semibold uppercase tracking-wide">
+ <h2 class="text-sm font-semibold uppercase tracking-wide">
```

**Files**:

- `src/routes/projects/[encoded_name]/+page.svelte` (line ~782)

---

### 4.2 Priority 2: Medium Effort

#### 4.2.1 Add View Toggle to Project Page

**Rationale**: Users who work on one project frequently may want the same grouping options.

**Implementation**:

1. Add `viewMode` state with localStorage persistence
2. Add view toggle button group (copy from sessions page)
3. Add time-based grouping logic (copy `groupedByDate` derived)
4. Conditionally render grouped or flat view

**Scope**: ~50 lines of code, mostly copy-paste from sessions page.

---

#### 4.2.2 Add Page Context Indicator

**Rationale**: Users should instantly know which view they're in.

**Design Options**:

**Option A: Header Badge**

```svelte
<PageHeader title="Sessions">
	<Badge slot="badge" variant="subtle">All Projects</Badge>
</PageHeader>

<PageHeader title={project.name}>
	<Badge slot="badge" variant="subtle">Project View</Badge>
</PageHeader>
```

**Option B: Breadcrumb Enhancement**

```
Sessions / All Projects
Projects / my-project / Sessions
```

**Option C: Subtle Background Tint**

- Project page: Slight tint matching project's primary color
- Sessions page: Neutral background

**Recommendation**: Option A (Header Badge) is clearest and easiest to implement.

---

#### 4.2.3 Unify Branch Filter Interaction

**Recommendation**: Keep different patterns but explain why:

- **Project page**: Multi-select makes sense (you're deep in one project, want to compare branches)
- **Sessions page**: Single-select makes sense (cross-project context, branch names may collide)

**Enhancement**: When sessions page has a project selected, consider switching to multi-select chips to match project page experience.

---

### 4.3 Priority 3: Larger Refactors

#### 4.3.1 Create Unified `FilterBar` Component

**Rationale**: Reduce duplication, ensure future consistency.

```svelte
<!-- Proposed: FilterBar.svelte -->
<script lang="ts">
	interface Props {
		// Core filters (always present)
		filters: SearchFilters;
		onFiltersChange: (filters: SearchFilters) => void;

		// Optional: Project filter (sessions page only)
		projectFilter?: string;
		onProjectChange?: (project: string | null) => void;
		projects?: ProjectOption[];

		// Optional: Branch filter
		branchFilter?: string | Set<string>;
		onBranchChange?: (branch: string | Set<string>) => void;
		branches?: string[];
		branchMode?: 'single' | 'multi';

		// Optional: View toggle
		viewMode?: 'list' | 'grid';
		onViewModeChange?: (mode: 'list' | 'grid') => void;
		showViewToggle?: boolean;

		// Counts for display
		totalCount: number;
		filteredCount: number;
		liveStatusCounts?: LiveStatusCounts;
	}
</script>

<div class="flex flex-col gap-2">
	<div class="flex flex-wrap items-center gap-2">
		<SessionSearchBar ... />
		{#if projects}
			<ProjectDropdown ... />
		{/if}
		{#if branches}
			{#if branchMode === 'multi'}
				<BranchChips ... />
			{:else}
				<BranchDropdown ... />
			{/if}
		{/if}
		{#if showViewToggle}
			<ViewToggle ... />
		{/if}
	</div>
	<ActiveFilterChips ... />
</div>
```

**Benefits**:

- Single source of truth for filter bar layout
- Automatic consistency for new filter options
- Easier testing

**Effort**: ~200-300 lines, 1-2 days

---

#### 4.3.2 Merge SessionCard and GlobalSessionCard

**Rationale**: 90% identical code, diverging maintenance paths.

```svelte
<!-- Proposed: UnifiedSessionCard.svelte -->
<script lang="ts">
	interface Props {
		session: Session | SessionWithContext;
		liveSession?: LiveSessionSummary | null;

		// Display options
		showProject?: boolean; // true for global view
		showBranch?: boolean; // configurable
		compact?: boolean; // grid view mode

		// Navigation context
		projectEncodedName?: string; // required if showProject=false
	}
</script>
```

**Migration Path**:

1. Create `UnifiedSessionCard.svelte`
2. Update sessions page to use it
3. Update project page to use it
4. Delete `SessionCard.svelte` and `GlobalSessionCard.svelte`

**Effort**: ~100 lines refactor, half day

---

## 5. Implementation Order

```
Phase 1: Quick Fixes (PR #1)
├── Unify search placeholder
├── Unify grid gap to gap-3
└── Unify section header to <h2>

Phase 2: View Parity (PR #2)
├── Add view toggle to project page
├── Add time-based grouping to project page
└── Add page context badge to headers

Phase 3: Component Unification (PR #3)
├── Create FilterBar component
├── Migrate both pages to use it
└── Create UnifiedSessionCard component

Phase 4: Polish (PR #4)
├── Ensure same filters = same results (add tests)
├── Add URL state persistence to project page filters
└── Documentation updates
```

---

## 6. Testing Checklist

### 6.1 Filter Result Parity

For each filter combination, verify both pages show equivalent sessions:

- [ ] Status: All → same sessions (within project scope)
- [ ] Status: Live → same live sessions
- [ ] Status: Completed → same completed sessions
- [ ] Status: Live + specific sub-statuses → same filtered live sessions
- [ ] Date: Today → same sessions started today
- [ ] Date: 7d → same sessions from past week
- [ ] Date: 30d → same sessions from past month
- [ ] Scope: Titles only → search matches only titles
- [ ] Scope: Prompts only → search matches only prompts
- [ ] Combined filters → intersection works correctly

### 6.2 Visual Consistency

- [ ] Filter chips look identical on both pages
- [ ] Session cards have same spacing, borders, colors
- [ ] Recently Ended section is visually identical
- [ ] Mobile bottom sheet works identically
- [ ] Keyboard navigation (Cmd+K, Escape) works identically

### 6.3 Edge Cases

- [ ] Empty states match when no results
- [ ] Loading states match during data fetch
- [ ] Error states match when API fails
- [ ] Pagination doesn't break filter consistency

---

## 7. Open Questions

1. **Should project page persist filters to URL?**
    - Currently: No (local state only)
    - Sessions page: Yes (URL params)
    - Recommendation: Yes, for shareable links

2. **Should we add time grouping to project page by default or as opt-in?**
    - Default: Matches sessions page experience
    - Opt-in: Preserves existing UX for current users

3. **Multi-select branch on sessions page when project is selected?**
    - Yes: Consistent with project page
    - No: Keep it simple, single-select is clearer for cross-project

---

## 8. Appendix: File References

### Key Files to Modify

| File                                              | Lines | Changes Needed                        |
| ------------------------------------------------- | ----- | ------------------------------------- |
| `src/routes/projects/[encoded_name]/+page.svelte` | ~1086 | Placeholder, gap, header, view toggle |
| `src/routes/sessions/+page.svelte`                | ~1374 | Placeholder only (reference for copy) |
| `src/lib/components/SessionSearchBar.svelte`      | ~190  | Optional: default placeholder prop    |
| `src/lib/components/SessionCard.svelte`           | ~250  | Future: merge with GlobalSessionCard  |
| `src/lib/components/GlobalSessionCard.svelte`     | ~279  | Future: merge with SessionCard        |

### New Files to Create

| File                                           | Purpose                    |
| ---------------------------------------------- | -------------------------- |
| `src/lib/components/FilterBar.svelte`          | Unified filter bar wrapper |
| `src/lib/components/UnifiedSessionCard.svelte` | Merged session card        |
| `src/lib/components/ViewToggle.svelte`         | Extracted view mode toggle |
| `src/lib/components/PageContextBadge.svelte`   | Page identity indicator    |

---

_Document authored during feature/session-search branch review._

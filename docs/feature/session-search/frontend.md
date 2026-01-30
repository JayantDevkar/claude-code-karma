# Session Search - Frontend Implementation Tasks

**Feature:** Session Search with Filters
**Module:** `frontend/` submodule
**Related Design:** `docs/design/session-search-feature.md`

---

## Overview

Implement a unified session search component with:
- Single search input (searches titles + prompts by default)
- Filter dropdown with search scope, status, and date range options
- Active filter chips with individual remove buttons
- Auto-apply filtering (no submit button)
- URL persistence for shareable filtered views

---

## Current Implementation Analysis

### Existing Search (Project Page)
**File:** `frontend/src/routes/projects/[encoded_name]/+page.svelte:479-496`

```svelte
<div class="relative max-w-sm">
  <div class="absolute left-3 top-1/2 -translate-y-1/2 text-[var(--text-muted)]">
    <Search size={14} />
  </div>
  <input
    type="text"
    bind:value={searchQuery}
    placeholder="Search by prompt, slug, or ID..."
    class="w-full pl-9 pr-3 py-2 text-xs ..."
  />
</div>
```

### Components to Reuse

| Component | Location | Use Case |
|-----------|----------|----------|
| `TextInput` | `src/lib/components/ui/TextInput.svelte` | Base input styling |
| `Badge` | `src/lib/components/ui/Badge.svelte` | Filter chips |
| `EmptyState` | `src/lib/components/ui/EmptyState.svelte` | No results state |
| `TimeFilterDropdown` | `src/lib/components/TimeFilterDropdown.svelte` | Dropdown pattern |
| `ActiveBranches` | `src/lib/components/ActiveBranches.svelte` | Toggle chip pattern |

### Design System Tokens
**File:** `frontend/src/app.css`

```css
/* Key tokens to use */
--bg-base, --bg-subtle, --bg-muted
--text-primary, --text-secondary, --text-muted
--accent, --accent-subtle
--border, --border-hover
--radius-md, --radius-lg
--spacing-2, --spacing-3, --spacing-4
--duration-fast: 150ms
```

### State Management Patterns

```svelte
<!-- Svelte 5 Runes -->
let searchQuery = $state('');
let selectedFilters = $state<FilterState>({...});

let filteredSessions = $derived.by(() => {
  return sessions.filter(s => matchesFilters(s, selectedFilters));
});

$effect(() => {
  // Sync state to URL
  updateUrlParams(selectedFilters);
});
```

---

## Implementation Tasks

### Task 1: Create SessionSearchBar Component

**Goal:** Unified search bar with filter dropdown trigger

**File:** `frontend/src/lib/components/SessionSearchBar.svelte`

```svelte
<script lang="ts">
  import { Search, X, SlidersHorizontal, ChevronDown } from 'lucide-svelte';

  interface Props {
    searchQuery: string;
    onSearchChange: (query: string) => void;
    showFiltersDropdown: boolean;
    onToggleFilters: () => void;
    hasActiveFilters: boolean;
  }

  let {
    searchQuery = $bindable(''),
    onSearchChange,
    showFiltersDropdown,
    onToggleFilters,
    hasActiveFilters
  }: Props = $props();

  function handleClear() {
    searchQuery = '';
    onSearchChange('');
  }

  function handleInput(e: Event) {
    const value = (e.target as HTMLInputElement).value;
    searchQuery = value;
    onSearchChange(value);
  }
</script>

<div class="flex items-center gap-2">
  <!-- Search Input -->
  <div class="relative flex-1 max-w-md">
    <div class="absolute left-3 top-1/2 -translate-y-1/2 text-[var(--text-muted)]">
      <Search size={14} />
    </div>
    <input
      type="text"
      value={searchQuery}
      oninput={handleInput}
      placeholder="Search by title or prompt..."
      class="
        w-full pl-9 pr-8 py-2 text-sm
        bg-[var(--bg-base)] border border-[var(--border)]
        rounded-[var(--radius-md)]
        focus:outline-none focus:ring-2 focus:ring-[var(--accent)] focus:ring-offset-1
        transition-shadow placeholder:text-[var(--text-faint)]
      "
    />
    {#if searchQuery}
      <button
        onclick={handleClear}
        class="absolute right-3 top-1/2 -translate-y-1/2 text-[var(--text-muted)] hover:text-[var(--text-primary)]"
        aria-label="Clear search"
      >
        <X size={14} />
      </button>
    {/if}
  </div>

  <!-- Filters Button -->
  <button
    onclick={onToggleFilters}
    class="
      flex items-center gap-2 px-3 py-2
      bg-[var(--bg-base)] border border-[var(--border)]
      rounded-[var(--radius-md)]
      hover:border-[var(--border-hover)] hover:bg-[var(--bg-subtle)]
      transition-colors text-sm
      {hasActiveFilters ? 'border-[var(--accent)] text-[var(--accent)]' : 'text-[var(--text-secondary)]'}
    "
    aria-expanded={showFiltersDropdown}
  >
    <SlidersHorizontal size={14} />
    <span class="hidden sm:inline">Filters</span>
    {#if hasActiveFilters}
      <span class="w-1.5 h-1.5 rounded-full bg-[var(--accent)]"></span>
    {/if}
    <ChevronDown
      size={14}
      class="transition-transform {showFiltersDropdown ? 'rotate-180' : ''}"
    />
  </button>
</div>
```

**Key Features:**
- Search icon on left
- Clear button appears when text entered
- Filters button with active indicator
- Chevron rotates when dropdown open
- Responsive: hides "Filters" label on mobile

---

### Task 2: Create FiltersDropdown Component

**Goal:** Dropdown panel with all filter options

**File:** `frontend/src/lib/components/FiltersDropdown.svelte`

```svelte
<script lang="ts">
  import { Check } from 'lucide-svelte';
  import { onMount, onDestroy } from 'svelte';

  type SearchScope = 'both' | 'titles' | 'prompts';
  type SessionStatus = 'all' | 'active' | 'completed' | 'error';
  type DateRange = 'all' | 'today' | '7d' | '30d' | 'custom';

  interface Props {
    searchScope: SearchScope;
    onScopeChange: (scope: SearchScope) => void;
    status: SessionStatus;
    onStatusChange: (status: SessionStatus) => void;
    dateRange: DateRange;
    onDateRangeChange: (range: DateRange) => void;
    onReset: () => void;
    onClose: () => void;
  }

  let {
    searchScope, onScopeChange,
    status, onStatusChange,
    dateRange, onDateRangeChange,
    onReset, onClose
  }: Props = $props();

  let dropdownRef: HTMLDivElement;

  function handleClickOutside(event: MouseEvent) {
    if (dropdownRef && !dropdownRef.contains(event.target as Node)) {
      onClose();
    }
  }

  onMount(() => {
    document.addEventListener('click', handleClickOutside, true);
  });

  onDestroy(() => {
    document.removeEventListener('click', handleClickOutside, true);
  });

  const scopeOptions: { value: SearchScope; label: string }[] = [
    { value: 'both', label: 'Titles & Prompts' },
    { value: 'titles', label: 'Titles only' },
    { value: 'prompts', label: 'Prompts only' },
  ];

  const statusOptions: { value: SessionStatus; label: string; color?: string }[] = [
    { value: 'all', label: 'All' },
    { value: 'active', label: 'Active', color: 'var(--success)' },
    { value: 'completed', label: 'Completed', color: 'var(--text-muted)' },
    { value: 'error', label: 'Error', color: 'var(--error)' },
  ];

  const dateOptions: { value: DateRange; label: string }[] = [
    { value: 'all', label: 'All time' },
    { value: 'today', label: 'Today' },
    { value: '7d', label: 'Last 7 days' },
    { value: '30d', label: 'Last 30 days' },
    { value: 'custom', label: 'Custom range...' },
  ];
</script>

<div
  bind:this={dropdownRef}
  class="
    absolute right-0 top-full mt-2 w-72
    bg-[var(--bg-base)] border border-[var(--border)]
    rounded-[var(--radius-lg)] shadow-lg z-50
    overflow-hidden
  "
>
  <!-- Search Scope -->
  <div class="p-3 border-b border-[var(--border)]">
    <div class="text-[10px] uppercase tracking-wider text-[var(--text-muted)] mb-2">
      Search in
    </div>
    <div class="flex gap-1">
      {#each scopeOptions as option}
        <button
          onclick={() => onScopeChange(option.value)}
          class="
            flex-1 px-2 py-1.5 text-xs rounded-[var(--radius-sm)]
            transition-colors
            {searchScope === option.value
              ? 'bg-[var(--accent)] text-white'
              : 'bg-[var(--bg-muted)] text-[var(--text-secondary)] hover:bg-[var(--bg-subtle)]'}
          "
        >
          {option.label}
        </button>
      {/each}
    </div>
  </div>

  <!-- Status Filter -->
  <div class="p-3 border-b border-[var(--border)]">
    <div class="text-[10px] uppercase tracking-wider text-[var(--text-muted)] mb-2">
      Status
    </div>
    <div class="flex flex-wrap gap-1.5">
      {#each statusOptions as option}
        <button
          onclick={() => onStatusChange(option.value)}
          class="
            inline-flex items-center gap-1.5 px-2.5 py-1.5 text-xs
            rounded-[var(--radius-md)] border transition-colors
            {status === option.value
              ? 'bg-[var(--accent-subtle)] border-[var(--accent)] text-[var(--accent)]'
              : 'bg-[var(--bg-base)] border-[var(--border)] text-[var(--text-secondary)] hover:border-[var(--border-hover)]'}
          "
        >
          {#if option.color && status === option.value}
            <span
              class="w-1.5 h-1.5 rounded-full"
              style="background-color: {option.color}"
            ></span>
          {/if}
          {option.label}
        </button>
      {/each}
    </div>
  </div>

  <!-- Date Range -->
  <div class="p-3 border-b border-[var(--border)]">
    <div class="text-[10px] uppercase tracking-wider text-[var(--text-muted)] mb-2">
      Date range
    </div>
    <div class="space-y-0.5">
      {#each dateOptions as option}
        <button
          onclick={() => onDateRangeChange(option.value)}
          class="
            w-full flex items-center justify-between px-2 py-1.5 text-xs
            rounded-[var(--radius-sm)] transition-colors
            {dateRange === option.value
              ? 'bg-[var(--bg-muted)] text-[var(--text-primary)]'
              : 'text-[var(--text-secondary)] hover:bg-[var(--bg-subtle)]'}
          "
        >
          <span>{option.label}</span>
          {#if dateRange === option.value}
            <Check size={12} class="text-[var(--accent)]" />
          {/if}
        </button>
      {/each}
    </div>
  </div>

  <!-- Reset -->
  <div class="p-3">
    <button
      onclick={onReset}
      class="w-full px-3 py-1.5 text-xs text-[var(--text-muted)] hover:text-[var(--text-primary)] transition-colors"
    >
      Reset all filters
    </button>
  </div>
</div>
```

**Key Features:**
- Click-outside-to-close behavior
- Segmented button for search scope
- Chip-style buttons for status
- List with checkmarks for date range
- Reset all button at bottom

---

### Task 3: Create ActiveFilterChips Component

**Goal:** Display active filters as removable chips

**File:** `frontend/src/lib/components/ActiveFilterChips.svelte`

```svelte
<script lang="ts">
  import { X } from 'lucide-svelte';
  import Badge from '$lib/components/ui/Badge.svelte';

  interface FilterChip {
    key: string;
    label: string;
    value: string;
  }

  interface Props {
    chips: FilterChip[];
    onRemove: (key: string) => void;
    onClearAll: () => void;
    totalCount: number;
    filteredCount: number;
  }

  let { chips, onRemove, onClearAll, totalCount, filteredCount }: Props = $props();

  let hasActiveFilters = $derived(chips.length > 0);
</script>

{#if hasActiveFilters}
  <div class="flex flex-wrap items-center gap-2">
    <!-- Filter Chips -->
    {#each chips as chip}
      <button
        onclick={() => onRemove(chip.key)}
        class="
          inline-flex items-center gap-1.5 px-2.5 py-1
          bg-[var(--accent-subtle)] text-[var(--accent)]
          rounded-full text-xs font-medium
          hover:bg-[var(--accent)]/20 transition-colors
          group
        "
      >
        <span class="text-[var(--text-muted)]">{chip.label}:</span>
        <span>{chip.value}</span>
        <X size={12} class="opacity-60 group-hover:opacity-100" />
      </button>
    {/each}

    <!-- Count & Clear -->
    <div class="flex items-center gap-3 ml-auto text-xs text-[var(--text-muted)]">
      <span>
        {filteredCount} of {totalCount} sessions
      </span>
      <button
        onclick={onClearAll}
        class="hover:text-[var(--text-primary)] transition-colors"
      >
        Clear all
      </button>
    </div>
  </div>
{/if}
```

**Key Features:**
- Rounded pill-style chips
- Label:value format
- Remove button on each chip
- Session count indicator
- Clear all link

---

### Task 4: Create Types and Utilities

**Goal:** TypeScript types and filter utility functions

**File:** `frontend/src/lib/types/search.ts`

```typescript
export type SearchScope = 'both' | 'titles' | 'prompts';
export type SessionStatus = 'all' | 'active' | 'completed' | 'error';
export type DateRange = 'all' | 'today' | '7d' | '30d' | 'custom';

export interface SearchFilters {
  query: string;
  scope: SearchScope;
  status: SessionStatus;
  dateRange: DateRange;
  customStart?: Date;
  customEnd?: Date;
}

export const DEFAULT_FILTERS: SearchFilters = {
  query: '',
  scope: 'both',
  status: 'all',
  dateRange: 'all',
};

export interface FilterChip {
  key: keyof SearchFilters;
  label: string;
  value: string;
}
```

**File:** `frontend/src/lib/utils/search.ts`

```typescript
import type { SearchFilters, FilterChip, DateRange } from '$lib/types/search';

/**
 * Convert filters to URL search params
 */
export function filtersToParams(filters: SearchFilters): URLSearchParams {
  const params = new URLSearchParams();

  if (filters.query) params.set('q', filters.query);
  if (filters.scope !== 'both') params.set('scope', filters.scope);
  if (filters.status !== 'all') params.set('status', filters.status);
  if (filters.dateRange !== 'all') params.set('range', filters.dateRange);
  if (filters.customStart) params.set('from', filters.customStart.toISOString().split('T')[0]);
  if (filters.customEnd) params.set('to', filters.customEnd.toISOString().split('T')[0]);

  return params;
}

/**
 * Parse URL search params to filters
 */
export function paramsToFilters(params: URLSearchParams): Partial<SearchFilters> {
  return {
    query: params.get('q') || '',
    scope: (params.get('scope') as SearchFilters['scope']) || 'both',
    status: (params.get('status') as SearchFilters['status']) || 'all',
    dateRange: (params.get('range') as SearchFilters['dateRange']) || 'all',
    customStart: params.get('from') ? new Date(params.get('from')!) : undefined,
    customEnd: params.get('to') ? new Date(params.get('to')!) : undefined,
  };
}

/**
 * Get active filter chips for display
 */
export function getFilterChips(filters: SearchFilters): FilterChip[] {
  const chips: FilterChip[] = [];

  if (filters.scope !== 'both') {
    chips.push({
      key: 'scope',
      label: 'Search',
      value: filters.scope === 'titles' ? 'Titles' : 'Prompts',
    });
  }

  if (filters.status !== 'all') {
    chips.push({
      key: 'status',
      label: 'Status',
      value: filters.status.charAt(0).toUpperCase() + filters.status.slice(1),
    });
  }

  if (filters.dateRange !== 'all') {
    const labels: Record<DateRange, string> = {
      all: 'All time',
      today: 'Today',
      '7d': 'Last 7 days',
      '30d': 'Last 30 days',
      custom: 'Custom',
    };
    chips.push({
      key: 'dateRange',
      label: 'Date',
      value: labels[filters.dateRange],
    });
  }

  return chips;
}

/**
 * Get date range timestamps for API call
 */
export function getDateRangeTimestamps(
  range: DateRange,
  customStart?: Date,
  customEnd?: Date
): { start_ts?: number; end_ts?: number } {
  const now = new Date();

  switch (range) {
    case 'today':
      const todayStart = new Date(now.getFullYear(), now.getMonth(), now.getDate());
      return { start_ts: todayStart.getTime() };

    case '7d':
      const weekAgo = new Date(now.getTime() - 7 * 24 * 60 * 60 * 1000);
      return { start_ts: weekAgo.getTime() };

    case '30d':
      const monthAgo = new Date(now.getTime() - 30 * 24 * 60 * 60 * 1000);
      return { start_ts: monthAgo.getTime() };

    case 'custom':
      return {
        start_ts: customStart?.getTime(),
        end_ts: customEnd?.getTime(),
      };

    default:
      return {};
  }
}
```

---

### Task 5: Integrate into Project Page

**Goal:** Replace existing search with new SessionSearchBar

**File:** `frontend/src/routes/projects/[encoded_name]/+page.svelte`

**Changes:**

1. Import new components:
```svelte
<script lang="ts">
  import SessionSearchBar from '$lib/components/SessionSearchBar.svelte';
  import FiltersDropdown from '$lib/components/FiltersDropdown.svelte';
  import ActiveFilterChips from '$lib/components/ActiveFilterChips.svelte';
  import {
    DEFAULT_FILTERS,
    filtersToParams,
    paramsToFilters,
    getFilterChips,
    getDateRangeTimestamps
  } from '$lib/utils/search';
  import type { SearchFilters } from '$lib/types/search';
</script>
```

2. Add state management:
```svelte
<script lang="ts">
  // Filter state
  let filters = $state<SearchFilters>({ ...DEFAULT_FILTERS });
  let showFiltersDropdown = $state(false);
  let searchTimeout: ReturnType<typeof setTimeout>;

  // Derived state
  let filterChips = $derived(getFilterChips(filters));
  let hasActiveFilters = $derived(
    filters.query !== '' ||
    filters.scope !== 'both' ||
    filters.status !== 'all' ||
    filters.dateRange !== 'all'
  );

  // Filtered sessions
  let filteredSessions = $derived.by(() => {
    let result = [...project.sessions];

    // Text search
    if (filters.query) {
      const q = filters.query.toLowerCase();
      result = result.filter(s => {
        const matchesTitle = filters.scope !== 'prompts' &&
          s.session_titles?.some(t => t.toLowerCase().includes(q));
        const matchesPrompt = filters.scope !== 'titles' &&
          s.initial_prompt?.toLowerCase().includes(q);
        const matchesSlug = s.slug?.toLowerCase().includes(q);
        return matchesTitle || matchesPrompt || matchesSlug;
      });
    }

    // Status filter
    if (filters.status !== 'all') {
      result = result.filter(s => {
        // Determine status based on end_time recency
        // This should match API logic
        return s.status === filters.status;
      });
    }

    // Date range filter
    const { start_ts, end_ts } = getDateRangeTimestamps(
      filters.dateRange,
      filters.customStart,
      filters.customEnd
    );
    if (start_ts) {
      result = result.filter(s =>
        s.start_time && new Date(s.start_time).getTime() >= start_ts
      );
    }
    if (end_ts) {
      result = result.filter(s =>
        s.start_time && new Date(s.start_time).getTime() <= end_ts
      );
    }

    // Branch filter (existing)
    if (selectedBranchFilters.size > 0) {
      result = result.filter(s =>
        s.git_branches?.some(b => selectedBranchFilters.has(b))
      );
    }

    // Sort by start_time descending
    return result.sort((a, b) =>
      new Date(b.start_time || 0).getTime() - new Date(a.start_time || 0).getTime()
    );
  });

  // Debounced search handler
  function handleSearchChange(query: string) {
    clearTimeout(searchTimeout);
    searchTimeout = setTimeout(() => {
      filters.query = query;
    }, 300);
  }

  // Filter handlers
  function handleScopeChange(scope: SearchFilters['scope']) {
    filters.scope = scope;
  }

  function handleStatusChange(status: SearchFilters['status']) {
    filters.status = status;
  }

  function handleDateRangeChange(range: SearchFilters['dateRange']) {
    filters.dateRange = range;
    // TODO: Open date picker modal if 'custom'
  }

  function handleRemoveFilter(key: keyof SearchFilters) {
    filters[key] = DEFAULT_FILTERS[key];
  }

  function handleClearAllFilters() {
    filters = { ...DEFAULT_FILTERS };
    selectedBranchFilters.clear();
  }

  // URL sync
  $effect(() => {
    if (!browser) return;
    const params = filtersToParams(filters);
    const url = new URL(window.location.href);
    url.search = params.toString();
    window.history.replaceState({}, '', url.toString());
  });
</script>
```

3. Replace search UI in template:
```svelte
<!-- Sessions Section -->
<div class="space-y-4">
  <div class="flex items-center justify-between">
    <h2 class="text-lg font-semibold text-[var(--text-primary)]">
      Sessions
    </h2>
  </div>

  <!-- Search & Filters -->
  <div class="relative">
    <SessionSearchBar
      bind:searchQuery={filters.query}
      onSearchChange={handleSearchChange}
      {showFiltersDropdown}
      onToggleFilters={() => showFiltersDropdown = !showFiltersDropdown}
      {hasActiveFilters}
    />

    {#if showFiltersDropdown}
      <FiltersDropdown
        searchScope={filters.scope}
        onScopeChange={handleScopeChange}
        status={filters.status}
        onStatusChange={handleStatusChange}
        dateRange={filters.dateRange}
        onDateRangeChange={handleDateRangeChange}
        onReset={handleClearAllFilters}
        onClose={() => showFiltersDropdown = false}
      />
    {/if}
  </div>

  <!-- Active Filters -->
  <ActiveFilterChips
    chips={filterChips}
    onRemove={handleRemoveFilter}
    onClearAll={handleClearAllFilters}
    totalCount={project.sessions.length}
    filteredCount={filteredSessions.length}
  />

  <!-- Branch Filters (existing) -->
  {#if project.is_git_repository && branchesData?.branches?.length > 0}
    <ActiveBranches ... />
  {/if}

  <!-- Sessions Grid -->
  {#if filteredSessions.length > 0}
    <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
      {#each filteredSessions as session}
        <SessionCard {session} />
      {/each}
    </div>
  {:else}
    <EmptyState
      icon={Search}
      title="No sessions found"
      description="Try adjusting your search or filters"
    >
      <button
        onclick={handleClearAllFilters}
        class="mt-4 px-4 py-2 text-sm bg-[var(--accent)] text-white rounded-[var(--radius-md)]"
      >
        Clear all filters
      </button>
    </EmptyState>
  {/if}
</div>
```

---

### Task 6: Add Keyboard Shortcuts

**Goal:** Support keyboard navigation and shortcuts

**File:** Update `SessionSearchBar.svelte`

```svelte
<script lang="ts">
  import { onMount } from 'svelte';

  let inputRef: HTMLInputElement;

  function handleKeydown(e: KeyboardEvent) {
    // Cmd/Ctrl + K to focus search
    if ((e.metaKey || e.ctrlKey) && e.key === 'k') {
      e.preventDefault();
      inputRef?.focus();
    }

    // Escape to clear and blur
    if (e.key === 'Escape' && document.activeElement === inputRef) {
      handleClear();
      inputRef?.blur();
    }
  }

  onMount(() => {
    document.addEventListener('keydown', handleKeydown);
    return () => document.removeEventListener('keydown', handleKeydown);
  });
</script>

<input bind:this={inputRef} ... />

<!-- Show keyboard hint -->
<div class="hidden sm:flex absolute right-12 top-1/2 -translate-y-1/2 items-center gap-0.5 text-[10px] text-[var(--text-faint)]">
  <kbd class="px-1 py-0.5 bg-[var(--bg-muted)] rounded text-[9px]">⌘</kbd>
  <kbd class="px-1 py-0.5 bg-[var(--bg-muted)] rounded text-[9px]">K</kbd>
</div>
```

---

### Task 7: Mobile Responsive Adaptations

**Goal:** Bottom sheet filters on mobile

**File:** Create `frontend/src/lib/components/FiltersBottomSheet.svelte`

```svelte
<script lang="ts">
  import { X } from 'lucide-svelte';
  import { fly } from 'svelte/transition';

  interface Props {
    open: boolean;
    onClose: () => void;
    children: import('svelte').Snippet;
  }

  let { open, onClose, children }: Props = $props();
</script>

{#if open}
  <!-- Backdrop -->
  <div
    class="fixed inset-0 bg-black/50 z-40"
    onclick={onClose}
    transition:fly={{ duration: 200 }}
  ></div>

  <!-- Sheet -->
  <div
    class="fixed bottom-0 left-0 right-0 z-50 bg-[var(--bg-base)] rounded-t-2xl max-h-[80vh] overflow-auto"
    transition:fly={{ y: 300, duration: 300 }}
  >
    <!-- Drag Handle -->
    <div class="flex justify-center py-3">
      <div class="w-10 h-1 bg-[var(--border)] rounded-full"></div>
    </div>

    <!-- Header -->
    <div class="flex items-center justify-between px-4 pb-3 border-b border-[var(--border)]">
      <h3 class="text-base font-semibold">Filters</h3>
      <button onclick={onClose} class="p-1">
        <X size={20} />
      </button>
    </div>

    <!-- Content -->
    <div class="p-4">
      {@render children()}
    </div>
  </div>
{/if}
```

**Update project page for mobile:**
```svelte
<script lang="ts">
  import { browser } from '$app/environment';

  let isMobile = $state(false);

  $effect(() => {
    if (browser) {
      const checkMobile = () => isMobile = window.innerWidth < 640;
      checkMobile();
      window.addEventListener('resize', checkMobile);
      return () => window.removeEventListener('resize', checkMobile);
    }
  });
</script>

{#if isMobile}
  <FiltersBottomSheet open={showFiltersDropdown} onClose={() => showFiltersDropdown = false}>
    <!-- Mobile filter content -->
  </FiltersBottomSheet>
{:else}
  <FiltersDropdown ... />
{/if}
```

---

## File Structure

```
frontend/src/lib/
├── components/
│   ├── SessionSearchBar.svelte      # NEW
│   ├── FiltersDropdown.svelte       # NEW
│   ├── ActiveFilterChips.svelte     # NEW
│   ├── FiltersBottomSheet.svelte    # NEW (mobile)
│   └── ui/
│       └── ... (existing)
├── types/
│   └── search.ts                    # NEW
└── utils/
    └── search.ts                    # NEW
```

---

## Testing Requirements

### Component Tests

```typescript
// SessionSearchBar.test.ts
describe('SessionSearchBar', () => {
  it('shows clear button when search has value');
  it('calls onSearchChange on input');
  it('clears search on clear button click');
  it('toggles filter dropdown on button click');
  it('shows active indicator when filters are applied');
});

// FiltersDropdown.test.ts
describe('FiltersDropdown', () => {
  it('closes on click outside');
  it('calls scope change handler');
  it('calls status change handler');
  it('calls date range change handler');
  it('resets all filters on reset click');
});

// ActiveFilterChips.test.ts
describe('ActiveFilterChips', () => {
  it('renders chips for each active filter');
  it('removes filter on chip click');
  it('clears all on clear all click');
  it('shows correct counts');
});
```

### E2E Tests

```typescript
// session-search.spec.ts
test('should filter sessions by search query', async ({ page }) => {
  await page.goto('/projects/-Users-me-project');
  await page.fill('[placeholder*="Search"]', 'auth');
  await expect(page.locator('.session-card')).toHaveCount(3);
});

test('should filter by status', async ({ page }) => {
  await page.click('button:has-text("Filters")');
  await page.click('button:has-text("Active")');
  await expect(page.locator('.filter-chip')).toContainText('Active');
});

test('should persist filters in URL', async ({ page }) => {
  await page.fill('[placeholder*="Search"]', 'test');
  await expect(page).toHaveURL(/q=test/);
});
```

---

## Accessibility Requirements

1. **ARIA labels** on all interactive elements
2. **Keyboard navigation** for dropdown options
3. **Focus management** when dropdown opens/closes
4. **Screen reader announcements** for filter changes
5. **Sufficient color contrast** for all states

---

## Dependencies

- No new npm packages required
- Uses existing `lucide-svelte` for icons
- Uses existing CSS custom properties
- Uses Svelte 5 runes (already in use)

---

## Rollout Plan

1. **Phase 1:** Create types and utility functions
2. **Phase 2:** Build SessionSearchBar component
3. **Phase 3:** Build FiltersDropdown component
4. **Phase 4:** Build ActiveFilterChips component
5. **Phase 5:** Integrate into project page (replace existing search)
6. **Phase 6:** Add keyboard shortcuts
7. **Phase 7:** Mobile bottom sheet adaptation
8. **Phase 8:** Testing and polish

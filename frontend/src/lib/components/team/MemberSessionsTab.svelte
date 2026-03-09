<script lang="ts">
	import { browser } from '$app/environment';
	import {
		Layers,
		List,
		LayoutGrid,
		Search,
		FolderOpen,
		X,
		Loader2
	} from 'lucide-svelte';
	import { isToday, isYesterday, isThisWeek, isThisMonth } from 'date-fns';
	import { onMount } from 'svelte';
	import { API_BASE } from '$lib/config';
	import GlobalSessionCard from '$lib/components/GlobalSessionCard.svelte';
	import EmptyState from '$lib/components/ui/EmptyState.svelte';
	import TokenSearchInput from '$lib/components/TokenSearchInput.svelte';
	import FiltersDropdown from '$lib/components/FiltersDropdown.svelte';
	import FiltersBottomSheet from '$lib/components/FiltersBottomSheet.svelte';
	import ActiveFilterChips from '$lib/components/ActiveFilterChips.svelte';
	import type {
		MemberProfile,
		SessionWithContext,
		SearchFilters,
		SearchScopeSelection,
		AllSessionsResponse
	} from '$lib/api-types';
	import { getProjectNameFromEncoded } from '$lib/utils';
	import {
		DEFAULT_FILTERS,
		DEFAULT_SCOPE_SELECTION,
		getFilterChips,
		hasActiveFilters as checkHasActiveFilters,
		filterSessionsByTokens,
		filterSessionsByDateRange,
		scopeSelectionToApi,
		apiToScopeSelection
	} from '$lib/search';

	/** Get display label for a project encoded name (deduplicates worktrees/subdirs). */
	function getProjectLabel(encodedName: string): string {
		return getProjectNameFromEncoded(encodedName);
	}

	interface Props {
		profile: MemberProfile;
	}

	let { profile }: Props = $props();

	// Data state
	let sessions = $state<SessionWithContext[]>([]);
	let loading = $state(true);
	let error = $state<string | null>(null);

	// View mode
	let viewMode = $state<'list' | 'grid'>('list');
	let viewModeInitialized = $state(false);

	$effect(() => {
		if (browser && !viewModeInitialized) {
			const saved = localStorage.getItem('claude-code-karma-member-sessions-view-mode');
			if (saved === 'list' || saved === 'grid') {
				viewMode = saved;
			}
			viewModeInitialized = true;
		}
	});

	$effect(() => {
		if (browser && viewModeInitialized) {
			localStorage.setItem('claude-code-karma-member-sessions-view-mode', viewMode);
		}
	});

	// Filter state
	let filters = $state<SearchFilters>({ ...DEFAULT_FILTERS });
	let scopeSelection = $state<SearchScopeSelection>({ ...DEFAULT_SCOPE_SELECTION });
	let showFiltersDropdown = $state(false);
	let isMobile = $state(false);
	let searchTokens = $state<string[]>([]);
	let selectedProjectFilters = $state<Set<string>>(new Set());

	// Mobile detection
	$effect(() => {
		if (!browser) return;
		const checkMobile = () => {
			isMobile = window.innerWidth < 640;
		};
		checkMobile();
		window.addEventListener('resize', checkMobile);
		return () => window.removeEventListener('resize', checkMobile);
	});

	// Fetch sessions from /sessions/all with user filter
	// Local machine sessions have source=local and no remote_user_id,
	// so we query differently for the local device vs remote members.
	async function fetchSessions() {
		loading = true;
		error = null;
		try {
			const params = new URLSearchParams({ per_page: '200' });
			if (profile.is_you) {
				// Local sessions have source=local and no remote_user_id.
				// Fetch all local, then filter to shared projects client-side.
				params.set('source', 'local');
			} else {
				params.set('source', 'remote');
				params.set('user', profile.user_id);
			}
			const res = await fetch(`${API_BASE}/sessions/all?${params}`);
			if (!res.ok) {
				error = `Failed to load sessions (${res.status})`;
				return;
			}
			const data: AllSessionsResponse = await res.json();
			let fetched = data.sessions;

			// For local user, only show sessions from projects shared with teams
			if (profile.is_you) {
				const sharedProjects = new Set(
					profile.teams.flatMap((t) => t.projects.map((p) => p.encoded_name))
				);
				if (sharedProjects.size > 0) {
					fetched = fetched.filter((s) => sharedProjects.has(s.project_encoded_name ?? ''));
				}
			}
			sessions = fetched;
		} catch {
			error = 'Network error loading sessions';
		} finally {
			loading = false;
		}
	}

	onMount(() => {
		fetchSessions();
	});

	// Available projects for filter pills — keyed by encoded_name to deduplicate
	// worktrees and subdirectories that share the same project
	type ProjectPill = { encoded: string; label: string };
	let availableProjects = $derived.by(() => {
		const seen = new Map<string, string>();
		for (const s of sessions) {
			const enc = s.project_encoded_name ?? '';
			if (enc && !seen.has(enc)) {
				seen.set(enc, getProjectLabel(enc));
			}
		}
		return [...seen.entries()]
			.map(([encoded, label]) => ({ encoded, label }))
			.sort((a, b) => a.label.localeCompare(b.label));
	});

	// Filtering pipeline
	let filteredSessions = $derived.by(() => {
		let result = sessions;

		// Filter by project encoded_name (matches filter pills)
		if (selectedProjectFilters.size > 0) {
			result = result.filter((s) => selectedProjectFilters.has(s.project_encoded_name ?? ''));
		}

		// Filter by search tokens
		if (searchTokens.length > 0) {
			result = filterSessionsByTokens(result, searchTokens, scopeSelection);
		}

		// Filter by date range
		if (filters.dateRange !== 'all') {
			result = filterSessionsByDateRange(
				result,
				filters.dateRange,
				filters.customStart,
				filters.customEnd
			);
		}

		// Sort by start_time descending
		return [...result].sort(
			(a, b) =>
				new Date(b.start_time || 0).getTime() - new Date(a.start_time || 0).getTime()
		);
	});

	let filteredSessionsCount = $derived(filteredSessions.length);
	let totalCount = $derived(sessions.length);

	// Date grouping
	type DateGroup = { label: string; sessions: SessionWithContext[] };

	let groupedByDate = $derived.by(() => {
		const today: SessionWithContext[] = [];
		const yesterday: SessionWithContext[] = [];
		const thisWeek: SessionWithContext[] = [];
		const thisMonth: SessionWithContext[] = [];
		const older: SessionWithContext[] = [];

		for (const session of filteredSessions) {
			if (!session.start_time) {
				older.push(session);
				continue;
			}
			const startTime = new Date(session.start_time);
			if (isToday(startTime)) today.push(session);
			else if (isYesterday(startTime)) yesterday.push(session);
			else if (isThisWeek(startTime, { weekStartsOn: 1 })) thisWeek.push(session);
			else if (isThisMonth(startTime)) thisMonth.push(session);
			else older.push(session);
		}

		const groups: DateGroup[] = [];
		if (today.length > 0) groups.push({ label: 'Today', sessions: today });
		if (yesterday.length > 0) groups.push({ label: 'Yesterday', sessions: yesterday });
		if (thisWeek.length > 0) groups.push({ label: 'This Week', sessions: thisWeek });
		if (thisMonth.length > 0) groups.push({ label: 'This Month', sessions: thisMonth });
		if (older.length > 0) groups.push({ label: 'Older', sessions: older });
		return groups;
	});

	// Filter chips
	let hasActiveFilters = $derived(checkHasActiveFilters(filters));
	let filterChips = $derived(getFilterChips(filters));
	let activeFilterCount = $derived(filterChips.length);

	// Handler functions
	function handleTokensChange(tokens: string[]) {
		searchTokens = tokens;
	}

	function handleScopeSelectionChange(sel: SearchScopeSelection) {
		scopeSelection = sel;
		filters = { ...filters, scope: scopeSelectionToApi(sel) };
	}

	function handleStatusChange(status: SearchFilters['status']) {
		filters = { ...filters, status };
	}

	function handleDateRangeChange(
		dateRange: SearchFilters['dateRange'],
		customStart?: Date,
		customEnd?: Date
	) {
		filters = { ...filters, dateRange, customStart, customEnd };
	}

	function handleRemoveFilter(key: string) {
		if (key === 'scope') {
			scopeSelection = { ...DEFAULT_SCOPE_SELECTION };
			filters = { ...filters, scope: 'both' };
		} else if (key === 'status') {
			filters = { ...filters, status: 'all' };
		} else if (key === 'dateRange') {
			filters = { ...filters, dateRange: 'all', customStart: undefined, customEnd: undefined };
		} else if (key === 'source') {
			filters = { ...filters, source: 'all' };
		}
	}

	function handleClearAllFilters() {
		filters = { ...DEFAULT_FILTERS };
		scopeSelection = { ...DEFAULT_SCOPE_SELECTION };
		searchTokens = [];
		selectedProjectFilters = new Set();
		showFiltersDropdown = false;
	}

	function handleProjectToggle(project: string) {
		const next = new Set(selectedProjectFilters);
		if (next.has(project)) {
			next.delete(project);
		} else {
			next.add(project);
		}
		selectedProjectFilters = next;
	}

	function handleClearAllProjects() {
		selectedProjectFilters = new Set();
	}
</script>

<div class="space-y-4">
	{#if loading}
		<div class="flex items-center justify-center py-12">
			<Loader2 size={20} class="animate-spin text-[var(--text-muted)]" />
		</div>
	{:else if error}
		<p class="text-sm text-[var(--error)] py-8 text-center">{error}</p>
	{:else if sessions.length === 0}
		<EmptyState
			icon={Layers}
			title="No synced sessions"
			description="No sessions from this member have been synced yet."
		/>
	{:else}
		<!-- Header: count + view mode toggle -->
		<div class="flex items-center justify-between">
			<div class="flex items-center gap-2 text-sm text-[var(--text-muted)]">
				<Layers size={16} class="text-[var(--nav-purple)]" />
				<span class="font-medium text-[var(--text-primary)]">{totalCount}</span>
				<span>{totalCount === 1 ? 'session' : 'sessions'}</span>
			</div>
			<div class="flex items-center gap-3">
				<span class="text-xs text-[var(--text-muted)] font-mono tabular-nums">
					{#if hasActiveFilters || selectedProjectFilters.size > 0 || searchTokens.length > 0}
						{filteredSessionsCount} filtered sessions
					{:else}
						{totalCount} sessions
					{/if}
				</span>
				<!-- View Mode Toggle -->
				<div
					class="flex items-center gap-1 p-1 bg-[var(--bg-subtle)] rounded-[6px] border border-[var(--border)]"
					role="group"
					aria-label="View mode"
				>
					<button
						onclick={() => (viewMode = 'list')}
						class="p-1.5 rounded transition-colors focus:outline-none focus:ring-2 focus:ring-[var(--accent)] focus:ring-offset-2 {viewMode ===
						'list'
							? 'bg-[var(--bg-base)] text-[var(--text-primary)] shadow-sm'
							: 'text-[var(--text-muted)] hover:text-[var(--text-secondary)]'}"
						aria-label="List view (grouped by date)"
						aria-pressed={viewMode === 'list'}
					>
						<List size={16} strokeWidth={2} />
					</button>
					<button
						onclick={() => (viewMode = 'grid')}
						class="p-1.5 rounded transition-colors focus:outline-none focus:ring-2 focus:ring-[var(--accent)] focus:ring-offset-2 {viewMode ===
						'grid'
							? 'bg-[var(--bg-base)] text-[var(--text-primary)] shadow-sm'
							: 'text-[var(--text-muted)] hover:text-[var(--text-secondary)]'}"
						aria-label="Grid view (compact)"
						aria-pressed={viewMode === 'grid'}
					>
						<LayoutGrid size={16} strokeWidth={2} />
					</button>
				</div>
			</div>
		</div>

		<!-- Search & Filters -->
		<div class="space-y-3">
			<div class="relative flex gap-2">
				<TokenSearchInput
					tokens={searchTokens}
					onTokensChange={handleTokensChange}
					placeholder="Search titles, prompts, or slugs..."
					class="flex-1"
				/>
				<!-- Filters Button -->
				<button
					onclick={() => (showFiltersDropdown = !showFiltersDropdown)}
					class="inline-flex items-center gap-2 px-3 h-[38px] text-xs font-medium rounded-lg hover:border-[var(--border-hover)] transition-all whitespace-nowrap {hasActiveFilters
						? 'bg-[var(--accent-subtle)] border border-[var(--accent)] text-[var(--accent)]'
						: 'bg-[var(--bg-base)] border border-[var(--border)] text-[var(--text-secondary)] hover:bg-[var(--bg-subtle)]'}"
				>
					<span>Filters</span>
					{#if activeFilterCount > 0}
						<span
							class="inline-flex items-center justify-center min-w-[18px] h-[18px] px-1 bg-[var(--accent)] text-white rounded-full text-[10px] font-bold tabular-nums"
						>
							{activeFilterCount}
						</span>
					{/if}
				</button>

				{#if showFiltersDropdown && !isMobile}
					<FiltersDropdown
						{scopeSelection}
						onScopeSelectionChange={handleScopeSelectionChange}
						status={filters.status}
						onStatusChange={handleStatusChange}
						dateRange={filters.dateRange}
						onDateRangeChange={handleDateRangeChange}
						onReset={handleClearAllFilters}
						onClose={() => (showFiltersDropdown = false)}
					/>
				{/if}
			</div>
		</div>

		<!-- Mobile Filters Bottom Sheet -->
		{#if isMobile}
			<FiltersBottomSheet
				open={showFiltersDropdown}
				onClose={() => (showFiltersDropdown = false)}
				{scopeSelection}
				onScopeSelectionChange={handleScopeSelectionChange}
				status={filters.status}
				onStatusChange={handleStatusChange}
				dateRange={filters.dateRange}
				onDateRangeChange={handleDateRangeChange}
				onReset={handleClearAllFilters}
			/>
		{/if}

		<!-- Active Filters -->
		<ActiveFilterChips
			chips={filterChips}
			onRemove={handleRemoveFilter}
			onClearAll={handleClearAllFilters}
			{totalCount}
			filteredCount={filteredSessionsCount}
		/>

		<!-- Project Filter Chips -->
		{#if availableProjects.length > 1}
			<div class="flex items-center gap-2 flex-wrap">
				<span class="text-xs text-[var(--text-muted)] font-medium">Projects:</span>
				{#each availableProjects as project (project.encoded)}
					<button
						onclick={() => handleProjectToggle(project.encoded)}
						class="inline-flex items-center gap-1.5 px-2.5 py-1 text-xs rounded-full border transition-colors {selectedProjectFilters.has(
							project.encoded
						)
							? 'bg-[var(--accent-subtle)] border-[var(--accent)] text-[var(--accent)]'
							: 'bg-[var(--bg-base)] border-[var(--border)] text-[var(--text-secondary)] hover:border-[var(--border-hover)] hover:text-[var(--text-primary)]'}"
					>
						<FolderOpen size={10} />
						{project.label}
						{#if selectedProjectFilters.has(project.encoded)}
							<X size={10} class="opacity-60 hover:opacity-100" />
						{/if}
					</button>
				{/each}
				{#if selectedProjectFilters.size > 1}
					<button
						onclick={handleClearAllProjects}
						class="text-xs text-[var(--text-muted)] hover:text-[var(--text-primary)] transition-colors"
					>
						Clear projects
					</button>
				{/if}
			</div>
		{/if}

		<!-- Session Cards -->
		{#if filteredSessions.length > 0}
			{#if viewMode === 'list'}
				<div class="space-y-8">
					{#each groupedByDate as group (group.label)}
						<div>
							<h2
								class="text-sm font-semibold uppercase tracking-wide text-[var(--text-secondary)] mb-4"
							>
								{group.label}
								<span class="text-[var(--text-faint)] font-medium ml-1.5"
									>({group.sessions.length})</span
								>
							</h2>
							<div
								class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3"
							>
								{#each group.sessions as session (session.uuid)}
									<GlobalSessionCard {session} />
								{/each}
							</div>
						</div>
					{/each}
				</div>
			{:else}
				<div class="space-y-6">
					{#each groupedByDate as group (group.label)}
						<div>
							<h2
								class="text-sm font-semibold uppercase tracking-wide text-[var(--text-secondary)] mb-3"
							>
								{group.label}
								<span class="text-[var(--text-faint)] font-medium ml-1.5"
									>({group.sessions.length})</span
								>
							</h2>
							<div
								class="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-2"
							>
								{#each group.sessions as session (session.uuid)}
									<GlobalSessionCard {session} compact />
								{/each}
							</div>
						</div>
					{/each}
				</div>
			{/if}
		{:else if hasActiveFilters || searchTokens.length > 0 || selectedProjectFilters.size > 0}
			<EmptyState icon={Search} title="No sessions match your filters">
				<div class="text-sm text-[var(--text-muted)] space-y-2 max-w-md">
					{#if searchTokens.length > 0}
						<p>
							No sessions found matching: <span
								class="font-medium text-[var(--text-secondary)]"
								>{searchTokens.join(', ')}</span
							>
						</p>
					{/if}
					{#if selectedProjectFilters.size > 0}
						<p class="text-xs">
							Project filter: {[...selectedProjectFilters].map((enc) => getProjectLabel(enc)).join(', ')}
						</p>
					{/if}
				</div>
				<button
					onclick={handleClearAllFilters}
					class="mt-4 px-4 py-2 text-sm bg-[var(--accent)] text-white rounded-lg hover:bg-[var(--accent-hover)] transition-colors"
				>
					Clear all filters
				</button>
			</EmptyState>
		{/if}
	{/if}
</div>

<script lang="ts">
	import { browser } from '$app/environment';
	import { replaceState } from '$app/navigation';
	import {
		Cable,
		Wrench,
		Play,
		FolderOpen,
		Bot,
		AlertCircle,
		ExternalLink,
		Puzzle,
		TrendingUp,
		Layers,
		Search,
		LayoutGrid,
		List,
		X
	} from 'lucide-svelte';
	import { formatDistanceToNow, isToday, isYesterday, isThisWeek, isThisMonth } from 'date-fns';
	import { onMount, tick } from 'svelte';

	import PageHeader from '$lib/components/layout/PageHeader.svelte';
	import StatsGrid from '$lib/components/StatsGrid.svelte';
	import SegmentedControl from '$lib/components/ui/SegmentedControl.svelte';
	import Badge from '$lib/components/ui/Badge.svelte';
	import McpServerIcon from '$lib/components/tools/McpServerIcon.svelte';
	import McpContextBar from '$lib/components/tools/McpContextBar.svelte';
	import McpTrendChart from '$lib/components/tools/McpTrendChart.svelte';
	import ContextSplitCard from '$lib/components/tools/ContextSplitCard.svelte';
	import GlobalSessionCard from '$lib/components/GlobalSessionCard.svelte';
	import EmptyState from '$lib/components/ui/EmptyState.svelte';
	import TokenSearchInput from '$lib/components/TokenSearchInput.svelte';
	import FiltersDropdown from '$lib/components/FiltersDropdown.svelte';
	import FiltersBottomSheet from '$lib/components/FiltersBottomSheet.svelte';
	import ActiveFilterChips from '$lib/components/ActiveFilterChips.svelte';
	import { getServerColorVars, getServerChartHex } from '$lib/utils/mcp';
	import {
		DEFAULT_FILTERS,
		DEFAULT_SCOPE_SELECTION,
		getFilterChips,
		hasActiveFilters as checkHasActiveFilters,
		filterSessionsByTokens,
		filterSessionsByQuery,
		filterSessionsByDateRange,
		filterSessionsByProject,
		scopeSelectionToApi,
		apiToScopeSelection,
		restoreAllFiltersFromUrl,
		buildFilterUrlParams
	} from '$lib/search';
	import type {
		StatItem,
		McpSessionSummary,
		SessionWithContext,
		SearchFilters,
		SearchScopeSelection
	} from '$lib/api-types';

	let { data } = $props();

	let detail = $derived(data.detail);

	// Tab state
	let activeTab = $state<'overview' | 'history'>('overview');

	const tabOptions = [
		{ label: 'Overview', value: 'overview' },
		{ label: 'History', value: 'history' }
	];

	// View mode for sessions
	let viewMode = $state<'list' | 'grid'>('grid');
	let viewModeInitialized = $state(false);

	$effect(() => {
		if (browser && !viewModeInitialized) {
			const saved = localStorage.getItem('claude-karma-server-sessions-view-mode');
			if (saved === 'list' || saved === 'grid') {
				viewMode = saved;
			}
			viewModeInitialized = true;
		}
	});

	$effect(() => {
		if (browser && viewModeInitialized) {
			localStorage.setItem('claude-karma-server-sessions-view-mode', viewMode);
		}
	});

	// Filter state
	let filters = $state<SearchFilters>({ ...DEFAULT_FILTERS });
	let scopeSelection = $state<SearchScopeSelection>({ ...DEFAULT_SCOPE_SELECTION });
	let showFiltersDropdown = $state(false);
	let isMobile = $state(false);
	let searchTokens = $state<string[]>([]);
	let selectedProjectFilters = $state<Set<string>>(new Set());

	// URL sync state
	let filtersReady = $state(false);
	let tabsReady = $state(false);

	// Restore filters from URL params
	function restoreFiltersFromUrl(params: URLSearchParams) {
		const restored = restoreAllFiltersFromUrl(params);
		searchTokens = restored.tokens;
		filters.status = restored.status;
		filters.dateRange = restored.dateRange;
		filters.customStart = restored.customStart;
		filters.customEnd = restored.customEnd;
		scopeSelection = apiToScopeSelection(restored.scope);
		if (restored.project) {
			const match = sessionsAsContext.find(
				(s) =>
					s.project_name === restored.project ||
					s.project_encoded_name === restored.project
			);
			if (match) {
				selectedProjectFilters = new Set([match.project_name]);
			}
		}
	}

	// Initialize tab and filters from URL, handle popstate
	onMount(() => {
		const params = new URLSearchParams(window.location.search);
		const tabParam = params.get('tab');
		if (tabParam === 'history') activeTab = 'history';
		restoreFiltersFromUrl(params);
		tabsReady = true;
		filtersReady = true;

		const handlePopState = () => {
			const p = new URLSearchParams(window.location.search);
			const t = p.get('tab');
			activeTab = t === 'history' ? 'history' : 'overview';
			restoreFiltersFromUrl(p);
		};
		window.addEventListener('popstate', handlePopState);
		return () => window.removeEventListener('popstate', handlePopState);
	});

	// Unified URL sync effect
	$effect(() => {
		if (!browser || !tabsReady || !filtersReady) return;
		const url = buildFilterUrlParams(window.location.href, {
			filters: {
				query: '',
				tokens: searchTokens,
				scope: scopeSelectionToApi(scopeSelection),
				status: filters.status,
				dateRange: filters.dateRange,
				customStart: filters.customStart,
				customEnd: filters.customEnd
			},
			project: selectedProjectFilters.size > 0 ? [...selectedProjectFilters][0] : undefined,
			tab: activeTab,
			defaultTab: 'overview'
		});
		tick().then(() => replaceState(url.toString(), {}));
	});

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

	let colorVars = $derived(getServerColorVars(data.serverName, detail?.plugin_name));
	let accentColor = $derived(colorVars.color);
	let chartAccentHex = $derived(getServerChartHex(data.serverName, detail?.plugin_name));

	// Stats
	let stats = $derived<StatItem[]>(
		detail
			? [
					{
						title: 'Tools',
						value: detail.tool_count,
						icon: Wrench,
						color: 'teal'
					},
					{
						title: 'Total Calls',
						value: detail.total_calls.toLocaleString(),
						icon: Play,
						color: 'blue'
					},
					{
						title: 'Sessions',
						value: detail.session_count,
						icon: FolderOpen,
						color: 'green'
					},
					{
						title: 'Subagent %',
						value:
							detail.total_calls > 0
								? Math.round((detail.subagent_calls / detail.total_calls) * 100) +
									'%'
								: '0%',
						icon: Bot,
						color: 'purple'
					}
				]
			: []
	);

	// Tool breakdown sorted by calls
	let sortedTools = $derived(detail ? [...detail.tools].sort((a, b) => b.calls - a.calls) : []);

	let maxToolCalls = $derived(sortedTools.length > 0 ? sortedTools[0].calls : 1);

	// Usage trend max for bar chart
	let trendSlice = $derived(detail && detail.trend.length > 0 ? detail.trend.slice(-30) : []);

	let trendMaxCalls = $derived(
		detail && detail.trend.length > 0 ? Math.max(...detail.trend.map((t) => t.calls), 1) : 1
	);

	// Map McpSessionSummary to SessionWithContext for filtering and display
	function toSessionWithContext(s: McpSessionSummary): SessionWithContext {
		return {
			uuid: s.uuid,
			slug: s.slug ?? '',
			message_count: s.message_count,
			start_time: s.start_time ?? '',
			end_time: s.end_time ?? undefined,
			duration_seconds: s.duration_seconds ?? undefined,
			models_used: s.models_used,
			subagent_count: s.subagent_count,
			has_todos: false,
			initial_prompt: s.initial_prompt ?? undefined,
			git_branches: s.git_branches,
			session_titles: s.session_titles,
			project_encoded_name: s.project_encoded_name ?? undefined,
			project_path: s.project_encoded_name ?? '',
			project_name: s.project_encoded_name?.split('-').pop() ?? ''
		};
	}

	// Sessions as SessionWithContext for filtering
	let sessionsAsContext = $derived<SessionWithContext[]>(
		detail ? detail.sessions.map(toSessionWithContext) : []
	);

	// Map session UUID to tool_source + subagent deep-link href
	let toolSourceMap = $derived<
		Map<string, { source: 'main' | 'subagent' | 'both'; href?: string }>
	>(
		new Map(
			(detail?.sessions ?? [])
				.filter((s) => s.tool_source)
				.map((s) => {
					const agentId = s.subagent_agent_ids?.[0];
					const href =
						agentId && s.project_encoded_name
							? `/projects/${s.project_encoded_name}/${s.uuid.slice(0, 8)}/agents/${agentId}`
							: undefined;
					return [
						s.uuid,
						{ source: s.tool_source as 'main' | 'subagent' | 'both', href }
					] as const;
				})
		)
	);

	let totalCount = $derived(detail?.sessions_total ?? 0);

	// Available projects for filter
	let availableProjects = $derived(
		[...new Set(sessionsAsContext.map((s) => s.project_name).filter(Boolean))].sort()
	);

	// Derived filter state
	let filtersWithScope = $derived({
		...filters,
		scope: scopeSelectionToApi(scopeSelection)
	});
	let filterChips = $derived(getFilterChips(filtersWithScope));
	let hasActiveFilters = $derived(
		checkHasActiveFilters(filtersWithScope) || !scopeSelection.titles || !scopeSelection.prompts
	);
	let activeFilterCount = $derived(
		filterChips.length + (selectedProjectFilters.size > 0 ? 1 : 0)
	);

	// Filtered sessions
	let filteredSessions = $derived.by(() => {
		if (sessionsAsContext.length === 0) return [];
		let result = [...sessionsAsContext];

		result = filterSessionsByProject(result, selectedProjectFilters) as SessionWithContext[];

		if (searchTokens.length > 0) {
			result = filterSessionsByTokens(
				result,
				searchTokens,
				scopeSelection
			) as SessionWithContext[];
		} else {
			result = filterSessionsByQuery(
				result,
				filters.query,
				scopeSelection
			) as SessionWithContext[];
		}

		result = filterSessionsByDateRange(
			result,
			filters.dateRange,
			filters.customStart,
			filters.customEnd
		) as SessionWithContext[];

		return result.sort(
			(a, b) => new Date(b.start_time).getTime() - new Date(a.start_time).getTime()
		);
	});

	let filteredSessionsCount = $derived(filteredSessions.length);

	// Time-based grouping
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

	// Handler functions
	function handleTokensChange(tokens: string[]) {
		searchTokens = tokens;
	}

	function handleSearchChange(query: string) {
		filters.query = query;
	}

	function handleScopeSelectionChange(selection: SearchScopeSelection) {
		scopeSelection = selection;
	}

	function handleStatusChange(status: SearchFilters['status']) {
		filters.status = status;
	}

	function handleDateRangeChange(range: SearchFilters['dateRange']) {
		filters.dateRange = range;
	}

	function handleRemoveFilter(key: keyof SearchFilters) {
		if (key === 'scope') {
			scopeSelection = { ...DEFAULT_SCOPE_SELECTION };
		}
		filters = { ...filters, [key]: DEFAULT_FILTERS[key] };
	}

	function handleClearAllFilters() {
		filters = { ...DEFAULT_FILTERS };
		scopeSelection = { ...DEFAULT_SCOPE_SELECTION };
		selectedProjectFilters = new Set();
		searchTokens = [];
	}

	function handleProjectToggle(project: string) {
		const newSet = new Set(selectedProjectFilters);
		if (newSet.has(project)) {
			newSet.delete(project);
		} else {
			newSet.add(project);
		}
		selectedProjectFilters = newSet;
	}

	function handleClearAllProjects() {
		selectedProjectFilters = new Set();
	}
</script>

<div class="space-y-8">
	<!-- Page Header -->
	{#if detail}
		<PageHeader
			title={detail.display_name}
			icon={Cable}
			iconColorRaw={{ color: accentColor, subtle: colorVars.subtle }}
			breadcrumbs={[
				{ label: 'Dashboard', href: '/' },
				{ label: 'Tools', href: '/tools' },
				{ label: detail.display_name }
			]}
			metadata={[
				{ text: `${detail.tool_count} tool${detail.tool_count !== 1 ? 's' : ''}` },
				{
					text: `${detail.total_calls.toLocaleString()} call${detail.total_calls !== 1 ? 's' : ''}`
				},
				{ text: `${detail.session_count} session${detail.session_count !== 1 ? 's' : ''}` }
			]}
		>
			{#snippet badges()}
				{#if detail.plugin_name}
					<a
						href="/plugins/{encodeURIComponent(detail.plugin_name)}"
						class="inline-flex items-center gap-1.5 px-2.5 py-1 text-xs font-medium rounded-full hover:bg-[var(--bg-muted)] transition-colors no-underline"
						style="color: {colorVars.color}; background-color: {colorVars.subtle};"
					>
						<Puzzle size={12} />
						{detail.plugin_name}
					</a>
				{:else}
					<Badge variant="accent">
						{detail.source}
					</Badge>
				{/if}
			{/snippet}
		</PageHeader>

		<!-- Hero Stats -->
		<div
			class="relative overflow-hidden rounded-2xl p-8 border border-[var(--border)]"
			style="background: linear-gradient(135deg, color-mix(in srgb, {accentColor} 3%, transparent) 0%, color-mix(in srgb, {accentColor} 8%, transparent) 100%);"
		>
			<div
				class="absolute -top-24 -right-24 w-96 h-96 opacity-10 rounded-full blur-3xl pointer-events-none"
				style="background-color: {accentColor};"
			></div>
			<div class="relative">
				<StatsGrid {stats} columns={4} />
			</div>
		</div>

		<!-- Tab Navigation -->
		<div class="flex items-center justify-between">
			<SegmentedControl options={tabOptions} bind:value={activeTab} />
			{#if detail.last_used}
				<span class="text-sm text-[var(--text-muted)]">
					Last used {formatDistanceToNow(new Date(detail.last_used))} ago
				</span>
			{/if}
		</div>

		<!-- Overview Tab -->
		{#if activeTab === 'overview'}
			<div class="space-y-6">
				<!-- Context Split Card -->
				<div
					class="bg-[var(--bg-base)] border border-[var(--border)] rounded-xl p-6 shadow-sm hover:shadow-md transition-shadow"
				>
					<ContextSplitCard
						mainCalls={detail.main_calls}
						subagentCalls={detail.subagent_calls}
						totalCalls={detail.total_calls}
						firstUsed={detail.first_used}
						lastUsed={detail.last_used}
						sessions={detail.sessions}
						subagentColor={accentColor}
					/>

					<!-- Related Plugin -->
					{#if detail.plugin_name}
						<div class="mt-6 pt-4 border-t border-[var(--border)]">
							<a
								href="/plugins/{encodeURIComponent(detail.plugin_name)}"
								class="flex items-center gap-3 p-3 bg-[var(--bg-subtle)] rounded-lg hover:bg-[var(--bg-muted)] transition-colors group"
							>
								<Puzzle size={18} style="color: {colorVars.color};" />
								<div class="flex-1">
									<p
										class="text-sm font-medium text-[var(--text-primary)] transition-colors"
										style="--hover-color: {colorVars.color};"
									>
										{detail.plugin_name} plugin
									</p>
									<p class="text-xs text-[var(--text-muted)]">
										View plugin details
									</p>
								</div>
								<ExternalLink size={14} class="text-[var(--text-faint)]" />
							</a>
						</div>
					{/if}
				</div>

				<!-- Usage Trend Card -->
				{#if detail.trend && detail.trend.length > 0}
					<div
						class="bg-[var(--bg-base)] border border-[var(--border)] rounded-xl p-6 shadow-sm hover:shadow-md transition-shadow"
					>
						<div class="flex items-center gap-2 mb-6">
							<TrendingUp size={18} class="text-[var(--text-muted)]" />
							<h3 class="text-lg font-bold text-[var(--text-primary)]">
								Usage Trend
							</h3>
							<span class="text-xs text-[var(--text-muted)] ml-auto"
								>Last {detail.trend.length} days</span
							>
						</div>

						<McpTrendChart trend={detail.trend} accentColor={chartAccentHex} />
					</div>
				{/if}

				<!-- Tool Breakdown Card -->
				<div
					class="bg-[var(--bg-base)] border border-[var(--border)] rounded-xl p-6 shadow-sm hover:shadow-md transition-shadow"
				>
					<div class="flex items-center gap-2 mb-6">
						<Wrench size={18} class="text-[var(--text-muted)]" />
						<h3 class="text-lg font-bold text-[var(--text-primary)]">Tool Breakdown</h3>
					</div>

					{#if sortedTools.length === 0}
						<p class="text-sm text-[var(--text-muted)]">No tool data available</p>
					{:else}
						<div class="space-y-3.5 stagger-children">
							{#each sortedTools as tool (tool.full_name)}
								<div class="group">
									<div class="flex items-center justify-between mb-2">
										<a
											href="/tools/{encodeURIComponent(
												data.serverName
											)}/{encodeURIComponent(tool.name)}"
											class="text-sm text-[var(--text-secondary)] font-medium truncate max-w-[60%] hover:text-[var(--accent)] transition-colors"
											title={tool.full_name}
										>
											{tool.name}
										</a>
										<div class="flex items-center gap-3">
											<McpContextBar
												mainCalls={tool.main_calls}
												subagentCalls={tool.subagent_calls}
												compact
											/>
											<span
												class="text-sm text-[var(--text-primary)] tabular-nums font-semibold"
											>
												{tool.calls.toLocaleString()}
											</span>
										</div>
									</div>
									<div
										class="h-2 bg-[var(--bg-subtle)] rounded-full overflow-hidden"
									>
										<div
											class="h-full rounded-full transition-all duration-300 ease-out"
											style="width: {(tool.calls / maxToolCalls) *
												100}%; background-color: {accentColor};"
										></div>
									</div>
								</div>
							{/each}
						</div>
					{/if}
				</div>

			</div>

			<!-- History Tab -->
		{:else if activeTab === 'history'}
			<div class="space-y-4">
				<div class="flex items-center justify-between">
					<div class="flex items-center gap-2 text-sm text-[var(--text-muted)]">
						<Layers size={16} style="color: {accentColor};" />
						<span class="font-medium text-[var(--text-primary)]">{totalCount}</span>
						<span>{totalCount === 1 ? 'session' : 'sessions'} using this server</span>
					</div>
					<div class="flex items-center gap-3">
						<span class="text-xs text-[var(--text-muted)] font-mono tabular-nums">
							{#if hasActiveFilters || selectedProjectFilters.size > 0}
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
						{#each availableProjects as project}
							<button
								onclick={() => handleProjectToggle(project)}
								class="inline-flex items-center gap-1.5 px-2.5 py-1 text-xs rounded-full border transition-colors {selectedProjectFilters.has(
									project
								)
									? 'bg-[var(--accent-subtle)] border-[var(--accent)] text-[var(--accent)]'
									: 'bg-[var(--bg-base)] border-[var(--border)] text-[var(--text-secondary)] hover:border-[var(--border-hover)] hover:text-[var(--text-primary)]'}"
							>
								<FolderOpen size={10} />
								{project}
								{#if selectedProjectFilters.has(project)}
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
											{@const meta = toolSourceMap.get(session.uuid)}
											<GlobalSessionCard
												{session}
												toolSource={meta?.source}
												subagentHref={meta?.href}
											/>
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
											{@const meta = toolSourceMap.get(session.uuid)}
											<GlobalSessionCard
												{session}
												compact
												toolSource={meta?.source}
												subagentHref={meta?.href}
											/>
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
									Project filter: {[...selectedProjectFilters].join(', ')}
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
				{:else}
					<EmptyState
						icon={Layers}
						title="No sessions yet"
						description="This server hasn't been used in any sessions."
					/>
				{/if}
			</div>
		{/if}
	{:else}
		<!-- Server not found -->
		<PageHeader
			title={data.serverName}
			icon={Cable}
			iconColor="--nav-teal"
			breadcrumbs={[
				{ label: 'Dashboard', href: '/' },
				{ label: 'Tools', href: '/tools' },
				{ label: data.serverName }
			]}
		/>
		<div
			class="flex items-center gap-3 px-5 py-4 bg-[var(--bg-subtle)] rounded-xl border border-dashed border-[var(--border)]"
		>
			<AlertCircle size={20} class="text-[var(--text-muted)] flex-shrink-0" />
			<div>
				<p class="text-sm text-[var(--text-secondary)] font-medium">Server not found</p>
				<p class="text-xs text-[var(--text-muted)]">
					No MCP server named "{data.serverName}" was found in your session data
				</p>
			</div>
		</div>
	{/if}
</div>

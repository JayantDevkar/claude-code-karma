<script lang="ts">
	import { browser } from '$app/environment';
	import { replaceState } from '$app/navigation';
	import { page } from '$app/stores';
	import {
		Bot,
		Play,
		DollarSign,
		Clock,
		FolderOpen,
		Wrench,
		AlertCircle,
		TrendingUp,
		Hash,
		Layers,
		FileText,
		Search,
		LayoutGrid,
		List,
		X,
		Puzzle,
		Package,
		Zap,
		Terminal
	} from 'lucide-svelte';
	import { formatDistanceToNow, isToday, isYesterday, isThisWeek, isThisMonth } from 'date-fns';
	import { onMount, tick } from 'svelte';

	import PageHeader from '$lib/components/layout/PageHeader.svelte';
	import StatsGrid from '$lib/components/StatsGrid.svelte';
	import SegmentedControl from '$lib/components/ui/SegmentedControl.svelte';
	import AgentTrendChart from '$lib/components/agents/AgentTrendChart.svelte';
	import CollapsibleGroup from '$lib/components/ui/CollapsibleGroup.svelte';
	import GlobalSessionCard from '$lib/components/GlobalSessionCard.svelte';
	import EmptyState from '$lib/components/ui/EmptyState.svelte';
	import Badge from '$lib/components/ui/Badge.svelte';
	import TokenSearchInput from '$lib/components/TokenSearchInput.svelte';
	import FiltersDropdown from '$lib/components/FiltersDropdown.svelte';
	import FiltersBottomSheet from '$lib/components/FiltersBottomSheet.svelte';
	import ActiveFilterChips from '$lib/components/ActiveFilterChips.svelte';
	import {
		formatCost,
		formatDuration,
		getSubagentColorVars,
		getPluginChartHex,
		getProjectNameFromEncoded,
		renderMarkdownEffect
	} from '$lib/utils';
	import { parseMcpTool } from '$lib/utils/mcp';
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
		AgentUsageDetail,
		AgentInvocation,
		AgentInfo,
		SessionWithContext,
		SearchFilters,
		SearchScopeSelection
	} from '$lib/api-types';

	let { data } = $props();

	// Tab state
	let activeTab = $state<'overview' | 'activity' | 'history'>('overview');

	// Sessions data
	let sessions = $derived(data.sessions as SessionWithContext[]);
	let totalCount = $derived(data.sessionsTotalCount as number);

	// Filter state
	let filters = $state<SearchFilters>({ ...DEFAULT_FILTERS });
	let scopeSelection = $state<SearchScopeSelection>({ ...DEFAULT_SCOPE_SELECTION });
	let showFiltersDropdown = $state(false);
	let isMobile = $state(false);
	let searchTokens = $state<string[]>([]);
	let selectedProjectFilters = $state<Set<string>>(new Set());

	// View mode
	let viewMode = $state<'list' | 'grid'>('grid');
	let viewModeInitialized = $state(false);

	$effect(() => {
		if (browser && !viewModeInitialized) {
			const saved = localStorage.getItem('claude-karma-agent-sessions-view-mode');
			if (saved === 'list' || saved === 'grid') {
				viewMode = saved;
			}
			viewModeInitialized = true;
		}
	});

	$effect(() => {
		if (browser && viewModeInitialized) {
			localStorage.setItem('claude-karma-agent-sessions-view-mode', viewMode);
		}
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
			const projectName = data.projectNameMap[restored.project] || restored.project;
			const match = sessions.find((s) => s.project_name === projectName);
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
		else if (tabParam === 'activity') activeTab = 'activity';
		restoreFiltersFromUrl(params);
		tabsReady = true;
		filtersReady = true;

		const handlePopState = () => {
			const p = new URLSearchParams(window.location.search);
			const t = p.get('tab');
			activeTab = t === 'history' ? 'history' : t === 'activity' ? 'activity' : 'overview';
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

	// Available projects for filter
	let availableProjects = $derived([...new Set(sessions.map((s) => s.project_name))].sort());

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
		if (sessions.length === 0) return [];
		let result = [...sessions] as SessionWithContext[];

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

	const groupedByDate = $derived.by(() => {
		const today: SessionWithContext[] = [];
		const yesterday: SessionWithContext[] = [];
		const thisWeek: SessionWithContext[] = [];
		const thisMonth: SessionWithContext[] = [];
		const older: SessionWithContext[] = [];

		for (const session of filteredSessions) {
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

	const tabOptions = [
		{ label: 'Overview', value: 'overview' },
		{ label: 'Activity', value: 'activity' },
		{ label: 'History', value: 'history' }
	];

	const categoryLabels: Record<string, string> = {
		builtin: 'Built-in',
		plugin: 'Plugin',
		custom: 'Custom',
		project: 'Project'
	};

	// Get consistent colors based on subagent_type (matches session/subagent views)
	let colorVars = $derived(getSubagentColorVars(data.subagentType));

	// Hex color for Chart.js (canvas can't resolve oklch/CSS variables)
	let chartHex = $derived(
		data.detail?.plugin_source
			? getPluginChartHex(data.detail.plugin_source)
			: undefined
	);

	// Compute stats for hero section
	let stats = $derived<StatItem[]>(
		data.detail
			? [
					{
						title: 'Total Runs',
						value: data.detail.total_runs.toLocaleString(),
						icon: Play,
						color: 'blue'
					},
					{
						title: 'Total Cost',
						value: formatCost(data.detail.total_cost_usd),
						icon: DollarSign,
						color: 'green'
					},
					{
						title: 'Avg Duration',
						value: formatDuration(data.detail.avg_duration_seconds),
						icon: Clock,
						color: 'purple'
					},
					{
						title: 'Projects',
						value: data.detail.projects_used_in.length.toString(),
						icon: FolderOpen,
						color: 'orange'
					}
				]
			: []
	);

	// Sort tools by usage count
	let sortedTools = $derived(
		data.detail
			? Object.entries(data.detail.top_tools)
					.sort((a, b) => b[1] - a[1])
					.slice(0, 10)
			: []
	);

	// Sort skills by usage count
	let sortedSkills = $derived(
		data.detail
			? Object.entries(data.detail.top_skills)
					.sort((a, b) => b[1] - a[1])
					.slice(0, 10)
			: []
	);

	// Sort commands by usage count
	let sortedCommands = $derived(
		data.detail
			? Object.entries(data.detail.top_commands)
					.sort((a, b) => b[1] - a[1])
					.slice(0, 10)
			: []
	);

	// Sort projects by usage count
	let sortedProjects = $derived(
		data.detail
			? Object.entries(data.detail.usage_by_project)
					.sort((a, b) => b[1] - a[1])
					.slice(0, 10)
			: []
	);

	// Total counts for activity tab summary
	let totalToolUses = $derived(sortedTools.reduce((sum, [, c]) => sum + c, 0));
	let totalSkillUses = $derived(sortedSkills.reduce((sum, [, c]) => sum + c, 0));
	let totalCommandUses = $derived(sortedCommands.reduce((sum, [, c]) => sum + c, 0));

	// Helper to get project display name from encoded name
	// Uses the projectNameMap (from projects API) with a pattern-based fallback
	function getProjectDisplayName(encodedName: string): string {
		return data.projectNameMap[encodedName] || getProjectNameFromEncoded(encodedName);
	}

	// Max value for bar charts
	let maxToolCount = $derived(sortedTools.length > 0 ? sortedTools[0][1] : 1);
	let maxSkillCount = $derived(sortedSkills.length > 0 ? sortedSkills[0][1] : 1);
	let maxCommandCount = $derived(sortedCommands.length > 0 ? sortedCommands[0][1] : 1);
	let maxProjectCount = $derived(sortedProjects.length > 0 ? sortedProjects[0][1] : 1);

	// Token usage calculations for visual breakdown
	let totalTokens = $derived(
		data.detail ? data.detail.total_input_tokens + data.detail.total_output_tokens : 0
	);
	let inputPercent = $derived(
		totalTokens > 0 && data.detail ? (data.detail.total_input_tokens / totalTokens) * 100 : 50
	);
	let outputPercent = $derived(
		totalTokens > 0 && data.detail ? (data.detail.total_output_tokens / totalTokens) * 100 : 50
	);

	// Agent usage trend data
	let trendData = $derived(data.trend || []);

	// Agent info for definition section
	let agentInfo = $derived(data.agentInfo as AgentInfo | null);
	let hasAgentContent = $derived(agentInfo?.content && agentInfo.content.trim().length > 0);

	// Render markdown content for agent definition
	let renderedAgentContent = $state('');
	$effect(() => {
		if (agentInfo?.content) {
			renderMarkdownEffect(agentInfo.content, {}, (html) => {
				renderedAgentContent = html;
			});
		}
	});
</script>

<div class="space-y-8">
	<!-- Page Header -->
	<PageHeader
		title={data.detail?.agent_name ?? data.subagentType}
		icon={Bot}
		iconColorRaw={colorVars}
		breadcrumbs={[
			{ label: 'Dashboard', href: '/' },
			{ label: 'Agents', href: '/agents' },
			{ label: data.detail?.agent_name ?? data.subagentType }
		]}
		metadata={data.detail?.plugin_source
			? [
					{
						icon: Puzzle,
						text: data.detail.plugin_source,
						href: `/plugins/${encodeURIComponent(data.detail.plugin_source)}`
					}
				]
			: []}
	>
		{#snippet badges()}
			{#if data.detail}
				{#if data.detail.category === 'plugin' && data.detail.plugin_source}
					<a
						href="/plugins/{encodeURIComponent(data.detail.plugin_source)}"
						class="no-underline"
					>
						<Badge variant="purple" icon={Package}>Plugin</Badge>
					</a>
				{:else}
					<Badge variant={data.detail.category === 'builtin' ? 'slate' : 'accent'}>
						{categoryLabels[data.detail.category] || data.detail.category}
					</Badge>
				{/if}
			{/if}
		{/snippet}
	</PageHeader>

	<!-- Hero Stats Row with Agent-Colored Gradient -->
	{#if data.detail}
		<div
			class="relative overflow-hidden rounded-2xl p-8 border border-[var(--border)]"
			style="background: linear-gradient(135deg, {colorVars.subtle} 0%, {colorVars.subtle} 100%);"
		>
			<!-- Decorative blur element -->
			<div
				class="absolute -top-24 -right-24 w-96 h-96 opacity-20 rounded-full blur-3xl pointer-events-none"
				style="background-color: {colorVars.color};"
			></div>

			<!-- Stats Grid -->
			<div class="relative">
				<StatsGrid {stats} columns={4} />
			</div>
		</div>
	{:else}
		<!-- No usage data banner -->
		<div
			class="flex items-center gap-3 px-5 py-4 bg-[var(--bg-subtle)] rounded-xl border border-dashed border-[var(--border)]"
		>
			<AlertCircle size={20} class="text-[var(--text-muted)] flex-shrink-0" />
			<div>
				<p class="text-sm text-[var(--text-secondary)] font-medium">No usage data yet</p>
				<p class="text-xs text-[var(--text-muted)]">
					Usage statistics will appear here once this agent has been invoked in a session
				</p>
			</div>
		</div>
	{/if}

	<!-- Agent Definition Section -->
	{#if hasAgentContent}
		<CollapsibleGroup title="Agent Definition" open={!data.detail}>
			{#snippet icon()}
				<FileText size={16} style="color: {colorVars.color};" />
			{/snippet}

			{#snippet children()}
				{#if agentInfo?.description}
					<div class="mb-4 pb-4 border-b border-[var(--border)]">
						<p class="text-sm text-[var(--text-secondary)] leading-relaxed">
							{agentInfo.description}
						</p>
					</div>
				{/if}

				{#if agentInfo?.capabilities && agentInfo.capabilities.length > 0}
					<div class="mb-4 pb-4 border-b border-[var(--border)]">
						<h4
							class="text-xs font-semibold text-[var(--text-muted)] uppercase tracking-wider mb-2"
						>
							Capabilities
						</h4>
						<div class="flex flex-wrap gap-2">
							{#each agentInfo.capabilities as capability}
								<span
									class="px-3 py-1 bg-[var(--bg-muted)] text-[var(--text-secondary)] text-xs rounded-full border border-[var(--border)]"
								>
									{capability}
								</span>
							{/each}
						</div>
					</div>
				{/if}

				<div class="markdown-preview max-w-none prose prose-slate dark:prose-invert">
					{@html renderedAgentContent}
				</div>
			{/snippet}
		</CollapsibleGroup>
	{/if}

	<!-- Tab Navigation -->
	<div class="flex items-center justify-between">
		<SegmentedControl options={tabOptions} bind:value={activeTab} />

		{#if data.detail?.last_used}
			<span class="text-sm text-[var(--text-muted)]">
				Last used {formatDistanceToNow(new Date(data.detail.last_used))} ago
			</span>
		{/if}
	</div>

	<!-- Tab Content -->
	{#if activeTab === 'overview'}
		{#if data.detail}
			<!-- Usage Trend Chart -->
			{#if trendData.length > 0}
				<div
					class="bg-[var(--bg-base)] border border-[var(--border)] rounded-xl p-6 shadow-sm hover:shadow-md transition-shadow"
				>
					<div class="flex items-center gap-2 mb-4">
						<TrendingUp size={18} style="color: {colorVars.color};" />
						<h3 class="text-lg font-bold text-[var(--text-primary)]">Usage Trend</h3>
						<span class="text-xs text-[var(--text-muted)] ml-auto">Last 90 days</span>
					</div>
					<AgentTrendChart trend={trendData} cssColor={chartHex ?? colorVars.color} />
				</div>
			{/if}

			<!-- Usage by Project — full-width horizontal bar -->
			<div
				class="bg-[var(--bg-base)] border border-[var(--border)] rounded-xl p-6 shadow-sm hover:shadow-md transition-shadow"
			>
				<div class="flex items-center gap-2 mb-6">
					<FolderOpen size={18} class="text-[var(--text-muted)]" />
					<h3 class="text-lg font-bold text-[var(--text-primary)]">
						Usage by Project
					</h3>
				</div>

				{#if sortedProjects.length === 0}
					<p class="text-sm text-[var(--text-muted)]">No project data available</p>
				{:else}
					<div class="space-y-3.5 stagger-children">
						{#each sortedProjects as [project, count]}
							<div class="group">
								<div class="flex items-center justify-between mb-2">
									<a
										href="/projects/{project}"
										class="text-sm text-[var(--accent)] font-semibold truncate max-w-[70%] hover:underline"
										title={getProjectDisplayName(project)}
									>
										{getProjectDisplayName(project)}
									</a>
									<span
										class="text-sm text-[var(--text-primary)] tabular-nums font-semibold"
									>
										{count.toLocaleString()} run{count !== 1 ? 's' : ''}
									</span>
								</div>
								<div
									class="h-2 bg-[var(--bg-subtle)] rounded-full overflow-hidden"
								>
									<div
										class="h-full rounded-full transition-all duration-300 ease-out"
										style="width: {(count / maxProjectCount) *
											100}%; background-color: {colorVars.color};"
									></div>
								</div>
							</div>
						{/each}
					</div>
				{/if}
			</div>

			<div class="grid grid-cols-1 lg:grid-cols-2 gap-6">
				<!-- Token Usage Card -->
				<div
					class="bg-[var(--bg-base)] border border-[var(--border)] rounded-xl p-6 shadow-sm hover:shadow-md transition-shadow"
				>
					<div class="flex items-center gap-2 mb-6">
						<Hash size={18} class="text-[var(--text-muted)]" />
						<h3 class="text-lg font-bold text-[var(--text-primary)]">Token Usage</h3>
					</div>

					<!-- Total tokens with gradient text -->
					<div class="mb-6">
						<p class="text-4xl font-bold gradient-text tabular-nums">
							{totalTokens.toLocaleString()}
						</p>
						<p class="text-xs text-[var(--text-muted)] mt-1">total tokens processed</p>
					</div>

					<!-- Enhanced visual breakdown bar -->
					<div class="mb-4">
						<div
							class="flex h-4 rounded-full overflow-hidden bg-[var(--bg-muted)] shadow-inner"
						>
							<div
								class="transition-all duration-300 ease-out"
								style="width: {inputPercent}%; background: linear-gradient(90deg, var(--accent) 0%, #a78bfa 100%);"
								title="Input: {data.detail.total_input_tokens.toLocaleString()}"
							></div>
							<div
								class="transition-all duration-300 ease-out"
								style="width: {outputPercent}%; background: linear-gradient(90deg, var(--nav-teal) 0%, #5eead4 100%);"
								title="Output: {data.detail.total_output_tokens.toLocaleString()}"
							></div>
						</div>
					</div>

					<!-- Enhanced legend -->
					<div class="grid grid-cols-2 gap-3 text-xs">
						<div
							class="flex items-center gap-2 text-[var(--text-secondary)] bg-[var(--bg-subtle)] rounded-lg p-2.5"
						>
							<span
								class="w-3 h-3 rounded-full"
								style="background: linear-gradient(135deg, var(--accent) 0%, #a78bfa 100%);"
							></span>
							<div class="flex-1 min-w-0">
								<div class="font-medium">Input</div>
								<div
									class="text-[var(--text-primary)] font-semibold tabular-nums truncate"
								>
									{data.detail.total_input_tokens.toLocaleString()}
								</div>
							</div>
						</div>
						<div
							class="flex items-center gap-2 text-[var(--text-secondary)] bg-[var(--bg-subtle)] rounded-lg p-2.5"
						>
							<span
								class="w-3 h-3 rounded-full"
								style="background: linear-gradient(135deg, var(--nav-teal) 0%, #5eead4 100%);"
							></span>
							<div class="flex-1 min-w-0">
								<div class="font-medium">Output</div>
								<div
									class="text-[var(--text-primary)] font-semibold tabular-nums truncate"
								>
									{data.detail.total_output_tokens.toLocaleString()}
								</div>
							</div>
						</div>
					</div>
				</div>

				<!-- Timeline & Stats Card -->
				<div
					class="bg-[var(--bg-base)] border border-[var(--border)] rounded-xl p-6 shadow-sm hover:shadow-md transition-shadow"
				>
					<div class="flex items-center gap-2 mb-6">
						<TrendingUp size={18} class="text-[var(--text-muted)]" />
						<h3 class="text-lg font-bold text-[var(--text-primary)]">
							Activity & Stats
						</h3>
					</div>

					<div class="grid grid-cols-2 gap-3">
						<div class="bg-[var(--bg-subtle)] rounded-lg p-4">
							<p
								class="text-xs text-[var(--text-muted)] uppercase tracking-wider font-semibold mb-2"
							>
								First Used
							</p>
							<p class="text-base font-semibold text-[var(--text-primary)]">
								{#if data.detail.first_used}
									{formatDistanceToNow(new Date(data.detail.first_used))} ago
								{:else}
									Unknown
								{/if}
							</p>
						</div>
						<div class="bg-[var(--bg-subtle)] rounded-lg p-4">
							<p
								class="text-xs text-[var(--text-muted)] uppercase tracking-wider font-semibold mb-2"
							>
								Last Used
							</p>
							<p class="text-base font-semibold text-[var(--text-primary)]">
								{#if data.detail.last_used}
									{formatDistanceToNow(new Date(data.detail.last_used))} ago
								{:else}
									Unknown
								{/if}
							</p>
						</div>
						<div class="bg-[var(--bg-subtle)] rounded-lg p-4">
							<p
								class="text-xs text-[var(--text-muted)] uppercase tracking-wider font-semibold mb-2"
							>
								Total Time
							</p>
							<p class="text-base font-semibold text-[var(--text-primary)]">
								{formatDuration(
									data.detail.avg_duration_seconds * data.detail.total_runs
								)}
							</p>
						</div>
						<div class="bg-[var(--bg-subtle)] rounded-lg p-4">
							<p
								class="text-xs text-[var(--text-muted)] uppercase tracking-wider font-semibold mb-2"
							>
								Avg Cost/Run
							</p>
							<p class="text-base font-semibold text-[var(--text-primary)]">
								{formatCost(data.detail.total_cost_usd / data.detail.total_runs)}
							</p>
						</div>
					</div>
				</div>
			</div>
		{:else}
			<div
				class="text-center py-12 bg-[var(--bg-subtle)] rounded-xl border border-dashed border-[var(--border)]"
			>
				<Play class="mx-auto text-[var(--text-muted)] mb-3" size={36} />
				<p class="text-sm text-[var(--text-muted)]">No usage overview available yet</p>
			</div>
		{/if}
	{:else if activeTab === 'activity'}
		{#if data.detail}
			<!-- Activity Summary Stats -->
			<div class="grid grid-cols-3 gap-4">
				<div class="bg-[var(--bg-base)] border border-[var(--border)] rounded-xl p-5 text-center">
					<div class="flex items-center justify-center gap-2 mb-2">
						<Wrench size={16} style="color: {colorVars.color};" />
						<span class="text-xs font-semibold text-[var(--text-muted)] uppercase tracking-wider">Tools</span>
					</div>
					<p class="text-2xl font-bold text-[var(--text-primary)] tabular-nums">{sortedTools.length}</p>
					<p class="text-xs text-[var(--text-muted)] mt-1">{totalToolUses.toLocaleString()} total uses</p>
				</div>
				<div class="bg-[var(--bg-base)] border border-[var(--border)] rounded-xl p-5 text-center">
					<div class="flex items-center justify-center gap-2 mb-2">
						<Zap size={16} style="color: {colorVars.color};" />
						<span class="text-xs font-semibold text-[var(--text-muted)] uppercase tracking-wider">Skills</span>
					</div>
					<p class="text-2xl font-bold text-[var(--text-primary)] tabular-nums">{sortedSkills.length}</p>
					<p class="text-xs text-[var(--text-muted)] mt-1">{totalSkillUses.toLocaleString()} total uses</p>
				</div>
				<div class="bg-[var(--bg-base)] border border-[var(--border)] rounded-xl p-5 text-center">
					<div class="flex items-center justify-center gap-2 mb-2">
						<Terminal size={16} style="color: {colorVars.color};" />
						<span class="text-xs font-semibold text-[var(--text-muted)] uppercase tracking-wider">Commands</span>
					</div>
					<p class="text-2xl font-bold text-[var(--text-primary)] tabular-nums">{sortedCommands.length}</p>
					<p class="text-xs text-[var(--text-muted)] mt-1">{totalCommandUses.toLocaleString()} total uses</p>
				</div>
			</div>

			<!-- Top Tools Used -->
			<div
				class="bg-[var(--bg-base)] border border-[var(--border)] rounded-xl p-6 shadow-sm hover:shadow-md transition-shadow"
			>
				<div class="flex items-center gap-2 mb-6">
					<Wrench size={18} style="color: {colorVars.color};" />
					<h3 class="text-lg font-bold text-[var(--text-primary)]">Top Tools Used</h3>
					<span class="text-xs text-[var(--text-muted)] ml-auto tabular-nums">{sortedTools.length} unique tools</span>
				</div>

				{#if sortedTools.length === 0}
					<p class="text-sm text-[var(--text-muted)]">No tool usage data available</p>
				{:else}
					<div class="space-y-3.5 stagger-children">
						{#each sortedTools as [tool, count]}
							{@const mcp = parseMcpTool(tool)}
							<div class="group">
								<div class="flex items-center justify-between mb-2">
									{#if mcp}
										<a
											href="/tools/{encodeURIComponent(mcp.server)}/{encodeURIComponent(mcp.shortName)}"
											class="text-sm text-[var(--accent)] font-semibold truncate max-w-[70%] hover:underline"
											title={tool}
										>
											{mcp.shortName}
										</a>
									{:else}
										<span
											class="text-sm text-[var(--text-secondary)] font-medium truncate max-w-[70%]"
											title={tool}>{tool}</span
										>
									{/if}
									<span
										class="text-sm text-[var(--text-primary)] tabular-nums font-semibold"
									>
										{count.toLocaleString()}
									</span>
								</div>
								<div
									class="h-2 bg-[var(--bg-subtle)] rounded-full overflow-hidden"
								>
									<div
										class="h-full rounded-full transition-all duration-300 ease-out"
										style="width: {(count / maxToolCount) *
											100}%; background-color: {colorVars.color};"
									></div>
								</div>
							</div>
						{/each}
					</div>
				{/if}
			</div>

			<!-- Skills and Commands in 2-col grid -->
			<div class="grid grid-cols-1 lg:grid-cols-2 gap-6">
				<!-- Top Skills Used -->
				<div
					class="bg-[var(--bg-base)] border border-[var(--border)] rounded-xl p-6 shadow-sm hover:shadow-md transition-shadow"
				>
					<div class="flex items-center gap-2 mb-6">
						<Zap size={18} style="color: {colorVars.color};" />
						<h3 class="text-lg font-bold text-[var(--text-primary)]">Top Skills Used</h3>
					</div>

					{#if sortedSkills.length === 0}
						<div class="text-center py-8">
							<Zap class="mx-auto text-[var(--text-muted)] mb-2" size={24} />
							<p class="text-sm text-[var(--text-muted)]">No skills used by this agent</p>
						</div>
					{:else}
						<div class="space-y-3.5 stagger-children">
							{#each sortedSkills as [skill, count]}
								<div class="group">
									<div class="flex items-center justify-between mb-2">
										<a
											href="/skills/{encodeURIComponent(skill)}"
											class="text-sm text-[var(--accent)] font-semibold truncate max-w-[70%] hover:underline"
											title={skill}
										>
											{skill}
										</a>
										<span
											class="text-sm text-[var(--text-primary)] tabular-nums font-semibold"
										>
											{count.toLocaleString()}
										</span>
									</div>
									<div
										class="h-2 bg-[var(--bg-subtle)] rounded-full overflow-hidden"
									>
										<div
											class="h-full rounded-full transition-all duration-300 ease-out"
											style="width: {(count / maxSkillCount) *
												100}%; background-color: {colorVars.color};"
										></div>
									</div>
								</div>
							{/each}
						</div>
					{/if}
				</div>

				<!-- Top Commands Used -->
				<div
					class="bg-[var(--bg-base)] border border-[var(--border)] rounded-xl p-6 shadow-sm hover:shadow-md transition-shadow"
				>
					<div class="flex items-center gap-2 mb-6">
						<Terminal size={18} style="color: {colorVars.color};" />
						<h3 class="text-lg font-bold text-[var(--text-primary)]">Top Commands Used</h3>
					</div>

					{#if sortedCommands.length === 0}
						<div class="text-center py-8">
							<Terminal class="mx-auto text-[var(--text-muted)] mb-2" size={24} />
							<p class="text-sm text-[var(--text-muted)]">No commands used by this agent</p>
						</div>
					{:else}
						<div class="space-y-3.5 stagger-children">
							{#each sortedCommands as [command, count]}
								<div class="group">
									<div class="flex items-center justify-between mb-2">
										<span
											class="text-sm text-[var(--text-secondary)] font-medium truncate max-w-[70%]"
											title={command}>{command}</span
										>
										<span
											class="text-sm text-[var(--text-primary)] tabular-nums font-semibold"
										>
											{count.toLocaleString()}
										</span>
									</div>
									<div
										class="h-2 bg-[var(--bg-subtle)] rounded-full overflow-hidden"
									>
										<div
											class="h-full rounded-full transition-all duration-300 ease-out"
											style="width: {(count / maxCommandCount) *
												100}%; background-color: {colorVars.color};"
										></div>
									</div>
								</div>
							{/each}
						</div>
					{/if}
				</div>
			</div>
		{:else}
			<div
				class="text-center py-12 bg-[var(--bg-subtle)] rounded-xl border border-dashed border-[var(--border)]"
			>
				<Wrench class="mx-auto text-[var(--text-muted)] mb-3" size={36} />
				<p class="text-sm text-[var(--text-muted)]">No activity data available yet</p>
			</div>
		{/if}
	{:else if activeTab === 'history'}
		<!-- Sessions with Search & Filters (matching skills detail page pattern) -->
		<div class="space-y-4">
			<div class="flex items-center justify-between">
				<div class="flex items-center gap-2 text-sm text-[var(--text-muted)]">
					<Layers size={16} style="color: {colorVars.color};" />
					<span class="font-medium text-[var(--text-primary)]">{totalCount}</span>
					<span>{totalCount === 1 ? 'session' : 'sessions'} using this agent</span>
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
								<div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
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
										<GlobalSessionCard {session} />
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
					description="This agent hasn't been used in any sessions."
				/>
			{/if}
		</div>
	{/if}
</div>

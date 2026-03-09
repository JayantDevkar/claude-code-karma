<script lang="ts">
	import {
		Bot,
		Search,
		Play,
		Clock,
		Cpu,
		Puzzle,
		Wrench,
		FolderOpen,
		ChevronsUpDown,
		ChevronsDownUp,
		ExternalLink
	} from 'lucide-svelte';
	import { navigating } from '$app/stores';
	import { createUrlViewState } from '$lib/utils/url-view-state';
	import { listNavigation } from '$lib/actions/listNavigation';
	import PageHeader from '$lib/components/layout/PageHeader.svelte';
	import SkeletonBox from '$lib/components/skeleton/SkeletonBox.svelte';
	import SkeletonText from '$lib/components/skeleton/SkeletonText.svelte';
	import SkeletonStatsCard from '$lib/components/skeleton/SkeletonStatsCard.svelte';
	import SkeletonAgentCard from '$lib/components/skeleton/SkeletonAgentCard.svelte';
	import StatsGrid from '$lib/components/StatsGrid.svelte';
	import SegmentedControl from '$lib/components/ui/SegmentedControl.svelte';
	import CollapsibleGroup from '$lib/components/ui/CollapsibleGroup.svelte';
	import AgentUsageCard from '$lib/components/agents/AgentUsageCard.svelte';
	import AgentUsageTable from '$lib/components/agents/AgentUsageTable.svelte';
	import UsageAnalytics from '$lib/components/charts/UsageAnalytics.svelte';
	import MemberUsageGrid from '$lib/components/members/MemberUsageGrid.svelte';
	import type { AgentCategory, AgentUsageSummary, StatItem } from '$lib/api-types';
	import {
		formatTokens,
		getSubagentColorVars,
		getPluginColorVars,
		getScopeColorVars,
		getSubagentChartHex,
		getSubagentTypeDisplayName
	} from '$lib/utils';

	// Server data — loaded once, never re-fetched on tab switch
	let { data } = $props();

	// Pure client-side filter state (no goto, no navigation, no flicker)
	let searchQuery = $state('');
	let selectedCategory = $state<AgentCategory>('all');
	let viewMode = $state<'agents' | 'table' | 'analytics' | 'members'>('agents');
	const validViews = ['agents', 'table', 'analytics', 'members'] as const;

	// URL state persistence for view mode
	const { initFromUrl, syncToUrl } = createUrlViewState(
		'agents', validViews,
		() => viewMode, (v) => viewMode = v
	);
	$effect(initFromUrl);
	$effect(syncToUrl);

	// Reset sub-filter when entering members view
	$effect(() => { if (viewMode === 'members') selectedCategory = 'all'; });

	const viewOptions = [
		{ label: 'By Category', value: 'agents' },
		{ label: 'All Agents', value: 'table' },
		{ label: 'Usage Analytics', value: 'analytics' },
		{ label: 'By Member', value: 'members' }
	];

	// Category filter options — dynamically built from actual data so empty categories are hidden
	const allCategoryDefs: { label: string; value: string }[] = [
		{ label: 'Built-in', value: 'builtin' },
		{ label: 'Plugins', value: 'plugin' },
		{ label: 'Custom', value: 'custom' },
		{ label: 'Project', value: 'project' },
		{ label: 'Claude Tax', value: 'claude_tax' },
		{ label: 'Unknown', value: 'unknown' }
	];
	let categoryOptions = $derived([
		{ label: 'All', value: 'all' },
		...allCategoryDefs.filter((c) => (data.usage.by_category[c.value] ?? 0) > 0)
	]);

	// Stats from full dataset (unfiltered)
	let stats = $derived<StatItem[]>([
		{
			title: 'Total Agents',
			value: data.usage.total,
			icon: Bot,
			color: 'purple'
		},
		{
			title: 'Total Runs',
			value: data.usage.total_runs.toLocaleString(),
			icon: Play,
			color: 'blue'
		},
		{
			title: 'Tokens In',
			value: formatTokens(
				data.usage.agents.reduce((sum, a) => sum + a.total_input_tokens, 0)
			),
			icon: Cpu,
			color: 'green'
		},
		{
			title: 'Tokens Out',
			value: formatTokens(
				data.usage.agents.reduce((sum, a) => sum + a.total_output_tokens, 0)
			),
			icon: Cpu,
			color: 'orange'
		}
	]);

	// Client-side filtering — instant, no round-trip (matches skills page pattern)
	let filteredAgents = $derived.by(() => {
		let agents = data.usage.agents;

		if (selectedCategory !== 'all') {
			agents = agents.filter((a) => a.category === selectedCategory);
		}

		if (searchQuery.trim()) {
			const q = searchQuery.toLowerCase();
			agents = agents.filter(
				(a) =>
					a.agent_name.toLowerCase().includes(q) ||
					(a.subagent_type && a.subagent_type.toLowerCase().includes(q)) ||
					(a.plugin_source && a.plugin_source.toLowerCase().includes(q))
			);
		}

		return agents;
	});

	let maxRuns = $derived(
		filteredAgents.length > 0 ? Math.max(...filteredAgents.map((a) => a.total_runs)) : 100
	);

	// Group agents by category or plugin source for display
	interface AgentGroup {
		key: string;
		label: string;
		icon: typeof Bot;
		agents: AgentUsageSummary[];
		pluginName: string | null;
	}

	let groupedAgents = $derived.by<AgentGroup[]>(() => {
		const agents = filteredAgents;
		const groups: Map<string, AgentGroup> = new Map();

		for (const agent of agents) {
			let groupKey: string;
			let groupLabel: string;
			let groupIcon: typeof Bot;
			let pluginName: string | null = null;

			if (agent.category === 'plugin' && agent.plugin_source) {
				groupKey = `plugin:${agent.plugin_source}`;
				groupLabel = agent.plugin_source;
				groupIcon = Puzzle;
				pluginName = agent.plugin_source;
			} else if (agent.category === 'builtin') {
				groupKey = 'builtin';
				groupLabel = 'Built-in Agents';
				groupIcon = Bot;
			} else if (agent.category === 'custom') {
				groupKey = 'custom';
				groupLabel = 'Custom Agents';
				groupIcon = Wrench;
			} else if (agent.category === 'project') {
				groupKey = 'project';
				groupLabel = 'Project Agents';
				groupIcon = FolderOpen;
			} else if (agent.category === 'claude_tax') {
				groupKey = 'claude_tax';
				groupLabel = 'Claude Tax';
				groupIcon = Cpu;
			} else if (agent.category === 'unknown') {
				groupKey = 'unknown';
				groupLabel = 'Unclassified Agents';
				groupIcon = Bot;
			} else {
				groupKey = 'other';
				groupLabel = 'Other Agents';
				groupIcon = Bot;
			}

			if (!groups.has(groupKey)) {
				groups.set(groupKey, {
					key: groupKey,
					label: groupLabel,
					icon: groupIcon,
					agents: [],
					pluginName
				});
			}
			groups.get(groupKey)!.agents.push(agent);
		}

		const sortOrder = ['builtin', 'custom', 'project', 'claude_tax', 'unknown'];
		return Array.from(groups.values()).sort((a, b) => {
			const aOrder = sortOrder.indexOf(a.key);
			const bOrder = sortOrder.indexOf(b.key);
			if (aOrder !== -1 && bOrder !== -1) return aOrder - bOrder;
			if (aOrder !== -1) return -1;
			if (bOrder !== -1) return 1;
			return a.label.localeCompare(b.label);
		});
	});

	// Track which groups are expanded (all collapsed by default, matching tools page)
	let expandedGroups = $state<Set<string>>(new Set());
	// Snapshot of expanded groups before search
	let previousExpandedGroups = $state<Set<string> | null>(null);

	// Auto-expand/restore logic
	$effect(() => {
		const hasSearch = searchQuery.trim().length > 0;

		if (hasSearch) {
			// Snapshot state if starting a new search
			if (previousExpandedGroups === null) {
				previousExpandedGroups = new Set(expandedGroups);
			}
			// Auto-expand all matching groups
			if (groupedAgents.length > 0) {
				expandedGroups = new Set(groupedAgents.map((g) => g.key));
			}
		} else {
			// Restore previous state if clearing search
			if (previousExpandedGroups !== null) {
				expandedGroups = previousExpandedGroups;
				previousExpandedGroups = null;
			}
		}
	});

	function toggleGroup(key: string) {
		if (expandedGroups.has(key)) {
			expandedGroups.delete(key);
		} else {
			expandedGroups.add(key);
		}
		expandedGroups = new Set(expandedGroups);
	}

	let allExpanded = $derived(
		groupedAgents.length > 0 && groupedAgents.every((g) => expandedGroups.has(g.key))
	);

	function expandAll() {
		expandedGroups = new Set(groupedAgents.map((g) => g.key));
	}

	function collapseAll() {
		expandedGroups = new Set();
	}

	function toggleAllGroups() {
		if (allExpanded) {
			collapseAll();
		} else {
			expandAll();
		}
	}

	// Agents with definitions but no usage data
	let unusedDefinitions = $derived.by(() => {
		const usedNames = new Set(data.usage.agents.map((a) => a.agent_name));
		return data.definitions.filter((d) => !usedNames.has(d.name));
	});

	// Build a category lookup from agent data for analytics filtering
	// Key by subagent_type since that's what the trend API uses in by_item
	let agentCategoryMap = $derived.by(() => {
		const map = new Map<string, string>();
		for (const agent of data.usage.agents) {
			map.set(agent.subagent_type, agent.category);
		}
		return map;
	});

	let excludeFn = $derived.by(() => {
		if (selectedCategory === 'all') return undefined;
		return (name: string) => agentCategoryMap.get(name) !== selectedCategory;
	});

	let hasAgents = $derived(data.usage.agents.length > 0 || unusedDefinitions.length > 0);
	let hasFilteredAgents = $derived(filteredAgents.length > 0);

	let isPageLoading = $derived(!!$navigating && $navigating.to?.route.id === '/agents');
</script>

<div class="space-y-8">
	{#if isPageLoading}
		<div class="space-y-8" role="status" aria-busy="true" aria-label="Loading...">
			<!-- Page Header skeleton -->
			<div>
				<div class="flex items-center gap-2 mb-2">
					<SkeletonText width="70px" size="xs" />
					<span class="text-[var(--text-muted)]">/</span>
					<SkeletonText width="50px" size="xs" />
				</div>
				<div class="flex items-center gap-4">
					<SkeletonBox width="48px" height="48px" rounded="lg" />
					<div>
						<SkeletonText width="100px" size="xl" class="mb-2" />
						<SkeletonText width="300px" size="sm" />
					</div>
				</div>
			</div>

			<!-- Hero Stats skeleton -->
			<div
				class="relative overflow-hidden rounded-2xl p-8 border border-[var(--border)]"
				style="background: linear-gradient(135deg, rgba(124, 58, 237, 0.02) 0%, rgba(124, 58, 237, 0.06) 100%);"
			>
				<div class="relative grid grid-cols-1 sm:grid-cols-4 gap-4">
					{#each Array(4) as _}
						<SkeletonStatsCard />
					{/each}
				</div>
			</div>

			<!-- Filters row skeleton -->
			<div class="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
				<div class="flex items-center gap-3 flex-wrap">
					<div class="flex gap-1">
						{#each Array(3) as _}
							<SkeletonBox width="110px" height="36px" rounded="lg" />
						{/each}
					</div>
					<div class="flex gap-1">
						{#each Array(5) as _}
							<SkeletonBox width="70px" height="32px" rounded="lg" />
						{/each}
					</div>
				</div>
				<div class="flex items-center gap-3">
					<SkeletonBox width="256px" height="40px" rounded="lg" />
					<SkeletonBox width="120px" height="40px" rounded="lg" />
				</div>
			</div>

			<!-- Collapsible agent groups skeleton -->
			<div class="space-y-4">
				{#each Array(2) as _, groupIndex}
					<div class="border border-[var(--border)] rounded-[var(--radius-lg)] overflow-hidden bg-[var(--bg-base)]">
						<div class="flex items-center gap-3 px-4 py-4">
							<SkeletonBox width="16px" height="16px" rounded="sm" />
							<SkeletonBox width="32px" height="32px" rounded="md" />
							<SkeletonText width="120px" size="sm" />
							<div class="flex-1"></div>
							<SkeletonText width="60px" size="xs" />
						</div>
						{#if groupIndex === 0}
							<div class="border-t border-[var(--border)] p-4">
								<div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-5">
									{#each Array(3) as _}
										<SkeletonAgentCard />
									{/each}
								</div>
							</div>
						{/if}
					</div>
				{/each}
			</div>
		</div>
	{:else}
	<!-- Page Header -->
	<PageHeader
		title="Agents"
		icon={Bot}
		iconColor="--nav-purple"
		breadcrumbs={[{ label: 'Dashboard', href: '/' }, { label: 'Agents' }]}
		subtitle="View agent usage analytics and manage custom agent definitions"
	/>

	<!-- Hero Stats -->
	{#if hasAgents}
		<div
			class="relative overflow-hidden rounded-2xl p-8 border border-[var(--border)]"
			style="background: linear-gradient(135deg, rgba(124, 58, 237, 0.02) 0%, rgba(124, 58, 237, 0.06) 100%);"
		>
			<div
				class="absolute -top-24 -right-24 w-96 h-96 bg-violet-500/5 rounded-full blur-3xl pointer-events-none"
			></div>
			<div
				class="absolute -bottom-24 -left-24 w-64 h-64 bg-blue-500/3 rounded-full blur-3xl pointer-events-none"
			></div>
			<div class="relative">
				<StatsGrid {stats} columns={4} />
			</div>
		</div>
	{/if}

	<!-- Filters Row -->
	<div
		class="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4"
		use:listNavigation
	>
		<div class="flex items-center gap-3 flex-wrap">
			<SegmentedControl options={viewOptions} bind:value={viewMode} />
			{#if viewMode !== 'members'}
				<SegmentedControl options={categoryOptions} bind:value={selectedCategory} size="sm" />
			{/if}
		</div>

		{#if viewMode !== 'analytics' && viewMode !== 'members'}
			<div class="flex items-center gap-3 w-full sm:w-auto">
				<div class="relative flex-1 sm:flex-initial">
					<Search
						class="absolute left-3 top-1/2 -translate-y-1/2 text-[var(--text-muted)]"
						size={16}
					/>
					<input
						type="text"
						bind:value={searchQuery}
						placeholder="Search agents..."
						class="
							pl-9 pr-4 py-2
							bg-[var(--bg-base)]
							border border-[var(--border)]
							rounded-lg text-sm
							focus:outline-none focus:border-[var(--accent)] focus:ring-2 focus:ring-[var(--accent)]/20
							w-full sm:w-64
							transition-all
							text-[var(--text-primary)]
							placeholder:text-[var(--text-faint)]
						"
						data-search-input
					/>
				</div>

				{#if viewMode === 'agents' && groupedAgents.length > 1}
					<button
						onclick={toggleAllGroups}
						class="
							flex items-center gap-1.5 px-3 py-2
							text-sm font-medium
							text-[var(--text-secondary)]
							hover:text-[var(--text-primary)]
							bg-[var(--bg-base)]
							border border-[var(--border)]
							rounded-lg
							transition-all
							hover:bg-[var(--bg-subtle)]
							whitespace-nowrap
						"
						title={allExpanded ? 'Collapse all groups' : 'Expand all groups'}
					>
						{#if allExpanded}
							<ChevronsDownUp size={16} />
							<span class="hidden sm:inline">Collapse All</span>
						{:else}
							<ChevronsUpDown size={16} />
							<span class="hidden sm:inline">Expand All</span>
						{/if}
					</button>
				{/if}
			</div>
		{/if}
	</div>

	<!-- Content Area -->
	{#if viewMode === 'members'}
		<!-- By Member View -->
		<MemberUsageGrid
			endpoint="/agents/usage/trend"
			domainLabel="Agents"
			domainIcon={Bot}
			excludeItemFn={excludeFn}
		/>
	{:else if viewMode === 'analytics'}
		<!-- Usage Analytics View -->
		<UsageAnalytics
			endpoint="/agents/usage/trend"
			itemLabel="Agents"
			colorFn={getSubagentChartHex}
			excludeItemFn={excludeFn}
			itemLinkPrefix="/agents/"
			itemDisplayFn={getSubagentTypeDisplayName}
		/>
	{:else if !hasAgents}
		<div
			class="text-center py-20 bg-[var(--bg-subtle)] rounded-2xl border border-dashed border-[var(--border)]"
		>
			<Bot class="mx-auto text-[var(--text-muted)] mb-3" size={48} />
			<p class="text-[var(--text-secondary)] font-medium">No agents found</p>
			<p class="text-sm text-[var(--text-muted)] mt-1">
				Agent usage data will appear here once you start using Claude Code
			</p>
		</div>
	{:else if !hasFilteredAgents}
		<div
			class="text-center py-20 bg-[var(--bg-subtle)] rounded-2xl border border-dashed border-[var(--border)]"
		>
			<Search class="mx-auto text-[var(--text-muted)] mb-3" size={48} />
			<p class="text-[var(--text-secondary)] font-medium">No matching agents</p>
			<p class="text-sm text-[var(--text-muted)] mt-1">
				Try adjusting your search or category filter
			</p>
		</div>
	{:else if viewMode === 'table'}
		<!-- Flat Table View -->
		<AgentUsageTable agents={filteredAgents} />
	{:else}
		<!-- Grouped Agent Display -->
		<div class="space-y-4">
			{#each groupedAgents as group (group.key)}
				{@const groupColors = group.pluginName
					? getPluginColorVars(group.pluginName)
					: group.key === 'project'
						? getScopeColorVars('project')
						: group.key === 'custom'
							? getScopeColorVars('user')
							: { color: 'var(--text-muted)', subtle: 'var(--bg-subtle)' }}
				<CollapsibleGroup
					title={group.label}
					open={expandedGroups.has(group.key)}
					onOpenChange={() => toggleGroup(group.key)}
					accentColor={groupColors.color}
				>
					{#snippet icon()}
						{@const GroupIcon = group.icon}
						<div
							class="p-1.5 rounded-md"
							style="background-color: {groupColors.subtle}; color: {groupColors.color};"
						>
							<GroupIcon size={14} />
						</div>
					{/snippet}
					{#snippet metadata()}
						<div class="flex items-center gap-3">
							<span class="text-xs text-[var(--text-muted)] tabular-nums">
								{group.agents.length} agent{group.agents.length !== 1 ? 's' : ''}
							</span>
							{#if group.pluginName}
								<a
									href="/plugins/{encodeURIComponent(group.pluginName)}"
									class="
										inline-flex items-center gap-1 px-2 py-0.5
										text-[10px] font-medium
										text-[var(--accent)] hover:text-[var(--text-primary)]
										bg-[var(--accent-subtle)] hover:bg-[var(--bg-muted)]
										rounded-full
										transition-colors
									"
									onclick={(e) => e.stopPropagation()}
									title="View plugin"
								>
									<Puzzle size={10} />
									View plugin
									<ExternalLink size={9} />
								</a>
							{/if}
						</div>
					{/snippet}

					<div
						class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-5 stagger-children"
					>
						{#each group.agents as agent (agent.subagent_type)}
							<AgentUsageCard {agent} {maxRuns} />
						{/each}
					</div>
				</CollapsibleGroup>
			{/each}
		</div>

		<!-- Defined but Unused Agents -->
		{#if unusedDefinitions.length > 0 && (selectedCategory === 'all' || selectedCategory === 'custom')}
			<CollapsibleGroup
				title="Available Agents"
				open={expandedGroups.has('available')}
				onOpenChange={() => toggleGroup('available')}
			>
				{#snippet icon()}
					<div class="p-1.5 bg-[var(--bg-subtle)] rounded-md">
						<Bot size={14} class="text-[var(--text-muted)]" />
					</div>
				{/snippet}
				{#snippet metadata()}
					<span class="text-xs text-[var(--text-muted)] tabular-nums">
						{unusedDefinitions.length} agent{unusedDefinitions.length !== 1 ? 's' : ''} &middot;
						no usage yet
					</span>
				{/snippet}

				<div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-5 stagger-children">
					{#each unusedDefinitions as def (def.name)}
						{@const colorVars = getSubagentColorVars(def.name)}
						<a
							href="/agents/{encodeURIComponent(def.name)}"
							class="
								group block
								bg-[var(--bg-base)]
								border border-[var(--border)]
								rounded-xl
								p-6
								shadow-sm hover:shadow-xl hover:-translate-y-1
								transition-all duration-300
								relative overflow-hidden
								focus:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent)] focus-visible:ring-offset-2
							"
							style="border-left: 4px solid {colorVars.color}; opacity: 0.75;"
							data-list-item
						>
							<div class="flex items-start justify-between mb-5">
								<div
									class="p-3 rounded-xl transition-all duration-300 group-hover:scale-110"
									style="background-color: {colorVars.subtle}; color: {colorVars.color};"
								>
									<Bot size={22} strokeWidth={2.5} />
								</div>
								<span
									class="px-2.5 py-1 rounded-full text-[10px] font-semibold uppercase tracking-wider bg-[var(--bg-subtle)] text-[var(--text-muted)]"
								>
									Custom
								</span>
							</div>

							<h3
								class="text-lg font-bold text-[var(--text-primary)] mb-4 truncate pr-4 tracking-tight group-hover:text-[var(--accent)] transition-colors"
							>
								{def.name}
							</h3>

							<div
								class="flex items-center justify-between text-xs text-[var(--text-muted)] pt-4 border-t border-[var(--border-subtle)]"
							>
								<span class="flex items-center gap-1.5">
									<Play size={12} />
									<span>0 runs</span>
								</span>
								<span class="flex items-center gap-1.5">
									<Clock size={12} />
									<span>Never used</span>
								</span>
							</div>
						</a>
					{/each}
				</div>
			</CollapsibleGroup>
		{/if}

	{/if}
	{/if}
</div>

<script lang="ts">
	import {
		Cable,
		Wrench,
		Play,
		Activity,
		Search,
		ChevronsUpDown,
		ChevronsDownUp,
		ExternalLink,
		Puzzle
	} from 'lucide-svelte';
	import { navigating } from '$app/stores';
	import { createUrlViewState } from '$lib/utils/url-view-state';
	import { listNavigation } from '$lib/actions/listNavigation';
	import PageHeader from '$lib/components/layout/PageHeader.svelte';
	import SkeletonBox from '$lib/components/skeleton/SkeletonBox.svelte';
	import SkeletonText from '$lib/components/skeleton/SkeletonText.svelte';
	import SkeletonStatsCard from '$lib/components/skeleton/SkeletonStatsCard.svelte';
	import StatsGrid from '$lib/components/StatsGrid.svelte';
	import SegmentedControl from '$lib/components/ui/SegmentedControl.svelte';
	import CollapsibleGroup from '$lib/components/ui/CollapsibleGroup.svelte';
	import Badge from '$lib/components/ui/Badge.svelte';
	import McpServerIcon from '$lib/components/tools/McpServerIcon.svelte';
	import McpToolCard from '$lib/components/tools/McpToolCard.svelte';
	import McpToolTable from '$lib/components/tools/McpToolTable.svelte';
	import McpContextBar from '$lib/components/tools/McpContextBar.svelte';
	import { getServerColorVars, getToolItemChartHex, parseBuiltinTool, parseMcpTool } from '$lib/utils/mcp';
	import UsageAnalytics from '$lib/components/charts/UsageAnalytics.svelte';
	import MemberUsageGrid from '$lib/components/members/MemberUsageGrid.svelte';
	import type { McpServer, StatItem } from '$lib/api-types';

	let { data } = $props();

	// Client-side filter state
	let searchQuery = $state('');
	let viewMode = $state<'servers' | 'tools' | 'analytics' | 'members'>('servers');
	let sourceFilter = $state<'all' | 'plugin' | 'standalone' | 'builtin'>('all');
	const validViews = ['servers', 'tools', 'analytics', 'members'] as const;

	// URL state persistence for view mode
	const { initFromUrl, syncToUrl } = createUrlViewState(
		'servers', validViews,
		() => viewMode, (v) => viewMode = v
	);
	$effect(initFromUrl);
	$effect(syncToUrl);

	// Reset sub-filter when entering members view
	$effect(() => { if (viewMode === 'members') sourceFilter = 'all'; });

	const viewOptions = [
		{ label: 'By Server', value: 'servers' },
		{ label: 'All Tools', value: 'tools' },
		{ label: 'Usage Analytics', value: 'analytics' },
		{ label: 'By Member', value: 'members' }
	];

	const sourceOptions = [
		{ label: 'All', value: 'all' },
		{ label: 'Built-in', value: 'builtin' },
		{ label: 'Plugin', value: 'plugin' },
		{ label: 'Standalone', value: 'standalone' }
	];

	// Hero stats
	let stats = $derived<StatItem[]>([
		{
			title: 'Servers',
			value: data.overview.total_servers,
			icon: Cable,
			color: 'teal'
		},
		{
			title: 'Tools',
			value: data.overview.total_tools,
			icon: Wrench,
			color: 'blue'
		},
		{
			title: 'Total Calls',
			value: data.overview.total_calls.toLocaleString(),
			icon: Play,
			color: 'purple'
		},
		{
			title: 'Sessions',
			value: data.overview.total_sessions,
			icon: Activity,
			color: 'green'
		}
	]);

	// Filtered servers
	let filteredServers = $derived.by(() => {
		let servers = data.overview.servers;

		if (sourceFilter !== 'all') {
			servers = servers.filter((s) => s.source === sourceFilter);
		}

		if (searchQuery.trim()) {
			const q = searchQuery.toLowerCase();
			return servers
				.map((server) => {
					// Check if server name matches query (show all tools)
					const nameMatches =
						server.display_name.toLowerCase().includes(q) ||
						server.name.toLowerCase().includes(q);

					if (nameMatches) {
						return server;
					}

					// Filter tools
					const matchingTools = server.tools.filter((t) =>
						t.name.toLowerCase().includes(q)
					);

					// Return server with filtered tools if any match
					if (matchingTools.length > 0) {
						return { ...server, tools: matchingTools };
					}

					return null;
				})
				.filter((s) => s !== null); // Remove nulls (servers with no matches)
		}

		return servers;
	});

	// Expand/collapse state
	let expandedServers = $state<Set<string>>(new Set());
	let previousExpandedServers = $state<Set<string> | null>(null);

	// Auto-expand/restore logic
	$effect(() => {
		const hasSearch = searchQuery.trim().length > 0;

		if (hasSearch) {
			if (previousExpandedServers === null) {
				previousExpandedServers = new Set(expandedServers);
			}
			if (filteredServers.length > 0) {
				expandedServers = new Set(filteredServers.map((s) => s.name));
			}
		} else {
			if (previousExpandedServers !== null) {
				expandedServers = previousExpandedServers;
				previousExpandedServers = null;
			}
		}
	});

	// All sections collapsed by default — user can expand individually or use Expand All

	function toggleServer(name: string) {
		if (expandedServers.has(name)) {
			expandedServers.delete(name);
		} else {
			expandedServers.add(name);
		}
		expandedServers = new Set(expandedServers);
	}

	let allExpanded = $derived(
		filteredServers.length > 0 && filteredServers.every((s) => expandedServers.has(s.name))
	);

	function toggleAllGroups() {
		if (allExpanded) {
			expandedServers = new Set();
		} else {
			expandedServers = new Set(filteredServers.map((s) => s.name));
		}
	}

	// Max calls across all tools (for tier badge computation)
	let globalMaxCalls = $derived.by(() => {
		let max = 0;
		for (const server of data.overview.servers) {
			for (const tool of server.tools) {
				if (tool.calls > max) max = tool.calls;
			}
		}
		return max || 100;
	});

	// Build a source lookup from server data for analytics filtering
	let toolSourceMap = $derived.by(() => {
		const map = new Map<string, string>();
		for (const server of data.overview.servers) {
			for (const tool of server.tools) {
				map.set(tool.full_name, server.source);
			}
		}
		return map;
	});

	let excludeFn = $derived.by(() => {
		if (sourceFilter === 'all') return undefined;
		return (name: string) => toolSourceMap.get(name) !== sourceFilter;
	});

	let hasServers = $derived(data.overview.servers.length > 0);
	let hasFiltered = $derived(filteredServers.length > 0);

	let isPageLoading = $derived(!!$navigating && $navigating.to?.route.id === '/tools');
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
						<SkeletonText width="80px" size="xl" class="mb-2" />
						<SkeletonText width="300px" size="sm" />
					</div>
				</div>
			</div>

			<!-- Hero Stats skeleton -->
			<div
				class="relative overflow-hidden rounded-2xl p-8 border border-[var(--border)]"
				style="background: linear-gradient(135deg, rgba(8, 145, 178, 0.02) 0%, rgba(8, 145, 178, 0.06) 100%);"
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
							<SkeletonBox width="100px" height="36px" rounded="lg" />
						{/each}
					</div>
					<div class="flex gap-1">
						{#each Array(4) as _}
							<SkeletonBox width="80px" height="32px" rounded="lg" />
						{/each}
					</div>
				</div>
				<div class="flex items-center gap-3">
					<SkeletonBox width="256px" height="40px" rounded="lg" />
					<SkeletonBox width="120px" height="40px" rounded="lg" />
				</div>
			</div>

			<!-- Collapsible server groups skeleton -->
			<div class="space-y-4">
				{#each Array(3) as _, groupIndex}
					<div class="border border-[var(--border)] rounded-[var(--radius-lg)] overflow-hidden bg-[var(--bg-base)]">
						<div class="flex items-center gap-3 px-4 py-4">
							<SkeletonBox width="16px" height="16px" rounded="sm" />
							<SkeletonBox width="32px" height="32px" rounded="md" />
							<SkeletonText width="160px" size="sm" />
							<div class="flex-1"></div>
							<SkeletonText width="80px" size="xs" />
						</div>
						{#if groupIndex === 0}
							<div class="border-t border-[var(--border)] p-4">
								<div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-3">
									{#each Array(4) as _}
										<SkeletonBox height="100px" rounded="md" />
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
		title="Tools"
		icon={Wrench}
		iconColor="--nav-teal"
		breadcrumbs={[{ label: 'Dashboard', href: '/' }, { label: 'Tools' }]}
		subtitle="Built-in tools and external MCP integrations"
	/>

	<!-- Hero Stats -->
	{#if hasServers}
		<div
			class="relative overflow-hidden rounded-2xl p-8 border border-[var(--border)]"
			style="background: linear-gradient(135deg, rgba(8, 145, 178, 0.02) 0%, rgba(8, 145, 178, 0.06) 100%);"
		>
			<div
				class="absolute -top-24 -right-24 w-96 h-96 bg-cyan-500/5 rounded-full blur-3xl pointer-events-none"
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
				<SegmentedControl options={sourceOptions} bind:value={sourceFilter} size="sm" />
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
						placeholder="Search servers or tools..."
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

				{#if viewMode === 'servers' && filteredServers.length > 1}
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
						title={allExpanded ? 'Collapse all' : 'Expand all'}
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

	<!-- Content -->
	{#if viewMode === 'members'}
		<!-- By Member View -->
		<MemberUsageGrid
			endpoint="/tools/usage/trend"
			domainLabel="Tools"
			domainIcon={Wrench}
			excludeItemFn={excludeFn}
		/>
	{:else if viewMode === 'analytics'}
		<!-- Usage Analytics View -->
		<UsageAnalytics
			endpoint="/tools/usage/trend"
			itemLabel="Tools"
			colorFn={getToolItemChartHex}
			excludeItemFn={excludeFn}
			itemLinkFn={(name) => {
				const builtin = parseBuiltinTool(name);
				if (builtin) {
					return `/tools/${encodeURIComponent(builtin.server)}/${encodeURIComponent(builtin.shortName)}`;
				}
				const mcp = parseMcpTool(name);
				if (mcp) {
					return `/tools/${encodeURIComponent(mcp.server)}/${encodeURIComponent(mcp.shortName)}`;
				}
				return `/tools/${encodeURIComponent(name)}`;
			}}
			itemDisplayFn={(name) => {
				if (parseBuiltinTool(name)) return name;
				const mcp = parseMcpTool(name);
				if (mcp) {
					const server = mcp.server.replace(/^plugin_/, '');
					return `${server} / ${mcp.shortName}`.replaceAll('_', ' ');
				}
				return name.replaceAll('_', ' ');
			}}
		/>
	{:else if !hasServers}
		<div
			class="text-center py-20 bg-[var(--bg-subtle)] rounded-2xl border border-dashed border-[var(--border)]"
		>
			<Wrench class="mx-auto text-[var(--text-muted)] mb-3" size={48} />
			<p class="text-[var(--text-secondary)] font-medium">No tools found</p>
			<p class="text-sm text-[var(--text-muted)] mt-1">
				Tool usage will appear here once you start using Claude Code
			</p>
		</div>
	{:else if !hasFiltered}
		<div
			class="text-center py-20 bg-[var(--bg-subtle)] rounded-2xl border border-dashed border-[var(--border)]"
		>
			<Search class="mx-auto text-[var(--text-muted)] mb-3" size={48} />
			<p class="text-[var(--text-secondary)] font-medium">No matching servers</p>
			<p class="text-sm text-[var(--text-muted)] mt-1">
				Try adjusting your search or source filter
			</p>
		</div>
	{:else if viewMode === 'tools'}
		<!-- Flat Table View -->
		<McpToolTable servers={filteredServers} />
	{:else}
		<!-- Grouped By Server View -->
		<div class="space-y-4">
			{#each filteredServers as server (server.name)}
				{@const colorVars = getServerColorVars(server.name, server.plugin_name)}
				<CollapsibleGroup
					title={server.display_name}
					open={expandedServers.has(server.name)}
					onOpenChange={() => toggleServer(server.name)}
					accentColor={colorVars.color}
				>
					{#snippet icon()}
						<div
							class="p-1.5 rounded-md"
							style="background-color: {colorVars.subtle}; color: {colorVars.color};"
						>
							<McpServerIcon serverName={server.name} size={14} />
						</div>
					{/snippet}

					{#snippet metadata()}
						<div class="flex items-center gap-3">
							<span class="text-xs text-[var(--text-muted)] tabular-nums">
								{server.total_calls.toLocaleString()} call{server.total_calls !== 1
									? 's'
									: ''} · {server.session_count} session{server.session_count !==
								1
									? 's'
									: ''}
							</span>
							{#if server.plugin_name}
								<a
									href="/plugins/{encodeURIComponent(server.plugin_name)}"
									class="
										inline-flex items-center gap-1 px-2 py-0.5
										text-[10px] font-medium
										hover:text-[var(--text-primary)]
										hover:bg-[var(--bg-muted)]
										rounded-full
										transition-colors
									"
									style="color: {colorVars.color}; background-color: {colorVars.subtle};"
									onclick={(e) => e.stopPropagation()}
									title="View {server.plugin_name} plugin"
								>
									<Puzzle size={10} />
									{server.plugin_name}
								</a>
							{:else}
								<Badge variant="accent" size="sm">
									{server.source}
								</Badge>
							{/if}
						</div>
					{/snippet}

					<div class="space-y-4">
						<!-- Server-level context bar -->
						<div class="flex items-center justify-between">
							<McpContextBar
								mainCalls={server.main_calls}
								subagentCalls={server.subagent_calls}
								accentColor={colorVars.color}
							/>
							<a
								href="/tools/{server.name}"
								class="text-xs text-[var(--accent)] hover:underline flex items-center gap-1"
							>
								View details
								<ExternalLink size={10} />
							</a>
						</div>

						<!-- Tool Cards Grid -->
						<div
							class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-3"
						>
							{#each server.tools.slice(0, 12) as tool (tool.full_name)}
								<a
									href="/tools/{encodeURIComponent(
										server.name
									)}/{encodeURIComponent(tool.name)}"
									class="no-underline"
								>
									<McpToolCard
										{tool}
										serverTotalCalls={server.total_calls}
										maxCalls={globalMaxCalls}
										accentColor={colorVars.color}
									/>
								</a>
							{/each}
						</div>

						{#if server.tools.length > 12}
							<a
								href="/tools/{server.name}"
								class="block text-center text-sm text-[var(--accent)] hover:underline py-2"
							>
								+{server.tools.length - 12} more tools →
							</a>
						{/if}

						<!-- Server footer -->
						<div
							class="flex items-center gap-4 text-xs text-[var(--text-faint)] pt-2 border-t border-[var(--border)]"
						>
							<span>Source: {server.source}</span>
							{#if server.first_used}
								<span
									>First: {new Date(server.first_used).toLocaleDateString()}</span
								>
							{/if}
							{#if server.last_used}
								<span>Last: {new Date(server.last_used).toLocaleDateString()}</span>
							{/if}
						</div>
					</div>
				</CollapsibleGroup>
			{/each}
		</div>
	{/if}
	{/if}
</div>

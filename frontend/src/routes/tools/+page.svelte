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
	import { listNavigation } from '$lib/actions/listNavigation';
	import PageHeader from '$lib/components/layout/PageHeader.svelte';
	import StatsGrid from '$lib/components/StatsGrid.svelte';
	import SegmentedControl from '$lib/components/ui/SegmentedControl.svelte';
	import CollapsibleGroup from '$lib/components/ui/CollapsibleGroup.svelte';
	import Badge from '$lib/components/ui/Badge.svelte';
	import McpServerIcon from '$lib/components/tools/McpServerIcon.svelte';
	import McpToolCard from '$lib/components/tools/McpToolCard.svelte';
	import McpToolTable from '$lib/components/tools/McpToolTable.svelte';
	import McpContextBar from '$lib/components/tools/McpContextBar.svelte';
	import { getServerColorVars } from '$lib/utils/mcp';
	import type { McpServer, StatItem } from '$lib/api-types';

	let { data } = $props();

	// Client-side filter state
	let searchQuery = $state('');
	let viewMode = $state<'servers' | 'tools'>('servers');
	let sourceFilter = $state<'all' | 'plugin' | 'standalone'>('all');

	const viewOptions = [
		{ label: 'By Server', value: 'servers' },
		{ label: 'All Tools', value: 'tools' }
	];

	const sourceOptions = [
		{ label: 'All', value: 'all' },
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

	let hasServers = $derived(data.overview.servers.length > 0);
	let hasFiltered = $derived(filteredServers.length > 0);
</script>

<div class="space-y-8">
	<!-- Page Header -->
	<PageHeader
		title="MCP Tools"
		icon={Cable}
		iconColor="--nav-teal"
		breadcrumbs={[{ label: 'Dashboard', href: '/' }, { label: 'Tools' }]}
		subtitle="External integrations via Model Context Protocol"
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
			<SegmentedControl options={sourceOptions} bind:value={sourceFilter} size="sm" />
		</div>

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
	</div>

	<!-- Content -->
	{#if !hasServers}
		<div
			class="text-center py-20 bg-[var(--bg-subtle)] rounded-2xl border border-dashed border-[var(--border)]"
		>
			<Cable class="mx-auto text-[var(--text-muted)] mb-3" size={48} />
			<p class="text-[var(--text-secondary)] font-medium">No MCP tools found</p>
			<p class="text-sm text-[var(--text-muted)] mt-1">
				MCP tool usage will appear here once you use Claude Code with MCP servers
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
</div>

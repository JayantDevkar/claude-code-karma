<script lang="ts">
	import { Puzzle, Search, Bot, Zap, Terminal } from 'lucide-svelte';
	import PageHeader from '$lib/components/layout/PageHeader.svelte';
	import StatsGrid from '$lib/components/StatsGrid.svelte';
	import SegmentedControl from '$lib/components/ui/SegmentedControl.svelte';
	import PluginCard from '$lib/components/plugins/PluginCard.svelte';
	import { SkeletonPluginCard } from '$lib/components/skeleton';
	import { API_BASE } from '$lib/config';
	import type { PluginSummary, PluginsOverview, StatItem } from '$lib/api-types';

	let { data } = $props();

	// Check if data is still loading
	let isLoading = $derived(!data.plugins && !data.error);

	// Progressive usage loading state
	let usageLoaded = $state(false);
	let pluginUsageMap = $state<Record<string, { total_runs: number; estimated_cost_usd: number }>>(
		{}
	);

	// Fetch full usage stats in the background after initial render
	$effect(() => {
		if (data.plugins && typeof window !== 'undefined') {
			fetch(`${API_BASE}/plugins?include_usage=true`)
				.then((r) => r.json())
				.then((full: PluginsOverview) => {
					const map: Record<string, { total_runs: number; estimated_cost_usd: number }> =
						{};
					for (const p of full.plugins) {
						map[p.name] = {
							total_runs: p.total_runs,
							estimated_cost_usd: p.estimated_cost_usd
						};
					}
					pluginUsageMap = map;
					usageLoaded = true;
				})
				.catch(() => {
					usageLoaded = true;
				});
		}
	});

	// Merge usage data into the initial plugin list once loaded
	let enrichedPlugins = $derived.by<PluginSummary[]>(() => {
		const plugins = data.plugins?.plugins || [];
		if (!usageLoaded) return plugins;
		return plugins.map((p) => ({
			...p,
			total_runs: pluginUsageMap[p.name]?.total_runs ?? p.total_runs,
			estimated_cost_usd: pluginUsageMap[p.name]?.estimated_cost_usd ?? p.estimated_cost_usd
		}));
	});

	// Filter state
	let searchQuery = $state('');
	let selectedFilter = $state<'all' | 'official' | 'community'>('all');

	const filterOptions = [
		{ label: 'All', value: 'all' },
		{ label: 'Official', value: 'official' },
		{ label: 'Community', value: 'community' }
	];

	// Compute stats for hero section
	let stats = $derived.by<StatItem[]>(() => {
		const plugins = enrichedPlugins;
		const totalPlugins = plugins.length;
		const totalAgents = plugins.reduce((sum, p) => sum + p.agent_count, 0);
		const totalSkills = plugins.reduce((sum, p) => sum + p.skill_count, 0);
		const totalCommands = plugins.reduce((sum, p) => sum + (p.command_count || 0), 0);

		return [
			{ title: 'Plugins', value: totalPlugins, icon: Puzzle, color: 'purple' },
			{ title: 'Agents', value: totalAgents, icon: Bot, color: 'blue' },
			{ title: 'Skills', value: totalSkills, icon: Zap, color: 'green' },
			{ title: 'Commands', value: totalCommands, icon: Terminal, color: 'teal' }
		];
	});

	// Filter plugins
	let filteredPlugins = $derived.by<PluginSummary[]>(() => {
		let plugins = enrichedPlugins;

		// Filter by type
		if (selectedFilter === 'official') {
			plugins = plugins.filter((p) => p.is_official);
		} else if (selectedFilter === 'community') {
			plugins = plugins.filter((p) => !p.is_official);
		}

		// Filter by search
		if (searchQuery.trim()) {
			const query = searchQuery.toLowerCase();
			plugins = plugins.filter(
				(p) =>
					p.name.toLowerCase().includes(query) ||
					(p.description && p.description.toLowerCase().includes(query))
			);
		}

		return plugins;
	});

	let hasPlugins = $derived(enrichedPlugins.length > 0);
	let hasFilteredPlugins = $derived(filteredPlugins.length > 0);
</script>

<div class="space-y-8">
	<!-- Page Header -->
	<PageHeader
		title="Plugins"
		icon={Puzzle}
		iconColor="--nav-violet"
		breadcrumbs={[{ label: 'Dashboard', href: '/' }, { label: 'Plugins' }]}
		subtitle="View and manage Claude Code plugins"
	/>

	<!-- Hero Stats -->
	{#if hasPlugins}
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
	<div class="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
		<SegmentedControl options={filterOptions} bind:value={selectedFilter} />

		<div class="relative w-full sm:w-64">
			<Search
				class="absolute left-3 top-1/2 -translate-y-1/2 text-[var(--text-muted)]"
				size={16}
			/>
			<input
				type="text"
				bind:value={searchQuery}
				placeholder="Search plugins..."
				class="pl-9 pr-4 py-2 w-full bg-[var(--bg-base)] border border-[var(--border)] rounded-lg text-sm focus:outline-none focus:border-[var(--accent)] focus:ring-2 focus:ring-[var(--accent)]/20 text-[var(--text-primary)] placeholder:text-[var(--text-faint)] transition-all"
			/>
		</div>
	</div>

	<!-- Content -->
	{#if isLoading}
		<!-- Loading Skeleton -->
		<div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-5">
			{#each Array(6) as _}
				<SkeletonPluginCard />
			{/each}
		</div>
	{:else if data.error}
		<div
			class="text-center py-20 bg-[var(--bg-subtle)] rounded-2xl border border-dashed border-[var(--border)]"
		>
			<Puzzle class="mx-auto text-[var(--text-muted)] mb-3" size={48} />
			<p class="text-[var(--text-secondary)] font-medium">Error loading plugins</p>
			<p class="text-sm text-[var(--text-muted)] mt-1">{data.error}</p>
		</div>
	{:else if !hasPlugins}
		<div
			class="text-center py-20 bg-[var(--bg-subtle)] rounded-2xl border border-dashed border-[var(--border)]"
		>
			<Puzzle class="mx-auto text-[var(--text-muted)] mb-3" size={48} />
			<p class="text-[var(--text-secondary)] font-medium">No plugins installed</p>
			<p class="text-sm text-[var(--text-muted)] mt-1">
				Install plugins via Claude Code to see them here
			</p>
		</div>
	{:else if !hasFilteredPlugins}
		<div
			class="text-center py-20 bg-[var(--bg-subtle)] rounded-2xl border border-dashed border-[var(--border)]"
		>
			<Search class="mx-auto text-[var(--text-muted)] mb-3" size={48} />
			<p class="text-[var(--text-secondary)] font-medium">No matching plugins</p>
			<p class="text-sm text-[var(--text-muted)] mt-1">Try adjusting your search or filter</p>
		</div>
	{:else}
		<div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-5 stagger-children">
			{#each filteredPlugins as plugin (plugin.name)}
				<PluginCard {plugin} {usageLoaded} />
			{/each}
		</div>
	{/if}
</div>

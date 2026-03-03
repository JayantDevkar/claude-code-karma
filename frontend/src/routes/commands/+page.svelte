<script lang="ts">
	import {
		Terminal,
		Search,
		Zap,
		Play,
		Sparkles,
		FileText,
		ChevronsUpDown,
		ChevronsDownUp
	} from 'lucide-svelte';
	import { listNavigation } from '$lib/actions/listNavigation';
	import PageHeader from '$lib/components/layout/PageHeader.svelte';
	import StatsGrid from '$lib/components/StatsGrid.svelte';
	import SegmentedControl from '$lib/components/ui/SegmentedControl.svelte';
	import CollapsibleGroup from '$lib/components/ui/CollapsibleGroup.svelte';
	import CommandUsageCard from '$lib/components/commands/CommandUsageCard.svelte';
	import CommandUsageTable from '$lib/components/commands/CommandUsageTable.svelte';
	import UsageAnalytics from '$lib/components/charts/UsageAnalytics.svelte';
	import { getCommandCategoryColorVars, getCommandCategoryLabel, getCommandChartHex } from '$lib/utils';
	import type { CommandUsage, CommandCategory, StatItem } from '$lib/api-types';

	let { data } = $props();

	// View state
	let activeView = $state<'groups' | 'table' | 'analytics'>('groups');

	// Filter state
	let searchQuery = $state('');
	let selectedFilter = $state<'all' | 'builtin' | 'bundled' | 'user'>('all');

	const filterOptions = [
		{ label: 'All', value: 'all' },
		{ label: 'Built-in', value: 'builtin' },
		{ label: 'Bundled', value: 'bundled' },
		{ label: 'User', value: 'user' }
	];

	const viewTabs = [
		{ label: 'By Category', value: 'groups' },
		{ label: 'All Commands', value: 'table' },
		{ label: 'Usage Analytics', value: 'analytics' }
	];

	// Compute stats for hero section
	let stats = $derived.by<StatItem[]>(() => {
		const usage = data.usage || [];
		const totalCommands = usage.length;
		const totalUses = usage.reduce((sum: number, cmd: CommandUsage) => sum + cmd.count, 0);
		const builtinCount = usage.filter(
			(c: CommandUsage) => c.category === 'builtin_command'
		).length;
		const userCount = usage.filter(
			(c: CommandUsage) => c.category === 'user_command' || c.category === 'custom_skill'
		).length;

		return [
			{
				title: 'Total Commands',
				value: totalCommands,
				icon: Terminal,
				color: 'blue'
			},
			{
				title: 'Total Uses',
				value: totalUses.toLocaleString(),
				icon: Play,
				color: 'purple'
			},
			{
				title: 'Built-in',
				value: builtinCount,
				icon: Zap,
				color: 'teal'
			},
			{
				title: 'User Commands',
				value: userCount,
				icon: FileText,
				color: 'green'
			}
		];
	});

	// Filter commands by search query and type
	let filteredCommands = $derived.by(() => {
		let commands = data.usage || [];

		// Filter by type
		if (selectedFilter === 'builtin') {
			commands = commands.filter((c: CommandUsage) => c.category === 'builtin_command');
		} else if (selectedFilter === 'bundled') {
			commands = commands.filter((c: CommandUsage) => c.category === 'bundled_skill');
		} else if (selectedFilter === 'user') {
			commands = commands.filter(
				(c: CommandUsage) =>
					c.category === 'user_command' ||
					c.category === 'custom_skill' ||
					c.category === 'plugin_skill'
			);
		}

		// Filter by search query
		if (searchQuery.trim()) {
			const query = searchQuery.toLowerCase();
			commands = commands.filter(
				(c: CommandUsage) =>
					c.name.toLowerCase().includes(query) ||
					(c.description && c.description.toLowerCase().includes(query))
			);
		}

		return commands;
	});

	// Group commands by category for display
	interface CommandGroup {
		key: CommandCategory;
		label: string;
		icon: typeof Terminal;
		commands: CommandUsage[];
	}

	const categoryOrder: CommandCategory[] = [
		'builtin_command',
		'bundled_skill',
		'plugin_skill',
		'custom_skill',
		'user_command'
	];

	const categoryIcons: Record<CommandCategory, typeof Terminal> = {
		builtin_command: Terminal,
		bundled_skill: Sparkles,
		plugin_skill: Zap,
		custom_skill: Zap,
		user_command: FileText
	};

	let groupedCommands = $derived.by<CommandGroup[]>(() => {
		const commands = filteredCommands;
		const groups: Map<CommandCategory, CommandGroup> = new Map();

		for (const cmd of commands) {
			const cat = cmd.category ?? 'user_command';
			if (!groups.has(cat)) {
				groups.set(cat, {
					key: cat,
					label: getCommandCategoryLabel(cat),
					icon: categoryIcons[cat] ?? Terminal,
					commands: []
				});
			}
			groups.get(cat)!.commands.push(cmd);
		}

		// Sort by predefined category order
		return categoryOrder
			.filter((cat) => groups.has(cat))
			.map((cat) => groups.get(cat)!);
	});

	// Track which groups are expanded
	let expandedGroups = $state<Set<string>>(new Set(['builtin_command', 'bundled_skill']));
	let previousExpandedGroups = $state<Set<string> | null>(null);

	// Auto-expand groups when searching
	$effect(() => {
		const hasSearch = searchQuery.trim().length > 0;

		if (hasSearch) {
			if (previousExpandedGroups === null) {
				previousExpandedGroups = new Set(expandedGroups);
			}
			if (groupedCommands.length > 0) {
				expandedGroups = new Set(groupedCommands.map((g) => g.key));
			}
		} else {
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
		groupedCommands.length > 0 && groupedCommands.every((g) => expandedGroups.has(g.key))
	);

	function toggleAllGroups() {
		if (allExpanded) {
			expandedGroups = new Set();
		} else {
			expandedGroups = new Set(groupedCommands.map((g) => g.key));
		}
	}

	// Calculate max usage for progress bars
	let maxUsage = $derived(
		filteredCommands.length > 0 ? Math.max(...filteredCommands.map((c: CommandUsage) => c.count)) : 100
	);

	// Build a category lookup from command data for analytics filtering
	let commandCategoryMap = $derived.by(() => {
		const map = new Map<string, string>();
		for (const cmd of data.usage || []) {
			map.set(cmd.name, cmd.category ?? 'user_command');
		}
		return map;
	});

	let excludeFn = $derived.by(() => {
		if (selectedFilter === 'all') return undefined;
		if (selectedFilter === 'builtin') {
			return (name: string) => commandCategoryMap.get(name) !== 'builtin_command';
		}
		if (selectedFilter === 'bundled') {
			return (name: string) => commandCategoryMap.get(name) !== 'bundled_skill';
		}
		// 'user' — exclude builtin and bundled
		return (name: string) => {
			const cat = commandCategoryMap.get(name);
			return cat === 'builtin_command' || cat === 'bundled_skill';
		};
	});

	let hasCommands = $derived((data.usage || []).length > 0);
	let hasFilteredCommands = $derived(filteredCommands.length > 0);
</script>

<div class="space-y-8">
	<!-- Page Header -->
	<PageHeader
		title="Commands"
		icon={Terminal}
		iconColor="--nav-blue"
		breadcrumbs={[{ label: 'Dashboard', href: '/' }, { label: 'Commands' }]}
		subtitle="Track command usage analytics across all sessions"
	/>

	<!-- Hero Stats -->
	{#if hasCommands}
		<div
			class="relative overflow-hidden rounded-2xl p-8 border border-[var(--border)]"
			style="background: linear-gradient(135deg, rgba(59, 130, 246, 0.02) 0%, rgba(59, 130, 246, 0.06) 100%);"
		>
			<div
				class="absolute -top-24 -right-24 w-96 h-96 bg-blue-500/5 rounded-full blur-3xl pointer-events-none"
			></div>
			<div
				class="absolute -bottom-24 -left-24 w-64 h-64 bg-teal-500/3 rounded-full blur-3xl pointer-events-none"
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
			<SegmentedControl options={viewTabs} bind:value={activeView} />
			<SegmentedControl options={filterOptions} bind:value={selectedFilter} size="sm" />
		</div>

		{#if activeView !== 'analytics'}
			<div class="flex items-center gap-3 w-full sm:w-auto">
				<div class="relative flex-1 sm:flex-initial">
					<Search
						class="absolute left-3 top-1/2 -translate-y-1/2 text-[var(--text-muted)]"
						size={16}
					/>
					<input
						type="text"
						bind:value={searchQuery}
						placeholder="Search commands..."
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

				{#if activeView === 'groups' && groupedCommands.length > 1}
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
	{#if activeView === 'analytics'}
		<UsageAnalytics
			endpoint="/commands/usage/trend"
			itemLabel="Commands"
			colorFn={getCommandChartHex}
			excludeItemFn={excludeFn}
			itemLinkPrefix="/commands/"
			itemDisplayFn={(name) => '/' + name}
		/>
	{:else if !hasCommands}
		<div
			class="text-center py-20 bg-[var(--bg-subtle)] rounded-2xl border border-dashed border-[var(--border)]"
		>
			<Terminal class="mx-auto text-[var(--text-muted)] mb-3" size={48} />
			<p class="text-[var(--text-secondary)] font-medium">No commands found</p>
			<p class="text-sm text-[var(--text-muted)] mt-1">
				Command usage data will appear here once you start using commands in Claude Code
			</p>
		</div>
	{:else if !hasFilteredCommands}
		<div
			class="text-center py-20 bg-[var(--bg-subtle)] rounded-2xl border border-dashed border-[var(--border)]"
		>
			<Search class="mx-auto text-[var(--text-muted)] mb-3" size={48} />
			<p class="text-[var(--text-secondary)] font-medium">No matching commands</p>
			<p class="text-sm text-[var(--text-muted)] mt-1">
				Try adjusting your search or filter
			</p>
		</div>
	{:else if activeView === 'table'}
		<CommandUsageTable commands={filteredCommands} />
	{:else}
		<!-- Grouped Command Display (By Category) -->
		<div class="space-y-4">
			{#each groupedCommands as group (group.key)}
				{@const groupColors = getCommandCategoryColorVars(group.key)}
				<CollapsibleGroup
					title={group.label}
					open={expandedGroups.has(group.key)}
					onOpenChange={() => toggleGroup(group.key)}
				>
					{#snippet icon()}
						{@const Icon = group.icon}
						<div
							class="p-1.5 rounded-md"
							style="background-color: {groupColors.subtle};"
						>
							<Icon size={14} style="color: {groupColors.color};" />
						</div>
					{/snippet}
					{#snippet metadata()}
						<span class="text-xs text-[var(--text-muted)] tabular-nums">
							{group.commands.length} command{group.commands.length !== 1 ? 's' : ''}
						</span>
					{/snippet}

					<div
						class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-5 stagger-children"
					>
						{#each group.commands as command (command.name)}
							<CommandUsageCard {command} {maxUsage} />
						{/each}
					</div>
				</CollapsibleGroup>
			{/each}
		</div>
	{/if}
</div>

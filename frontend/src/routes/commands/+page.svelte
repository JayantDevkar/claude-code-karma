<script lang="ts">
	import { navigating } from '$app/stores';
	import {
		Terminal,
		Search,
		Zap,
		Play,
		Sparkles,
		FileText,
		Puzzle,
		ExternalLink,
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
	import SkeletonBox from '$lib/components/skeleton/SkeletonBox.svelte';
	import SkeletonText from '$lib/components/skeleton/SkeletonText.svelte';
	import { getCommandCategoryColorVars, getCommandCategoryLabel, getCommandChartHex, getPluginColorVars } from '$lib/utils';
	import type { CommandUsage, CommandCategory, StatItem } from '$lib/api-types';

	let { data } = $props();

	// Loading state: navigating TO this page from elsewhere
	let isPageLoading = $derived(!!$navigating && $navigating.to?.route.id === '/commands');

	// View state
	let activeView = $state<'groups' | 'table' | 'analytics'>('groups');

	// Filter state
	let searchQuery = $state('');
	let selectedFilter = $state<'all' | 'builtin' | 'bundled' | 'plugin' | 'user'>('all');

	const filterOptions = [
		{ label: 'All', value: 'all' },
		{ label: 'Built-in', value: 'builtin' },
		{ label: 'Bundled', value: 'bundled' },
		{ label: 'Plugin', value: 'plugin' },
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
		const totalUses = usage.reduce((sum: number, cmd: CommandUsage) => sum + (cmd.count ?? 0), 0);
		const builtinCount = usage.filter(
			(c: CommandUsage) => c.category === 'builtin_command'
		).length;
		const pluginCount = usage.filter(
			(c: CommandUsage) =>
				c.category === 'plugin_command' || c.category === 'plugin_skill'
		).length;
		const userCount = usage.filter(
			(c: CommandUsage) =>
				c.category === 'user_command' || c.category === 'custom_skill'
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
				title: 'Plugin',
				value: pluginCount,
				icon: Puzzle,
				color: 'green'
			},
			{
				title: 'User',
				value: userCount,
				icon: FileText,
				color: 'orange'
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
		} else if (selectedFilter === 'plugin') {
			commands = commands.filter(
				(c: CommandUsage) =>
					c.category === 'plugin_command' || c.category === 'plugin_skill'
			);
		} else if (selectedFilter === 'user') {
			commands = commands.filter(
				(c: CommandUsage) =>
					c.category === 'user_command' || c.category === 'custom_skill'
			);
		}

		// Filter by search query
		if (searchQuery.trim()) {
			const query = searchQuery.toLowerCase();
			commands = commands.filter(
				(c: CommandUsage) =>
					c.name.toLowerCase().includes(query) ||
					(c.description && c.description.toLowerCase().includes(query)) ||
					(c.plugin && c.plugin.toLowerCase().includes(query))
			);
		}

		return commands;
	});

	// Group commands by category for display, with dynamic plugin grouping
	interface CommandGroup {
		key: string;
		label: string;
		icon: typeof Terminal;
		commands: CommandUsage[];
		pluginName: string | null;
	}

	// Priority order for non-plugin categories
	const categoryPriority: Record<string, number> = {
		builtin_command: 0,
		bundled_skill: 1,
		// plugin groups go here (priority 2)
		custom_skill: 3,
		user_command: 4
	};

	const categoryIcons: Record<string, typeof Terminal> = {
		builtin_command: Terminal,
		bundled_skill: Sparkles,
		custom_skill: Zap,
		user_command: FileText
	};

	let groupedCommands = $derived.by<CommandGroup[]>(() => {
		const commands = filteredCommands;
		const groups: Map<string, CommandGroup> = new Map();

		for (const cmd of commands) {
			const cat = cmd.category ?? 'user_command';
			let groupKey: string;
			let groupLabel: string;
			let groupIcon: typeof Terminal;
			let pluginName: string | null = null;

			if ((cat === 'plugin_command' || cat === 'plugin_skill') && cmd.plugin) {
				groupKey = `plugin:${cmd.plugin}`;
				groupLabel = cmd.plugin;
				groupIcon = Puzzle;
				pluginName = cmd.plugin;
			} else {
				groupKey = cat;
				groupLabel = getCommandCategoryLabel(cat);
				groupIcon = categoryIcons[cat] ?? Terminal;
			}

			if (!groups.has(groupKey)) {
				groups.set(groupKey, {
					key: groupKey,
					label: groupLabel,
					icon: groupIcon,
					commands: [],
					pluginName
				});
			}
			groups.get(groupKey)!.commands.push(cmd);
		}

		// Sort: fixed categories by priority, plugin groups alphabetically in between
		return Array.from(groups.values()).sort((a, b) => {
			const aPriority = categoryPriority[a.key] ?? 2;
			const bPriority = categoryPriority[b.key] ?? 2;
			if (aPriority !== bPriority) return aPriority - bPriority;
			return a.label.localeCompare(b.label);
		});
	});

	// Track which groups are expanded
	let expandedGroups = $state<Set<string>>(new Set(['builtin_command']));
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
		if (selectedFilter === 'plugin') {
			return (name: string) => {
				const cat = commandCategoryMap.get(name);
				return cat !== 'plugin_command' && cat !== 'plugin_skill';
			};
		}
		// 'user' — only user_command and custom_skill
		return (name: string) => {
			const cat = commandCategoryMap.get(name);
			return cat !== 'user_command' && cat !== 'custom_skill';
		};
	});

	let hasCommands = $derived((data.usage || []).length > 0);
	let hasFilteredCommands = $derived(filteredCommands.length > 0);
</script>

<div class="space-y-8">
	{#if isPageLoading}
		<!-- Loading Skeleton -->
		<div class="space-y-8" role="status" aria-busy="true" aria-label="Loading commands...">
			<!-- Header skeleton -->
			<div>
				<div class="flex items-center gap-2 mb-2">
					<SkeletonText width="70px" size="xs" />
					<span class="text-[var(--text-muted)]">/</span>
					<SkeletonText width="80px" size="xs" />
				</div>
				<div class="flex items-center gap-3">
					<SkeletonBox width="32px" height="32px" rounded="lg" />
					<SkeletonText width="140px" size="xl" />
				</div>
			</div>

			<!-- Stats skeleton -->
			<div class="rounded-2xl p-8 border border-[var(--border)] bg-[var(--bg-subtle)]">
				<div class="grid grid-cols-5 gap-6">
					{#each Array(5) as _}
						<div class="space-y-2">
							<SkeletonText width="80px" size="xs" />
							<SkeletonText width="50px" size="lg" />
						</div>
					{/each}
				</div>
			</div>

			<!-- Filter bar skeleton -->
			<div class="flex items-center justify-between">
				<div class="flex items-center gap-3">
					<SkeletonBox width="240px" height="36px" rounded="lg" />
					<SkeletonBox width="280px" height="32px" rounded="lg" />
				</div>
				<SkeletonBox width="200px" height="36px" rounded="lg" />
			</div>

			<!-- Card grid skeleton -->
			<div class="space-y-4">
				{#each Array(2) as _}
					<div>
						<div class="flex items-center gap-2 mb-4">
							<SkeletonBox width="28px" height="28px" rounded="md" />
							<SkeletonText width="120px" size="sm" />
							<SkeletonText width="60px" size="xs" />
						</div>
						<div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-5">
							{#each Array(3) as _}
								<div class="p-4 rounded-xl border border-[var(--border)] bg-[var(--bg-base)] space-y-3">
									<div class="flex items-center gap-3">
										<SkeletonBox width="36px" height="36px" rounded="lg" />
										<div class="flex-1 space-y-1.5">
											<SkeletonText width="120px" size="sm" />
											<SkeletonText width="60px" size="xs" />
										</div>
										<SkeletonBox width="40px" height="24px" rounded="full" />
									</div>
									<SkeletonBox width="100%" height="6px" rounded="full" />
								</div>
							{/each}
						</div>
					</div>
				{/each}
			</div>
		</div>
	{:else}

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
				<StatsGrid {stats} columns={5} />
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
						aria-label="Search commands"
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
				{@const groupColors = group.pluginName
					? getPluginColorVars(group.pluginName)
					: getCommandCategoryColorVars(group.key)}
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
						<div class="flex items-center gap-3">
							<span class="text-xs text-[var(--text-muted)] tabular-nums">
								{group.commands.length} command{group.commands.length !== 1 ? 's' : ''}
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

	{/if}
</div>

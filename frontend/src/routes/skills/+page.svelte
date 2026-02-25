<script lang="ts">
	import {
		Wrench,
		Search,
		Zap,
		Play,
		Puzzle,
		FolderOpen,
		ChevronsUpDown,
		ChevronsDownUp,
		ExternalLink
	} from 'lucide-svelte';
	import { page } from '$app/state';
	import { listNavigation } from '$lib/actions/listNavigation';
	import PageHeader from '$lib/components/layout/PageHeader.svelte';
	import StatsGrid from '$lib/components/StatsGrid.svelte';
	import SegmentedControl from '$lib/components/ui/SegmentedControl.svelte';
	import CollapsibleGroup from '$lib/components/ui/CollapsibleGroup.svelte';
	import SkillUsageCard from '$lib/components/skills/SkillUsageCard.svelte';
	import SkillList from '$lib/components/skills/SkillList.svelte';
	import { getSkillGroupColorVars } from '$lib/utils';
	import type { SkillUsage, StatItem } from '$lib/api-types';

	// Server data
	let { data } = $props();

	// View state - default to "Usage Analytics"
	let activeView = $state<'usage' | 'files'>('usage');

	// Filter state
	let searchQuery = $state('');
	let selectedFilter = $state<'all' | 'plugin' | 'file'>('all');

	// Read path from URL for Browse Files navigation
	let urlPath = $derived(page.url.searchParams.get('path') || '');

	// Auto-switch to files view when path param is present
	$effect(() => {
		if (urlPath) {
			activeView = 'files';
		}
	});

	// Filter options
	const filterOptions = [
		{ label: 'All', value: 'all' },
		{ label: 'Plugin', value: 'plugin' },
		{ label: 'Custom', value: 'file' }
	];

	// View tab options
	const viewTabs = [
		{ label: 'Usage Analytics', value: 'usage' },
		{ label: 'Browse Files', value: 'files' }
	];

	// Compute stats for hero section
	let stats = $derived.by<StatItem[]>(() => {
		const usage = data.usage || [];
		const totalSkills = usage.length;
		const totalUses = usage.reduce((sum, skill) => sum + skill.count, 0);
		const pluginSkills = usage.filter((s) => s.is_plugin).length;

		return [
			{
				title: 'Total Skills',
				value: totalSkills,
				icon: Zap,
				color: 'purple'
			},
			{
				title: 'Total Uses',
				value: totalUses.toLocaleString(),
				icon: Play,
				color: 'blue'
			},
			{
				title: 'Plugin Skills',
				value: pluginSkills,
				icon: Puzzle,
				color: 'green'
			}
		];
	});

	// Filter skills by search query and type
	let filteredSkills = $derived.by(() => {
		let skills = data.usage || [];

		// Filter by type
		if (selectedFilter === 'plugin') {
			skills = skills.filter((s) => s.is_plugin);
		} else if (selectedFilter === 'file') {
			skills = skills.filter((s) => !s.is_plugin);
		}

		// Filter by search query
		if (searchQuery.trim()) {
			const query = searchQuery.toLowerCase();
			skills = skills.filter(
				(s) =>
					s.name.toLowerCase().includes(query) ||
					(s.plugin && s.plugin.toLowerCase().includes(query))
			);
		}

		return skills;
	});

	// Group skills by plugin source for display
	interface SkillGroup {
		key: string;
		label: string;
		icon: typeof Zap;
		skills: SkillUsage[];
		pluginName: string | null;
	}

	let groupedSkills = $derived.by<SkillGroup[]>(() => {
		const skills = filteredSkills;
		const groups: Map<string, SkillGroup> = new Map();

		for (const skill of skills) {
			let groupKey: string;
			let groupLabel: string;
			let groupIcon: typeof Zap;
			let pluginName: string | null = null;

			if (skill.is_plugin && skill.plugin) {
				groupKey = `plugin:${skill.plugin}`;
				groupLabel = skill.plugin;
				groupIcon = Puzzle;
				pluginName = skill.plugin;
			} else if (!skill.is_plugin) {
				groupKey = 'file';
				groupLabel = 'Custom Skills';
				groupIcon = FolderOpen;
			} else {
				groupKey = 'other';
				groupLabel = 'Other Skills';
				groupIcon = Zap;
			}

			if (!groups.has(groupKey)) {
				groups.set(groupKey, {
					key: groupKey,
					label: groupLabel,
					icon: groupIcon,
					skills: [],
					pluginName
				});
			}
			groups.get(groupKey)!.skills.push(skill);
		}

		// Sort groups: file-based first, then plugins alphabetically
		return Array.from(groups.values()).sort((a, b) => {
			if (a.key === 'file') return -1;
			if (b.key === 'file') return 1;
			return a.label.localeCompare(b.label);
		});
	});

	// Track which groups are expanded
	let expandedGroups = $state<Set<string>>(new Set(['file']));
	let previousExpandedGroups = $state<Set<string> | null>(null);

	// Auto-expand groups when searching rule:
	// 1. When entering search (query > 0), snapshot current state
	// 2. Expand all matching groups
	// 3. When clearing search, restore snapshot
	$effect(() => {
		const hasSearch = searchQuery.trim().length > 0;

		if (hasSearch) {
			// Entering search mode: Snapshot if not already done
			if (previousExpandedGroups === null) {
				previousExpandedGroups = new Set(expandedGroups);
			}
			// Force expand matches
			if (groupedSkills.length > 0) {
				expandedGroups = new Set(groupedSkills.map((g) => g.key));
			}
		} else {
			// Exiting search mode: Restore snapshot
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

	// Check if all groups are expanded
	let allExpanded = $derived(
		groupedSkills.length > 0 && groupedSkills.every((g) => expandedGroups.has(g.key))
	);

	function expandAll() {
		expandedGroups = new Set(groupedSkills.map((g) => g.key));
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

	// Calculate max usage for progress bars
	let maxUsage = $derived(
		filteredSkills.length > 0 ? Math.max(...filteredSkills.map((s) => s.count)) : 100
	);

	// Check if we have any skills
	let hasSkills = $derived((data.usage || []).length > 0);
	let hasFilteredSkills = $derived(filteredSkills.length > 0);
</script>

<div class="space-y-8">
	<!-- Page Header with Breadcrumb -->
	<PageHeader
		title="Skills"
		icon={Wrench}
		iconColor="--nav-orange"
		breadcrumbs={[{ label: 'Dashboard', href: '/' }, { label: 'Skills' }]}
		subtitle="Track skill usage analytics and browse skill files"
	/>

	<!-- Hero Stats Row with Gradient Background -->
	{#if hasSkills}
		<div
			class="relative overflow-hidden rounded-2xl p-8 border border-[var(--border)]"
			style="background: linear-gradient(135deg, rgba(124, 58, 237, 0.02) 0%, rgba(124, 58, 237, 0.06) 100%);"
		>
			<!-- Decorative blur elements -->
			<div
				class="absolute -top-24 -right-24 w-96 h-96 bg-violet-500/5 rounded-full blur-3xl pointer-events-none"
			></div>
			<div
				class="absolute -bottom-24 -left-24 w-64 h-64 bg-blue-500/3 rounded-full blur-3xl pointer-events-none"
			></div>

			<!-- Stats Grid -->
			<div class="relative">
				<StatsGrid {stats} columns={3} />
			</div>
		</div>
	{/if}

	<!-- View Tabs -->
	<div class="flex items-center gap-4">
		<SegmentedControl
			options={viewTabs}
			bind:value={activeView}
			onchange={(value) => {
				activeView = value as 'usage' | 'files';
			}}
		/>
	</div>

	<!-- Usage Analytics View -->
	{#if activeView === 'usage'}
		<!-- Filters Row -->
		<div
			class="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4"
			use:listNavigation
		>
			<!-- Type Filter -->
			<SegmentedControl options={filterOptions} bind:value={selectedFilter} />

			<!-- Search and Expand/Collapse Controls -->
			<div class="flex items-center gap-3 w-full sm:w-auto">
				<!-- Search Input -->
				<div class="relative flex-1 sm:flex-initial">
					<Search
						class="absolute left-3 top-1/2 -translate-y-1/2 text-[var(--text-muted)]"
						size={16}
					/>
					<input
						type="text"
						bind:value={searchQuery}
						placeholder="Search skills..."
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

				<!-- Expand/Collapse All Toggle -->
				{#if groupedSkills.length > 1}
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
		</div>

		<!-- Content Area -->
		{#if !hasSkills}
			<!-- Empty State: No skills at all -->
			<div
				class="text-center py-20 bg-[var(--bg-subtle)] rounded-2xl border border-dashed border-[var(--border)]"
			>
				<Zap class="mx-auto text-[var(--text-muted)] mb-3" size={48} />
				<p class="text-[var(--text-secondary)] font-medium">No skills found</p>
				<p class="text-sm text-[var(--text-muted)] mt-1">
					Skill usage data will appear here once you start using skills in Claude Code
				</p>
			</div>
		{:else if !hasFilteredSkills}
			<!-- Empty State: No matching results -->
			<div
				class="text-center py-20 bg-[var(--bg-subtle)] rounded-2xl border border-dashed border-[var(--border)]"
			>
				<Search class="mx-auto text-[var(--text-muted)] mb-3" size={48} />
				<p class="text-[var(--text-secondary)] font-medium">No matching skills</p>
				<p class="text-sm text-[var(--text-muted)] mt-1">
					Try adjusting your search or filter
				</p>
			</div>
		{:else}
			<!-- Grouped Skill Display -->
			<div class="space-y-4">
				{#each groupedSkills as group (group.key)}
					{@const groupColors = getSkillGroupColorVars(group.key)}
					<CollapsibleGroup
						title={group.label}
						open={expandedGroups.has(group.key)}
						onOpenChange={() => toggleGroup(group.key)}
					>
						{#snippet icon()}
							<div
								class="p-1.5 rounded-md"
								style="background-color: {groupColors.subtle};"
							>
								{#if group.icon === Puzzle}
									<Puzzle size={14} style="color: {groupColors.color};" />
								{:else if group.icon === FolderOpen}
									<FolderOpen size={14} style="color: {groupColors.color};" />
								{:else}
									<Zap size={14} style="color: {groupColors.color};" />
								{/if}
							</div>
						{/snippet}
						{#snippet metadata()}
							<div class="flex items-center gap-3">
								<span class="text-xs text-[var(--text-muted)] tabular-nums">
									{group.skills.length} skill{group.skills.length !== 1
										? 's'
										: ''}
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
							{#each group.skills as skill (skill.name)}
								<SkillUsageCard {skill} {maxUsage} />
							{/each}
						</div>
					</CollapsibleGroup>
				{/each}
			</div>
		{/if}
	{:else}
		<!-- Browse Files View -->
		<SkillList currentPath={urlPath} />
	{/if}
</div>

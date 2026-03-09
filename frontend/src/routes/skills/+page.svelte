<script lang="ts">
	import {
		Wrench,
		Search,
		Zap,
		Play,
		Puzzle,
		FolderOpen,
		Sparkles,
		ChevronsUpDown,
		ChevronsDownUp,
		ExternalLink,
		Download
	} from 'lucide-svelte';
	import { browser } from '$app/environment';
	import { navigating } from '$app/stores';
	import { listNavigation } from '$lib/actions/listNavigation';
	import PageHeader from '$lib/components/layout/PageHeader.svelte';
	import SkeletonBox from '$lib/components/skeleton/SkeletonBox.svelte';
	import SkeletonText from '$lib/components/skeleton/SkeletonText.svelte';
	import SkeletonStatsCard from '$lib/components/skeleton/SkeletonStatsCard.svelte';
	import SkeletonSkillCard from '$lib/components/skeleton/SkeletonSkillCard.svelte';
	import StatsGrid from '$lib/components/StatsGrid.svelte';
	import SegmentedControl from '$lib/components/ui/SegmentedControl.svelte';
	import CollapsibleGroup from '$lib/components/ui/CollapsibleGroup.svelte';
	import SkillUsageCard from '$lib/components/skills/SkillUsageCard.svelte';
	import SkillUsageTable from '$lib/components/skills/SkillUsageTable.svelte';
	import UsageAnalytics from '$lib/components/charts/UsageAnalytics.svelte';
	import MemberUsageGrid from '$lib/components/members/MemberUsageGrid.svelte';
	import { getSkillGroupColorVars, getSkillCategoryColorVars, getSkillChartHex, cleanSkillName } from '$lib/utils';
	import type { SkillUsage, StatItem } from '$lib/api-types';

	// The API returns extra fields not in the SkillUsage type
	interface SkillWithRemote extends SkillUsage {
		remote_user_ids?: string[];
	}

	// Server data
	let { data } = $props();

	// View state — default to "By Category" grouped view
	let activeView = $state<'groups' | 'table' | 'analytics' | 'members'>('groups');
	const validViews = ['groups', 'table', 'analytics', 'members'] as const;

	// URL state persistence for view mode
	let viewReady = $state(false);
	$effect(() => {
		if (!browser || viewReady) return;
		const params = new URLSearchParams(window.location.search);
		const view = params.get('view');
		if (view && (validViews as readonly string[]).includes(view)) activeView = view as typeof activeView;
		viewReady = true;
	});
	$effect(() => {
		if (!browser || !viewReady) return;
		const url = new URL(window.location.href);
		if (activeView === 'groups') url.searchParams.delete('view');
		else url.searchParams.set('view', activeView);
		history.replaceState({}, '', url.toString());
	});

	// Filter state
	let searchQuery = $state('');
	let selectedFilter = $state<'all' | 'bundled' | 'plugin' | 'custom' | 'inherited'>('all');

	// Filter options
	const filterOptions = [
		{ label: 'All', value: 'all' },
		{ label: 'Bundled', value: 'bundled' },
		{ label: 'Plugin', value: 'plugin' },
		{ label: 'Custom', value: 'custom' },
		{ label: 'Inherited', value: 'inherited' }
	];

	// View tab options
	const viewTabs = [
		{ label: 'By Category', value: 'groups' },
		{ label: 'All Skills', value: 'table' },
		{ label: 'Usage Analytics', value: 'analytics' },
		{ label: 'By Member', value: 'members' }
	];

	// Compute stats for hero section
	let stats = $derived.by<StatItem[]>(() => {
		const usage = data.usage || [];
		const totalSkills = usage.length;
		const totalUses = usage.reduce((sum: number, skill: SkillUsage) => sum + skill.count, 0);
		const bundledSkills = usage.filter((s: SkillUsage) => s.category === 'bundled_skill').length;
		const pluginSkills = usage.filter((s: SkillUsage) => s.category === 'plugin_skill').length;

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
				title: 'Bundled',
				value: bundledSkills,
				icon: Sparkles,
				color: 'purple'
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

		// Filter by category
		if (selectedFilter === 'bundled') {
			skills = skills.filter((s: SkillUsage) => s.category === 'bundled_skill');
		} else if (selectedFilter === 'plugin') {
			skills = skills.filter((s: SkillUsage) => s.category === 'plugin_skill');
		} else if (selectedFilter === 'custom') {
			skills = skills.filter((s: SkillUsage) => s.category === 'custom_skill');
		} else if (selectedFilter === 'inherited') {
			skills = skills.filter((s: SkillUsage) => s.category === 'inherited_skill');
		}

		// Filter by search query
		if (searchQuery.trim()) {
			const query = searchQuery.toLowerCase();
			skills = skills.filter(
				(s: SkillUsage) =>
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

			if (skill.category === 'bundled_skill') {
				groupKey = 'bundled_skill';
				groupLabel = 'Bundled Skills';
				groupIcon = Sparkles;
			} else if (skill.category === 'plugin_skill' && skill.plugin) {
				groupKey = `plugin:${skill.plugin}`;
				groupLabel = skill.plugin;
				groupIcon = Puzzle;
				pluginName = skill.plugin;
			} else if (skill.category === 'inherited_skill') {
				groupKey = 'inherited_skill';
				groupLabel = 'Inherited Skills';
				groupIcon = Download;
			} else if (skill.category === 'custom_skill') {
				groupKey = 'custom_skill';
				groupLabel = 'Custom Skills';
				groupIcon = FolderOpen;
			} else {
				// Backward compat fallback for skills without category
				if (skill.is_plugin && skill.plugin) {
					groupKey = `plugin:${skill.plugin}`;
					groupLabel = skill.plugin;
					groupIcon = Puzzle;
					pluginName = skill.plugin;
				} else {
					groupKey = 'custom_skill';
					groupLabel = 'Custom Skills';
					groupIcon = FolderOpen;
				}
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

		// Sort groups: bundled first, then custom, then plugins alphabetically
		return Array.from(groups.values()).sort((a, b) => {
			const priority: Record<string, number> = { 'bundled_skill': 0, 'custom_skill': 1, 'inherited_skill': 2 };
			const aPriority = priority[a.key] ?? 3;
			const bPriority = priority[b.key] ?? 3;
			if (aPriority !== bPriority) return aPriority - bPriority;
			return a.label.localeCompare(b.label);
		});
	});

	// Track which groups are expanded
	let expandedGroups = $state<Set<string>>(new Set(['bundled_skill']));
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
		filteredSkills.length > 0 ? Math.max(...filteredSkills.map((s: SkillUsage) => s.count)) : 100
	);

	// Build lookup maps from skill data for analytics filtering (O(1) per lookup)
	let skillCategoryMap = $derived.by(() => {
		const map = new Map<string, string>();
		for (const skill of (data.usage || [])) {
			map.set(skill.name, skill.category ?? (skill.is_plugin ? 'plugin_skill' : 'custom_skill'));
		}
		return map;
	});

	let excludeFn = $derived.by(() => {
		if (selectedFilter === 'all') return undefined;
		const categoryFilter: Record<string, string> = {
			bundled: 'bundled_skill',
			plugin: 'plugin_skill',
			custom: 'custom_skill',
			inherited: 'inherited_skill'
		};
		const targetCategory = categoryFilter[selectedFilter];
		if (targetCategory) {
			return (name: string) => skillCategoryMap.get(name) !== targetCategory;
		}
		return undefined;
	});

	// Check if we have any skills
	let hasSkills = $derived((data.usage || []).length > 0);
	let hasFilteredSkills = $derived(filteredSkills.length > 0);

	let isPageLoading = $derived(!!$navigating && $navigating.to?.route.id === '/skills');
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
						<SkeletonText width="340px" size="sm" />
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
						{#each Array(4) as _}
							<SkeletonBox width="70px" height="32px" rounded="lg" />
						{/each}
					</div>
				</div>
				<div class="flex items-center gap-3">
					<SkeletonBox width="256px" height="40px" rounded="lg" />
					<SkeletonBox width="120px" height="40px" rounded="lg" />
				</div>
			</div>

			<!-- Grouped skill cards skeleton -->
			<div class="space-y-4">
				{#each Array(2) as _, groupIndex}
					<div class="border border-[var(--border)] rounded-[var(--radius-lg)] overflow-hidden bg-[var(--bg-base)]">
						<div class="flex items-center gap-3 px-4 py-4">
							<SkeletonBox width="16px" height="16px" rounded="sm" />
							<SkeletonBox width="32px" height="32px" rounded="md" />
							<SkeletonText width="140px" size="sm" />
							<div class="flex-1"></div>
							<SkeletonText width="60px" size="xs" />
						</div>
						{#if groupIndex === 0}
							<div class="border-t border-[var(--border)] p-4">
								<div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-5">
									{#each Array(6) as _}
										<SkeletonSkillCard />
									{/each}
								</div>
							</div>
						{/if}
					</div>
				{/each}
			</div>
		</div>
	{:else}
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
			<SegmentedControl
				options={viewTabs}
				bind:value={activeView}
			/>
			{#if activeView !== 'members'}
				<SegmentedControl options={filterOptions} bind:value={selectedFilter} size="sm" />
			{/if}
		</div>

		<!-- Search and Expand/Collapse Controls -->
		{#if activeView !== 'analytics' && activeView !== 'members'}
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
						aria-label="Search skills"
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
				{#if activeView === 'groups' && groupedSkills.length > 1}
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
	{#if activeView === 'members'}
		<!-- By Member View -->
		<MemberUsageGrid
			endpoint="/skills/usage/trend"
			domainLabel="Skills"
			domainIcon={Wrench}
			items={(data.usage as SkillWithRemote[] ?? []).map((s) => ({
				name: s.name,
				count: s.count,
				remote_user_ids: s.remote_user_ids
			}))}
			itemDisplayFn={(name) => cleanSkillName(name, name.includes(':'))}
			itemLinkFn={(name) => `/skills/${encodeURIComponent(name)}`}
			excludeItemFn={excludeFn}
		/>
	{:else if activeView === 'analytics'}
		<!-- Usage Analytics View -->
		<UsageAnalytics
			endpoint="/skills/usage/trend"
			itemLabel="Skills"
			colorFn={getSkillChartHex}
			excludeItemFn={excludeFn}
			itemLinkPrefix="/skills/"
			itemDisplayFn={(name) => cleanSkillName(name, name.includes(':'))}
		/>
	{:else if !hasSkills}
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
	{:else if activeView === 'table'}
		<!-- Flat Table View -->
		<SkillUsageTable skills={filteredSkills} />
	{:else}
		<!-- Grouped Skill Display (By Category) -->
		<div class="space-y-4">
			{#each groupedSkills as group (group.key)}
				{@const groupColors = group.key.startsWith('plugin:') ? getSkillGroupColorVars(group.key) : getSkillCategoryColorVars(group.key)}
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
							{:else if group.icon === Sparkles}
								<Sparkles size={14} style="color: {groupColors.color};" />
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
						class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-5 stagger-children"
					>
						{#each group.skills as skill (skill.name)}
							<SkillUsageCard {skill} {maxUsage} />
						{/each}
					</div>
				</CollapsibleGroup>
			{/each}
		</div>
	{/if}
	{/if}
</div>

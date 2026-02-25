<script lang="ts">
	import { FolderOpen, GitBranch, Activity, Search, ChevronDown, ChevronUp } from 'lucide-svelte';
	import type { Project } from '$lib/api-types';
	import { groupProjects } from '$lib/utils/grouped-projects';
	import ProjectTreeGroup from '$lib/components/ProjectTreeGroup.svelte';
	import ProjectCard from '$lib/components/ProjectCard.svelte';
	import PageHeader from '$lib/components/layout/PageHeader.svelte';
	import { projectTreeStore } from '$lib/stores/project-tree-store';
	import { listNavigation } from '$lib/actions/listNavigation';

	let { data } = $props();
	const allProjects = $derived(data.projects as Project[]);

	// Subscribe to store state for expand/collapse tracking
	const storeState = $derived($projectTreeStore);

	// Search and filter state
	let searchQuery = $state('');
	let sortBy = $state<
		| 'name-asc'
		| 'name-desc'
		| 'recent'
		| 'oldest'
		| 'sessions-most'
		| 'sessions-least'
		| 'agents-most'
		| 'agents-least'
	>('recent');
	let filterType = $state<'all' | 'git' | 'non-git'>('all');
	let showSortDropdown = $state(false);
	let showFilterDropdown = $state(false);

	// Group projects by git root
	const grouped = $derived(groupProjects(allProjects));

	// Computed aggregate stats
	const stats = $derived.by(() => {
		const totalProjects = allProjects.length;
		// Count git projects from grouped structure
		const gitProjectCount =
			grouped.gitRoots.reduce(
				(sum, g) => sum + (g.rootProject ? 1 : 0) + g.nestedProjects.length,
				0
			) + grouped.singleGitProjects.length;
		const gitRepoCount = grouped.gitRoots.length + grouped.singleGitProjects.length;
		const totalSessions = allProjects.reduce((sum, p) => sum + p.session_count, 0);
		const totalAgents = allProjects.reduce((sum, p) => sum + p.agent_count, 0);

		return {
			totalProjects,
			gitProjectCount,
			gitRepoCount,
			totalSessions,
			totalAgents
		};
	});

	// Computed filtered and sorted projects with grouping
	const filteredGrouped = $derived.by(() => {
		let filtered = allProjects;

		// Apply search
		if (searchQuery.trim()) {
			const query = searchQuery.toLowerCase();
			filtered = filtered.filter(
				(p) =>
					getProjectName(p.path).toLowerCase().includes(query) ||
					p.path.toLowerCase().includes(query)
			);
		}

		// Apply type filter
		if (filterType === 'git') {
			filtered = filtered.filter(
				(p) => p.git_root_path !== null && p.git_root_path !== undefined
			);
		} else if (filterType === 'non-git') {
			filtered = filtered.filter((p) => !p.git_root_path);
		}

		// Helper to get latest activity time (prefer latest_session_time, fallback to sessions)
		const getActivityTime = (p: Project) =>
			p.latest_session_time ?? p.sessions?.[0]?.start_time;

		// Apply sort before grouping
		const sorted = [...filtered];
		switch (sortBy) {
			case 'name-asc':
				sorted.sort((a, b) => getProjectName(a.path).localeCompare(getProjectName(b.path)));
				break;
			case 'name-desc':
				sorted.sort((a, b) => getProjectName(b.path).localeCompare(getProjectName(a.path)));
				break;
			case 'recent':
				sorted.sort((a, b) => {
					const timeA = getActivityTime(a) ? new Date(getActivityTime(a)!).getTime() : 0;
					const timeB = getActivityTime(b) ? new Date(getActivityTime(b)!).getTime() : 0;
					return timeB - timeA;
				});
				break;
			case 'oldest':
				sorted.sort((a, b) => {
					const timeA = getActivityTime(a) ? new Date(getActivityTime(a)!).getTime() : 0;
					const timeB = getActivityTime(b) ? new Date(getActivityTime(b)!).getTime() : 0;
					return timeA - timeB;
				});
				break;
			case 'sessions-most':
				sorted.sort((a, b) => b.session_count - a.session_count);
				break;
			case 'sessions-least':
				sorted.sort((a, b) => a.session_count - b.session_count);
				break;
			case 'agents-most':
				sorted.sort((a, b) => b.agent_count - a.agent_count);
				break;
			case 'agents-least':
				sorted.sort((a, b) => a.agent_count - b.agent_count);
				break;
		}

		// Group the filtered and sorted projects
		return groupProjects(sorted);
	});

	// Check if all git roots are expanded
	const allRootPaths = $derived(filteredGrouped.gitRoots.map((g) => g.rootPath));
	const allExpanded = $derived(projectTreeStore.isAllExpanded(allRootPaths, storeState));

	// Toggle all expand/collapse
	function toggleExpandAll() {
		if (allExpanded) {
			projectTreeStore.collapseAll();
		} else {
			projectTreeStore.expandAll(allRootPaths);
		}
	}

	// Total count for display
	const totalFilteredCount = $derived(
		filteredGrouped.gitRoots.reduce(
			(sum, g) => sum + (g.rootProject ? 1 : 0) + g.nestedProjects.length,
			0
		) +
			filteredGrouped.singleGitProjects.length +
			filteredGrouped.otherProjects.length
	);

	function formatTime(timestamp?: string) {
		if (!timestamp) return 'No activity';
		const date = new Date(timestamp);
		const now = new Date();
		const diff = now.getTime() - date.getTime();
		const hours = Math.floor(diff / (1000 * 60 * 60));
		const days = Math.floor(hours / 24);

		if (hours < 1) return 'Just now';
		if (hours < 24) return `${hours}h ago`;
		if (days < 7) return `${days}d ago`;
		if (days < 30) return `${Math.floor(days / 7)}w ago`;
		return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
	}

	function getProjectName(path: string) {
		return path.split('/').pop() || path;
	}

	function getSortLabel(sort: typeof sortBy) {
		const labels = {
			'name-asc': 'Name (A-Z)',
			'name-desc': 'Name (Z-A)',
			recent: 'Recently Active',
			oldest: 'Oldest First',
			'sessions-most': 'Most Sessions',
			'sessions-least': 'Least Sessions',
			'agents-most': 'Most Agents',
			'agents-least': 'Least Agents'
		};
		return labels[sort];
	}

	function getFilterLabel(filter: typeof filterType) {
		const labels = {
			all: 'All Projects',
			git: 'Git Only',
			'non-git': 'Non-Git Only'
		};
		return labels[filter];
	}
</script>

<div use:listNavigation>
	<!-- Page Header with Breadcrumb -->
	<PageHeader
		title="Projects"
		icon={FolderOpen}
		iconColor="--nav-blue"
		breadcrumbs={[{ label: 'Dashboard', href: '/' }, { label: 'Projects' }]}
		subtitle="Active Claude Code workspaces"
	>
		{#snippet headerRight()}
			<!-- Compact Stats -->
			<div class="flex items-center gap-4 text-xs">
				<div
					class="flex items-center gap-1.5 px-2 py-1 rounded-md bg-[var(--bg-subtle)] border border-[var(--border-subtle)] table-nums"
				>
					<span class="text-[var(--text-muted)] font-medium">Total</span>
					<span class="text-[var(--text-primary)] font-semibold mono"
						>{stats.totalProjects}</span
					>
				</div>
				<div
					class="flex items-center gap-1.5 px-2 py-1 rounded-md bg-[var(--bg-subtle)] border border-[var(--border-subtle)] table-nums"
				>
					<span class="text-[var(--text-muted)] font-medium">Git Repos</span>
					<span class="text-[var(--text-primary)] font-semibold mono"
						>{stats.gitRepoCount}</span
					>
				</div>
				<div
					class="flex items-center gap-1.5 px-2 py-1 rounded-md bg-[var(--bg-subtle)] border border-[var(--border-subtle)] table-nums"
				>
					<span class="text-[var(--text-muted)] font-medium">Sessions</span>
					<span class="text-[var(--text-primary)] font-semibold mono"
						>{stats.totalSessions}</span
					>
				</div>
			</div>
		{/snippet}
	</PageHeader>

	<!-- Search and Filters -->
	<div class="mb-6 flex flex-col sm:flex-row gap-2">
		<!-- Search Bar -->
		<div class="flex-1 relative group">
			<div
				class="absolute left-2.5 top-1/2 -translate-y-1/2 text-[var(--text-faint)] group-focus-within:text-[var(--text-secondary)] transition-colors"
			>
				<Search size={14} strokeWidth={2} />
			</div>
			<input
				type="text"
				placeholder="Search projects..."
				bind:value={searchQuery}
				class="w-full pl-8 pr-3 h-9 text-sm font-medium bg-[var(--bg-base)] border border-[var(--border)] rounded-[6px] focus:outline-none focus:border-[var(--border-hover)] focus:ring-1 focus:ring-[var(--border-subtle)] transition-all placeholder:text-[var(--text-faint)] placeholder:font-normal text-[var(--text-primary)]"
				data-search-input
			/>
		</div>

		<!-- Sort Dropdown -->
		<div class="relative">
			<button
				onclick={() => {
					showSortDropdown = !showSortDropdown;
					showFilterDropdown = false;
				}}
				class="inline-flex items-center gap-2 px-3 h-9 text-xs font-medium bg-[var(--bg-base)] border border-[var(--border)] rounded-[6px] hover:bg-[var(--bg-subtle)] hover:border-[var(--border-hover)] transition-all whitespace-nowrap text-[var(--text-secondary)]"
			>
				<span>Sort:</span>
				<span class="text-[var(--text-primary)]">{getSortLabel(sortBy)}</span>
				<ChevronDown size={12} strokeWidth={2} class="text-[var(--text-faint)]" />
			</button>
			{#if showSortDropdown}
				<div
					class="absolute right-0 mt-1 w-48 bg-[var(--bg-base)] border border-[var(--border)] rounded-lg shadow-[var(--shadow-md)] z-10 py-1"
				>
					<button
						onclick={() => {
							sortBy = 'recent';
							showSortDropdown = false;
						}}
						class="w-full px-4 py-1.5 text-left text-xs font-medium hover:bg-[var(--bg-subtle)] transition-colors {sortBy ===
						'recent'
							? 'text-[var(--text-primary)]'
							: 'text-[var(--text-secondary)]'}"
					>
						Recently Active
					</button>
					<button
						onclick={() => {
							sortBy = 'oldest';
							showSortDropdown = false;
						}}
						class="w-full px-4 py-1.5 text-left text-xs font-medium hover:bg-[var(--bg-subtle)] transition-colors {sortBy ===
						'oldest'
							? 'text-[var(--text-primary)]'
							: 'text-[var(--text-secondary)]'}"
					>
						Oldest First
					</button>
					<div class="border-t border-[var(--border-subtle)] my-1"></div>
					<button
						onclick={() => {
							sortBy = 'name-asc';
							showSortDropdown = false;
						}}
						class="w-full px-4 py-1.5 text-left text-xs font-medium hover:bg-[var(--bg-subtle)] transition-colors {sortBy ===
						'name-asc'
							? 'text-[var(--text-primary)]'
							: 'text-[var(--text-secondary)]'}"
					>
						Name (A-Z)
					</button>
					<button
						onclick={() => {
							sortBy = 'name-desc';
							showSortDropdown = false;
						}}
						class="w-full px-4 py-1.5 text-left text-xs font-medium hover:bg-[var(--bg-subtle)] transition-colors {sortBy ===
						'name-desc'
							? 'text-[var(--text-primary)]'
							: 'text-[var(--text-secondary)]'}"
					>
						Name (Z-A)
					</button>
					<div class="border-t border-[var(--border-subtle)] my-1"></div>
					<button
						onclick={() => {
							sortBy = 'sessions-most';
							showSortDropdown = false;
						}}
						class="w-full px-4 py-1.5 text-left text-xs font-medium hover:bg-[var(--bg-subtle)] transition-colors {sortBy ===
						'sessions-most'
							? 'text-[var(--text-primary)]'
							: 'text-[var(--text-secondary)]'}"
					>
						Most Sessions
					</button>
					<button
						onclick={() => {
							sortBy = 'sessions-least';
							showSortDropdown = false;
						}}
						class="w-full px-4 py-1.5 text-left text-xs font-medium hover:bg-[var(--bg-subtle)] transition-colors {sortBy ===
						'sessions-least'
							? 'text-[var(--text-primary)]'
							: 'text-[var(--text-secondary)]'}"
					>
						Least Sessions
					</button>
				</div>
			{/if}
		</div>

		<!-- Filter Dropdown -->
		<div class="relative">
			<button
				onclick={() => {
					showFilterDropdown = !showFilterDropdown;
					showSortDropdown = false;
				}}
				class="inline-flex items-center gap-2 px-3 h-9 text-xs font-medium bg-[var(--bg-base)] border border-[var(--border)] rounded-[6px] hover:bg-[var(--bg-subtle)] hover:border-[var(--border-hover)] transition-all whitespace-nowrap text-[var(--text-secondary)]"
			>
				<span>Filter:</span>
				<span class="text-[var(--text-primary)]">{getFilterLabel(filterType)}</span>
				<ChevronDown size={12} strokeWidth={2} class="text-[var(--text-faint)]" />
			</button>
			{#if showFilterDropdown}
				<div
					class="absolute right-0 mt-1 w-40 bg-[var(--bg-base)] border border-[var(--border)] rounded-lg shadow-[var(--shadow-md)] z-10 py-1"
				>
					<button
						onclick={() => {
							filterType = 'all';
							showFilterDropdown = false;
						}}
						class="w-full px-4 py-1.5 text-left text-xs font-medium hover:bg-[var(--bg-subtle)] transition-colors {filterType ===
						'all'
							? 'text-[var(--text-primary)]'
							: 'text-[var(--text-secondary)]'}"
					>
						All Projects
					</button>
					<button
						onclick={() => {
							filterType = 'git';
							showFilterDropdown = false;
						}}
						class="w-full px-4 py-1.5 text-left text-xs font-medium hover:bg-[var(--bg-subtle)] transition-colors {filterType ===
						'git'
							? 'text-[var(--text-primary)]'
							: 'text-[var(--text-secondary)]'}"
					>
						Git Only
					</button>
					<button
						onclick={() => {
							filterType = 'non-git';
							showFilterDropdown = false;
						}}
						class="w-full px-4 py-1.5 text-left text-xs font-medium hover:bg-[var(--bg-subtle)] transition-colors {filterType ===
						'non-git'
							? 'text-[var(--text-primary)]'
							: 'text-[var(--text-secondary)]'}"
					>
						Non-Git Only
					</button>
				</div>
			{/if}
		</div>
	</div>

	<!-- Git Repositories Section -->
	{#if filteredGrouped.gitRoots.length > 0 || filteredGrouped.singleGitProjects.length > 0}
		<div class="mb-8">
			<!-- Section Header -->
			<div class="flex items-center justify-between mb-4">
				<h2
					class="text-sm font-semibold uppercase tracking-wide text-[var(--text-secondary)]"
				>
					Git Repositories
					<span class="text-[var(--text-faint)] font-medium ml-1.5">
						({stats.gitRepoCount})
					</span>
				</h2>

				{#if filteredGrouped.gitRoots.length > 0}
					<button
						onclick={toggleExpandAll}
						class="
							inline-flex items-center gap-1.5
							px-3 py-1.5
							text-xs font-medium
							text-[var(--text-secondary)]
							hover:text-[var(--text-primary)]
							bg-[var(--bg-subtle)]
							hover:bg-[var(--bg-muted)]
							border border-[var(--border)]
							rounded-[6px]
							transition-colors
						"
					>
						{#if allExpanded}
							<ChevronUp size={14} strokeWidth={2} />
							<span>Collapse All</span>
						{:else}
							<ChevronDown size={14} strokeWidth={2} />
							<span>Expand All</span>
						{/if}
					</button>
				{/if}
			</div>

			<!-- Collapsible Git Root Groups -->
			{#if filteredGrouped.gitRoots.length > 0}
				<div class="space-y-3 mb-4">
					{#each filteredGrouped.gitRoots as group (group.rootPath)}
						<ProjectTreeGroup {group} />
					{/each}
				</div>
			{/if}

			<!-- Single Git Projects (Flat Grid) -->
			{#if filteredGrouped.singleGitProjects.length > 0}
				<div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
					{#each filteredGrouped.singleGitProjects as project (project.encoded_name)}
						<ProjectCard {project} variant="default" hideGitBadge={true} />
					{/each}
				</div>
			{/if}
		</div>
	{/if}

	<!-- Non-Git Projects Section -->
	{#if filteredGrouped.otherProjects.length > 0}
		<div>
			<h2
				class="text-sm font-semibold uppercase tracking-wide text-[var(--text-secondary)] mb-4"
			>
				Non-Git Projects
				<span class="text-[var(--text-faint)] font-medium ml-1.5">
					({filteredGrouped.otherProjects.length})
				</span>
			</h2>

			<div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
				{#each filteredGrouped.otherProjects as project (project.encoded_name)}
					<ProjectCard {project} variant="default" />
				{/each}
			</div>
		</div>
	{/if}

	<!-- Empty State -->
	{#if totalFilteredCount === 0}
		<div class="text-center py-16">
			<div
				class="inline-flex items-center justify-center w-16 h-16 bg-[var(--bg-muted)] rounded-lg mb-4"
			>
				<FolderOpen size={28} class="text-[var(--text-faint)]" />
			</div>
			<h3 class="text-base font-semibold text-[var(--text-primary)] mb-2">
				{searchQuery || filterType !== 'all' ? 'No matching projects' : 'No projects found'}
			</h3>
			<p class="text-sm font-medium text-[var(--text-muted)]">
				{searchQuery || filterType !== 'all'
					? 'Try adjusting your filters'
					: 'Start using Claude Code to see your projects here'}
			</p>
		</div>
	{/if}
</div>

<!-- Click outside to close dropdowns -->
<svelte:window
	onclick={(e) => {
		const target = e.target as HTMLElement;
		if (!target.closest('button')) {
			showSortDropdown = false;
			showFilterDropdown = false;
		}
	}}
/>

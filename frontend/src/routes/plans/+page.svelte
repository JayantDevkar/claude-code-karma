<script lang="ts">
	import { browser } from '$app/environment';
	import { replaceState } from '$app/navigation';
	import { onMount, onDestroy } from 'svelte';
	import { FileText, Search, FolderOpen, GitBranch, ChevronDown, X, Globe } from 'lucide-svelte';
	import { listNavigation } from '$lib/actions/listNavigation';
	import PageHeader from '$lib/components/layout/PageHeader.svelte';
	import { PlanCard } from '$lib/components/plan';
	import Pagination from '$lib/components/Pagination.svelte';
	import TokenSearchInput from '$lib/components/TokenSearchInput.svelte';
	import { paramToTokens, tokensToParam } from '$lib/search';
	import { keyboardOverrides } from '$lib/stores/keyboardOverrides';
	import { API_BASE } from '$lib/config';
	import type { PlanListResponse, PlanWithContext, Project } from '$lib/api-types';
	import { isToday, isYesterday, isThisWeek, isThisMonth } from 'date-fns';

	// Server data (used for initial load only)
	let { data } = $props();

	// Client-side response state — starts from server data, updated by fetch
	// svelte-ignore state_referenced_locally
	let plansResponse = $state<PlanListResponse>(data.plansResponse);
	// svelte-ignore state_referenced_locally
	let projects = $state<Project[]>(data.projects);
	let isLoading = $state(false);
	let fetchController: AbortController | null = null;

	// Ctrl+K support
	let searchInputRef: { focus: () => void } | undefined;
	let unregisterCtrlK: (() => void) | undefined;

	onMount(() => {
		// Register CTRL+K override to focus search input on this page
		unregisterCtrlK = keyboardOverrides.registerCtrlK(() => {
			searchInputRef?.focus();
		});
	});

	onDestroy(() => {
		unregisterCtrlK?.();
	});

	// Pagination state
	// svelte-ignore state_referenced_locally
	let currentPage = $state(data.page || 1);
	// svelte-ignore state_referenced_locally
	let perPage = $state(data.perPage || 24);

	// Filter state - initialize from server data
	// svelte-ignore state_referenced_locally
	let searchTokens = $state<string[]>(data.search ? paramToTokens(data.search) : []);
	// svelte-ignore state_referenced_locally
	let selectedProject = $state<string | null>(data.project || null);
	// svelte-ignore state_referenced_locally
	let selectedBranch = $state<string | null>(data.branch || null);
	// svelte-ignore state_referenced_locally
	let selectedSource = $state<string | null>(data.source || null);
	let showProjectDropdown = $state(false);
	let showBranchDropdown = $state(false);

	// Track if this is the initial mount (skip first fetch since we have server data)
	let initialized = $state(false);

	// Extract available projects from projects list
	let availableProjects = $derived(projects);

	// Extract unique branches for selected project from current plans
	let availableBranches = $derived.by(() => {
		if (!selectedProject) return [];

		const branchSet = new Set<string>();

		for (const plan of plansResponse.plans) {
			if (
				plan.session_context &&
				plan.session_context.project_encoded_name === selectedProject &&
				plan.session_context.git_branches
			) {
				for (const branch of plan.session_context.git_branches) {
					branchSet.add(branch);
				}
			}
		}

		return Array.from(branchSet).sort();
	});

	// Build URL params from current state
	function buildParams(): URLSearchParams {
		const params = new URLSearchParams();
		const searchParam = tokensToParam(searchTokens);
		if (searchParam) params.set('search', searchParam);
		if (selectedProject) params.set('project', selectedProject);
		if (selectedBranch) params.set('branch', selectedBranch);
		if (selectedSource) params.set('source', selectedSource);
		params.set('page', currentPage.toString());
		params.set('per_page', perPage.toString());
		return params;
	}

	// Sync URL without triggering navigation (like sessions page)
	function syncUrl() {
		if (!browser) return;
		const params = new URLSearchParams();
		const searchParam = tokensToParam(searchTokens);
		if (searchParam) params.set('search', searchParam);
		if (selectedProject) params.set('project', selectedProject);
		if (selectedBranch) params.set('branch', selectedBranch);
		if (selectedSource) params.set('source', selectedSource);
		if (currentPage > 1) params.set('page', currentPage.toString());
		if (perPage !== 24) params.set('per_page', perPage.toString());

		const newUrl = params.toString() ? `?${params}` : window.location.pathname;
		try {
			replaceState(newUrl, {});
		} catch {
			// Router may not be initialized yet during SSR/hydration
		}
	}

	// Client-side fetch for plans data
	async function fetchPlans() {
		if (!browser) return;

		// Abort any in-flight request
		if (fetchController) fetchController.abort();
		fetchController = new AbortController();

		isLoading = true;
		try {
			const params = buildParams();
			const res = await fetch(`${API_BASE}/plans/with-context?${params}`, {
				signal: fetchController.signal
			});
			if (res.ok) {
				plansResponse = await res.json();
			}
		} catch (e) {
			if (e instanceof Error && e.name === 'AbortError') return;
			console.error('Failed to fetch plans:', e);
		} finally {
			isLoading = false;
			fetchController = null;
		}
	}

	// Reactive fetch: whenever filters/page change, fetch new data and sync URL
	$effect(() => {
		// Read all reactive dependencies
		const _tokens = searchTokens;
		const _project = selectedProject;
		const _branch = selectedBranch;
		const _source = selectedSource;
		const _page = currentPage;
		const _perPage = perPage;

		if (!initialized) {
			initialized = true;
			return; // Skip first run — we already have server data
		}

		syncUrl();
		fetchPlans();
	});

	// Handle browser back/forward
	$effect(() => {
		if (!browser) return;

		const handlePopState = () => {
			const url = new URL(window.location.href);
			const search = url.searchParams.get('search') || '';
			searchTokens = search ? paramToTokens(search) : [];
			selectedProject = url.searchParams.get('project') || null;
			selectedBranch = url.searchParams.get('branch') || null;
			selectedSource = url.searchParams.get('source') || null;
			currentPage = parseInt(url.searchParams.get('page') || '1', 10);
			perPage = parseInt(url.searchParams.get('per_page') || '24', 10);
		};

		window.addEventListener('popstate', handlePopState);
		return () => window.removeEventListener('popstate', handlePopState);
	});

	// Handle token changes — reset to page 1
	function handleTokensChange(tokens: string[]) {
		searchTokens = tokens;
		currentPage = 1;
	}

	// Handle project change — reset branch and page
	function handleProjectChange(project: string | null) {
		selectedProject = project;
		selectedBranch = null;
		currentPage = 1;
		showProjectDropdown = false;
	}

	// Handle branch change — reset page
	function handleBranchChange(branch: string | null) {
		selectedBranch = branch;
		currentPage = 1;
		showBranchDropdown = false;
	}

	// Plans from current response
	let filteredPlans = $derived(plansResponse.plans);

	// Pagination handler
	function goToPage(page: number) {
		currentPage = page;
	}

	// Day-based grouping (operates on current page's plans)
	type DateGroup = {
		label: string;
		plans: PlanWithContext[];
	};

	let groupedByDate = $derived.by(() => {
		const today: PlanWithContext[] = [];
		const yesterday: PlanWithContext[] = [];
		const thisWeek: PlanWithContext[] = [];
		const thisMonth: PlanWithContext[] = [];
		const older: PlanWithContext[] = [];

		for (const plan of filteredPlans) {
			const modified = new Date(plan.modified);

			if (isToday(modified)) {
				today.push(plan);
			} else if (isYesterday(modified)) {
				yesterday.push(plan);
			} else if (isThisWeek(modified, { weekStartsOn: 1 })) {
				thisWeek.push(plan);
			} else if (isThisMonth(modified)) {
				thisMonth.push(plan);
			} else {
				older.push(plan);
			}
		}

		const groups: DateGroup[] = [];
		if (today.length > 0) groups.push({ label: 'Today', plans: today });
		if (yesterday.length > 0) groups.push({ label: 'Yesterday', plans: yesterday });
		if (thisWeek.length > 0) groups.push({ label: 'This Week', plans: thisWeek });
		if (thisMonth.length > 0) groups.push({ label: 'This Month', plans: thisMonth });
		if (older.length > 0) groups.push({ label: 'Older', plans: older });

		return groups;
	});

	// Check if we have any plans
	let hasResults = $derived(plansResponse.total > 0);
	let hasActiveFilters = $derived(
		searchTokens.length > 0 || selectedProject !== null || selectedBranch !== null || selectedSource !== null
	);

	// Helper to get project name from path
	function getProjectName(path: string): string {
		return path.split('/').pop() || path;
	}

	// Helper to get selected project path for display
	let selectedProjectPath = $derived(
		availableProjects.find((p) => p.encoded_name === selectedProject)?.path || ''
	);

	// Clear all filters
	function clearFilters() {
		searchTokens = [];
		selectedProject = null;
		selectedBranch = null;
		selectedSource = null;
		currentPage = 1;
	}
</script>

<div use:listNavigation>
	<!-- Page Header with Breadcrumb -->
	<PageHeader
		title="Plans"
		icon={FileText}
		iconColor="--nav-yellow"
		breadcrumbs={[{ label: 'Dashboard', href: '/' }, { label: 'Plans' }]}
		subtitle="Implementation plans from Claude Code plan mode sessions"
	>
		{#snippet headerRight()}
			<!-- Compact Stats -->
			<div class="flex items-center gap-4 text-xs">
				<div
					class="flex items-center gap-1.5 px-2 py-1 rounded-md bg-[var(--bg-subtle)] border border-[var(--border-subtle)] table-nums"
				>
					<span class="text-[var(--text-muted)] font-medium">Total</span>
					<span class="text-[var(--text-primary)] font-semibold mono"
						>{plansResponse.total}</span
					>
				</div>
			</div>
		{/snippet}
	</PageHeader>

	<!-- Search and Filters -->
	<div class="mb-6 flex flex-col sm:flex-row gap-2">
		<!-- Token Search Bar -->
		<TokenSearchInput
			bind:this={searchInputRef}
			tokens={searchTokens}
			onTokensChange={handleTokensChange}
			placeholder="Search plans by title, slug, or content..."
			class="flex-1"
			{isLoading}
		/>

		<!-- Project Filter Dropdown -->
		<div class="relative">
			<button
				onclick={() => {
					showProjectDropdown = !showProjectDropdown;
					showBranchDropdown = false;
				}}
				class="inline-flex items-center gap-2 px-3 h-9 text-xs font-medium rounded-[6px] hover:border-[var(--border-hover)] transition-all whitespace-nowrap {selectedProject
					? 'bg-[var(--subagent-plan-subtle)] border border-[var(--subagent-plan)] text-[var(--subagent-plan)]'
					: 'bg-[var(--bg-base)] border border-[var(--border)] text-[var(--text-secondary)] hover:bg-[var(--bg-subtle)]'}"
			>
				<FolderOpen
					size={12}
					strokeWidth={2}
					class={selectedProject
						? 'text-[var(--subagent-plan)]'
						: 'text-[var(--text-faint)]'}
				/>
				<span>Project:</span>
				<span
					class="max-w-[120px] truncate {selectedProject
						? 'text-[var(--subagent-plan)]'
						: 'text-[var(--text-primary)]'}"
				>
					{selectedProject ? getProjectName(selectedProjectPath) : 'All'}
				</span>
				<ChevronDown
					size={12}
					strokeWidth={2}
					class={selectedProject
						? 'text-[var(--subagent-plan)]'
						: 'text-[var(--text-faint)]'}
				/>
			</button>
			{#if showProjectDropdown}
				<div
					class="absolute right-0 mt-1 w-64 bg-[var(--bg-base)] border border-[var(--border)] rounded-lg shadow-[var(--shadow-md)] z-10 py-1 max-h-80 overflow-y-auto"
				>
					<button
						onclick={() => handleProjectChange(null)}
						class="w-full px-4 py-1.5 text-left text-xs font-medium hover:bg-[var(--bg-subtle)] transition-colors {selectedProject ===
						null
							? 'text-[var(--text-primary)] bg-[var(--bg-subtle)]'
							: 'text-[var(--text-secondary)]'}"
					>
						All Projects
					</button>
					<div class="border-t border-[var(--border-subtle)] my-1"></div>
					{#each availableProjects as project (project.encoded_name)}
						<button
							onclick={() => handleProjectChange(project.encoded_name)}
							class="w-full px-4 py-1.5 text-left text-xs font-medium hover:bg-[var(--bg-subtle)] transition-colors flex items-center justify-between gap-2 {selectedProject ===
							project.encoded_name
								? 'text-[var(--text-primary)] bg-[var(--bg-subtle)]'
								: 'text-[var(--text-secondary)]'}"
						>
							<span class="truncate" title={project.path}
								>{getProjectName(project.path)}</span
							>
						</button>
					{/each}
				</div>
			{/if}
		</div>

		<!-- Branch Filter Dropdown (only shown when project is selected) -->
		{#if selectedProject && availableBranches.length > 0}
			<div class="relative">
				<button
					onclick={() => {
						showBranchDropdown = !showBranchDropdown;
						showProjectDropdown = false;
					}}
					class="inline-flex items-center gap-2 px-3 h-9 text-xs font-medium rounded-[6px] hover:border-[var(--border-hover)] transition-all whitespace-nowrap {selectedBranch
						? 'bg-[var(--subagent-plan-subtle)] border border-[var(--subagent-plan)] text-[var(--subagent-plan)]'
						: 'bg-[var(--bg-base)] border border-[var(--border)] text-[var(--text-secondary)] hover:bg-[var(--bg-subtle)]'}"
				>
					<GitBranch
						size={12}
						strokeWidth={2}
						class={selectedBranch
							? 'text-[var(--subagent-plan)]'
							: 'text-[var(--text-faint)]'}
					/>
					<span>Branch:</span>
					<span
						class="max-w-[100px] truncate {selectedBranch
							? 'text-[var(--subagent-plan)]'
							: 'text-[var(--text-primary)]'}"
					>
						{selectedBranch || 'All'}
					</span>
					<ChevronDown
						size={12}
						strokeWidth={2}
						class={selectedBranch
							? 'text-[var(--subagent-plan)]'
							: 'text-[var(--text-faint)]'}
					/>
				</button>
				{#if showBranchDropdown}
					<div
						class="absolute right-0 mt-1 w-56 bg-[var(--bg-base)] border border-[var(--border)] rounded-lg shadow-[var(--shadow-md)] z-10 py-1 max-h-80 overflow-y-auto"
					>
						<button
							onclick={() => {
								selectedBranch = null;
								showBranchDropdown = false;
								currentPage = 1;
							}}
							class="w-full px-4 py-1.5 text-left text-xs font-medium hover:bg-[var(--bg-subtle)] transition-colors {selectedBranch ===
							null
								? 'text-[var(--text-primary)] bg-[var(--bg-subtle)]'
								: 'text-[var(--text-secondary)]'}"
						>
							All Branches
						</button>
						<div class="border-t border-[var(--border-subtle)] my-1"></div>
						{#each availableBranches as branch (branch)}
							<button
								onclick={() => {
									selectedBranch = branch;
									showBranchDropdown = false;
								}}
								class="w-full px-4 py-1.5 text-left text-xs font-medium hover:bg-[var(--bg-subtle)] transition-colors truncate {selectedBranch ===
								branch
									? 'text-[var(--text-primary)] bg-[var(--bg-subtle)]'
									: 'text-[var(--text-secondary)]'}"
								title={branch}
							>
								{branch}
							</button>
						{/each}
					</div>
				{/if}
			</div>
		{/if}

		<!-- Source Filter (Local / Remote / All) -->
		<div class="flex items-center">
			<button
				onclick={() => {
					if (selectedSource === null) selectedSource = 'remote';
					else if (selectedSource === 'remote') selectedSource = 'local';
					else selectedSource = null;
					currentPage = 1;
				}}
				class="inline-flex items-center gap-2 px-3 h-9 text-xs font-medium rounded-[6px] hover:border-[var(--border-hover)] transition-all whitespace-nowrap {selectedSource
					? 'bg-[var(--subagent-plan-subtle)] border border-[var(--subagent-plan)] text-[var(--subagent-plan)]'
					: 'bg-[var(--bg-base)] border border-[var(--border)] text-[var(--text-secondary)] hover:bg-[var(--bg-subtle)]'}"
				title="Filter by source: {selectedSource || 'all'}"
			>
				<Globe
					size={12}
					strokeWidth={2}
					class={selectedSource
						? 'text-[var(--subagent-plan)]'
						: 'text-[var(--text-faint)]'}
				/>
				<span>{selectedSource === 'remote' ? 'Remote' : selectedSource === 'local' ? 'Local' : 'All'}</span>
			</button>
		</div>

		<!-- Clear Filters Button (shown when filters are active) -->
		{#if hasActiveFilters}
			<button
				onclick={clearFilters}
				class="inline-flex items-center gap-1.5 px-3 h-9 text-xs font-medium text-[var(--text-secondary)] hover:text-[var(--text-primary)] bg-[var(--bg-base)] border border-[var(--border)] rounded-[6px] hover:bg-[var(--bg-subtle)] hover:border-[var(--border-hover)] transition-all"
			>
				<X size={12} strokeWidth={2} />
				<span>Clear</span>
			</button>
		{/if}
	</div>

	<!-- Active Filters Summary -->
	{#if selectedProject || selectedBranch}
		<div class="mb-4 flex items-center gap-2 text-xs text-[var(--text-muted)]">
			<span>Showing plans for</span>
			{#if selectedProject}
				<span
					class="inline-flex items-center gap-1 px-2 py-0.5 bg-[var(--subagent-plan-subtle)] border border-[var(--subagent-plan)] rounded font-medium text-[var(--subagent-plan)]"
				>
					<FolderOpen size={10} />
					{getProjectName(selectedProjectPath)}
				</span>
			{/if}
			{#if selectedBranch}
				<span
					class="inline-flex items-center gap-1 px-2 py-0.5 bg-[var(--subagent-plan-subtle)] border border-[var(--subagent-plan)] rounded font-medium text-[var(--subagent-plan)]"
				>
					<GitBranch size={10} />
					{selectedBranch}
				</span>
			{/if}
			<span class="text-[var(--text-faint)]">({plansResponse.total} plans)</span>
		</div>
	{/if}

	<!-- Content Area -->
	<div class="transition-opacity duration-150" style:opacity={isLoading ? 0.6 : 1}>
		{#if !hasResults && !hasActiveFilters}
			<!-- Empty State: No plans at all -->
			<div class="text-center py-16">
				<div
					class="inline-flex items-center justify-center w-16 h-16 bg-[var(--bg-muted)] rounded-lg mb-4"
				>
					<FileText size={28} class="text-[var(--text-faint)]" />
				</div>
				<h3 class="text-base font-semibold text-[var(--text-primary)] mb-2">
					No plans found
				</h3>
				<p class="text-sm font-medium text-[var(--text-muted)]">
					Plans will appear here when you use Claude Code's plan mode
				</p>
			</div>
		{:else if !hasResults && hasActiveFilters}
			<!-- Empty State: No matching results -->
			<div class="text-center py-16">
				<div
					class="inline-flex items-center justify-center w-16 h-16 bg-[var(--bg-muted)] rounded-lg mb-4"
				>
					<Search size={28} class="text-[var(--text-faint)]" />
				</div>
				<h3 class="text-base font-semibold text-[var(--text-primary)] mb-2">
					No matching plans
				</h3>
				<p class="text-sm font-medium text-[var(--text-muted)]">
					Try adjusting your search query or filters
				</p>
				<button
					onclick={clearFilters}
					class="mt-4 inline-flex items-center gap-1.5 px-4 py-2 text-sm font-medium text-[var(--text-secondary)] hover:text-[var(--text-primary)] bg-[var(--bg-subtle)] border border-[var(--border)] rounded-lg hover:bg-[var(--bg-muted)] transition-all"
				>
					<X size={14} />
					Clear all filters
				</button>
			</div>
		{:else}
			<!-- Day-based Grouped View -->
			<div class="space-y-8">
				{#each groupedByDate as group (group.label)}
					<div>
						<!-- Section Header -->
						<h2
							class="text-sm font-semibold uppercase tracking-wide text-[var(--text-secondary)] mb-4"
						>
							{group.label}
							<span class="text-[var(--text-faint)] font-medium ml-1.5">
								({group.plans.length})
							</span>
						</h2>

						<!-- Plan Cards Grid -->
						<div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-3">
							{#each group.plans as plan (`${plan.slug}-${plan.remote_user_id ?? 'local'}`)}
								<PlanCard {plan} />
							{/each}
						</div>
					</div>
				{/each}
			</div>

			<!-- Pagination Controls -->
			<Pagination
				total={plansResponse.total}
				page={currentPage}
				{perPage}
				totalPages={plansResponse.total_pages}
				onPageChange={goToPage}
				itemLabel="plans"
			/>
		{/if}
	</div>
</div>

<!-- Click outside to close dropdowns -->
<svelte:window
	onclick={(e) => {
		const target = e.target as HTMLElement;
		if (!target.closest('button')) {
			showProjectDropdown = false;
			showBranchDropdown = false;
		}
	}}
/>

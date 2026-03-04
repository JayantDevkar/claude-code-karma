<script lang="ts">
	import { browser } from '$app/environment';
	import { page, navigating } from '$app/stores';
	import { History, Search, Archive, FolderOpen, MessageSquare } from 'lucide-svelte';
	import { ArchivedPageSkeleton } from '$lib/components/skeleton';
	import EmptyState from '$lib/components/ui/EmptyState.svelte';
	import ArchivedProjectGroup from '$lib/components/ArchivedProjectGroup.svelte';
	import PageHeader from '$lib/components/layout/PageHeader.svelte';
	import SegmentedControl from '$lib/components/ui/SegmentedControl.svelte';
	import type { ArchivedPromptsResponse, ArchivedProject } from '$lib/api-types';

	let { data } = $props();
	let archived = $derived(data.archived as ArchivedPromptsResponse);

	let isLoading = $derived(!!$navigating && $navigating.to?.route.id === '/archived');

	// Search state — initialized from URL on mount
	let searchInput = $state(browser ? ($page.url.searchParams.get('search') ?? '') : '');

	// View mode driven by segmented control
	let viewMode = $state<'all' | 'recent' | 'active'>('all');

	const viewOptions = [
		{ label: 'All', value: 'all' },
		{ label: 'Recent', value: 'recent' },
		{ label: 'Most Active', value: 'active' }
	];

	// Client-side search filter: matches project name or prompt content
	let filteredProjects = $derived.by<ArchivedProject[]>(() => {
		const query = searchInput.trim().toLowerCase();
		if (!query) return archived.projects;

		return archived.projects
			.map((project) => {
				// Check if project name matches
				const nameMatch = project.project_name.toLowerCase().includes(query);

				// Filter sessions to those with matching prompts
				const matchingSessions = project.sessions
					.map((session) => {
						const matchingPrompts = session.prompts.filter((p) =>
							p.display.toLowerCase().includes(query)
						);
						if (matchingPrompts.length === 0 && !nameMatch) return null;
						// If name matches, keep entire session; otherwise only matching prompts
						if (nameMatch && matchingPrompts.length === 0) return session;
						return {
							...session,
							prompts: matchingPrompts,
							prompt_count: matchingPrompts.length,
							first_prompt_preview:
								matchingPrompts[0]?.display.slice(0, 150) +
								(matchingPrompts[0]?.display.length > 150 ? '...' : '')
						};
					})
					.filter(Boolean) as ArchivedProject['sessions'];

				if (matchingSessions.length === 0) return null;

				return {
					...project,
					sessions: matchingSessions,
					session_count: matchingSessions.length,
					prompt_count: matchingSessions.reduce((sum, s) => sum + s.prompt_count, 0)
				};
			})
			.filter(Boolean) as ArchivedProject[];
	});

	// Apply view mode sorting/filtering on top of search results
	let displayProjects = $derived.by<ArchivedProject[]>(() => {
		const projects = [...filteredProjects];
		switch (viewMode) {
			case 'recent': {
				const thirtyDays = 30 * 24 * 60 * 60 * 1000;
				const cutoff = Date.now() - thirtyDays;
				return projects
					.filter((p) => new Date(p.date_range.end).getTime() >= cutoff)
					.sort(
						(a, b) =>
							new Date(b.date_range.end).getTime() -
							new Date(a.date_range.end).getTime()
					);
			}
			case 'active':
				return projects.sort((a, b) => b.session_count - a.session_count);
			default:
				return projects;
		}
	});

	// Filtered counts for badges
	let filteredSessionCount = $derived(
		filteredProjects.reduce((sum, p) => sum + p.session_count, 0)
	);
	let filteredPromptCount = $derived(
		filteredProjects.reduce((sum, p) => sum + p.prompt_count, 0)
	);
	let isSearching = $derived(searchInput.trim().length > 0);

	let hasProjects = $derived(archived.projects.length > 0);

	// Sync search to URL via history.replaceState (no SvelteKit navigation)
	let urlSyncTimeout: ReturnType<typeof setTimeout>;
	function handleSearchInput(event: Event) {
		const value = (event.target as HTMLInputElement).value;
		searchInput = value;

		if (!browser) return;
		clearTimeout(urlSyncTimeout);
		urlSyncTimeout = setTimeout(() => {
			const url = new URL(window.location.href);
			if (value.trim()) {
				url.searchParams.set('search', value.trim());
			} else {
				url.searchParams.delete('search');
			}
			window.history.replaceState(window.history.state, '', url.toString());
		}, 300);
	}

	function clearSearch() {
		searchInput = '';
		if (browser) {
			const url = new URL(window.location.href);
			url.searchParams.delete('search');
			window.history.replaceState(window.history.state, '', url.toString());
		}
	}
</script>

<div class="space-y-6">
	{#if isLoading}
		<div role="status" aria-busy="true" aria-label="Loading...">
			<ArchivedPageSkeleton />
		</div>
	{:else}
	<!-- Page Header with inline stat badges -->
	<PageHeader
		title="Archived"
		icon={History}
		iconColor="--nav-gray"
		breadcrumbs={[{ label: 'Dashboard', href: '/' }, { label: 'Archived' }]}
		subtitle="Archived prompts from sessions that have been cleaned up"
	>
		{#snippet badges()}
			{#if hasProjects}
				<div class="flex items-center gap-2">
					<span
						class="inline-flex items-center gap-1.5 px-2.5 py-1 text-xs font-medium rounded-full border border-[var(--border)] bg-[var(--bg-subtle)] text-[var(--text-secondary)]"
					>
						<Archive size={12} />
						Sessions {isSearching
							? `${filteredSessionCount} / ${archived.total_archived_sessions}`
							: archived.total_archived_sessions}
					</span>
					<span
						class="inline-flex items-center gap-1.5 px-2.5 py-1 text-xs font-medium rounded-full border border-[var(--border)] bg-[var(--bg-subtle)] text-[var(--text-secondary)]"
					>
						<MessageSquare size={12} />
						Prompts {isSearching
							? `${filteredPromptCount.toLocaleString()} / ${archived.total_archived_prompts.toLocaleString()}`
							: archived.total_archived_prompts.toLocaleString()}
					</span>
					<span
						class="inline-flex items-center gap-1.5 px-2.5 py-1 text-xs font-medium rounded-full border border-[var(--border)] bg-[var(--bg-subtle)] text-[var(--text-secondary)]"
					>
						<FolderOpen size={12} />
						Projects {isSearching
							? `${filteredProjects.length} / ${archived.projects.length}`
							: archived.projects.length}
					</span>
				</div>
			{/if}
		{/snippet}
	</PageHeader>

	<!-- Filters Row: Search full-width, then controls -->
	<div class="flex flex-col sm:flex-row items-start sm:items-center gap-4">
		<!-- Search Input -->
		<div class="relative flex-1 w-full">
			<Search
				class="absolute left-3 top-1/2 -translate-y-1/2 text-[var(--text-muted)]"
				size={16}
			/>
			<input
				type="text"
				value={searchInput}
				oninput={handleSearchInput}
				placeholder="Search archived prompts..."
				class="
					pl-9 pr-4 py-2
					bg-[var(--bg-base)]
					border border-[var(--border)]
					rounded-lg text-sm
					focus:outline-none focus:border-[var(--accent)] focus:ring-2 focus:ring-[var(--accent)]/20
					w-full
					transition-all
					text-[var(--text-primary)]
					placeholder:text-[var(--text-faint)]
				"
				data-search-input
			/>
			{#if searchInput}
				<button
					onclick={clearSearch}
					class="
						absolute right-3 top-1/2 -translate-y-1/2
						text-[var(--text-muted)] hover:text-[var(--text-primary)]
						transition-colors
					"
				>
					&times;
				</button>
			{/if}
		</div>

		<!-- View Mode Segmented Control -->
		<SegmentedControl options={viewOptions} bind:value={viewMode} />
	</div>

	<!-- Content: flat list based on view mode -->
	{#if displayProjects.length > 0}
		<div class="space-y-3">
			{#each displayProjects as project (project.encoded_name)}
				<ArchivedProjectGroup {project} />
			{/each}
		</div>
	{:else if searchInput}
		<EmptyState
			icon={Search}
			title="No matching prompts"
			description="No archived prompts match your search query."
		>
			<button onclick={clearSearch} class="text-sm text-[var(--accent)] hover:underline">
				Clear search
			</button>
		</EmptyState>
	{:else if viewMode === 'recent' && hasProjects}
		<EmptyState
			icon={Archive}
			title="No recent archived projects"
			description="No projects have been archived in the last 30 days. Try switching to All to see everything."
		/>
	{:else}
		<EmptyState
			icon={Archive}
			title="No archived prompts"
			description="When sessions are cleaned up by Claude Code's retention policy, their prompts will appear here."
		>
			<p class="text-xs text-[var(--text-muted)] mt-2">
				Your current retention setting preserves session data. Prompts from sessions deleted
				before you changed this setting would appear here.
			</p>
		</EmptyState>
	{/if}
	{/if}
</div>

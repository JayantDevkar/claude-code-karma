<script lang="ts">
	import { FolderGit2, RefreshCw, Search, CheckCircle2, Users } from 'lucide-svelte';
	import type { SyncProject } from '$lib/api-types';
	import { API_BASE } from '$lib/config';
	import { pushSyncAction } from '$lib/stores/syncActions.svelte';
	import ProjectRow from '$lib/components/sync/ProjectRow.svelte';

	interface ApiProject {
		display_name: string | null;
		encoded_name: string;
		session_count?: number;
	}

	interface TeamProject {
		name: string;
		encoded_name: string;
		path?: string;
	}

	interface Team {
		name: string;
		projects: TeamProject[];
		members: string[];
	}

	interface ProjectStatusEntry {
		local_count: number;
		packaged_count: number;
		received_counts: Record<string, number>;
		gap: number;
	}

	let { active = false, teamName = null }: { active?: boolean; teamName?: string | null } =
		$props();

	let projects = $state<SyncProject[]>([]);
	let loading = $state(true);
	let error = $state<string | null>(null);
	let selectingAll = $state(false);
	let projectStatusMap = $state<Map<string, ProjectStatusEntry>>(new Map());

	// Search/filter state
	let searchQuery = $state('');

	// Enable All confirmation state
	let showEnableAllConfirm = $state(false);

	// Flash message state
	let flashMessage = $state<string | null>(null);
	let flashTimeout: ReturnType<typeof setTimeout> | null = null;

	function showFlash(msg: string) {
		flashMessage = msg;
		if (flashTimeout) clearTimeout(flashTimeout);
		flashTimeout = setTimeout(() => (flashMessage = null), 3000);
	}

	// Filtered projects (case-insensitive search on name)
	let filteredProjects = $derived(
		searchQuery.trim()
			? projects.filter((p) =>
					p.name.toLowerCase().includes(searchQuery.trim().toLowerCase())
				)
			: projects
	);

	async function loadProjects() {
		if (!teamName) return;
		if (projects.length === 0) loading = true;
		error = null;
		try {
			const [projectsRes, teamsRes] = await Promise.all([
				fetch(`${API_BASE}/projects`),
				fetch(`${API_BASE}/sync/teams`).catch(() => null)
			]);

			const apiProjects: ApiProject[] = projectsRes.ok ? await projectsRes.json() : [];
			const teamsData = teamsRes?.ok ? await teamsRes.json() : { teams: [] };
			const teams: Team[] = teamsData.teams ?? [];

			// Only look at the team matching teamName
			const activeTeam = teams.find((t) => t.name === teamName) ?? null;

			// Collect synced encoded_names from the active team only
			const syncedSet = new Set<string>();
			const memberCountMap = new Map<string, number>();
			if (activeTeam) {
				for (const tp of activeTeam.projects) {
					syncedSet.add(tp.encoded_name);
					memberCountMap.set(tp.encoded_name, activeTeam.members.length);
				}
			}

			// Fetch project-status for the active team
			const newStatusMap = new Map<string, ProjectStatusEntry>();
			if (teamName) {
				const statusRes = await fetch(
					`${API_BASE}/sync/teams/${encodeURIComponent(teamName)}/project-status`
				).catch(() => null);
				if (statusRes?.ok) {
					const statusData: Record<string, ProjectStatusEntry> = await statusRes.json();
					for (const [name, entry] of Object.entries(statusData)) {
						newStatusMap.set(name, entry);
					}
				}
			}
			projectStatusMap = newStatusMap;

			const built = apiProjects.map((p) => {
				const isSynced = syncedSet.has(p.encoded_name);
				return {
					name: p.display_name ?? p.encoded_name,
					encoded_name: p.encoded_name,
					local_session_count: p.session_count ?? 0,
					synced: isSynced,
					status: isSynced ? ('synced' as const) : ('not-syncing' as const),
					last_sync_at: null,
					machine_count: isSynced ? (memberCountMap.get(p.encoded_name) ?? 0) : 0,
					pending_count: 0
				};
			});

			// Sort: synced first, then alphabetical within each group
			built.sort((a, b) => {
				if (a.synced !== b.synced) return a.synced ? -1 : 1;
				return a.name.localeCompare(b.name);
			});

			projects = built;
		} catch {
			error = 'Failed to load projects.';
		} finally {
			loading = false;
		}
	}

	async function handleToggle(encodedName: string, enable: boolean) {
		if (!teamName) return;
		if (enable) {
			await fetch(`${API_BASE}/sync/teams/${encodeURIComponent(teamName)}/projects`, {
				method: 'POST',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify({ name: encodedName, encoded_name: encodedName, path: '' })
			});
			pushSyncAction('project_added', `Project shared with team`, teamName ?? '');
		} else {
			await fetch(
				`${API_BASE}/sync/teams/${encodeURIComponent(teamName)}/projects/${encodeURIComponent(encodedName)}`,
				{ method: 'DELETE' }
			);
			pushSyncAction('project_removed', `Project removed from team`, teamName ?? '');
		}
		await loadProjects();
	}

	async function handleSyncNow(encodedName: string) {
		await fetch(`${API_BASE}/sync/projects/${encodeURIComponent(encodedName)}/sync-now`, {
			method: 'POST'
		});
		await loadProjects();
		showFlash('Sync triggered');
	}

	function handleAction(msg: string) {
		showFlash(msg);
	}

	async function enableAll() {
		if (!teamName) return;
		const unsynced = projects.filter((p) => !p.synced);
		if (unsynced.length === 0) return;
		selectingAll = true;
		showEnableAllConfirm = false;
		try {
			await Promise.all(
				unsynced.map((p) =>
					fetch(`${API_BASE}/sync/teams/${encodeURIComponent(teamName!)}/projects`, {
						method: 'POST',
						headers: { 'Content-Type': 'application/json' },
						body: JSON.stringify({ name: p.encoded_name, encoded_name: p.encoded_name, path: '' })
					})
				)
			);
			await loadProjects();
			showFlash(`Enabled sync for ${unsynced.length} project${unsynced.length !== 1 ? 's' : ''}`);
		} finally {
			selectingAll = false;
		}
	}

	let unsyncedCount = $derived(projects.filter((p) => !p.synced).length);

	// Detect duplicate display names to show disambiguating subtitles
	let duplicateNames = $derived.by<Set<string>>(() => {
		const counts = new Map<string, number>();
		for (const p of projects) {
			counts.set(p.name, (counts.get(p.name) ?? 0) + 1);
		}
		return new Set([...counts.entries()].filter(([, c]) => c > 1).map(([n]) => n));
	});

	function getSubtitle(project: SyncProject): string | undefined {
		if (!duplicateNames.has(project.name)) return undefined;
		// Show last 2 path segments from encoded_name for disambiguation
		const parts = project.encoded_name.replace(/^-/, '').split('-');
		const tail = parts.slice(-3).join('/');
		return `.../${tail}`;
	}

	$effect(() => {
		if (active && teamName) {
			loadProjects();
		}
	});
</script>

<div class="p-6 space-y-4">
	<!-- Flash message -->
	{#if flashMessage}
		<div
			class="flex items-center gap-2 px-4 py-2.5 rounded-[var(--radius-lg)] bg-[var(--success)]/10 border border-[var(--success)]/20 text-xs font-medium text-[var(--success)]"
		>
			<CheckCircle2 size={14} class="shrink-0" />
			{flashMessage}
		</div>
	{/if}

	<!-- Team context banner -->
	{#if teamName}
		<div class="flex items-center gap-2 px-3 py-2 rounded-[var(--radius)] bg-[var(--accent)]/5 border border-[var(--accent)]/15">
			<Users size={12} class="text-[var(--accent)] shrink-0" />
			<span class="text-xs text-[var(--text-secondary)]">
				Syncing with team <span class="font-semibold text-[var(--text-primary)]">{teamName}</span>
			</span>
		</div>
	{/if}

	<!-- Header row -->
	<div class="flex items-center justify-between">
		<div>
			<h2 class="text-sm font-semibold text-[var(--text-primary)]">Projects</h2>
			{#if !loading && projects.length > 0}
				<p class="text-xs text-[var(--text-muted)] mt-0.5">
					{#if searchQuery.trim()}
						Showing {filteredProjects.length} of {projects.length}
					{:else}
						{projects.filter((p) => p.synced).length} of {projects.length} syncing with {teamName}
					{/if}
				</p>
			{/if}
		</div>

		{#if !loading && unsyncedCount > 0}
			{#if showEnableAllConfirm}
				<div class="flex items-center gap-2 px-3 py-1.5 rounded-md border border-[var(--border)] bg-[var(--bg-subtle)]">
					<span class="text-xs text-[var(--text-secondary)]">
						Enable sync for {unsyncedCount} project{unsyncedCount !== 1 ? 's' : ''}?
					</span>
					<button
						class="px-2.5 py-1 text-xs font-medium rounded-md bg-[var(--accent)] text-white hover:bg-[var(--accent-hover)] transition-colors disabled:opacity-50"
						onclick={enableAll}
						disabled={selectingAll}
					>
						{#if selectingAll}
							<RefreshCw size={11} class="animate-spin inline-block mr-1" />
							Enabling...
						{:else}
							Confirm
						{/if}
					</button>
					<button
						class="px-2.5 py-1 text-xs font-medium rounded-md border border-[var(--border)] text-[var(--text-muted)] hover:text-[var(--text-primary)] transition-colors"
						onclick={() => (showEnableAllConfirm = false)}
					>
						Cancel
					</button>
				</div>
			{:else}
				<button
					class="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-md border border-[var(--border)] text-[var(--text-secondary)] hover:text-[var(--text-primary)] hover:bg-[var(--bg-subtle)] transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
					onclick={() => (showEnableAllConfirm = true)}
					disabled={selectingAll}
					aria-label="Enable sync for all projects"
				>
					Enable All ({unsyncedCount})
				</button>
			{/if}
		{/if}
	</div>

	<!-- Content -->
	{#if !teamName}
		<div
			class="py-12 flex flex-col items-center gap-3 text-center border border-dashed border-[var(--border)] rounded-[var(--radius-lg)]"
		>
			<FolderGit2 size={32} class="text-[var(--text-muted)]" />
			<p class="text-sm text-[var(--text-muted)]">Select a team to manage projects</p>
		</div>
	{:else if loading}
		<!-- Loading skeleton -->
		<div class="space-y-2">
			{#each [1, 2, 3] as i (i)}
				<div
					class="h-12 rounded-[var(--radius-lg)] border border-[var(--border)] bg-[var(--bg-subtle)] animate-pulse"
				></div>
			{/each}
		</div>
	{:else if error}
		<div
			class="flex items-center gap-2 p-4 rounded-[var(--radius-lg)] border border-[var(--error)]/20 bg-[var(--error-subtle)] text-xs text-[var(--error)]"
		>
			{error}
			<button
				onclick={loadProjects}
				class="ml-auto underline hover:no-underline text-[var(--error)]"
			>
				Retry
			</button>
		</div>
	{:else if projects.length === 0}
		<!-- Empty state -->
		<div
			class="py-12 flex flex-col items-center gap-3 text-center border border-dashed border-[var(--border)] rounded-[var(--radius-lg)]"
		>
			<FolderGit2 size={32} class="text-[var(--text-muted)]" />
			<div>
				<p class="text-sm font-medium text-[var(--text-secondary)]">No projects found</p>
				<p class="text-xs text-[var(--text-muted)] mt-1">
					Start a Claude Code session to see your projects here.
				</p>
			</div>
		</div>
	{:else}
		<!-- Search input -->
		<div class="relative">
			<Search size={14} class="absolute left-3 top-1/2 -translate-y-1/2 text-[var(--text-muted)]" />
			<input
				type="text"
				bind:value={searchQuery}
				placeholder="Filter projects..."
				class="w-full pl-9 pr-3 py-2 text-sm rounded-[var(--radius)] border border-[var(--border)] bg-[var(--bg-base)] text-[var(--text-primary)] placeholder:text-[var(--text-muted)] focus:outline-none focus:ring-2 focus:ring-[var(--accent)]/40 focus:border-[var(--accent)] transition-colors"
			/>
		</div>

		<!-- Project list -->
		{#if filteredProjects.length === 0}
			<div class="py-8 text-center">
				<p class="text-sm text-[var(--text-muted)]">No projects match "{searchQuery.trim()}"</p>
			</div>
		{:else}
			<div class="space-y-2">
				{#each filteredProjects as project (project.encoded_name)}
					<ProjectRow
						{project}
						projectStatus={projectStatusMap.get(project.encoded_name) ?? null}
						subtitle={getSubtitle(project)}
						onToggle={handleToggle}
						onSyncNow={handleSyncNow}
						onaction={handleAction}
					/>
				{/each}
			</div>
		{/if}
	{/if}
</div>

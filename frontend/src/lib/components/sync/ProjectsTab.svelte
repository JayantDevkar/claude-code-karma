<script lang="ts">
	import { onMount } from 'svelte';
	import { FolderGit2, RefreshCw } from 'lucide-svelte';
	import { API_BASE } from '$lib/config';
	import ProjectRow from '$lib/components/sync/ProjectRow.svelte';

	interface SyncProject {
		name: string;
		encoded_name: string;
		local_session_count: number;
		synced: boolean;
		status: 'synced' | 'syncing' | 'pending' | 'not-syncing';
		last_sync_at: string | null;
		machine_count: number;
		pending_count: number;
	}

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

	let projects = $state<SyncProject[]>([]);
	let loading = $state(true);
	let error = $state<string | null>(null);
	let selectingAll = $state(false);

	async function loadProjects() {
		loading = true;
		error = null;
		try {
			const [projectsRes, teamsRes] = await Promise.all([
				fetch(`${API_BASE}/projects`),
				fetch(`${API_BASE}/sync/teams`).catch(() => null)
			]);

			const apiProjects: ApiProject[] = projectsRes.ok ? await projectsRes.json() : [];
			const teamsData = teamsRes?.ok ? await teamsRes.json() : { teams: [] };
			const teams: Team[] = teamsData.teams ?? [];

			// Collect all synced encoded_names across all teams
			const syncedSet = new Set<string>();
			const teamCountMap = new Map<string, number>();
			for (const team of teams) {
				for (const tp of team.projects) {
					syncedSet.add(tp.encoded_name);
					teamCountMap.set(tp.encoded_name, team.members.length);
				}
			}

			projects = apiProjects.map((p) => {
				const isSynced = syncedSet.has(p.encoded_name);
				return {
					name: p.display_name ?? p.encoded_name,
					encoded_name: p.encoded_name,
					local_session_count: p.session_count ?? 0,
					synced: isSynced,
					status: isSynced ? ('synced' as const) : ('not-syncing' as const),
					last_sync_at: null,
					machine_count: teamCountMap.get(p.encoded_name) ?? 0,
					pending_count: 0
				};
			});
		} catch {
			error = 'Failed to load projects.';
		} finally {
			loading = false;
		}
	}

	async function handleToggle(name: string, enable: boolean) {
		const endpoint = enable ? 'enable' : 'disable';
		await fetch(`${API_BASE}/sync/projects/${encodeURIComponent(name)}/${endpoint}`, {
			method: 'POST'
		});
		await loadProjects();
	}

	async function handleSyncNow(name: string) {
		await fetch(`${API_BASE}/sync/projects/${encodeURIComponent(name)}/sync-now`, {
			method: 'POST'
		});
		await loadProjects();
	}

	async function selectAll() {
		const unsynced = projects.filter((p) => !p.synced);
		if (unsynced.length === 0) return;
		selectingAll = true;
		try {
			await Promise.all(
				unsynced.map((p) =>
					fetch(`${API_BASE}/sync/projects/${encodeURIComponent(p.name)}/enable`, {
						method: 'POST'
					})
				)
			);
			await loadProjects();
		} finally {
			selectingAll = false;
		}
	}

	let unsyncedCount = $derived(projects.filter((p) => !p.synced).length);

	onMount(() => {
		loadProjects();
	});
</script>

<div class="p-6 space-y-4">
	<!-- Header row -->
	<div class="flex items-center justify-between">
		<div>
			<h2 class="text-sm font-semibold text-[var(--text-primary)]">Projects</h2>
			{#if !loading && projects.length > 0}
				<p class="text-xs text-[var(--text-muted)] mt-0.5">
					{projects.filter((p) => p.synced).length} of {projects.length} syncing
				</p>
			{/if}
		</div>

		{#if !loading && unsyncedCount > 0}
			<button
				class="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-md border border-[var(--border)] text-[var(--text-secondary)] hover:text-[var(--text-primary)] hover:bg-[var(--bg-subtle)] transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
				onclick={selectAll}
				disabled={selectingAll}
				aria-label="Enable sync for all projects"
			>
				{#if selectingAll}
					<RefreshCw size={11} class="animate-spin" />
					Enabling...
				{:else}
					Select All
				{/if}
			</button>
		{/if}
	</div>

	<!-- Content -->
	{#if loading}
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
		<!-- Project list -->
		<div class="space-y-2">
			{#each projects as project (project.encoded_name)}
				<ProjectRow {project} onToggle={handleToggle} onSyncNow={handleSyncNow} />
			{/each}
		</div>
	{/if}
</div>

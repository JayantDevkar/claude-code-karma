<script lang="ts">
	import { API_BASE } from '$lib/config';
	import { invalidateAll } from '$app/navigation';
	import {
		FolderSync,
		Plus,
		RefreshCw,
		Trash2,
		CheckCircle2,
		Loader2
	} from 'lucide-svelte';
	import type { SyncTeamProject, SyncProjectStatus, SyncSessionLimit } from '$lib/api-types';
	import { getProjectNameFromEncoded } from '$lib/utils';
	import AddProjectDialog from './AddProjectDialog.svelte';
	import SessionLimitSelector from './SessionLimitSelector.svelte';
	import ProjectMemberBar from './ProjectMemberBar.svelte';

	function getProjectDisplayName(project: SyncTeamProject): string {
		if (project.path) {
			const segments = project.path.replace(/\/+$/, '').split('/');
			return segments[segments.length - 1] || project.path;
		}
		return getProjectNameFromEncoded(project.encoded_name);
	}

	interface Props {
		projects: SyncTeamProject[];
		teamName: string;
		projectStatuses: SyncProjectStatus[];
		allProjects: { encoded_name: string; name: string; path: string }[];
		sharedProjectNames: string[];
		syncSessionLimit: SyncSessionLimit;
		userNames?: Record<string, string>;
		onrefresh: () => void;
	}

	let {
		projects,
		teamName,
		projectStatuses,
		allProjects,
		sharedProjectNames,
		syncSessionLimit,
		userNames,
		onrefresh
	}: Props = $props();

	let showAddProject = $state(false);
	let syncAllActing = $state(false);
	let syncError = $state('');
	let removeProjectConfirm = $state<string | null>(null);
	let removeProjectError = $state<string | null>(null);

	function getProjectStatus(encodedName: string): SyncProjectStatus | undefined {
		return projectStatuses.find((p) => p.encoded_name === encodedName);
	}

	async function syncAllNow() {
		syncAllActing = true;
		syncError = '';
		try {
			const res = await fetch(
				`${API_BASE}/sync/teams/${encodeURIComponent(teamName)}/sync-now`,
				{ method: 'POST' }
			);
			if (!res.ok) {
				syncError = 'Sync failed \u2014 try again';
			} else {
				invalidateAll();
			}
		} catch {
			syncError = 'Network error';
		} finally {
			syncAllActing = false;
		}
	}

	async function handleRemoveProject(encodedName: string) {
		removeProjectError = null;
		try {
			const res = await fetch(
				`${API_BASE}/sync/teams/${encodeURIComponent(teamName)}/projects/${encodeURIComponent(encodedName)}`,
				{ method: 'DELETE' }
			);
			if (res.ok) {
				removeProjectConfirm = null;
				removeProjectError = null;
				invalidateAll();
			} else {
				removeProjectError = `Failed to remove project (${res.status})`;
			}
		} catch {
			removeProjectError = 'Network error \u2014 could not remove project';
		}
	}
</script>

<div class="space-y-4">
	<!-- Header row -->
	<div class="flex items-center justify-between">
		<div class="flex items-center gap-2">
			{#if projects.length > 0}
				<button
					onclick={syncAllNow}
					disabled={syncAllActing}
					class="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-[var(--radius-md)]
						bg-[var(--accent)] text-white hover:bg-[var(--accent-hover)] transition-colors
						disabled:opacity-50 disabled:cursor-not-allowed"
				>
					{#if syncAllActing}
						<Loader2 size={12} class="animate-spin" />
						Syncing...
					{:else}
						<RefreshCw size={12} />
						Sync Now
					{/if}
				</button>
			{/if}
			<button
				onclick={() => (showAddProject = true)}
				class="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-[var(--radius-md)]
					border border-[var(--border)] text-[var(--text-secondary)]
					hover:bg-[var(--bg-muted)] hover:text-[var(--text-primary)] transition-colors"
			>
				<Plus size={13} />
				Add Projects
			</button>
		</div>
		{#if projects.length > 0}
			<SessionLimitSelector {teamName} currentLimit={syncSessionLimit} />
		{/if}
	</div>

	{#if syncError}
		<p class="text-xs text-[var(--error)]" aria-live="polite">{syncError}</p>
	{/if}

	{#if removeProjectError}
		<p class="text-xs text-[var(--error)]" aria-live="polite">{removeProjectError}</p>
	{/if}

	<!-- Project cards -->
	<div class="space-y-2">
		{#each projects as project (project.encoded_name)}
			{@const status = getProjectStatus(project.encoded_name)}
			<div class="p-4 rounded-lg border border-[var(--border)] bg-[var(--bg-base)]">
				<!-- Project header info -->
				<div class="flex items-center justify-between">
					<div class="flex items-center gap-3 min-w-0">
						<FolderSync size={16} class="text-[var(--text-muted)] shrink-0" />
						<div class="min-w-0">
							<a
								href="/projects/{project.encoded_name}"
								class="text-sm font-medium text-[var(--text-primary)] hover:text-[var(--accent)] transition-colors truncate block"
							>
								{getProjectDisplayName(project)}
							</a>
							{#if project.path}
								<p class="text-[11px] text-[var(--text-muted)] truncate font-mono">{project.path}</p>
							{/if}
							{#if status}
								<p class="text-[11px] text-[var(--text-muted)] mt-0.5">
									{status.packaged_count}/{status.local_count} sessions packaged
								</p>
							{/if}
						</div>
					</div>
					<div class="flex items-center gap-2 shrink-0">
						{#if status}
							{#if status.gap === 0}
								<span class="flex items-center gap-1 px-2 py-1 text-[11px] font-medium rounded-full bg-[var(--success)]/10 text-[var(--success)] border border-[var(--success)]/20">
									<CheckCircle2 size={11} />
									In Sync
								</span>
							{:else}
								<span class="flex items-center gap-1 px-2 py-1 text-[11px] font-medium rounded-full bg-[var(--warning)]/10 text-[var(--warning)] border border-[var(--warning)]/20">
									{status.gap} behind
								</span>
							{/if}
						{/if}
						{#if removeProjectConfirm === project.encoded_name}
							<div class="flex items-center gap-1.5">
								<button
									onclick={() => handleRemoveProject(project.encoded_name)}
									class="px-2 py-1 text-xs font-medium rounded bg-[var(--error)] text-white hover:bg-[var(--error)]/80 transition-colors"
								>
									Remove
								</button>
								<button
									onclick={() => (removeProjectConfirm = null)}
									class="px-2 py-1 text-xs rounded text-[var(--text-muted)] hover:bg-[var(--bg-muted)] transition-colors"
								>
									Cancel
								</button>
							</div>
						{:else}
							<button
								onclick={() => (removeProjectConfirm = project.encoded_name)}
								class="p-1.5 rounded text-[var(--text-muted)] hover:text-[var(--error)] hover:bg-[var(--error)]/10 transition-colors"
								title="Remove from team"
								aria-label="Remove project {getProjectDisplayName(project)}"
							>
								<Trash2 size={14} />
							</button>
						{/if}
					</div>
				</div>

				<!-- Member contribution bar -->
				<ProjectMemberBar {project} {userNames} class="mt-3" />
			</div>
		{/each}

		{#if projects.length === 0}
			<p class="text-sm text-[var(--text-muted)] py-8 text-center">
				No projects shared yet. Add projects to start syncing sessions with your team.
			</p>
		{/if}
	</div>
</div>

<AddProjectDialog
	bind:open={showAddProject}
	{teamName}
	{allProjects}
	{sharedProjectNames}
	onadded={onrefresh}
/>

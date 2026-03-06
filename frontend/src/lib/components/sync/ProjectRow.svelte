<script lang="ts">
	import { ChevronDown, ChevronRight, RefreshCw, Power } from 'lucide-svelte';
	import type { SyncProject } from '$lib/api-types';
	import { formatRelativeTime } from '$lib/utils';
	import Badge from '$lib/components/ui/Badge.svelte';

	let {
		project,
		onToggle,
		onSyncNow
	}: {
		project: SyncProject;
		onToggle: (encodedName: string, enable: boolean) => Promise<void>;
		onSyncNow: (encodedName: string) => Promise<void>;
	} = $props();

	let expanded = $state(false);
	let toggling = $state(false);
	let syncing = $state(false);

	async function handleToggleDot(e: MouseEvent) {
		e.stopPropagation();
		toggling = true;
		try {
			await onToggle(project.encoded_name, !project.synced);
		} finally {
			toggling = false;
		}
	}

	async function handleEnableSync(e: MouseEvent) {
		e.stopPropagation();
		toggling = true;
		try {
			await onToggle(project.encoded_name, true);
		} finally {
			toggling = false;
		}
	}

	async function handleSyncNow(e: MouseEvent) {
		e.stopPropagation();
		syncing = true;
		try {
			await onSyncNow(project.encoded_name);
		} finally {
			syncing = false;
		}
	}
</script>

<div class="rounded-[var(--radius-lg)] border border-[var(--border)] bg-[var(--bg-subtle)] overflow-hidden">
	<!-- Collapsed row (always visible) -->
	<div class="flex items-center gap-3 px-4 py-3 hover:bg-[var(--bg-muted)] transition-colors">
		<!-- Toggle dot -->
		<button
			class="shrink-0 w-3 h-3 rounded-full border-2 transition-colors {project.synced
				? 'bg-[var(--success)] border-[var(--success)]'
				: 'bg-transparent border-[var(--text-muted)]'} {toggling ? 'opacity-50 cursor-wait' : 'cursor-pointer'}"
			onclick={handleToggleDot}
			disabled={toggling}
			aria-label={project.synced
				? `Disable sync for ${project.name}`
				: `Enable sync for ${project.name}`}
			title={project.synced ? 'Click to disable sync' : 'Click to enable sync'}
		></button>

		<!-- Expand trigger (covers name + status) -->
		<button
			class="flex-1 min-w-0 flex items-center gap-2 text-left"
			onclick={() => (expanded = !expanded)}
			aria-expanded={expanded}
		>
			<span class="text-sm font-medium text-[var(--text-primary)] truncate">{project.name}</span>

			{#if project.status === 'synced'}
				<Badge variant="success" size="sm">In sync</Badge>
			{:else if project.status === 'syncing'}
				<Badge variant="info" size="sm">Syncing</Badge>
			{:else if project.status === 'pending'}
				<Badge variant="warning" size="sm">{project.pending_count} pending</Badge>
			{:else}
				<span class="text-xs text-[var(--text-muted)]">Not syncing</span>
			{/if}
		</button>

		<!-- Right side: session count + last sync + action -->
		<div class="shrink-0 flex items-center gap-3">
			<span class="text-xs text-[var(--text-muted)] hidden sm:block">
				{project.local_session_count} session{project.local_session_count !== 1 ? 's' : ''}
			</span>

			{#if project.synced && project.last_sync_at}
				<span class="text-xs text-[var(--text-muted)] hidden sm:block">
					{formatRelativeTime(project.last_sync_at)}
				</span>
			{/if}

			{#if project.status === 'not-syncing'}
				<button
					class="px-2.5 py-1 text-xs font-medium rounded-md border border-[var(--border)] text-[var(--text-secondary)] hover:text-[var(--text-primary)] hover:bg-[var(--bg-base)] transition-colors disabled:opacity-50 flex items-center gap-1"
					onclick={handleEnableSync}
					disabled={toggling}
					aria-label="Enable sync for {project.name}"
				>
					<Power size={11} />
					Enable Sync
				</button>
			{:else}
				<button
					class="px-2.5 py-1 text-xs font-medium rounded-md border border-[var(--border)] text-[var(--text-secondary)] hover:text-[var(--text-primary)] hover:bg-[var(--bg-base)] transition-colors disabled:opacity-50 flex items-center gap-1"
					onclick={handleSyncNow}
					disabled={syncing}
					aria-label="Sync now for {project.name}"
				>
					<RefreshCw size={11} class={syncing ? 'animate-spin' : ''} />
					Sync Now
				</button>
			{/if}

			<!-- Expand chevron -->
			<button
				class="text-[var(--text-muted)]"
				onclick={() => (expanded = !expanded)}
				aria-expanded={expanded}
				aria-label="Expand details"
			>
				{#if expanded}
					<ChevronDown size={14} />
				{:else}
					<ChevronRight size={14} />
				{/if}
			</button>
		</div>
	</div>

	<!-- Expanded content -->
	{#if expanded}
		<div class="px-4 pb-4 pt-1 border-t border-[var(--border)] bg-[var(--bg-base)] space-y-3">
			<!-- Machine breakdown -->
			<div>
				<p class="text-xs font-medium text-[var(--text-muted)] mb-1.5">Machines</p>
				{#if project.machine_count === 0}
					<p class="text-xs text-[var(--text-muted)]">No machines syncing this project.</p>
				{:else}
					<p class="text-xs text-[var(--text-secondary)]">
						{project.machine_count} machine{project.machine_count !== 1 ? 's' : ''} syncing this project
					</p>
				{/if}
			</div>

		</div>
	{/if}
</div>

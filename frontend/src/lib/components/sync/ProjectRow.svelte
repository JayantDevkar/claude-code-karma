<script lang="ts">
	import { ChevronDown, ChevronRight, RefreshCw, Power } from 'lucide-svelte';
	import Badge from '$lib/components/ui/Badge.svelte';

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

	let {
		project,
		onToggle,
		onSyncNow
	}: {
		project: SyncProject;
		onToggle: (name: string, enable: boolean) => Promise<void>;
		onSyncNow: (name: string) => Promise<void>;
	} = $props();

	let expanded = $state(false);
	let toggling = $state(false);
	let syncing = $state(false);

	function formatRelativeTime(dateStr: string | null): string {
		if (!dateStr) return 'Never';
		const date = new Date(dateStr);
		const diffMs = Date.now() - date.getTime();
		const diffSec = Math.floor(diffMs / 1000);
		if (diffSec < 60) return `${diffSec}s ago`;
		const diffMin = Math.floor(diffSec / 60);
		if (diffMin < 60) return `${diffMin}m ago`;
		const diffHr = Math.floor(diffMin / 60);
		if (diffHr < 24) return `${diffHr}h ago`;
		const diffDay = Math.floor(diffHr / 24);
		return `${diffDay}d ago`;
	}

	async function handleToggleDot(e: MouseEvent) {
		e.stopPropagation();
		toggling = true;
		try {
			await onToggle(project.name, !project.synced);
		} finally {
			toggling = false;
		}
	}

	async function handleEnableSync(e: MouseEvent) {
		e.stopPropagation();
		toggling = true;
		try {
			await onToggle(project.name, true);
		} finally {
			toggling = false;
		}
	}

	async function handleSyncNow(e: MouseEvent) {
		e.stopPropagation();
		syncing = true;
		try {
			await onSyncNow(project.name);
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

			{#if project.synced}
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
			{:else if project.status === 'pending'}
				<button
					class="px-2.5 py-1 text-xs font-medium rounded-md border border-[var(--warning)]/40 text-[var(--warning)] hover:bg-[var(--warning-subtle)] transition-colors disabled:opacity-50 flex items-center gap-1"
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

			<!-- Placeholder links -->
			<div class="flex items-center gap-4">
				<button class="flex items-center gap-1 text-xs text-[var(--text-muted)] hover:text-[var(--text-primary)] transition-colors">
					<ChevronRight size={12} />
					Files
				</button>
				<button class="flex items-center gap-1 text-xs text-[var(--text-muted)] hover:text-[var(--text-primary)] transition-colors">
					<ChevronRight size={12} />
					Sync History
				</button>
			</div>
		</div>
	{/if}
</div>

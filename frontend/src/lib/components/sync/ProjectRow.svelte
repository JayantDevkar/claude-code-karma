<script lang="ts">
	import { ChevronDown, ChevronRight, RefreshCw, Power } from 'lucide-svelte';
	import type { SyncProject } from '$lib/api-types';
	import { formatRelativeTime } from '$lib/utils';
	import Badge from '$lib/components/ui/Badge.svelte';

	interface ProjectStatus {
		local_count: number;
		packaged_count: number;
		received_counts: Record<string, number>;
		gap: number;
	}

	let {
		project,
		projectStatus = null,
		subtitle,
		onToggle,
		onSyncNow,
		onaction
	}: {
		project: SyncProject;
		projectStatus?: ProjectStatus | null;
		subtitle?: string;
		onToggle: (encodedName: string, enable: boolean) => Promise<void>;
		onSyncNow: (encodedName: string) => Promise<void>;
		onaction?: (message: string) => void;
	} = $props();

	let expanded = $state(false);
	let toggling = $state(false);
	let syncing = $state(false);
	let confirmDisable = $state(false);

	async function handleCheckboxChange(e: Event) {
		const target = e.target as HTMLInputElement;
		const enabling = target.checked;

		if (!enabling) {
			// Disabling: show confirmation instead of immediately toggling
			// Revert the checkbox visual state until confirmed
			target.checked = true;
			confirmDisable = true;
			return;
		}

		// Enabling: proceed immediately
		toggling = true;
		try {
			await onToggle(project.encoded_name, true);
			onaction?.(`Sync enabled for ${project.name}`);
		} finally {
			toggling = false;
		}
	}

	async function confirmDisableSync() {
		toggling = true;
		confirmDisable = false;
		try {
			await onToggle(project.encoded_name, false);
			onaction?.(`Sync disabled for ${project.name}`);
		} finally {
			toggling = false;
		}
	}

	function cancelDisable() {
		confirmDisable = false;
	}

	async function handleEnableSync(e: MouseEvent) {
		e.stopPropagation();
		toggling = true;
		try {
			await onToggle(project.encoded_name, true);
			onaction?.(`Sync enabled for ${project.name}`);
		} finally {
			toggling = false;
		}
	}

	async function handleSyncNow(e: MouseEvent) {
		e.stopPropagation();
		syncing = true;
		try {
			await onSyncNow(project.encoded_name);
			onaction?.(`Sync triggered for ${project.name}`);
		} finally {
			syncing = false;
		}
	}
</script>

<div class="relative rounded-[var(--radius-lg)] border border-[var(--border)] bg-[var(--bg-subtle)] overflow-hidden">
	<!-- Inline disable confirmation overlay -->
	{#if confirmDisable}
		<div
			class="absolute inset-0 z-10 flex items-center justify-center bg-[var(--bg-base)]/90 rounded-[var(--radius-lg)]"
		>
			<div
				class="flex items-center gap-3 px-4 py-3 rounded-lg bg-[var(--bg-base)] border border-[var(--border)] shadow-md"
			>
				<span class="text-xs text-[var(--text-secondary)]">
					Stop syncing {project.name}?
				</span>
				<button
					onclick={() => confirmDisableSync()}
					disabled={toggling}
					class="px-2.5 py-1 text-xs font-medium rounded-md bg-[var(--error)] text-white hover:opacity-90 transition-opacity disabled:opacity-50"
				>
					{toggling ? '...' : 'Confirm'}
				</button>
				<button
					onclick={cancelDisable}
					class="px-2.5 py-1 text-xs font-medium rounded-md border border-[var(--border)] text-[var(--text-muted)] hover:text-[var(--text-primary)] transition-colors"
				>
					Cancel
				</button>
			</div>
		</div>
	{/if}

	<!-- Collapsed row (always visible) -->
	<div class="flex items-center gap-3 px-4 py-3 hover:bg-[var(--bg-muted)] transition-colors">
		<!-- Sync checkbox -->
		<input
			type="checkbox"
			checked={project.synced}
			onchange={handleCheckboxChange}
			disabled={toggling}
			aria-label={project.synced
				? `Disable sync for ${project.name}`
				: `Enable sync for ${project.name}`}
			title={project.synced ? 'Click to disable sync' : 'Click to enable sync'}
			class="shrink-0 w-4 h-4 rounded border-[var(--border)] text-[var(--accent)] focus:ring-[var(--accent)]/30 {toggling ? 'opacity-50 cursor-wait' : 'cursor-pointer'}"
		/>

		<!-- Expand trigger (covers name + status) -->
		<button
			class="flex-1 min-w-0 flex items-center gap-2 text-left"
			onclick={() => (expanded = !expanded)}
			aria-expanded={expanded}
		>
			<div class="min-w-0">
				<span class="text-sm font-medium text-[var(--text-primary)] truncate block">{project.name}</span>
				{#if subtitle}
					<span class="text-[11px] text-[var(--text-muted)] font-mono truncate block">{subtitle}</span>
				{/if}
			</div>

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

		<!-- Right side: session count + gap + received + last sync + action -->
		<div class="shrink-0 flex items-center gap-3">
			<span class="text-xs text-[var(--text-muted)] hidden sm:block">
				{project.local_session_count} session{project.local_session_count !== 1 ? 's' : ''}
			</span>

			<!-- Gap indicator (visible without expanding) -->
			{#if projectStatus && project.synced}
				{#if projectStatus.gap > 0}
					<span class="text-xs font-medium text-[var(--warning)]">
						{projectStatus.gap} behind
					</span>
				{:else if projectStatus.packaged_count > 0}
					<span class="text-xs text-[var(--success)]">up to date</span>
				{/if}
			{/if}

			<!-- Received count summary -->
			{#if projectStatus && project.synced}
				{@const totalReceived = Object.values(projectStatus.received_counts).reduce((a, b) => a + b, 0)}
				{#if totalReceived > 0}
					<span class="text-xs text-[var(--text-muted)] hidden sm:block">
						{totalReceived} received
					</span>
				{/if}
			{/if}

			{#if project.synced && project.last_sync_at}
				<span class="text-xs text-[var(--text-muted)] hidden sm:block">
					{formatRelativeTime(project.last_sync_at)}
				</span>
			{/if}

			{#if project.status === 'not-syncing'}
				<button
					class="px-2.5 py-1 text-xs font-medium rounded-md border border-[var(--accent)]/30 text-[var(--accent)] hover:bg-[var(--accent)]/10 transition-colors disabled:opacity-50 flex items-center gap-1"
					onclick={handleEnableSync}
					disabled={toggling}
					aria-label="Share {project.name} with team"
				>
					<Power size={11} />
					Share
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

			<!-- Sync status details -->
			{#if projectStatus}
				<div>
					<p class="text-xs font-medium text-[var(--text-muted)] mb-1.5">Sync Status</p>
					<div class="space-y-1">
						<div class="flex items-center justify-between">
							<span class="text-xs text-[var(--text-muted)]">Local sessions</span>
							<span class="text-xs text-[var(--text-secondary)]">{projectStatus.local_count}</span>
						</div>
						<div class="flex items-center justify-between">
							<span class="text-xs text-[var(--text-muted)]">Queued for sync</span>
							<span class="text-xs text-[var(--text-secondary)]">{projectStatus.packaged_count}</span>
						</div>
					</div>

					{#if projectStatus.gap > 0}
						<p class="mt-2 text-xs text-[var(--warning)]">
							{projectStatus.gap} session{projectStatus.gap !== 1 ? 's' : ''} pending — start the sync engine on the Overview tab to catch up
						</p>
					{/if}
				</div>

				{#if Object.keys(projectStatus.received_counts).length > 0}
					<div>
						<p class="text-xs font-medium text-[var(--text-muted)] mb-1.5">Received from members</p>
						<div class="space-y-1">
							{#each Object.entries(projectStatus.received_counts) as [member, count] (member)}
								<div class="flex items-center justify-between">
									<span class="text-xs text-[var(--text-muted)]">{member}</span>
									<span class="text-xs text-[var(--text-secondary)]">
										{count} session{count !== 1 ? 's' : ''}
									</span>
								</div>
							{/each}
						</div>
					</div>
				{/if}
			{/if}

		</div>
	{/if}
</div>

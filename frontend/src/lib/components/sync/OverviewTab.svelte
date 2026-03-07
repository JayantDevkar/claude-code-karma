<script lang="ts">
	import { untrack } from 'svelte';
	import { Play, Square, Monitor, FolderGit2, ArrowUp, ArrowDown, Bell, CheckCircle2, Loader2, Users, XCircle, RotateCcw } from 'lucide-svelte';
	import type { SyncDetect, SyncStatusResponse, SyncWatchStatus, SyncPendingFolder } from '$lib/api-types';
	import { formatRelativeTime } from '$lib/utils';
	import { API_BASE } from '$lib/config';
	import { pushSyncAction } from '$lib/stores/syncActions.svelte';

	let {
		detect = null,
		status = null,
		active = false,
		teamName = null,
		onteamchange,
		initialWatchStatus = null,
		initialPending = []
	}: {
		detect: SyncDetect | null;
		status: SyncStatusResponse | null;
		active?: boolean;
		teamName: string | null;
		onteamchange?: () => void;
		initialWatchStatus?: SyncWatchStatus | null;
		initialPending?: SyncPendingFolder[];
	} = $props();

	// ── Sync Engine watch status ──────────────────────────────────────────────
	let watchStatus = $state<SyncWatchStatus | null>(initialWatchStatus ?? null);
	let watchLoading = $state(initialWatchStatus === null);
	let watchActing = $state(false);

	async function loadWatchStatus() {
		if (watchStatus === null) watchLoading = true;
		try {
			const res = await fetch(`${API_BASE}/sync/watch/status`).catch(() => null);
			if (res?.ok) {
				watchStatus = await res.json();
			} else {
				watchStatus = null;
			}
		} finally {
			watchLoading = false;
		}
	}

	async function startWatch() {
		if (!teamName) return;
		watchActing = true;
		try {
			const url = new URL(`${API_BASE}/sync/watch/start`, window.location.origin);
			if (teamName) url.searchParams.set('team_name', teamName);
			const res = await fetch(url.toString(), { method: 'POST' }).catch(() => null);
			if (res?.ok) {
				watchStatus = await res.json();
				pushSyncAction('watch_started', 'Session watcher started', teamName ?? '');
			}
		} finally {
			watchActing = false;
		}
	}

	async function stopWatch() {
		watchActing = true;
		try {
			const res = await fetch(`${API_BASE}/sync/watch/stop`, { method: 'POST' }).catch(() => null);
			if (res?.ok) {
				watchStatus = await res.json();
				pushSyncAction('watch_stopped', 'Session watcher stopped');
			}
		} finally {
			watchActing = false;
		}
	}

	// ── Stats ─────────────────────────────────────────────────────────────────
	let projectCount = $state(0);
	let connectedMembers = $state(0);
	let totalMembers = $state(0);
	let sessionsSharedCount = $state(0);
	let sessionsReceivedCount = $state(0);
	let statsLoaded = $state(false);
	let statsLoading = $state(true);

	async function loadStats() {
		if (!statsLoaded) statsLoading = true;
		// Derive project count from status
		if (status?.teams) {
			let count = 0;
			for (const team of Object.values(status.teams) as Array<{ project_count?: number }>) {
				count += team.project_count ?? 0;
			}
			projectCount = count;
		}

		try {
			// Fetch devices to count connected members
			const devicesRes = await fetch(`${API_BASE}/sync/devices`).catch(() => null);
			if (devicesRes?.ok) {
				const devData = await devicesRes.json();
				const devices = devData.devices ?? [];
				const remoteDevices = devices.filter((d: { is_self?: boolean }) => !d.is_self);
				totalMembers = remoteDevices.length;
				connectedMembers = remoteDevices.filter((d: { connected?: boolean }) => d.connected).length;
			}

			// Fetch project status for session counts
			if (teamName) {
				const statusRes = await fetch(
					`${API_BASE}/sync/teams/${encodeURIComponent(teamName)}/project-status`
				).catch(() => null);
				if (statusRes?.ok) {
					const statusData = await statusRes.json();
					const projects = statusData.projects ?? Object.values(statusData);
					let shared = 0;
					let received = 0;
					for (const p of projects) {
						shared += (p as { packaged_count?: number }).packaged_count ?? 0;
						const counts = (p as { received_counts?: Record<string, number> }).received_counts ?? {};
						for (const count of Object.values(counts)) {
							received += count ?? 0;
						}
					}
					sessionsSharedCount = shared;
					sessionsReceivedCount = received;
				}
			}
		} catch {
			// Non-critical
		} finally {
			statsLoading = false;
			statsLoaded = true;
		}
	}

	// ── Folder label helper ──────────────────────────────────────────────────
	function parseFolderLabel(folderId: string): string {
		const match = folderId.match(/^karma-(?:out|in)-[^-]+-(.+)$/);
		if (match) return `${match[1]} sessions`;
		return folderId;
	}

	// ── Pending actions ───────────────────────────────────────────────────────
	let pendingFolders = $state<SyncPendingFolder[]>(initialPending ?? []);
	let pendingLoading = $state(initialPending.length === 0 && initialWatchStatus === null);
	let acceptingAll = $state(false);
	let pendingError = $state<string | null>(null);

	async function loadPending() {
		if (pendingFolders.length === 0 && !pendingError) pendingLoading = true;
		pendingError = null;
		try {
			const res = await fetch(`${API_BASE}/sync/pending`).catch(() => null);
			if (res?.ok) {
				const data = await res.json();
				pendingFolders = data.pending ?? data ?? [];
			} else {
				pendingFolders = [];
			}
		} catch {
			pendingError = 'Failed to load pending actions.';
		} finally {
			pendingLoading = false;
		}
	}

	async function acceptAll() {
		acceptingAll = true;
		const count = pendingFolders.length;
		try {
			await fetch(`${API_BASE}/sync/pending/accept`, { method: 'POST' }).catch(() => null);
			await loadPending();
			pushSyncAction('pending_accepted', `Accepted ${count} pending folder${count !== 1 ? 's' : ''}`);
		} finally {
			acceptingAll = false;
		}
	}

	// ── Reset sync ───────────────────────────────────────────────────────────
	let resetting = $state(false);
	let resetConfirm = $state(false);

	async function resetSync() {
		resetting = true;
		try {
			const res = await fetch(`${API_BASE}/sync/reset`, { method: 'POST' }).catch(() => null);
			if (res?.ok) {
				// Reload page to show setup wizard
				window.location.reload();
			}
		} finally {
			resetting = false;
			resetConfirm = false;
		}
	}

	// ── Load everything when tab becomes active or team changes ──────────────
	$effect(() => {
		if (!active) return;
		const _team = teamName; // track teamName so we re-fetch on team switch
		untrack(() => {
			loadWatchStatus();
			loadStats();
			loadPending();
		});
	});
</script>

<div class="p-6 space-y-5">

	<!-- ── 1. Sync Engine Banner ─────────────────────────────────────────── -->
	{#if watchLoading}
		<div class="h-14 rounded-[var(--radius-lg)] bg-[var(--bg-muted)] animate-pulse" aria-hidden="true"></div>
	{:else}
		{@const running = watchStatus?.running ?? false}
		{@const syncthingUp = detect?.running ?? false}
		<div
			class="flex items-center gap-3 p-4 rounded-[var(--radius-lg)] border {running
				? 'border-[var(--success)]/30 bg-[var(--status-active-bg)]'
				: 'border-[var(--warning)]/30 bg-[var(--status-idle-bg)]'}"
		>
			<span
				class="w-2.5 h-2.5 rounded-full shrink-0 {running ? 'bg-[var(--success)]' : 'bg-[var(--warning)]'}"
				aria-hidden="true"
			></span>
			<div class="flex-1 min-w-0">
				<span class="text-sm font-semibold text-[var(--text-primary)]">
					{running ? 'Session Watcher Running' : 'Session Watcher Stopped'}
				</span>
				{#if running && watchStatus?.team}
					<p class="text-xs text-[var(--text-secondary)] mt-0.5 truncate">
						Team: {watchStatus.team}{#if watchStatus.started_at} &middot; started {formatRelativeTime(watchStatus.started_at)}{/if}
					</p>
				{:else if !running}
					<p class="text-xs text-[var(--text-muted)] mt-0.5">Start the watcher to detect new sessions and package them for your teammates.</p>
				{/if}
				<p class="text-[11px] mt-1 {syncthingUp ? 'text-[var(--success)]' : 'text-[var(--error)]'}">
					Syncthing: {syncthingUp ? 'connected' : 'not running'}
				</p>
			</div>
			{#if running}
				<button
					onclick={stopWatch}
					disabled={watchActing}
					aria-label="Stop sync engine"
					class="shrink-0 flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-[var(--radius)] border border-[var(--error)]/30 text-[var(--error)] hover:bg-[var(--error-subtle)] transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
				>
					{#if watchActing}
						<Loader2 size={12} class="animate-spin" />
					{:else}
						<Square size={12} />
					{/if}
					Stop
				</button>
			{:else}
				<button
					onclick={startWatch}
					disabled={watchActing || !teamName}
					aria-label="Start sync engine"
					class="shrink-0 flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-[var(--radius)] bg-[var(--accent)] text-white hover:bg-[var(--accent-hover)] transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
				>
					{#if watchActing}
						<Loader2 size={12} class="animate-spin" />
					{:else}
						<Play size={12} />
					{/if}
					Start
				</button>
			{/if}
		</div>
	{/if}

	<!-- ── 2. Stats Row ──────────────────────────────────────────────────── -->
	{#if statsLoading}
		<div class="grid grid-cols-4 gap-3">
			{#each [1, 2, 3, 4] as i (i)}
				<div class="h-20 rounded-[var(--radius-lg)] bg-[var(--bg-muted)] animate-pulse" aria-hidden="true"></div>
			{/each}
		</div>
	{:else}
		<div class="grid grid-cols-4 gap-3">
			<div class="rounded-[var(--radius-lg)] border border-[var(--border)] bg-[var(--bg-subtle)] p-4 text-center">
				<Users size={16} class="mx-auto text-[var(--text-muted)] mb-1.5" />
				<p class="text-lg font-semibold text-[var(--text-primary)]">{connectedMembers}/{totalMembers}</p>
				<p class="text-[11px] text-[var(--text-muted)]">Members Online</p>
			</div>
			<div class="rounded-[var(--radius-lg)] border border-[var(--border)] bg-[var(--bg-subtle)] p-4 text-center">
				<FolderGit2 size={16} class="mx-auto text-[var(--text-muted)] mb-1.5" />
				<p class="text-lg font-semibold text-[var(--text-primary)]">{projectCount}</p>
				<p class="text-[11px] text-[var(--text-muted)]">Projects</p>
			</div>
			<div class="rounded-[var(--radius-lg)] border border-[var(--border)] bg-[var(--bg-subtle)] p-4 text-center">
				<ArrowUp size={16} class="mx-auto text-[var(--accent)] mb-1.5" />
				<p class="text-lg font-semibold text-[var(--text-primary)]">{sessionsSharedCount}</p>
				<p class="text-[11px] text-[var(--text-muted)]">Sessions Shared</p>
			</div>
			<div class="rounded-[var(--radius-lg)] border border-[var(--border)] bg-[var(--bg-subtle)] p-4 text-center">
				<ArrowDown size={16} class="mx-auto text-[var(--info)] mb-1.5" />
				<p class="text-lg font-semibold text-[var(--text-primary)]">{sessionsReceivedCount}</p>
				<p class="text-[11px] text-[var(--text-muted)]">Sessions Received</p>
			</div>
		</div>
	{/if}

	<!-- ── 3. Pending Actions (only when > 0) ──────────────────────────── -->
	{#if pendingLoading}
		<div class="rounded-[var(--radius-lg)] border border-[var(--border)] bg-[var(--bg-subtle)]">
			<div class="px-5 py-4 space-y-2">
				{#each [1, 2] as i (i)}
					<div class="h-10 rounded-[var(--radius)] bg-[var(--bg-muted)] animate-pulse" aria-hidden="true"></div>
				{/each}
			</div>
		</div>
	{:else if pendingError}
		<div
			class="flex items-center gap-3 p-4 rounded-[var(--radius-lg)] border border-[var(--error)]/20 bg-[var(--error-subtle)] text-xs text-[var(--error)]"
		>
			<XCircle size={13} class="shrink-0" />
			<span class="flex-1">{pendingError}</span>
			<button onclick={loadPending} class="underline hover:no-underline font-medium">Retry</button>
		</div>
	{:else if pendingFolders.length > 0}
		<div class="rounded-[var(--radius-lg)] border border-[var(--border)] bg-[var(--bg-subtle)]">
			<!-- Header -->
			<div class="flex items-center justify-between px-5 py-3.5 border-b border-[var(--border-subtle)]">
				<div class="flex items-center gap-2">
					<Bell size={14} class="text-[var(--text-muted)]" />
					<h3 class="text-sm font-semibold text-[var(--text-primary)]">Pending Actions</h3>
					<span class="px-1.5 py-0.5 text-[10px] font-medium rounded bg-[var(--warning)]/15 text-[var(--warning)] border border-[var(--warning)]/25">
						{pendingFolders.length}
					</span>
				</div>
				<button
					onclick={acceptAll}
					disabled={acceptingAll}
					aria-label="Accept all pending folder offers"
					class="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-[var(--radius)] bg-[var(--accent)] text-white hover:bg-[var(--accent-hover)] transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
				>
					{#if acceptingAll}
						<Loader2 size={12} class="animate-spin" />
						Accepting...
					{:else}
						<CheckCircle2 size={12} />
						Accept All
					{/if}
				</button>
			</div>

			<!-- Body -->
			<div class="px-5 divide-y divide-[var(--border-subtle)]">
				{#each pendingFolders as offer (offer.folder_id)}
					<div class="flex items-start gap-3 py-3.5">
						<FolderGit2 size={15} class="shrink-0 text-[var(--warning)] mt-0.5" />
						<div class="flex-1 min-w-0">
							<p class="text-sm font-medium text-[var(--text-primary)] truncate">{parseFolderLabel(offer.folder_id)}</p>
							<div class="flex items-center gap-3 mt-0.5 text-xs text-[var(--text-muted)]">
								<span>from <span class="text-[var(--text-secondary)]">{offer.from_member}</span></span>
								<span class="text-[var(--border)]">&middot;</span>
								<span>team <span class="text-[var(--text-secondary)]">{offer.from_team}</span></span>
								{#if offer.offered_at}
									<span class="text-[var(--border)]">&middot;</span>
									<span>{formatRelativeTime(offer.offered_at)}</span>
								{/if}
							</div>
						</div>
					</div>
				{/each}
			</div>
		</div>
	{/if}

	<!-- ── 4. Machine Details Card ───────────────────────────────────────── -->
	<div class="rounded-[var(--radius-lg)] border border-[var(--border)] bg-[var(--bg-subtle)] p-5 space-y-3">
		<div class="flex items-center gap-2 mb-1">
			<Monitor size={14} class="text-[var(--text-muted)]" />
			<h3 class="text-sm font-semibold text-[var(--text-primary)]">Machine Details</h3>
		</div>

		{#if status?.user_id}
			<div class="flex items-center justify-between">
				<span class="text-xs font-medium text-[var(--text-secondary)]">Your Name</span>
				<span class="text-xs text-[var(--text-primary)] font-mono">{status.user_id}</span>
			</div>
		{/if}

		{#if status?.machine_id}
			<div class="flex items-center justify-between">
				<span class="text-xs font-medium text-[var(--text-secondary)]">Machine</span>
				<span class="text-xs text-[var(--text-primary)] font-mono">{status.machine_id}</span>
			</div>
		{/if}

		{#if detect?.version}
			<div class="flex items-center justify-between">
				<span class="text-xs font-medium text-[var(--text-secondary)]">Syncthing Version</span>
				<span class="text-xs text-[var(--text-muted)]">v{detect.version}</span>
			</div>
		{/if}

		{#if !status?.user_id && !status?.machine_id && !detect?.version}
			<p class="text-xs text-[var(--text-muted)]">No machine details available.</p>
		{/if}

		<!-- Reset sync -->
		<div class="pt-3 mt-3 border-t border-[var(--border-subtle)]">
			{#if resetConfirm}
				<div class="flex items-center justify-between gap-2">
					<span class="text-xs text-[var(--text-secondary)]">Reset all sync config and return to setup?</span>
					<div class="flex items-center gap-1.5">
						<button
							onclick={resetSync}
							disabled={resetting}
							class="px-2.5 py-1 text-xs font-medium rounded-md bg-[var(--error)] text-white hover:opacity-90 transition-opacity disabled:opacity-50"
						>
							{resetting ? 'Resetting...' : 'Yes, reset'}
						</button>
						<button
							onclick={() => (resetConfirm = false)}
							class="px-2.5 py-1 text-xs font-medium rounded-md border border-[var(--border)] text-[var(--text-muted)] hover:text-[var(--text-primary)] transition-colors"
						>
							Cancel
						</button>
					</div>
				</div>
			{:else}
				<button
					onclick={() => (resetConfirm = true)}
					class="flex items-center gap-1.5 text-xs text-[var(--text-muted)] hover:text-[var(--error)] transition-colors"
				>
					<RotateCcw size={12} />
					Reset Sync Setup
				</button>
			{/if}
		</div>
	</div>

</div>

<script lang="ts">
	import { untrack } from 'svelte';
	import { Play, Square, Monitor, FolderGit2, ArrowUp, ArrowDown, Bell, CheckCircle2, Loader2, Users, XCircle, RotateCcw, Clock, RefreshCw, ChevronDown } from 'lucide-svelte';
	import type { SyncDetect, SyncStatusResponse, SyncWatchStatus, SyncPendingFolder, SyncProjectStatus, SyncEvent } from '$lib/api-types';
	import { formatRelativeTime } from '$lib/utils';
	import { API_BASE } from '$lib/config';

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
		try {
			await fetch(`${API_BASE}/sync/pending/accept`, { method: 'POST' }).catch(() => null);
			await loadPending();
		} finally {
			acceptingAll = false;
		}
	}

	// ── Per-Project Sync Status (Task 5) ─────────────────────────────────────
	let projectStatuses = $state<SyncProjectStatus[]>([]);
	let projectStatusLoading = $state(true);
	let syncAllActing = $state(false);

	async function loadProjectStatus() {
		if (!teamName) {
			projectStatuses = [];
			projectStatusLoading = false;
			return;
		}
		try {
			const res = await fetch(
				`${API_BASE}/sync/teams/${encodeURIComponent(teamName)}/project-status`
			).catch(() => null);
			if (res?.ok) {
				const data = await res.json();
				projectStatuses = data.projects ?? [];
			} else {
				projectStatuses = [];
			}
		} catch {
			projectStatuses = [];
		} finally {
			projectStatusLoading = false;
		}
	}

	async function syncAllNow() {
		if (!teamName) return;
		syncAllActing = true;
		try {
			await fetch(
				`${API_BASE}/sync/teams/${encodeURIComponent(teamName)}/sync-now`,
				{ method: 'POST' }
			).catch(() => null);
			await loadProjectStatus();
		} finally {
			syncAllActing = false;
		}
	}

	// ── Recent Activity (Task 6) ─────────────────────────────────────────────
	let recentEvents = $state<SyncEvent[]>([]);
	let activityLoading = $state(true);

	async function loadRecentActivity() {
		try {
			const res = await fetch(`${API_BASE}/sync/activity?limit=8`).catch(() => null);
			if (res?.ok) {
				const data = await res.json();
				recentEvents = data.events ?? [];
			} else {
				recentEvents = [];
			}
		} catch {
			recentEvents = [];
		} finally {
			activityLoading = false;
		}
	}

	function humanizeEvent(ev: SyncEvent): string {
		const member = ev.member_name ?? 'Someone';
		const team = ev.team_name ?? 'team';
		const project = ev.project_encoded_name ?? 'project';
		switch (ev.event_type) {
			case 'member_added':
				return `${member} joined ${team}`;
			case 'member_removed':
				return `${member} left ${team}`;
			case 'project_added':
				return `Project ${project} added to ${team}`;
			case 'project_removed':
				return `Project ${project} removed from ${team}`;
			case 'session_packaged':
				return `${member} packaged a session in ${project}`;
			case 'session_received':
				return `Received a session from ${member} in ${project}`;
			case 'watch_started':
				return `Session watcher started for ${team}`;
			case 'watch_stopped':
				return 'Session watcher stopped';
			case 'pending_accepted':
				return 'Pending folders accepted';
			case 'team_created':
				return `Team ${team} created`;
			case 'team_deleted':
				return `Team ${team} deleted`;
			default:
				return ev.detail ?? ev.event_type.replace(/_/g, ' ');
		}
	}

	// ── Machine Details accordion (Task 7) ───────────────────────────────────
	let machineDetailsOpen = $state(false);

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

	// ── Reset loading states when team changes ──────────────────────────────
	$effect(() => {
		teamName; // track teamName
		untrack(() => {
			statsLoaded = false;
			statsLoading = true;
			watchLoading = true;
			pendingLoading = true;
			projectStatusLoading = true;
			activityLoading = true;
		});
	});

	// ── Load everything when tab becomes active or team changes ──────────────
	$effect(() => {
		if (!active) return;
		const _team = teamName; // track teamName so we re-fetch on team switch
		untrack(() => {
			loadWatchStatus();
			loadStats();
			loadPending();
			loadProjectStatus();
			loadRecentActivity();
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
		<div class="grid grid-cols-2 sm:grid-cols-4 gap-3">
			{#each [1, 2, 3, 4] as i (i)}
				<div class="h-20 rounded-[var(--radius-lg)] bg-[var(--bg-muted)] animate-pulse" aria-hidden="true"></div>
			{/each}
		</div>
	{:else}
		{@const teamHref = teamName ? '/team/' + encodeURIComponent(teamName) : '/team'}
		<div class="grid grid-cols-2 sm:grid-cols-4 gap-3">
			<a href={teamHref} class="rounded-[var(--radius-lg)] border border-[var(--border)] bg-[var(--bg-subtle)] p-4 text-center no-underline hover:border-[var(--accent)]/40 transition-colors">
				<Users size={16} class="mx-auto text-[var(--text-muted)] mb-1.5" />
				<p class="text-lg font-semibold text-[var(--text-primary)]">{connectedMembers}/{totalMembers}</p>
				<p class="text-[11px] text-[var(--text-muted)]">Members Online</p>
			</a>
			<a href={teamHref} class="rounded-[var(--radius-lg)] border border-[var(--border)] bg-[var(--bg-subtle)] p-4 text-center no-underline hover:border-[var(--accent)]/40 transition-colors">
				<FolderGit2 size={16} class="mx-auto text-[var(--text-muted)] mb-1.5" />
				<p class="text-lg font-semibold text-[var(--text-primary)]">{projectCount}</p>
				<p class="text-[11px] text-[var(--text-muted)]">Projects</p>
			</a>
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

	<!-- ── 4. Per-Project Sync Status ──────────────────────────────────── -->
	{#if projectStatusLoading}
		<div class="rounded-[var(--radius-lg)] border border-[var(--border)] bg-[var(--bg-subtle)]">
			<div class="px-5 py-4 space-y-2">
				{#each [1, 2, 3] as i (i)}
					<div class="h-10 rounded-[var(--radius)] bg-[var(--bg-muted)] animate-pulse" aria-hidden="true"></div>
				{/each}
			</div>
		</div>
	{:else if projectStatuses.length > 0}
		<div class="rounded-[var(--radius-lg)] border border-[var(--border)] bg-[var(--bg-subtle)]">
			<!-- Header -->
			<div class="flex items-center justify-between px-5 py-3.5 border-b border-[var(--border-subtle)]">
				<div class="flex items-center gap-2">
					<FolderGit2 size={14} class="text-[var(--text-muted)]" />
					<h3 class="text-sm font-semibold text-[var(--text-primary)]">Project Sync Status</h3>
					<span class="px-1.5 py-0.5 text-[10px] font-medium rounded bg-[var(--accent)]/10 text-[var(--accent)] border border-[var(--accent)]/20">
						{projectStatuses.length}
					</span>
				</div>
				<button
					onclick={syncAllNow}
					disabled={syncAllActing}
					aria-label="Sync all projects now"
					class="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-[var(--radius)] bg-[var(--accent)] text-white hover:bg-[var(--accent-hover)] transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
				>
					{#if syncAllActing}
						<Loader2 size={12} class="animate-spin" />
						Syncing...
					{:else}
						<RefreshCw size={12} />
						Sync All Now
					{/if}
				</button>
			</div>

			<!-- Body -->
			<div class="px-5 divide-y divide-[var(--border-subtle)]">
				{#each projectStatuses as proj (proj.encoded_name)}
					<div class="flex items-center gap-3 py-3.5">
						<FolderGit2 size={15} class="shrink-0 text-[var(--text-muted)]" />
						<div class="flex-1 min-w-0">
							<a
								href="/projects/{proj.encoded_name}"
								class="text-sm font-medium text-[var(--text-primary)] hover:text-[var(--accent)] transition-colors truncate block"
							>
								{proj.name}
							</a>
							<p class="text-xs text-[var(--text-muted)] mt-0.5">
								{proj.packaged_count}/{proj.local_count} sessions packaged
							</p>
						</div>
						{#if proj.gap === 0}
							<span class="shrink-0 flex items-center gap-1 px-2 py-1 text-[11px] font-medium rounded-full bg-[var(--success)]/10 text-[var(--success)] border border-[var(--success)]/20">
								<CheckCircle2 size={11} />
								In Sync
							</span>
						{:else}
							<span class="shrink-0 flex items-center gap-1 px-2 py-1 text-[11px] font-medium rounded-full bg-[var(--warning)]/10 text-[var(--warning)] border border-[var(--warning)]/20">
								{proj.gap} behind
							</span>
						{/if}
					</div>
				{/each}
			</div>
		</div>
	{/if}

	<!-- ── 5. Recent Activity ─────────────────────────────────────────── -->
	{#if activityLoading}
		<div class="rounded-[var(--radius-lg)] border border-[var(--border)] bg-[var(--bg-subtle)]">
			<div class="px-5 py-4 space-y-2">
				{#each [1, 2, 3] as i (i)}
					<div class="h-8 rounded-[var(--radius)] bg-[var(--bg-muted)] animate-pulse" aria-hidden="true"></div>
				{/each}
			</div>
		</div>
	{:else if recentEvents.length > 0}
		<div class="rounded-[var(--radius-lg)] border border-[var(--border)] bg-[var(--bg-subtle)]">
			<!-- Header -->
			<div class="flex items-center gap-2 px-5 py-3.5 border-b border-[var(--border-subtle)]">
				<Clock size={14} class="text-[var(--text-muted)]" />
				<h3 class="text-sm font-semibold text-[var(--text-primary)]">Recent Activity</h3>
			</div>

			<!-- Body -->
			<div class="px-5 divide-y divide-[var(--border-subtle)]">
				{#each recentEvents as ev (ev.id)}
					<div class="flex items-center justify-between gap-3 py-3">
						<p class="text-xs text-[var(--text-secondary)] truncate flex-1">{humanizeEvent(ev)}</p>
						<span class="text-[11px] text-[var(--text-muted)] shrink-0 whitespace-nowrap">{formatRelativeTime(ev.created_at)}</span>
					</div>
				{/each}
			</div>
		</div>
	{/if}

	<!-- ── 6. Machine Details Card (collapsible) ───────────────────────── -->
	<div class="rounded-[var(--radius-lg)] border border-[var(--border)] bg-[var(--bg-subtle)]">
		<button
			onclick={() => (machineDetailsOpen = !machineDetailsOpen)}
			aria-expanded={machineDetailsOpen}
			class="flex items-center justify-between w-full px-5 py-3.5 text-left cursor-pointer hover:bg-[var(--bg-muted)]/50 transition-colors rounded-[var(--radius-lg)]"
		>
			<div class="flex items-center gap-2">
				<Monitor size={14} class="text-[var(--text-muted)]" />
				<h3 class="text-sm font-semibold text-[var(--text-primary)]">Machine Details</h3>
			</div>
			<ChevronDown
				size={14}
				class="text-[var(--text-muted)] transition-transform duration-200 {machineDetailsOpen ? 'rotate-180' : ''}"
			/>
		</button>

		{#if machineDetailsOpen}
			<div class="px-5 pb-5 space-y-3 border-t border-[var(--border-subtle)]">
				<div class="pt-3">
					{#if status?.user_id}
						<div class="flex items-center justify-between mb-3">
							<span class="text-xs font-medium text-[var(--text-secondary)]">Your Name</span>
							<span class="text-xs text-[var(--text-primary)] font-mono">{status.user_id}</span>
						</div>
					{/if}

					{#if status?.machine_id}
						<div class="flex items-center justify-between mb-3">
							<span class="text-xs font-medium text-[var(--text-secondary)]">Machine</span>
							<span class="text-xs text-[var(--text-primary)] font-mono">{status.machine_id}</span>
						</div>
					{/if}

					{#if detect?.version}
						<div class="flex items-center justify-between mb-3">
							<span class="text-xs font-medium text-[var(--text-secondary)]">Syncthing Version</span>
							<span class="text-xs text-[var(--text-muted)]">v{detect.version}</span>
						</div>
					{/if}

					{#if !status?.user_id && !status?.machine_id && !detect?.version}
						<p class="text-xs text-[var(--text-muted)]">No machine details available.</p>
					{/if}
				</div>

				<!-- Reset sync -->
				<div class="pt-3 border-t border-[var(--border-subtle)]">
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
		{/if}
	</div>

</div>

<script lang="ts">
	import { untrack } from 'svelte';
	import { Play, Square, Monitor, FolderGit2, ArrowUp, ArrowDown, CheckCircle2, Loader2, Users, RotateCcw, Clock, RefreshCw, ChevronDown, Copy, CheckCircle } from 'lucide-svelte';
	import type { SyncDetect, SyncStatusResponse, SyncWatchStatus, SyncProjectStatus, SyncEvent } from '$lib/api-types';
	import { formatRelativeTime, copyToClipboard } from '$lib/utils';
	import { formatSyncEvent } from '$lib/utils/sync-events';
	import { API_BASE } from '$lib/config';

	let {
		detect = null,
		status = null,
		active = false,
		teamName = null,
		onteamchange,
		initialWatchStatus = null
	}: {
		detect: SyncDetect | null;
		status: SyncStatusResponse | null;
		active?: boolean;
		teamName: string | null;
		onteamchange?: () => void;
		initialWatchStatus?: SyncWatchStatus | null;
	} = $props();

	// ── Sync Engine watch status ──────────────────────────────────────────────
	let watchStatus = $state<SyncWatchStatus | null>(null);
	let watchLoading = $state(true);

	// Seed from parent's cached data when available
	$effect(() => {
		if (initialWatchStatus !== null) {
			watchStatus = initialWatchStatus;
			watchLoading = false;
		}
	});
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
				// Auto-sync all existing unsynced sessions when watcher starts
				await syncAllNow();
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
	let connectedMembers = $state(0);
	let membersLoaded = $state(false);
	let membersLoading = $state(true);

	// Total members from DB (includes self) — more accurate than device count
	let totalMembers = $derived.by(() => {
		if (!teamName || !status?.teams) return 0;
		const team = status.teams[teamName] as { member_count?: number } | undefined;
		return team?.member_count ?? 0;
	});

	// Derive project count from status, scoped to active team
	let projectCount = $derived.by(() => {
		if (!teamName || !status?.teams) return 0;
		const team = status.teams[teamName] as { project_count?: number } | undefined;
		return team?.project_count ?? 0;
	});

	// Derive session counts from projectStatuses (fetched by loadProjectStatus)
	let sessionsSharedCount = $derived.by(() => {
		let shared = 0;
		for (const p of projectStatuses) {
			shared += (p as { packaged_count?: number }).packaged_count ?? 0;
		}
		return shared;
	});

	let sessionsReceivedCount = $derived.by(() => {
		let received = 0;
		for (const p of projectStatuses) {
			const counts = (p as { received_counts?: Record<string, number> }).received_counts ?? {};
			for (const count of Object.values(counts)) {
				received += count ?? 0;
			}
		}
		return received;
	});

	async function loadMemberStats() {
		if (!membersLoaded) membersLoading = true;
		try {
			const devicesRes = await fetch(`${API_BASE}/sync/devices`).catch(() => null);
			if (devicesRes?.ok) {
				const devData = await devicesRes.json();
				const devices = devData.devices ?? [];
				const remoteDevices = devices.filter((d: { is_self?: boolean }) => !d.is_self);
				// +1 for self (always online)
				connectedMembers = remoteDevices.filter((d: { connected?: boolean }) => d.connected).length + 1;
			}
		} catch {
			// Non-critical
		} finally {
			membersLoading = false;
			membersLoaded = true;
		}
	}

	// Pending actions are handled on individual team detail pages

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
			const url = new URL(`${API_BASE}/sync/activity`, window.location.origin);
			url.searchParams.set('limit', '8');
			if (teamName) url.searchParams.set('team_name', teamName);
			const res = await fetch(url.toString()).catch(() => null);
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

	// ── Machine Details accordion (Task 7) ───────────────────────────────────
	let machineDetailsOpen = $state(false);
	let copiedJoinCode = $state(false);
	let copiedDeviceId = $state(false);

	let ownDeviceId = $derived(detect?.device_id ?? status?.device_id ?? null);
	let ownJoinCode = $derived(
		status?.user_id && ownDeviceId
			? `${status.user_id}:${ownDeviceId}`
			: null
	);

	async function copyJoinCode() {
		if (!ownJoinCode) return;
		const ok = await copyToClipboard(ownJoinCode);
		if (ok) {
			copiedJoinCode = true;
			setTimeout(() => (copiedJoinCode = false), 2000);
		}
	}

	async function copyDeviceId() {
		if (!ownDeviceId) return;
		const ok = await copyToClipboard(ownDeviceId);
		if (ok) {
			copiedDeviceId = true;
			setTimeout(() => (copiedDeviceId = false), 2000);
		}
	}

	// ── Reset sync ───────────────────────────────────────────────────────────
	let resetting = $state(false);
	let resetConfirm = $state(false);
	let uninstallSyncthing = $state(false);
	let resetResult: Record<string, any> | null = $state(null);

	async function resetSync() {
		resetting = true;
		resetResult = null;
		try {
			const res = await fetch(`${API_BASE}/sync/reset`, {
				method: 'POST',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify({ uninstall_syncthing: uninstallSyncthing })
			}).catch(() => null);
			if (res?.ok) {
				const data = await res.json();
				resetResult = data.steps;
				// Brief delay to show result, then reload
				setTimeout(() => window.location.reload(), 1500);
			}
		} finally {
			resetting = false;
		}
	}

	// ── Reset loading states when team changes ──────────────────────────────
	$effect(() => {
		teamName; // track teamName
		untrack(() => {
			membersLoaded = false;
			membersLoading = true;
			watchLoading = true;
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
			loadMemberStats();
			loadProjectStatus();
			loadRecentActivity();
		});
	});
</script>

<div class="space-y-5">

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
	{#if membersLoading && projectStatusLoading}
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

	<!-- Pending actions are shown on individual team pages (teams/{name}) -->

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
						<p class="text-xs text-[var(--text-secondary)] truncate flex-1">{formatSyncEvent(ev)}</p>
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

					{#if ownDeviceId}
						<div class="flex items-center justify-between mb-3">
							<span class="text-xs font-medium text-[var(--text-secondary)]">Device ID</span>
							<div class="flex items-center gap-1.5">
								<span class="text-xs text-[var(--text-primary)] font-mono truncate max-w-[200px]">{ownDeviceId}</span>
								<button
									onclick={copyDeviceId}
									aria-label="Copy device ID"
									class="shrink-0 p-1 rounded text-[var(--text-muted)] hover:text-[var(--text-primary)] hover:bg-[var(--bg-muted)] transition-colors"
								>
									{#if copiedDeviceId}
										<CheckCircle size={12} class="text-[var(--success)]" />
									{:else}
										<Copy size={12} />
									{/if}
								</button>
							</div>
						</div>
					{/if}

					{#if ownJoinCode}
						<div class="mb-3 space-y-1.5">
							<span class="text-xs font-medium text-[var(--text-secondary)]">Your Join Code</span>
							<p class="text-[11px] text-[var(--text-muted)]">Share this with teammates so they can add you via "Add Member".</p>
							<div class="flex items-center gap-2">
								<code
									class="flex-1 px-3 py-2 text-xs font-mono rounded-[var(--radius-md)] border border-[var(--border)] bg-[var(--bg-muted)] text-[var(--text-primary)] break-all select-all leading-relaxed"
								>
									{ownJoinCode}
								</code>
								<button
									onclick={copyJoinCode}
									aria-label="Copy join code"
									class="shrink-0 p-2 rounded-[var(--radius-md)] border border-[var(--border)] bg-[var(--bg-base)] text-[var(--text-muted)] hover:text-[var(--text-primary)] hover:bg-[var(--bg-muted)] transition-colors"
								>
									{#if copiedJoinCode}
										<CheckCircle size={14} class="text-[var(--success)]" />
									{:else}
										<Copy size={14} />
									{/if}
								</button>
							</div>
						</div>
					{/if}

					{#if !status?.user_id && !status?.machine_id && !detect?.version}
						<p class="text-xs text-[var(--text-muted)]">No machine details available.</p>
					{/if}
				</div>

				<!-- Reset sync -->
				<div class="pt-3 border-t border-[var(--border-subtle)]">
					{#if resetResult}
						<div class="p-2.5 rounded-md bg-green-500/10 text-xs text-green-400">
							Sync reset complete. Reloading...
						</div>
					{:else if resetConfirm}
						<div class="space-y-2.5">
							<p class="text-xs font-medium text-[var(--error)]">This will:</p>
							<ul class="text-xs text-[var(--text-secondary)] space-y-1 pl-4 list-disc">
								<li>Remove all karma shared folders from Syncthing</li>
								<li>Remove all paired team devices</li>
								<li>Stop the Syncthing daemon</li>
								<li>Delete all remote sessions, handshakes & metadata</li>
								<li>Clear sync config, teams, members, events & rejections</li>
								<li>Remove stale database files</li>
							</ul>
							<label class="flex items-center gap-2 text-xs text-[var(--text-secondary)] cursor-pointer">
								<input type="checkbox" bind:checked={uninstallSyncthing} class="rounded" />
								Full uninstall (brew uninstall + remove config)
							</label>
							<div class="flex items-center gap-1.5 pt-1">
								<button
									onclick={resetSync}
									disabled={resetting}
									class="px-2.5 py-1 text-xs font-medium rounded-md bg-[var(--error)] text-white hover:opacity-90 transition-opacity disabled:opacity-50"
								>
									{resetting ? 'Resetting...' : 'Yes, nuke everything'}
								</button>
								<button
									onclick={() => { resetConfirm = false; uninstallSyncthing = false; }}
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

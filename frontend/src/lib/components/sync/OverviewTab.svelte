<script lang="ts">
	import { Play, Square, Monitor, FolderGit2, ArrowUp, ArrowDown, Bell, CheckCircle2, Copy, Loader2, Users, XCircle, Trash2, Sparkles } from 'lucide-svelte';
	import type { SyncDetect, SyncStatusResponse, SyncWatchStatus, SyncPendingFolder } from '$lib/api-types';
	import { formatBytes, formatRelativeTime } from '$lib/utils';
	import { API_BASE } from '$lib/config';

	let {
		detect = null,
		status = null,
		active = false,
		teamName = null,
		onteamchange
	}: {
		detect: SyncDetect | null;
		status: SyncStatusResponse | null;
		active?: boolean;
		teamName: string | null;
		onteamchange?: () => void;
	} = $props();

	// ── Sync Engine watch status ──────────────────────────────────────────────
	let watchStatus = $state<SyncWatchStatus | null>(null);
	let watchLoading = $state(true);
	let watchActing = $state(false);

	async function loadWatchStatus() {
		watchLoading = true;
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

	// ── Team management ──────────────────────────────────────────────────────
	let deletingTeam = $state(false);
	let deleteConfirm = $state(false);

	// Flash message
	let flashMessage = $state<string | null>(null);
	let flashTimeout: ReturnType<typeof setTimeout> | null = null;

	function showFlash(msg: string) {
		flashMessage = msg;
		if (flashTimeout) clearTimeout(flashTimeout);
		flashTimeout = setTimeout(() => (flashMessage = null), 3000);
	}

	async function deleteTeam() {
		if (!teamName) return;
		deletingTeam = true;
		try {
			const res = await fetch(`${API_BASE}/sync/teams/${encodeURIComponent(teamName)}`, {
				method: 'DELETE'
			});
			if (res.ok) {
				deleteConfirm = false;
				showFlash(`Team "${teamName}" deleted`);
				onteamchange?.();
			}
		} catch {
			// ignore
		} finally {
			deletingTeam = false;
		}
	}

	// ── Stats ─────────────────────────────────────────────────────────────────
	let memberCount = $state(0);
	let projectCount = $state(0);
	let syncedInBytes = $state(0);
	let syncedOutBytes = $state(0);
	let statsLoading = $state(true);

	type TeamEntry = { member_count?: number; project_count?: number; members?: unknown[] };

	let derivedMemberCount = $derived.by(() => {
		if (!status?.teams) return 0;
		let count = 0;
		for (const team of Object.values(status.teams) as TeamEntry[]) {
			count += team.member_count ?? (Array.isArray(team.members) ? team.members.length : 0);
		}
		return count;
	});

	let derivedProjectCount = $derived.by(() => {
		if (!status?.teams) return 0;
		let count = 0;
		for (const team of Object.values(status.teams) as TeamEntry[]) {
			count += team.project_count ?? 0;
		}
		return count;
	});

	async function loadStats() {
		statsLoading = true;
		memberCount = derivedMemberCount;
		projectCount = derivedProjectCount;
		try {
			const res = await fetch(`${API_BASE}/sync/projects`).catch(() => null);
			if (res?.ok) {
				const data = await res.json();
				const folders = data.folders ?? [];
				let inBytes = 0;
				let outBytes = 0;
				for (const f of folders) {
					const syncBytes = (f.inSyncBytes as number) ?? 0;
					const fType = (f.type as string) ?? 'sendreceive';
					if (fType === 'sendonly' || fType === 'sendreceive') outBytes += syncBytes;
					if (fType === 'receiveonly' || fType === 'sendreceive') inBytes += syncBytes;
				}
				syncedInBytes = inBytes;
				syncedOutBytes = outBytes;
			}
		} catch {
			// Non-critical
		} finally {
			statsLoading = false;
		}
	}

	// ── Machine details ───────────────────────────────────────────────────────
	let copiedDeviceId = $state(false);

	function copyDeviceId() {
		const id = detect?.device_id ?? '';
		navigator.clipboard.writeText(id).then(() => {
			copiedDeviceId = true;
			setTimeout(() => (copiedDeviceId = false), 2000);
		}).catch(() => {});
	}

	// ── Folder label helper ──────────────────────────────────────────────────
	function parseFolderLabel(folderId: string): string {
		// Pattern: "karma-out-{user}-{project}" or "karma-in-{user}-{project}"
		const match = folderId.match(/^karma-(?:out|in)-[^-]+-(.+)$/);
		if (match) return `${match[1]} sessions`;
		return folderId;
	}

	// ── Pending actions ───────────────────────────────────────────────────────
	let pendingFolders = $state<SyncPendingFolder[]>([]);
	let pendingLoading = $state(true);
	let acceptingAll = $state(false);
	let pendingError = $state<string | null>(null);

	async function loadPending() {
		pendingLoading = true;
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

	// ── Guided empty state ────────────────────────────────────────────────────
	let showGettingStarted = $derived(memberCount === 0 && projectCount === 0 && !statsLoading);

	// ── Load everything when tab becomes active ───────────────────────────────
	$effect(() => {
		if (active) {
			loadWatchStatus();
			loadStats();
			loadPending();
		}
	});
</script>

<div class="p-6 space-y-5">

	<!-- ── Flash message ───────────────────────────────────────────────── -->
	{#if flashMessage}
		<div
			class="flex items-center gap-2 px-4 py-2.5 rounded-[var(--radius-lg)] bg-[var(--success)]/10 border border-[var(--success)]/20 text-xs font-medium text-[var(--success)]"
		>
			<CheckCircle2 size={14} class="shrink-0" />
			{flashMessage}
		</div>
	{/if}

	<!-- ── 1. Sync Engine Banner ─────────────────────────────────────────── -->
	{#if watchLoading}
		<div class="h-14 rounded-[var(--radius-lg)] bg-[var(--bg-muted)] animate-pulse" aria-hidden="true"></div>
	{:else}
		{@const running = watchStatus?.running ?? false}
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
					{running ? 'Sync Engine Running' : 'Sync Engine Stopped'}
				</span>
				{#if running && watchStatus?.team}
					<p class="text-xs text-[var(--text-secondary)] mt-0.5 truncate">
						Team: {watchStatus.team}{#if watchStatus.started_at} &middot; started {formatRelativeTime(watchStatus.started_at)}{/if}
					</p>
				{:else if !running}
					<p class="text-xs text-[var(--text-muted)] mt-0.5">The sync engine watches your projects and packages new sessions for your teammates.</p>
				{/if}
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

	<!-- ── 2. Team Management ────────────────────────────────────────────── -->
	<div class="rounded-[var(--radius-lg)] border border-[var(--border)] bg-[var(--bg-subtle)] p-5 space-y-4">
		<div class="flex items-center gap-2 mb-1">
			<Users size={14} class="text-[var(--text-muted)]" />
			<h3 class="text-sm font-semibold text-[var(--text-primary)]">Team</h3>
		</div>

		{#if teamName}
			<!-- Active team display -->
			<div class="flex items-center justify-between gap-3">
				<div class="flex-1 min-w-0">
					<p class="text-xs font-medium text-[var(--text-secondary)]">Active Team</p>
					<p class="text-lg font-semibold text-[var(--text-primary)] truncate">{teamName}</p>
				</div>
				{#if deleteConfirm}
					<div class="flex items-center gap-1.5 bg-[var(--bg-base)] rounded-lg px-2.5 py-1.5 border border-[var(--border)] shadow-md">
						<span class="text-xs text-[var(--text-secondary)]">Are you sure?</span>
						<button
							onclick={deleteTeam}
							disabled={deletingTeam}
							class="px-2.5 py-1 text-xs font-medium rounded-md bg-[var(--error)] text-white hover:opacity-90 transition-opacity disabled:opacity-50"
						>
							{deletingTeam ? '...' : 'Yes'}
						</button>
						<button
							onclick={() => (deleteConfirm = false)}
							class="px-2.5 py-1 text-xs font-medium rounded-md border border-[var(--border)] text-[var(--text-muted)] hover:text-[var(--text-primary)] transition-colors"
						>
							No
						</button>
					</div>
				{:else}
					<button
						onclick={() => (deleteConfirm = true)}
						aria-label="Delete team"
						class="shrink-0 flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-[var(--radius)] border border-[var(--error)]/30 text-[var(--error)] hover:bg-[var(--error-subtle)] transition-colors"
					>
						<Trash2 size={12} />
						Delete Team
					</button>
				{/if}
			</div>
		{:else}
			<!-- No team — prompt to create -->
			<p class="text-xs text-[var(--text-muted)]">No team configured. Use "+ New Team" above to get started.</p>
		{/if}
	</div>

	<!-- ── 3. Stats Row ──────────────────────────────────────────────────── -->
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
				<p class="text-lg font-semibold text-[var(--text-primary)]">{memberCount}</p>
				<p class="text-[11px] text-[var(--text-muted)]">Members</p>
			</div>
			<div class="rounded-[var(--radius-lg)] border border-[var(--border)] bg-[var(--bg-subtle)] p-4 text-center">
				<FolderGit2 size={16} class="mx-auto text-[var(--text-muted)] mb-1.5" />
				<p class="text-lg font-semibold text-[var(--text-primary)]">{projectCount}</p>
				<p class="text-[11px] text-[var(--text-muted)]">Projects</p>
			</div>
			<div class="rounded-[var(--radius-lg)] border border-[var(--border)] bg-[var(--bg-subtle)] p-4 text-center">
				<ArrowDown size={16} class="mx-auto text-[var(--info)] mb-1.5" />
				<p class="text-lg font-semibold text-[var(--text-primary)]">{formatBytes(syncedInBytes)}</p>
				<p class="text-[11px] text-[var(--text-muted)]">Synced In</p>
			</div>
			<div class="rounded-[var(--radius-lg)] border border-[var(--border)] bg-[var(--bg-subtle)] p-4 text-center">
				<ArrowUp size={16} class="mx-auto text-[var(--accent)] mb-1.5" />
				<p class="text-lg font-semibold text-[var(--text-primary)]">{formatBytes(syncedOutBytes)}</p>
				<p class="text-[11px] text-[var(--text-muted)]">Synced Out</p>
			</div>
		</div>
	{/if}

	<!-- ── 4. Getting Started (guided empty state) ─────────────────────── -->
	{#if showGettingStarted}
		<div class="rounded-[var(--radius-lg)] border border-dashed border-[var(--accent)]/30 bg-[var(--accent)]/5 p-5 space-y-3">
			<div class="flex items-center gap-2">
				<Sparkles size={14} class="text-[var(--accent)]" />
				<h3 class="text-sm font-semibold text-[var(--text-primary)]">Getting Started</h3>
			</div>
			<p class="text-xs text-[var(--text-secondary)]">
				Your team is set up. Complete these steps to start syncing:
			</p>
			<ol class="space-y-2 ml-1">
				<li class="flex items-start gap-2.5">
					<span class="shrink-0 w-5 h-5 rounded-full bg-[var(--accent)]/10 text-[var(--accent)] text-xs font-semibold flex items-center justify-center mt-0.5">1</span>
					<div>
						<p class="text-sm font-medium text-[var(--text-primary)]">Add a teammate</p>
						<p class="text-xs text-[var(--text-muted)]">Go to Members tab</p>
					</div>
				</li>
				<li class="flex items-start gap-2.5">
					<span class="shrink-0 w-5 h-5 rounded-full bg-[var(--accent)]/10 text-[var(--accent)] text-xs font-semibold flex items-center justify-center mt-0.5">2</span>
					<div>
						<p class="text-sm font-medium text-[var(--text-primary)]">Enable project sync</p>
						<p class="text-xs text-[var(--text-muted)]">Go to Projects tab</p>
					</div>
				</li>
			</ol>
		</div>
	{/if}

	<!-- ── 5. Machine Details Card ───────────────────────────────────────── -->
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

		{#if detect?.device_id}
			<div class="flex items-center justify-between gap-2">
				<span class="text-xs font-medium text-[var(--text-secondary)]">Sync ID</span>
				<div class="flex items-center gap-1.5">
					<code class="text-xs font-mono text-[var(--text-muted)] truncate max-w-[280px]">
						{detect.device_id}
					</code>
					<button
						onclick={copyDeviceId}
						aria-label="Copy sync ID"
						class="shrink-0 p-1 rounded text-[var(--text-muted)] hover:text-[var(--text-primary)] transition-colors"
					>
						{#if copiedDeviceId}
							<CheckCircle2 size={12} class="text-[var(--success)]" />
						{:else}
							<Copy size={12} />
						{/if}
					</button>
				</div>
			</div>
		{/if}

		{#if detect?.version}
			<div class="flex items-center justify-between">
				<span class="text-xs font-medium text-[var(--text-secondary)]">Syncthing Version</span>
				<span class="text-xs text-[var(--text-muted)]">v{detect.version}</span>
			</div>
		{/if}

		{#if !status?.user_id && !status?.machine_id && !detect?.device_id}
			<p class="text-xs text-[var(--text-muted)]">No machine details available.</p>
		{/if}
	</div>

	<!-- ── 6. Pending Actions ────────────────────────────────────────────── -->
	<div class="rounded-[var(--radius-lg)] border border-[var(--border)] bg-[var(--bg-subtle)]">
		<!-- Header -->
		<div class="flex items-center justify-between px-5 py-3.5 border-b border-[var(--border-subtle)]">
			<div class="flex items-center gap-2">
				<Bell size={14} class="text-[var(--text-muted)]" />
				<h3 class="text-sm font-semibold text-[var(--text-primary)]">Pending Actions</h3>
				{#if !pendingLoading && pendingFolders.length > 0}
					<span class="px-1.5 py-0.5 text-[10px] font-medium rounded bg-[var(--warning)]/15 text-[var(--warning)] border border-[var(--warning)]/25">
						{pendingFolders.length}
					</span>
				{/if}
			</div>
			{#if !pendingLoading && pendingFolders.length > 0}
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
			{/if}
		</div>

		<!-- Body -->
		{#if pendingLoading}
			<div class="px-5 py-4 space-y-2">
				{#each [1, 2] as i (i)}
					<div class="h-10 rounded-[var(--radius)] bg-[var(--bg-muted)] animate-pulse" aria-hidden="true"></div>
				{/each}
			</div>
		{:else if pendingError}
			<div
				class="flex items-center gap-3 m-5 p-3 rounded-[var(--radius)] border border-[var(--error)]/20 bg-[var(--error-subtle)] text-xs text-[var(--error)]"
			>
				<XCircle size={13} class="shrink-0" />
				<span class="flex-1">{pendingError}</span>
				<button onclick={loadPending} class="underline hover:no-underline font-medium">Retry</button>
			</div>
		{:else if pendingFolders.length === 0}
			<div class="py-10 flex flex-col items-center gap-2.5 text-center">
				<CheckCircle2 size={24} class="text-[var(--success)] opacity-60" />
				<p class="text-sm text-[var(--text-muted)]">No pending actions</p>
			</div>
		{:else}
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
		{/if}
	</div>

</div>

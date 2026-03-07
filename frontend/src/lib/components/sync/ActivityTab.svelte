<script lang="ts">
	import { onMount, onDestroy } from 'svelte';
	import { Activity, ArrowUp, ArrowDown, FolderSync, HardDrive, RefreshCw, ChevronDown, ChevronRight, Users, UserPlus, UserMinus, FolderPlus, FolderMinus, Play, Square, Package, Download } from 'lucide-svelte';
	import { API_BASE } from '$lib/config';
	import { getProjectNameFromEncoded, formatBytes, formatBytesRate, formatRelativeTime } from '$lib/utils';
	import { getSyncActions, type SyncAction } from '$lib/stores/syncActions.svelte';
	import type { SyncEvent } from '$lib/api-types';

	let { active = false }: { active?: boolean } = $props();

	const POLL_INTERVAL = 5000;

	interface ActivityResponse {
		events: SyncEvent[];
		upload_rate: number;
		download_rate: number;
		upload_total: number;
		download_total: number;
	}

	let events = $state<SyncEvent[]>([]);
	let uploadRate = $state(0);
	let downloadRate = $state(0);
	let loading = $state(true);
	let error = $state<string | null>(null);
	let pollTimer: ReturnType<typeof setInterval> | null = null;

	interface FolderStats {
		id: string;
		displayName: string;
		type: string;
		state: string;
		globalFiles: number;
		globalBytes: number;
		localFiles: number;
		localBytes: number;
		needFiles: number;
		needBytes: number;
		inSyncBytes: number;
		completion: number;
	}

	let folderStats = $state<FolderStats[]>([]);
	let showFolderDetails = $state(false);

	async function loadFolderStats() {
		try {
			const res = await fetch(`${API_BASE}/sync/projects`).catch(() => null);
			if (res?.ok) {
				const data = await res.json();
				const stats: FolderStats[] = [];
				for (const f of data.folders ?? []) {
					if (!f.id) continue;
					let displayName = f.label || '';
					if (!displayName) {
						const pathStr = (f.path as string) || '';
						const userMatch = pathStr.match(/remote-sessions\/([^/]+)\//);
						const segments = pathStr.split('/');
						const encoded = segments[segments.length - 1] || '';
						const projectName = encoded.startsWith('-')
							? getProjectNameFromEncoded(encoded)
							: encoded;
						const user = userMatch?.[1] ?? '';
						displayName = user ? `${projectName} (${user})` : projectName;
					}
					const globalBytes = (f.globalBytes as number) ?? 0;
					const localBytes = (f.localBytes as number) ?? 0;
					stats.push({
						id: f.id,
						displayName,
						type: (f.type as string) ?? 'sendreceive',
						state: (f.state as string) ?? 'unknown',
						globalFiles: (f.globalFiles as number) ?? 0,
						globalBytes,
						localFiles: (f.localFiles as number) ?? 0,
						localBytes,
						needFiles: (f.needFiles as number) ?? 0,
						needBytes: (f.needBytes as number) ?? 0,
						inSyncBytes: (f.inSyncBytes as number) ?? 0,
						completion: globalBytes > 0 ? Math.round((localBytes / globalBytes) * 100) : 100
					});
				}
				folderStats = stats;
			}
		} catch {
			// Non-critical
		}
	}

	function formatEventType(event: SyncEvent): { title: string; detail: string; dotColor: string; icon: typeof Activity } {
		const team = event.team_name ?? '';
		const member = event.member_name ?? '';
		const project = event.project_encoded_name
			? getProjectNameFromEncoded(event.project_encoded_name)
			: '';

		switch (event.event_type) {
			case 'team_created':
				return {
					title: `Team "${team}" created`,
					detail: '',
					dotColor: 'bg-[var(--success)]',
					icon: Users
				};
			case 'team_deleted':
				return {
					title: `Team "${team}" deleted`,
					detail: '',
					dotColor: 'bg-[var(--error)]',
					icon: Users
				};
			case 'member_added':
				return {
					title: `${member || 'Member'} joined`,
					detail: team ? `Team: ${team}` : '',
					dotColor: 'bg-[var(--success)]',
					icon: UserPlus
				};
			case 'member_removed':
				return {
					title: `${member || 'Member'} removed`,
					detail: team ? `Team: ${team}` : '',
					dotColor: 'bg-[var(--text-muted)]',
					icon: UserMinus
				};
			case 'project_added':
				return {
					title: `Project "${project}" added`,
					detail: team ? `Team: ${team}` : '',
					dotColor: 'bg-[var(--success)]',
					icon: FolderPlus
				};
			case 'project_removed':
				return {
					title: `Project "${project}" removed`,
					detail: team ? `Team: ${team}` : '',
					dotColor: 'bg-[var(--text-muted)]',
					icon: FolderMinus
				};
			case 'watcher_started':
				return {
					title: 'Watcher started',
					detail: team ? `Team: ${team}` : '',
					dotColor: 'bg-[var(--success)]',
					icon: Play
				};
			case 'watcher_stopped':
				return {
					title: 'Watcher stopped',
					detail: team ? `Team: ${team}` : '',
					dotColor: 'bg-[var(--text-muted)]',
					icon: Square
				};
			case 'session_packaged':
				return {
					title: 'Session packaged',
					detail: project ? `${project}${team ? ` (${team})` : ''}` : '',
					dotColor: 'bg-[var(--accent)]',
					icon: Package
				};
			case 'session_received':
				return {
					title: `Session received${member ? ` from ${member}` : ''}`,
					detail: project || '',
					dotColor: 'bg-[var(--info)]',
					icon: Download
				};
			case 'pending_accepted':
				return {
					title: 'Pending folder accepted',
					detail: member ? `From: ${member}` : '',
					dotColor: 'bg-[var(--success)]',
					icon: FolderSync
				};
			default:
				return {
					title: event.event_type.replace(/_/g, ' '),
					detail: team || project || '',
					dotColor: 'bg-[var(--text-muted)]',
					icon: Activity
				};
		}
	}

	async function fetchActivity() {
		try {
			const res = await fetch(`${API_BASE}/sync/activity?limit=50`);
			if (res.ok) {
				const data: ActivityResponse = await res.json();
				events = data.events ?? [];
				uploadRate = data.upload_rate ?? 0;
				downloadRate = data.download_rate ?? 0;
				error = null;
			} else if (loading) {
				error = `Failed to load activity (${res.status})`;
			}
		} catch (e) {
			if (loading) {
				error = e instanceof Error ? e.message : 'Failed to load activity';
			}
		} finally {
			loading = false;
		}
	}

	let rescanning = $state(false);

	async function handleRescanAll() {
		rescanning = true;
		try {
			await fetch(`${API_BASE}/sync/rescan`, { method: 'POST' });
			await fetchActivity();
			await loadFolderStats();
		} finally {
			rescanning = false;
		}
	}

	// Reload when tab becomes active
	$effect(() => {
		if (active) {
			loadFolderStats();
			fetchActivity();
		}
	});

	onMount(() => {
		pollTimer = setInterval(fetchActivity, POLL_INTERVAL);
	});

	onDestroy(() => {
		if (pollTimer) clearInterval(pollTimer);
	});
</script>

<div class="space-y-4 p-4">
	<!-- Sync Now header -->
	<div class="flex items-center justify-between">
		<h2 class="text-sm font-semibold text-[var(--text-primary)]">Activity</h2>
		<button
			class="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-md bg-[var(--accent)] text-white hover:opacity-90 transition-opacity disabled:opacity-50 disabled:cursor-not-allowed"
			onclick={handleRescanAll}
			disabled={rescanning}
			aria-label="Rescan all folders"
		>
			<RefreshCw size={12} class={rescanning ? 'animate-spin' : ''} />
			{rescanning ? 'Scanning...' : 'Sync Now'}
		</button>
	</div>

	<!-- Compact bandwidth status bar -->
	<div class="flex items-center justify-between px-4 py-3 rounded-lg border border-[var(--border)] bg-[var(--bg-subtle)]">
		<span class="text-xs font-medium text-[var(--text-secondary)]">Transfer Rate</span>
		<div class="flex items-center gap-4 text-xs font-mono text-[var(--text-secondary)]">
			<span class="flex items-center gap-1">
				<ArrowUp size={11} class="text-[var(--accent)]" />
				{formatBytesRate(uploadRate)}
			</span>
			<span class="flex items-center gap-1">
				<ArrowDown size={11} class="text-[var(--info)]" />
				{formatBytesRate(downloadRate)}
			</span>
		</div>
	</div>

	<!-- User actions -->
	{#if getSyncActions().length > 0}
		<div class="rounded-lg border border-[var(--border)] bg-[var(--bg-subtle)]">
			<div class="px-4 py-3 border-b border-[var(--border-subtle)]">
				<h3 class="text-sm font-medium text-[var(--text-primary)]">Your Actions</h3>
			</div>
			<div class="px-4 divide-y divide-[var(--border-subtle)]">
				{#each [...getSyncActions()].reverse() as action (action.id)}
					<div class="flex gap-3 py-3">
						<span class="w-2 h-2 rounded-full mt-1.5 shrink-0 bg-[var(--accent)]"></span>
						<div class="flex-1 min-w-0">
							<div class="flex items-center justify-between">
								<span class="text-sm font-medium text-[var(--text-primary)]">{action.title}</span>
								<span class="text-xs text-[var(--text-muted)] shrink-0 ml-2">{formatRelativeTime(action.time)}</span>
							</div>
							{#if action.detail}
								<p class="text-xs text-[var(--text-secondary)] mt-0.5 truncate">{action.detail}</p>
							{/if}
						</div>
					</div>
				{/each}
			</div>
		</div>
	{/if}

	<!-- Event log (sync_events from SQLite) -->
	<div class="rounded-lg border border-[var(--border)] bg-[var(--bg-subtle)]">
		<div class="px-4 py-3 border-b border-[var(--border-subtle)]">
			<h3 class="text-sm font-medium text-[var(--text-primary)]">Sync Events</h3>
		</div>

		{#if loading}
			<div class="px-4 py-8 text-center text-sm text-[var(--text-muted)]">
				Loading activity...
			</div>
		{:else if error}
			<div class="px-4 py-8 text-center text-sm text-[var(--error)]">
				{error}
			</div>
		{:else if events.length === 0}
			<div class="px-4 py-12 flex flex-col items-center gap-3 text-[var(--text-muted)]">
				<Activity size={32} class="opacity-40" />
				<span class="text-sm">No activity yet</span>
				<span class="text-xs">Events will appear as you create teams, add members, and sync sessions</span>
			</div>
		{:else}
			<div class="px-4 divide-y divide-[var(--border-subtle)]">
				{#each events as event (event.id)}
					{@const fmt = formatEventType(event)}
					<div class="flex gap-3 py-3">
						<span class="w-2 h-2 rounded-full mt-1.5 shrink-0 {fmt.dotColor}"></span>
						<div class="flex-1 min-w-0">
							<div class="flex items-center justify-between">
								<span class="text-sm font-medium text-[var(--text-primary)]">{fmt.title}</span>
								<span class="text-xs text-[var(--text-muted)] shrink-0 ml-2">{formatRelativeTime(event.created_at)}</span>
							</div>
							{#if fmt.detail}
								<p class="text-xs text-[var(--text-secondary)] mt-0.5 truncate">{fmt.detail}</p>
							{/if}
						</div>
					</div>
				{/each}
			</div>
		{/if}
	</div>

	<!-- Folder Details (collapsible) -->
	{#if folderStats.length > 0}
		<div class="rounded-lg border border-[var(--border)] bg-[var(--bg-subtle)]">
			<button
				onclick={() => (showFolderDetails = !showFolderDetails)}
				class="w-full flex items-center justify-between px-4 py-3 text-left hover:bg-[var(--bg-muted)] transition-colors"
			>
				<h3 class="text-sm font-medium text-[var(--text-primary)]">Folder Details</h3>
				<div class="flex items-center gap-2">
					<span class="text-xs text-[var(--text-muted)]">{folderStats.length} folders</span>
					{#if showFolderDetails}
						<ChevronDown size={14} class="text-[var(--text-muted)]" />
					{:else}
						<ChevronRight size={14} class="text-[var(--text-muted)]" />
					{/if}
				</div>
			</button>
			{#if showFolderDetails}
				<div class="px-4 border-t border-[var(--border-subtle)] divide-y divide-[var(--border-subtle)]">
					{#each folderStats as folder (folder.id)}
						<div class="flex items-center gap-3 py-3">
							<FolderSync size={16} class="shrink-0 text-[var(--text-muted)]" />
							<div class="flex-1 min-w-0">
								<div class="flex items-center gap-2">
									<span class="text-sm font-medium text-[var(--text-primary)] truncate">{folder.displayName}</span>
									<span class="shrink-0 px-1.5 py-0.5 text-[10px] font-medium rounded {folder.state === 'idle' ? 'bg-[var(--success)]/10 text-[var(--success)]' : folder.state === 'syncing' ? 'bg-[var(--info)]/10 text-[var(--info)]' : 'bg-[var(--bg-muted)] text-[var(--text-muted)]'}">
											{folder.state === 'idle' ? 'Up to date' : folder.state}
									</span>
								</div>
								<div class="flex items-center gap-4 mt-1 text-xs text-[var(--text-muted)]">
									<span>
										<HardDrive size={10} class="inline -mt-0.5 mr-0.5" />
										{formatBytes(folder.globalBytes)}
									</span>
									<span>{folder.globalFiles.toLocaleString()} files</span>
									{#if folder.needBytes > 0}
										<span class="text-[var(--info)]">
											{formatBytes(folder.needBytes)} pending
										</span>
									{/if}
									<span class="font-mono">{folder.completion}%</span>
								</div>
							</div>
						</div>
					{/each}
				</div>
			{/if}
		</div>
	{/if}
</div>

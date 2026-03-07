<script lang="ts">
	import { onMount, onDestroy } from 'svelte';
	import { Activity, ArrowUp, ArrowDown, FolderSync, HardDrive, RefreshCw, ChevronDown, ChevronRight } from 'lucide-svelte';
	import { API_BASE } from '$lib/config';
	import { getProjectNameFromEncoded, formatBytes, formatBytesRate, formatRelativeTime } from '$lib/utils';
	import { getSyncActions, type SyncAction } from '$lib/stores/syncActions.svelte';

	let { active = false }: { active?: boolean } = $props();

	const POLL_INTERVAL = 3000;

	interface SyncEvent {
		id: number;
		type: string;
		time: string;
		data?: Record<string, unknown>;
	}

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
	let lastEventId = 0;

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

	// Lookup maps for resolving raw Syncthing IDs to human-readable names
	let deviceNameMap = $state<Map<string, string>>(new Map());
	let folderNameMap = $state<Map<string, string>>(new Map());
	let folderStats = $state<FolderStats[]>([]);
	let showFolderDetails = $state(false);

	function resolveDeviceName(deviceId: string): string {
		if (!deviceId) return '';
		const name = deviceNameMap.get(deviceId);
		if (name) return name;
		return deviceId.slice(0, 7);
	}

	function resolveFolderName(folderId: string): string {
		if (!folderId) return '';
		const name = folderNameMap.get(folderId);
		if (name) return name;
		return folderId;
	}

	async function loadLookupMaps() {
		try {
			const [devicesRes, foldersRes] = await Promise.all([
				fetch(`${API_BASE}/sync/devices`).catch(() => null),
				fetch(`${API_BASE}/sync/projects`).catch(() => null)
			]);
			if (devicesRes?.ok) {
				const data = await devicesRes.json();
				const map = new Map<string, string>();
				for (const d of data.devices ?? []) {
					if (d.device_id && d.name) map.set(d.device_id, d.name);
				}
				deviceNameMap = map;
			}
			if (foldersRes?.ok) {
				const data = await foldersRes.json();
				const nameMap = new Map<string, string>();
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
					nameMap.set(f.id, displayName);
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
				folderNameMap = nameMap;
				folderStats = stats;
			}
		} catch {
			// Non-critical — events still show raw IDs
		}
	}

	function formatEvent(event: SyncEvent): { title: string; detail: string; dotColor: string } {
		const folder = (event.data?.folder as string) || '';
		const device = (event.data?.device as string) || (event.data?.id as string) || '';
		const folderName = resolveFolderName(folder);
		const deviceName = resolveDeviceName(device);

		switch (event.type) {
			case 'ItemFinished': {
				const item = (event.data?.item as string) || '';
				const isSession = item.endsWith('.jsonl');
				const isManifest = item === 'manifest.json';
				if (isSession) {
					return {
						title: 'Session synced',
						detail: `${folderName} — ${item.replace('.jsonl', '').slice(0, 8)}...`,
						dotColor: 'bg-[var(--success)]'
					};
				}
				if (isManifest) {
					return {
						title: 'Sync manifest updated',
						detail: folderName,
						dotColor: 'bg-[var(--success)]'
					};
				}
				return {
					title: 'File synced',
					detail: `${folderName} — ${item}`,
					dotColor: 'bg-[var(--success)]'
				};
			}
			case 'DeviceConnected':
				return {
					title: `${deviceName || 'Teammate'} connected`,
					detail: 'Ready to sync sessions',
					dotColor: 'bg-[var(--success)]'
				};
			case 'DeviceDisconnected':
				return {
					title: `${deviceName || 'Teammate'} went offline`,
					detail: '',
					dotColor: 'bg-[var(--text-muted)]'
				};
			case 'FolderCompletion': {
				const pct = (event.data?.completion as number) ?? 0;
				if (pct >= 100) {
					return {
						title: 'All sessions up to date',
						detail: folderName,
						dotColor: 'bg-[var(--success)]'
					};
				}
				return {
					title: `Syncing sessions — ${Math.round(pct)}%`,
					detail: folderName,
					dotColor: 'bg-[var(--info)]'
				};
			}
			case 'FolderSummary':
				return {
					title: 'Scan completed',
					detail: folderName,
					dotColor: 'bg-[var(--text-muted)]'
				};
			case 'StateChanged': {
				const to = (event.data?.to as string) || '';
				if (to === 'idle') {
					return {
						title: 'Sync completed',
						detail: folderName,
						dotColor: 'bg-[var(--success)]'
					};
				}
				if (to === 'syncing') {
					return {
						title: 'Syncing sessions...',
						detail: folderName,
						dotColor: 'bg-[var(--info)]'
					};
				}
				if (to === 'scanning') {
					return {
						title: 'Scanning for changes...',
						detail: folderName,
						dotColor: 'bg-[var(--info)]'
					};
				}
				return {
					title: `State: ${to}`,
					detail: folderName,
					dotColor: 'bg-[var(--text-muted)]'
				};
			}
			case 'FolderErrors':
				return {
					title: 'Sync error',
					detail: ((event.data?.errors as Array<{ error: string }>) || [])[0]?.error || 'Unknown error',
					dotColor: 'bg-[var(--error)]'
				};
			default:
				return {
					title: event.type.replace(/([A-Z])/g, ' $1').trim(),
					detail: deviceName || folderName || '',
					dotColor: 'bg-[var(--text-muted)]'
				};
		}
	}

	async function fetchActivity() {
		try {
			const res = await fetch(`${API_BASE}/sync/activity?since=${lastEventId}&limit=50`);
			if (res.ok) {
				const data: ActivityResponse = await res.json();
				if (data.events?.length) {
					if (loading) {
						events = data.events;
					} else {
						const existingIds = new Set(events.map((e) => e.id));
						const newEvents = data.events.filter((e) => !existingIds.has(e.id));
						if (newEvents.length) {
							events = [...events, ...newEvents].slice(-100);
						}
					}
					lastEventId = Math.max(...data.events.map((e) => e.id));
				}
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
			await loadLookupMaps();
		} finally {
			rescanning = false;
		}
	}

	// Reload when tab becomes active
	$effect(() => {
		if (active) {
			loadLookupMaps();
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

	<!-- Event log (session-meaningful) -->
	<div class="rounded-lg border border-[var(--border)] bg-[var(--bg-subtle)]">
		<div class="px-4 py-3 border-b border-[var(--border-subtle)]">
			<h3 class="text-sm font-medium text-[var(--text-primary)]">Session Activity</h3>
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
			</div>
		{:else}
			<div class="px-4 divide-y divide-[var(--border-subtle)]">
				{#each [...events].reverse() as event (event.id)}
					{@const fmt = formatEvent(event)}
					<div class="flex gap-3 py-3">
						<span class="w-2 h-2 rounded-full mt-1.5 shrink-0 {fmt.dotColor}"></span>
						<div class="flex-1 min-w-0">
							<div class="flex items-center justify-between">
								<span class="text-sm font-medium text-[var(--text-primary)]">{fmt.title}</span>
								<span class="text-xs text-[var(--text-muted)] shrink-0 ml-2">{formatRelativeTime(event.time)}</span>
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

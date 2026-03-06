<script lang="ts">
	import { onMount, onDestroy } from 'svelte';
	import { Activity, ArrowUp, ArrowDown } from 'lucide-svelte';
	import BandwidthChart from './BandwidthChart.svelte';
	import { API_BASE } from '$lib/config';
	import { getProjectNameFromEncoded } from '$lib/utils';

	const MAX_HISTORY = 30;
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
	let uploadTotal = $state(0);
	let downloadTotal = $state(0);
	let uploadHistory = $state<number[]>([]);
	let downloadHistory = $state<number[]>([]);
	let labels = $state<string[]>([]);
	let loading = $state(true);
	let error = $state<string | null>(null);
	let pollTimer: ReturnType<typeof setInterval> | null = null;
	let lastEventId = 0;

	// Lookup maps for resolving raw Syncthing IDs to human-readable names
	let deviceNameMap = $state<Map<string, string>>(new Map());
	let folderNameMap = $state<Map<string, string>>(new Map());

	function formatBytes(value: number): string {
		if (value >= 1_000_000) return `${(value / 1_000_000).toFixed(1)} MB/s`;
		if (value >= 1_000) return `${(value / 1_000).toFixed(1)} KB/s`;
		return `${value.toFixed(0)} B/s`;
	}

	function formatBytesTotal(value: number): string {
		if (value >= 1_000_000_000) return `${(value / 1_000_000_000).toFixed(1)} GB`;
		if (value >= 1_000_000) return `${(value / 1_000_000).toFixed(1)} MB`;
		if (value >= 1_000) return `${(value / 1_000).toFixed(1)} KB`;
		return `${value} B`;
	}

	function timeLabel(): string {
		const d = new Date();
		return `${d.getHours().toString().padStart(2, '0')}:${d.getMinutes().toString().padStart(2, '0')}:${d.getSeconds().toString().padStart(2, '0')}`;
	}

	function pushHistory(upRate: number, downRate: number) {
		uploadHistory = [...uploadHistory.slice(-(MAX_HISTORY - 1)), upRate];
		downloadHistory = [...downloadHistory.slice(-(MAX_HISTORY - 1)), downRate];
		labels = [...labels.slice(-(MAX_HISTORY - 1)), timeLabel()];
	}

	function resolveDeviceName(deviceId: string): string {
		if (!deviceId) return '';
		const name = deviceNameMap.get(deviceId);
		if (name) return name;
		// Show short ID as fallback
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
				const map = new Map<string, string>();
				for (const f of data.folders ?? []) {
					if (!f.id) continue;
					if (f.label) {
						map.set(f.id, f.label);
						continue;
					}
					// Path: .../remote-sessions/{user}/{encoded_project_path}
					const pathStr = (f.path as string) || '';
					const userMatch = pathStr.match(/remote-sessions\/([^/]+)\//);
					const segments = pathStr.split('/');
					const encoded = segments[segments.length - 1] || '';
					// Reuse existing utility to decode encoded path → readable name
					const projectName = encoded.startsWith('-')
						? getProjectNameFromEncoded(encoded)
						: encoded;
					const user = userMatch?.[1] ?? '';
					map.set(f.id, user ? `${projectName} (${user})` : projectName);
				}
				folderNameMap = map;
			}
		} catch {
			// Non-critical — events still show raw IDs
		}
	}

	function formatRelativeTime(isoString: string): string {
		const date = new Date(isoString);
		const now = Date.now();
		const diffMs = now - date.getTime();
		const diffSec = Math.floor(diffMs / 1000);
		const diffMin = Math.floor(diffSec / 60);
		const diffHr = Math.floor(diffMin / 60);

		if (diffHr >= 24) {
			return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' });
		}
		if (diffHr >= 1) return `${diffHr}h ago`;
		if (diffMin >= 1) return `${diffMin}m ago`;
		if (diffSec >= 5) return `${diffSec}s ago`;
		return 'just now';
	}

	function formatEvent(event: SyncEvent): { title: string; detail: string; dotColor: string } {
		const folder = (event.data?.folder as string) || '';
		const device = (event.data?.device as string) || (event.data?.id as string) || '';

		switch (event.type) {
			case 'ItemFinished':
				return {
					title: 'Transfer complete',
					detail: (event.data?.item as string) || '',
					dotColor: 'bg-[var(--success)]'
				};
			case 'DownloadProgress':
				return {
					title: 'Transfer started',
					detail: (event.data?.item as string) || '',
					dotColor: 'bg-[var(--info)]'
				};
			case 'DeviceConnected':
				return {
					title: 'Device connected',
					detail: resolveDeviceName(device),
					dotColor: 'bg-[var(--success)]'
				};
			case 'DeviceDisconnected':
				return {
					title: 'Device disconnected',
					detail: resolveDeviceName(device),
					dotColor: 'bg-[var(--text-muted)]'
				};
			case 'FolderSummary':
				return {
					title: 'Scan completed',
					detail: resolveFolderName(folder),
					dotColor: 'bg-[var(--text-muted)]'
				};
			case 'FolderCompletion':
				return {
					title: 'Folder synced',
					detail: `${resolveFolderName(folder)} — ${(event.data?.completion as number) ?? 0}%`,
					dotColor: 'bg-[var(--success)]'
				};
			case 'FolderErrors':
				return {
					title: 'Error',
					detail: ((event.data?.errors as Array<{ error: string }>) || [])[0]?.error || 'Folder error',
					dotColor: 'bg-[var(--error)]'
				};
			case 'StateChanged':
				return {
					title: 'State changed',
					detail: `${resolveFolderName(folder)}: ${(event.data?.from as string) || ''} → ${(event.data?.to as string) || ''}`,
					dotColor: 'bg-[var(--info)]'
				};
			case 'ClusterConfigReceived':
				return {
					title: 'Cluster config received',
					detail: resolveDeviceName(device),
					dotColor: 'bg-[var(--info)]'
				};
			default:
				return {
					title: event.type,
					detail: '',
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
					// On first load replace; on poll, append new events
					if (loading) {
						events = data.events;
					} else {
						// Merge new events (higher IDs) at the end
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
				uploadTotal = data.upload_total ?? 0;
				downloadTotal = data.download_total ?? 0;
				pushHistory(uploadRate, downloadRate);
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

	onMount(() => {
		loadLookupMaps();
		fetchActivity();
		pollTimer = setInterval(fetchActivity, POLL_INTERVAL);
	});

	onDestroy(() => {
		if (pollTimer) clearInterval(pollTimer);
	});
</script>

<div class="space-y-4 p-4">
	<!-- Bandwidth section -->
	<div class="rounded-lg border border-[var(--border)] bg-[var(--bg-subtle)] p-4">
		<div class="flex items-center justify-between mb-3">
			<h3 class="text-sm font-medium text-[var(--text-primary)]">Bandwidth</h3>
			<div class="flex items-center gap-4 text-xs text-[var(--text-secondary)] font-mono">
				<span class="flex items-center gap-1">
					<ArrowUp size={11} class="text-[var(--accent)]" />
					{formatBytes(uploadRate)}
				</span>
				<span class="flex items-center gap-1">
					<ArrowDown size={11} class="text-[var(--info)]" />
					{formatBytes(downloadRate)}
				</span>
			</div>
		</div>
		<BandwidthChart
			uploadData={uploadHistory}
			downloadData={downloadHistory}
			{labels}
		/>
		<div class="flex items-center gap-6 mt-3 pt-3 border-t border-[var(--border-subtle)] text-xs text-[var(--text-muted)]">
			<span>Total up: <span class="font-mono text-[var(--text-secondary)]">{formatBytesTotal(uploadTotal)}</span></span>
			<span>Total down: <span class="font-mono text-[var(--text-secondary)]">{formatBytesTotal(downloadTotal)}</span></span>
		</div>
	</div>

	<!-- Event log -->
	<div class="rounded-lg border border-[var(--border)] bg-[var(--bg-subtle)]">
		<div class="px-4 py-3 border-b border-[var(--border-subtle)]">
			<h3 class="text-sm font-medium text-[var(--text-primary)]">Event Log</h3>
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
</div>

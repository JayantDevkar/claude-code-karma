<script lang="ts">
	import { onMount } from 'svelte';
	import { Activity, ArrowUp, ArrowDown } from 'lucide-svelte';
	import BandwidthChart from './BandwidthChart.svelte';
	import { API_BASE } from '$lib/config';

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
		upload_history: number[];
		download_history: number[];
		labels: string[];
	}

	let events = $state<SyncEvent[]>([]);
	let uploadRate = $state(0);
	let downloadRate = $state(0);
	let uploadHistory = $state<number[]>([]);
	let downloadHistory = $state<number[]>([]);
	let labels = $state<string[]>([]);
	let loading = $state(true);
	let error = $state<string | null>(null);

	function formatBytes(value: number): string {
		if (value >= 1_000_000) return `${(value / 1_000_000).toFixed(1)} MB/s`;
		if (value >= 1_000) return `${(value / 1_000).toFixed(1)} KB/s`;
		return `${value.toFixed(0)} B/s`;
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
					detail: ((event.data?.id as string) || '').slice(0, 20),
					dotColor: 'bg-[var(--success)]'
				};
			case 'DeviceDisconnected':
				return {
					title: 'Device disconnected',
					detail: ((event.data?.id as string) || '').slice(0, 20),
					dotColor: 'bg-[var(--text-muted)]'
				};
			case 'FolderSummary':
				return {
					title: 'Scan completed',
					detail: 'Folder status updated',
					dotColor: 'bg-[var(--text-muted)]'
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
					detail: `${(event.data?.from as string) || ''} \u2192 ${(event.data?.to as string) || ''}`,
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

	onMount(async () => {
		try {
			const res = await fetch(`${API_BASE}/sync/activity`);
			if (res.ok) {
				const data: ActivityResponse = await res.json();
				events = data.events ?? [];
				uploadRate = data.upload_rate ?? 0;
				downloadRate = data.download_rate ?? 0;
				uploadHistory = data.upload_history ?? [];
				downloadHistory = data.download_history ?? [];
				labels = data.labels ?? [];
			} else {
				error = `Failed to load activity (${res.status})`;
			}
		} catch (e) {
			error = e instanceof Error ? e.message : 'Failed to load activity';
		} finally {
			loading = false;
		}
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
				{#each events as event (event.id)}
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

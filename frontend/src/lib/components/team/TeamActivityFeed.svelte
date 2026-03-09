<script lang="ts">
	import { AlertTriangle, Circle } from 'lucide-svelte';
	import type { SyncEvent } from '$lib/api-types';
	import { formatRelativeTime } from '$lib/utils';
	import { formatSyncEvent, syncEventColor, isSyncEventWarning } from '$lib/utils/sync-events';
	import { API_BASE } from '$lib/config';

	let { events: initialEvents = [], teamName = '' }: { events: SyncEvent[]; teamName: string } =
		$props();

	let events = $state(initialEvents);
	let loading = $state(false);
	let offset = $state(initialEvents.length);
	let hasMore = $state(initialEvents.length >= 20);
	let filterType = $state<string>('');


	async function loadMore() {
		loading = true;
		try {
			const params = new URLSearchParams({
				limit: '20',
				offset: String(offset)
			});
			if (filterType) params.set('event_type', filterType);

			const res = await fetch(
				`${API_BASE}/sync/teams/${encodeURIComponent(teamName)}/activity?${params}`
			);
			if (res.ok) {
				const data = await res.json();
				const newEvents: SyncEvent[] = data.events || [];
				events = [...events, ...newEvents];
				offset += newEvents.length;
				hasMore = newEvents.length >= 20;
			}
		} finally {
			loading = false;
		}
	}

	async function applyFilter() {
		offset = 0;
		loading = true;
		try {
			const params = new URLSearchParams({ limit: '20' });
			if (filterType) params.set('event_type', filterType);

			const res = await fetch(
				`${API_BASE}/sync/teams/${encodeURIComponent(teamName)}/activity?${params}`
			);
			if (res.ok) {
				const data = await res.json();
				events = data.events || [];
				offset = events.length;
				hasMore = events.length >= 20;
			}
		} finally {
			loading = false;
		}
	}
</script>

<section class="space-y-3">
	<div class="flex items-center justify-between">
		<h3 class="text-sm font-medium text-[var(--text-secondary)]">Activity</h3>
		<select
			class="rounded-md border border-[var(--border)] bg-[var(--bg-subtle)] px-2 py-1 text-xs text-[var(--text-secondary)]"
			bind:value={filterType}
			onchange={applyFilter}
		>
			<option value="">All events</option>
			<option value="member_joined">Joins</option>
			<option value="project_shared">Shares</option>
			<option value="session_packaged">Sessions</option>
			<option value="file_rejected">Rejections</option>
			<option value="settings_changed">Settings</option>
		</select>
	</div>

	{#if events.length === 0}
		<p class="py-4 text-center text-sm text-[var(--text-muted)]">No activity yet</p>
	{:else}
		<div class="space-y-1">
			{#each events as event (event.id)}
				<div
					class="flex items-start gap-2 rounded-md px-2 py-1.5 text-sm {isSyncEventWarning(event.event_type)
						? 'bg-amber-500/5'
						: ''}"
				>
					<span class="mt-0.5 {syncEventColor(event.event_type)}">
						{#if isSyncEventWarning(event.event_type)}
							<svg
								class="h-3.5 w-3.5"
								fill="none"
								viewBox="0 0 24 24"
								stroke="currentColor"
								stroke-width="2"
							>
								<path
									d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-2.5L13.732 4.5c-.77-.833-2.694-.833-3.464 0L3.34 16.5c-.77.833.192 2.5 1.732 2.5z"
								/>
							</svg>
						{:else}
							<svg
								class="h-3.5 w-3.5"
								fill="currentColor"
								viewBox="0 0 24 24"
							>
								<circle cx="12" cy="12" r="4" />
							</svg>
						{/if}
					</span>
					<span class="flex-1 text-[var(--text-secondary)]">{formatSyncEvent(event)}</span>
					<span class="shrink-0 text-xs text-[var(--text-muted)]">
						{formatRelativeTime(event.created_at)}
					</span>
				</div>
			{/each}
		</div>

		{#if hasMore}
			<button
				class="w-full rounded-md border border-[var(--border)] py-1.5 text-xs text-[var(--text-muted)] hover:text-[var(--text-secondary)]"
				onclick={loadMore}
				disabled={loading}
			>
				{loading ? 'Loading...' : 'Load More'}
			</button>
		{/if}
	{/if}
</section>

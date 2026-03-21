<script lang="ts">
	import { Loader2 } from 'lucide-svelte';
	import { isToday, isYesterday, isThisWeek, isThisMonth } from 'date-fns';
	import type { SyncEvent, MemberProfile } from '$lib/api-types';
	import {
		formatSyncEvent,
		syncEventColor,
		isSyncEventWarning,
		SYNC_EVENT_META
	} from '$lib/utils/sync-events';
	import { formatRelativeTime } from '$lib/utils';
	import { API_BASE } from '$lib/config';

	interface Props {
		profile: MemberProfile;
	}

	let { profile }: Props = $props();

	let fetchedEvents = $state<SyncEvent[] | null>(null);
	let loading = $state(false);
	let offset = $state(0);
	let hasMore = $state(false);
	let events = $derived.by(() => fetchedEvents ?? profile.activity);

	// Initialize offset/hasMore from profile
	$effect(() => {
		if (!fetchedEvents) {
			offset = profile.activity.length;
			hasMore = profile.activity.length >= 50;
		}
	});
	let filterType = $state<string>('');

	// Filter pill definitions
	const typePills = [
		{ value: '', label: 'All' },
		{ value: 'member_joined', label: 'Joins' },
		{ value: 'project_shared', label: 'Shares' },
		{ value: 'session_packaged,session_received', label: 'Sessions' },
		{ value: 'sync_now', label: 'Syncs' },
		{ value: 'file_rejected', label: 'Rejections' },
		{ value: 'settings_changed', label: 'Settings' }
	];

	// Group events by date period
	type DateGroup = { label: string; events: SyncEvent[] };

	let groupedEvents = $derived.by(() => {
		const today: SyncEvent[] = [];
		const yesterday: SyncEvent[] = [];
		const thisWeek: SyncEvent[] = [];
		const thisMonth: SyncEvent[] = [];
		const older: SyncEvent[] = [];

		for (const event of events) {
			if (!event.created_at) {
				older.push(event);
				continue;
			}
			const date = new Date(event.created_at.replace(' ', 'T'));
			if (isToday(date)) today.push(event);
			else if (isYesterday(date)) yesterday.push(event);
			else if (isThisWeek(date, { weekStartsOn: 1 })) thisWeek.push(event);
			else if (isThisMonth(date)) thisMonth.push(event);
			else older.push(event);
		}

		const groups: DateGroup[] = [];
		if (today.length > 0) groups.push({ label: 'Today', events: today });
		if (yesterday.length > 0) groups.push({ label: 'Yesterday', events: yesterday });
		if (thisWeek.length > 0) groups.push({ label: 'This Week', events: thisWeek });
		if (thisMonth.length > 0) groups.push({ label: 'This Month', events: thisMonth });
		if (older.length > 0) groups.push({ label: 'Older', events: older });
		return groups;
	});

	async function fetchEvents(append: boolean = false) {
		loading = true;
		try {
			const params = new URLSearchParams({ limit: '50' });
			if (filterType) params.set('event_type', filterType);
			if (append) params.set('offset', String(offset));

			const res = await fetch(
				`${API_BASE}/sync/members/${encodeURIComponent(profile.user_id)}/activity?${params}`
			);
			if (res.ok) {
				const data = await res.json();
				const newEvents: SyncEvent[] = data.events || [];
				if (append) {
					fetchedEvents = [...(fetchedEvents ?? profile.activity), ...newEvents];
					offset += newEvents.length;
				} else {
					fetchedEvents = newEvents;
					offset = newEvents.length;
				}
				hasMore = newEvents.length >= 50;
			}
		} finally {
			loading = false;
		}
	}

	function selectTypeFilter(type: string) {
		filterType = type;
		fetchEvents();
	}
</script>

<section class="rounded-lg border border-[var(--border)] bg-[var(--bg-subtle)]">
	<!-- Header -->
	<div class="flex items-center justify-between px-4 pt-4 pb-3">
		<h3 class="text-sm font-medium text-[var(--text-primary)]">Activity Log</h3>
		{#if loading}
			<Loader2 size={14} class="animate-spin text-[var(--text-muted)]" />
		{/if}
	</div>

	<!-- Type filter pills -->
	<div class="flex flex-wrap gap-1.5 px-4 pb-3">
		{#each typePills as pill}
			<button
				class="px-2.5 py-1 text-xs font-medium rounded-full transition-colors
					{filterType === pill.value
						? 'bg-[var(--accent)] text-white'
						: 'bg-[var(--bg-muted)] text-[var(--text-muted)] hover:text-[var(--text-secondary)] hover:bg-[var(--bg-muted)]/80'}"
				onclick={() => selectTypeFilter(pill.value)}
			>
				{pill.label}
			</button>
		{/each}
	</div>

	<!-- Event list grouped by date -->
	<div class="border-t border-[var(--border)]">
		{#if events.length === 0}
			<p class="py-8 text-center text-sm text-[var(--text-muted)]">No activity yet</p>
		{:else}
			<div class="divide-y divide-[var(--border-subtle)]">
				{#each groupedEvents as group (group.label)}
					<!-- Date group header -->
					<div class="px-4 py-2 bg-[var(--bg-muted)]/40">
						<span class="text-[11px] font-semibold uppercase tracking-wider text-[var(--text-faint)]">
							{group.label}
							<span class="font-normal ml-1">({group.events.length})</span>
						</span>
					</div>

					{#each group.events as event, i (event.created_at + '-' + i)}
						<div
							class="flex items-start gap-3 px-4 py-3 {isSyncEventWarning(event.event_type)
								? 'bg-[var(--warning)]/5'
								: 'hover:bg-[var(--bg-muted)]/50'} transition-colors"
						>
							<!-- Status dot -->
							<span class="mt-1.5 shrink-0 {syncEventColor(event.event_type)}">
								{#if isSyncEventWarning(event.event_type)}
									<svg
										class="h-3 w-3"
										fill="none"
										viewBox="0 0 24 24"
										stroke="currentColor"
										stroke-width="2.5"
									>
										<path
											d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-2.5L13.732 4.5c-.77-.833-2.694-.833-3.464 0L3.34 16.5c-.77.833.192 2.5 1.732 2.5z"
										/>
									</svg>
								{:else}
									<span class="block w-2 h-2 rounded-full bg-current"></span>
								{/if}
							</span>

							<!-- Content -->
							<div class="flex-1 min-w-0">
								<p class="text-sm text-[var(--text-primary)]">
									{formatSyncEvent(event)}
								</p>
								<div class="flex items-center gap-2 mt-1">
									<span class="text-[11px] text-[var(--text-muted)]">
										{formatRelativeTime(event.created_at)}
									</span>
									{#if event.event_type && SYNC_EVENT_META[event.event_type]}
										<span
											class="inline-flex px-1.5 py-0.5 text-[10px] font-medium rounded-full
												bg-[var(--bg-muted)] text-[var(--text-muted)]"
										>
											{event.event_type.replace(/_/g, ' ')}
										</span>
									{/if}
									{#if event.team_name}
										<span
											class="inline-flex px-1.5 py-0.5 text-[10px] font-medium rounded-full
												border border-[var(--border)] text-[var(--text-muted)]"
										>
											{event.team_name}
										</span>
									{/if}
								</div>
							</div>
						</div>
					{/each}
				{/each}
			</div>

			{#if hasMore}
				<div class="px-4 py-3 border-t border-[var(--border)]">
					<button
						class="w-full py-2 text-xs font-medium rounded-[var(--radius-md)]
							border border-[var(--border)] text-[var(--text-muted)]
							hover:text-[var(--text-secondary)] hover:bg-[var(--bg-muted)] transition-colors"
						onclick={() => fetchEvents(true)}
						disabled={loading}
					>
						{loading ? 'Loading...' : 'Load More'}
					</button>
				</div>
			{/if}
		{/if}
	</div>
</section>

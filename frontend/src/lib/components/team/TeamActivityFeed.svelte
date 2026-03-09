<script lang="ts">
	import { Loader2 } from 'lucide-svelte';
	import type { SyncEvent, SyncTeamMember } from '$lib/api-types';
	import { formatSyncEvent, syncEventColor, isSyncEventWarning, SYNC_EVENT_META } from '$lib/utils/sync-events';
	import { getTeamMemberHexColor, formatRelativeTime } from '$lib/utils';
	import { API_BASE } from '$lib/config';

	interface Props {
		events: SyncEvent[];
		teamName: string;
		members?: SyncTeamMember[];
	}

	let { events: initialEvents = [], teamName = '', members = [] }: Props = $props();

	let events = $state<SyncEvent[]>([]);
	let loading = $state(false);
	let offset = $state(0);
	let hasMore = $state(false);
	let filterType = $state<string>('');
	let filterMember = $state<string>('');

	// Initialize from props
	$effect(() => {
		events = initialEvents;
		offset = initialEvents.length;
		hasMore = initialEvents.length >= 20;
	});

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

	function buildParams(): URLSearchParams {
		const params = new URLSearchParams({ limit: '20' });
		if (filterType) params.set('event_type', filterType);
		if (filterMember) params.set('member_name', filterMember);
		return params;
	}

	async function fetchEvents(append: boolean = false) {
		loading = true;
		try {
			const params = buildParams();
			if (append) params.set('offset', String(offset));

			const res = await fetch(
				`${API_BASE}/sync/teams/${encodeURIComponent(teamName)}/activity?${params}`
			);
			if (res.ok) {
				const data = await res.json();
				const newEvents: SyncEvent[] = data.events || [];
				if (append) {
					events = [...events, ...newEvents];
					offset += newEvents.length;
				} else {
					events = newEvents;
					offset = newEvents.length;
				}
				hasMore = newEvents.length >= 20;
			}
		} finally {
			loading = false;
		}
	}

	function selectTypeFilter(type: string) {
		filterType = type;
		fetchEvents();
	}

	function selectMemberFilter(member: string) {
		filterMember = filterMember === member ? '' : member;
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
	<div class="flex flex-wrap gap-1.5 px-4 pb-2">
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

	<!-- Member filter pills -->
	{#if members.length > 0}
		<div class="flex flex-wrap gap-1.5 px-4 pb-3">
			{#each members as member}
				{@const hex = getTeamMemberHexColor(member.name)}
				{@const active = filterMember === member.name}
				<button
					class="inline-flex items-center gap-1.5 px-2.5 py-1 text-xs font-medium rounded-full border transition-colors
						{active
							? 'opacity-100'
							: 'opacity-60 border-[var(--border)] text-[var(--text-muted)] hover:opacity-80'}"
					style={active ? `border-color: ${hex}; color: ${hex}; background-color: ${hex}11` : ''}
					onclick={() => selectMemberFilter(member.name)}
				>
					<span
						class="w-2 h-2 rounded-full shrink-0"
						style="background-color: {hex}"
					></span>
					{member.name}
				</button>
			{/each}
		</div>
	{/if}

	<!-- Event list -->
	<div class="border-t border-[var(--border)]">
		{#if events.length === 0}
			<p class="py-8 text-center text-sm text-[var(--text-muted)]">No activity yet</p>
		{:else}
			<div class="divide-y divide-[var(--border)]/50">
				{#each events as event (event.id)}
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
							</div>
						</div>
					</div>
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

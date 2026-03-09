<script lang="ts">
	import type { SyncEvent } from '$lib/api-types';
	import { formatRelativeTime } from '$lib/utils';
	import { API_BASE } from '$lib/config';

	let { events: initialEvents = [], teamName = '' }: { events: SyncEvent[]; teamName: string } =
		$props();

	let events = $state(initialEvents);
	let loading = $state(false);
	let offset = $state(initialEvents.length);
	let hasMore = $state(initialEvents.length >= 20);
	let filterType = $state<string>('');

	const EVENT_META: Record<string, { icon: string; color: string; label: string }> = {
		team_created: { icon: 'plus-circle', color: 'text-[var(--success)]', label: 'created the team' },
		team_deleted: { icon: 'trash-2', color: 'text-[var(--error)]', label: 'deleted the team' },
		team_left: { icon: 'log-out', color: 'text-[var(--warning)]', label: 'left the team' },
		member_joined: { icon: 'user-plus', color: 'text-[var(--success)]', label: 'joined the team' },
		member_added: { icon: 'user-plus', color: 'text-[var(--success)]', label: 'was added' },
		member_auto_accepted: {
			icon: 'user-check',
			color: 'text-[var(--success)]',
			label: 'was auto-accepted'
		},
		member_removed: { icon: 'user-minus', color: 'text-[var(--error)]', label: 'was removed' },
		project_shared: { icon: 'folder-plus', color: 'text-[var(--accent)]', label: 'shared a project' },
		project_added: { icon: 'folder-plus', color: 'text-[var(--accent)]', label: 'added a project' },
		project_removed: { icon: 'folder-minus', color: 'text-[var(--warning)]', label: 'removed a project' },
		folders_shared: { icon: 'share-2', color: 'text-[var(--accent)]', label: 'synced folders' },
		pending_accepted: {
			icon: 'check-circle',
			color: 'text-[var(--success)]',
			label: 'accepted pending folders'
		},
		session_packaged: { icon: 'package', color: 'text-[var(--accent)]', label: 'packaged a session' },
		session_received: {
			icon: 'download',
			color: 'text-[var(--accent)]',
			label: 'received a session'
		},
		file_rejected: { icon: 'shield-alert', color: 'text-[var(--error)]', label: 'file rejected' },
		sync_paused: { icon: 'pause-circle', color: 'text-[var(--warning)]', label: 'sync paused' },
		settings_changed: { icon: 'settings', color: 'text-[var(--accent)]', label: 'changed settings' },
		sync_now: { icon: 'refresh-cw', color: 'text-[var(--accent)]', label: 'triggered sync' },
		watcher_started: { icon: 'play-circle', color: 'text-[var(--success)]', label: 'watcher started' },
		watcher_stopped: { icon: 'stop-circle', color: 'text-[var(--warning)]', label: 'watcher stopped' }
	};

	function describeEvent(event: SyncEvent): string {
		const meta = EVENT_META[event.event_type];
		const actor = event.member_name || 'System';
		const base = meta ? `${actor} ${meta.label}` : `${actor}: ${event.event_type}`;

		let detail = '';
		if (event.detail) {
			try {
				const d = typeof event.detail === 'string' ? JSON.parse(event.detail) : event.detail;
				if (event.event_type === 'project_shared' && d.session_count !== undefined) {
					detail = ` (${d.session_count} sessions)`;
				} else if (event.event_type === 'pending_accepted' && d.count) {
					detail = ` (${d.count} folders)`;
				} else if (event.event_type === 'folders_shared') {
					detail = ` (${d.outboxes || 0} out, ${d.inboxes || 0} in)`;
				} else if (event.event_type === 'file_rejected' && d.reason) {
					detail = `: ${d.reason}`;
				} else if (event.event_type === 'settings_changed' && d.sync_session_limit) {
					const labels: Record<string, string> = {
						all: 'All sessions',
						recent_100: 'Recent 100',
						recent_10: 'Recent 10'
					};
					detail = ` → ${labels[d.sync_session_limit] || d.sync_session_limit}`;
				}
			} catch {
				/* ignore parse errors */
			}
		}

		if (
			event.project_encoded_name &&
			!['settings_changed', 'pending_accepted'].includes(event.event_type)
		) {
			const projName = event.project_encoded_name.split('-').pop() || event.project_encoded_name;
			return `${base} in ${projName}${detail}`;
		}

		return `${base}${detail}`;
	}

	function eventColor(type: string): string {
		return EVENT_META[type]?.color || 'text-[var(--text-muted)]';
	}

	function isWarning(type: string): boolean {
		return ['file_rejected', 'sync_paused'].includes(type);
	}

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
					class="flex items-start gap-2 rounded-md px-2 py-1.5 text-sm {isWarning(event.event_type)
						? 'bg-amber-500/5'
						: ''}"
				>
					<span class="mt-0.5 {eventColor(event.event_type)}">
						{#if isWarning(event.event_type)}
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
					<span class="flex-1 text-[var(--text-secondary)]">{describeEvent(event)}</span>
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

/**
 * Shared formatting utilities for SyncEvent objects.
 *
 * Consolidates event description logic previously duplicated between
 * OverviewTab.svelte (humanizeEvent) and TeamActivityFeed.svelte (describeEvent).
 */

import type { SyncEvent } from '$lib/api-types';

/**
 * Event metadata used for rendering (color, label).
 */
export const SYNC_EVENT_META: Record<string, { color: string; label: string }> = {
	team_created: { color: 'text-[var(--success)]', label: 'created the team' },
	team_deleted: { color: 'text-[var(--error)]', label: 'deleted the team' },
	team_left: { color: 'text-[var(--warning)]', label: 'left the team' },
	member_joined: { color: 'text-[var(--success)]', label: 'joined the team' },
	member_added: { color: 'text-[var(--success)]', label: 'was added' },
	member_auto_accepted: { color: 'text-[var(--success)]', label: 'was auto-accepted' },
	member_removed: { color: 'text-[var(--error)]', label: 'was removed' },
	project_shared: { color: 'text-[var(--accent)]', label: 'shared a project' },
	project_added: { color: 'text-[var(--accent)]', label: 'added a project' },
	project_removed: { color: 'text-[var(--warning)]', label: 'removed a project' },
	folders_shared: { color: 'text-[var(--accent)]', label: 'synced folders' },
	pending_accepted: { color: 'text-[var(--success)]', label: 'accepted pending folders' },
	session_packaged: { color: 'text-[var(--accent)]', label: 'packaged a session' },
	session_received: { color: 'text-[var(--accent)]', label: 'received a session' },
	file_rejected: { color: 'text-[var(--error)]', label: 'file rejected' },
	sync_paused: { color: 'text-[var(--warning)]', label: 'sync paused' },
	settings_changed: { color: 'text-[var(--accent)]', label: 'changed settings' },
	sync_now: { color: 'text-[var(--accent)]', label: 'triggered sync' },
	watcher_started: { color: 'text-[var(--success)]', label: 'watcher started' },
	watcher_stopped: { color: 'text-[var(--warning)]', label: 'watcher stopped' },
	watch_started: { color: 'text-[var(--success)]', label: 'watcher started' },
	watch_stopped: { color: 'text-[var(--warning)]', label: 'watcher stopped' },
	subscription_accepted: { color: 'text-[var(--success)]', label: 'accepted subscription' },
	subscription_paused: { color: 'text-[var(--warning)]', label: 'paused subscription' },
	subscription_resumed: { color: 'text-[var(--success)]', label: 'resumed subscription' },
	subscription_declined: { color: 'text-[var(--error)]', label: 'declined subscription' },
};

/**
 * Returns a human-readable description for a SyncEvent.
 *
 * Handles both v3 (member_name, string detail) and v4 (member_tag, Record detail) shapes.
 */
export function formatSyncEvent(ev: SyncEvent): string {
	const meta = SYNC_EVENT_META[ev.event_type];
	// v4 uses member_tag, v3 uses member_name
	const actor = ev.member_tag || ev.member_name || 'System';
	const team = ev.team_name ?? 'team';

	const base = meta ? `${actor} ${meta.label}` : `${actor}: ${ev.event_type.replace(/_/g, ' ')}`;

	// Simple overrides for team-level events
	switch (ev.event_type) {
		case 'watch_started':
			return `Session watcher started for ${team}`;
		case 'watch_stopped':
			return 'Session watcher stopped';
		case 'team_created':
			return `Team ${team} created`;
		case 'team_deleted':
			return `Team ${team} deleted`;
		case 'pending_accepted':
			break;
	}

	// Parse structured detail field (v4: already a Record, v3: JSON string)
	let detail = '';
	if (ev.detail) {
		try {
			const d = typeof ev.detail === 'string' ? JSON.parse(ev.detail) : ev.detail;
			if (ev.event_type === 'project_shared' && d.session_count !== undefined) {
				detail = ` (${d.session_count} sessions)`;
			} else if (ev.event_type === 'pending_accepted' && d.count) {
				detail = ` (${d.count} folders)`;
			} else if (ev.event_type === 'folders_shared') {
				detail = ` (${d.outboxes || 0} out, ${d.inboxes || 0} in)`;
			} else if (ev.event_type === 'file_rejected' && d.reason) {
				detail = `: ${d.reason}`;
			} else if (ev.event_type === 'settings_changed' && d.sync_session_limit) {
				const labels: Record<string, string> = {
					all: 'All',
					recent_100: 'Recent 100',
					recent_10: 'Recent 10'
				};
				detail = ` -> ${labels[d.sync_session_limit] || d.sync_session_limit}`;
			} else if (ev.event_type === 'subscription_accepted' && d.direction) {
				detail = ` (${d.direction})`;
			} else if (d.git_identity) {
				detail = ` for ${d.git_identity}`;
			}
		} catch {
			/* ignore parse errors */
		}
	}

	// Append project name suffix where relevant (v3 compat)
	if (
		ev.project_encoded_name &&
		!['settings_changed', 'pending_accepted'].includes(ev.event_type)
	) {
		const projName = ev.project_encoded_name.split('-').pop() || ev.project_encoded_name;
		return `${base} in ${projName}${detail}`;
	}

	return `${base}${detail}`;
}

/** Get the CSS color class for a sync event type */
export function syncEventColor(eventType: string): string {
	return SYNC_EVENT_META[eventType]?.color ?? 'text-[var(--text-muted)]';
}

/** Whether an event type should be shown with a warning indicator */
export function isSyncEventWarning(eventType: string): boolean {
	return ['file_rejected', 'sync_paused'].includes(eventType);
}

import { API_BASE } from '$lib/config';
import { fetchWithFallback } from '$lib/utils/api-fetch';
import type { HooksOverview, LiveSessionSummary } from '$lib/api-types';

export interface HookActivity {
	// A: per event type — ISO timestamp of most recent session that had this as last_hook
	lastSeenByEvent: Record<string, string>;
	// B: SessionEnd reason breakdown + total session count
	endReasons: Record<string, number>;
	totalSessions: number;
	// C: subagent stats across tracked sessions (SubagentStart/SubagentStop)
	subagentStats: {
		totalInvocations: number; // from analytics tools_used.Agent (all-time)
		trackedTotal: number; // from live session files (recent)
		sessionsWithAgents: number;
		byType: Record<string, number>;
	};
	// D: recent notification messages (Notification / PermissionRequest hooks)
	recentNotifications: Array<{
		message: string;
		sessionId: string;
		slug: string | null;
		projectEncodedName: string | null;
		updatedAt: string;
	}>;
	// Live pulse: event type currently active in a LIVE session
	activePulseEvent: string | null;
}

export async function load({ fetch, url }) {
	const [hooks, liveSessions, analytics] = await Promise.all([
		fetchWithFallback<HooksOverview>(fetch, `${API_BASE}/hooks`, {
			sources: [],
			event_summaries: [],
			registrations: [],
			stats: { total_sources: 0, total_registrations: 0, blocking_hooks: 0 }
		}),
		fetchWithFallback<{ sessions: LiveSessionSummary[] }>(
			fetch,
			`${API_BASE}/live-sessions?limit=100`,
			{ sessions: [] }
		),
		fetchWithFallback<{ total_sessions: number; tools_used: Record<string, number> }>(
			fetch,
			`${API_BASE}/analytics`,
			{ total_sessions: 0, tools_used: {} }
		)
	]);

	const sessions = liveSessions.sessions ?? [];

	// A: last seen per event type
	const lastSeenByEvent: Record<string, string> = {};
	for (const s of sessions) {
		if (s.last_hook && s.updated_at) {
			const existing = lastSeenByEvent[s.last_hook];
			if (!existing || s.updated_at > existing) {
				lastSeenByEvent[s.last_hook] = s.updated_at;
			}
		}
	}

	// B: end reasons + total sessions
	const endReasons: Record<string, number> = {};
	for (const s of sessions) {
		if (s.end_reason) {
			endReasons[s.end_reason] = (endReasons[s.end_reason] ?? 0) + 1;
		}
	}
	const totalSessions = analytics.total_sessions ?? 0;

	// C: subagent stats
	let trackedTotal = 0;
	let sessionsWithAgents = 0;
	const byType: Record<string, number> = {};
	for (const s of sessions) {
		const count = s.total_subagent_count ?? 0;
		if (count > 0) {
			sessionsWithAgents++;
			trackedTotal += count;
		}
		for (const sub of Object.values(s.subagents ?? {})) {
			const t = (sub as { agent_type?: string }).agent_type ?? 'unknown';
			byType[t] = (byType[t] ?? 0) + 1;
		}
	}

	// D: notification messages
	const recentNotifications = sessions
		.filter((s) => s.last_notification_message)
		.sort((a, b) => (b.updated_at > a.updated_at ? 1 : -1))
		.slice(0, 5)
		.map((s) => ({
			message: s.last_notification_message!,
			sessionId: s.session_id,
			slug: s.slug,
			projectEncodedName: s.project_encoded_name ?? null,
			updatedAt: s.updated_at
		}));

	// Live pulse: find LIVE session's last_hook
	const liveSession = sessions.find((s) => s.state === 'LIVE');
	const activePulseEvent = liveSession?.last_hook ?? null;

	const hookActivity: HookActivity = {
		lastSeenByEvent,
		endReasons,
		totalSessions,
		subagentStats: {
			totalInvocations: analytics.tools_used?.Agent ?? 0,
			trackedTotal,
			sessionsWithAgents,
			byType
		},
		recentNotifications,
		activePulseEvent
	};

	return {
		hooks,
		hookActivity,
		initialEvent: url.searchParams.get('event')
	};
}

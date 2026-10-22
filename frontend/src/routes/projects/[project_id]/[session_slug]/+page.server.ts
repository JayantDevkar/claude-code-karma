import type { LiveSessionSummary, PlanDetail, SessionTicketRow } from '$lib/api-types';
import { API_BASE } from '$lib/config';
import { safeFetch, fetchWithFallback } from '$lib/utils/api-fetch';
import { getSessionDisplayName } from '$lib/utils';
import { joinTitle } from '$lib/page-title';

/**
 * Session lookup result from the fast lookup endpoint
 * (see api/routers/projects.py:lookup_session). The `project_encoded_name`
 * field is the API's canonical identifier — extract it from the load and
 * pass it as `encodedName` to ConversationView; do NOT thread the URL
 * param (which can be a slug) through as encodedName.
 */
interface SessionLookupResult {
	uuid: string;
	slug: string | null;
	project_encoded_name: string;
	project_path: string;
	message_count: number;
	start_time: string | null;
	end_time: string | null;
	initial_prompt: string | null;
	matched_by: 'slug' | 'uuid_prefix' | 'uuid';
}

export async function load({ params, fetch }) {
	const { project_id, session_slug } = params;

	// Step 1: Use fast lookup endpoint to resolve slug/UUID to session UUID
	// This is ~100x faster than loading all sessions
	const lookupResult = await safeFetch<SessionLookupResult>(
		fetch,
		`${API_BASE}/projects/${project_id}/sessions/lookup?identifier=${encodeURIComponent(session_slug)}`
	);

	// If lookup fails, check for "starting" live session or return error
	if (!lookupResult.ok) {
		// Check if it's a "starting" live session that doesn't have JSONL yet
		const liveSessionResult = await safeFetch<LiveSessionSummary[]>(
			fetch,
			`${API_BASE}/live-sessions/active`
		);

		if (liveSessionResult.ok) {
			const matchingLiveSession = liveSessionResult.data.find(
				(ls) => ls.session_id.startsWith(session_slug) && ls.status === 'starting'
			);

			if (matchingLiveSession) {
				return {
					session: null,
					plan: null,
					liveSession: matchingLiveSession,
					isStarting: true,
					title: joinTitle([matchingLiveSession.session_id.slice(0, 8), 'Sessions']),
					project_id,
					session_slug,
					tickets: [] as SessionTicketRow[],
					error: null
				};
			}
		}

		// Return appropriate error
		const isNotFound =
			lookupResult.message?.includes('404') || lookupResult.message?.includes('not found');
		return {
			session: null,
			plan: null,
			liveSession: null,
			isStarting: false,
			project_id,
			session_slug,
			tickets: [] as SessionTicketRow[],
			title: isNotFound ? 'Session not found' : 'Failed to load session',
			error: isNotFound
				? `Session not found: ${session_slug}`
				: `Failed to lookup session: ${lookupResult.message}`
		};
	}

	const sessionLookup = lookupResult.data;
	const sessionUuid = sessionLookup.uuid;
	const projectPath = sessionLookup.project_path;
	// Canonical encoded_name from the API — pass to children that need
	// the system identifier (e.g., ConversationView's encodedName prop).
	const projectEncodedName = sessionLookup.project_encoded_name;

	// Timeline, file activity and subagents load client-side when their tab opens (#135)
	const [sessionResult, toolsData, tasksData, planResult, ticketsData] = await Promise.all([
		safeFetch<Record<string, unknown>>(fetch, `${API_BASE}/sessions/${sessionUuid}`),
		fetchWithFallback(fetch, `${API_BASE}/sessions/${sessionUuid}/tools`, []),
		fetchWithFallback(fetch, `${API_BASE}/sessions/${sessionUuid}/tasks`, []),
		safeFetch<PlanDetail>(fetch, `${API_BASE}/sessions/${sessionUuid}/plan`),
		fetchWithFallback<SessionTicketRow[]>(
			fetch,
			`${API_BASE}/sessions/${sessionUuid}/tickets`,
			[]
		)
	]);

	if (!sessionResult.ok) {
		console.error('Failed to fetch session:', sessionResult.message);
		return {
			session: null,
			plan: null,
			liveSession: null,
			isStarting: false,
			project_id,
			session_slug,
			tickets: [] as SessionTicketRow[],
			title: 'Failed to load session',
			error: `Failed to load session: ${sessionResult.message}`
		};
	}

	const sessionData = sessionResult.data;

	// Transform tools from API format to ToolUsage format [{tool_name, count}]
	const tools_used = (
		toolsData as Array<{ tool_name: string; count: number; by_session?: number }>
	).map((t) => ({
		tool_name: t.tool_name,
		count: t.count,
		by_session: t.by_session
	}));

	// Extract plan data (null if 404 or error - plan is optional)
	const plan = planResult.ok ? planResult.data : null;

	// Combine all data into session object
	const session = {
		...sessionData,
		project_path: projectPath,
		tools_used,
		tasks: tasksData
	};

	const sessionName = getSessionDisplayName(
		sessionData.session_titles as string[] | undefined,
		sessionLookup.slug ?? undefined,
		sessionUuid,
		sessionData.chain_title as string | undefined
	);

	return {
		session,
		plan,
		title: joinTitle([sessionName, 'Sessions']),
		liveSession: null,
		isStarting: false,
		project_id,
		project_encoded_name: projectEncodedName,
		session_slug,
		tickets: (ticketsData ?? []) as SessionTicketRow[],
		error: null
	};
}

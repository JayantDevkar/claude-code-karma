import type { LiveSessionSummary, PlanDetail } from '$lib/api-types';
import { API_BASE } from '$lib/config';
import { safeFetch, fetchWithFallback } from '$lib/utils/api-fetch';

/**
 * Session lookup result from the fast lookup endpoint.
 */
interface SessionLookupResult {
	uuid: string;
	slug: string | null;
	project_project_slug: string;
	project_path: string;
	message_count: number;
	start_time: string | null;
	end_time: string | null;
	initial_prompt: string | null;
	matched_by: 'slug' | 'uuid_prefix' | 'uuid';
}

export async function load({ params, fetch }) {
	const { project_slug, session_slug } = params;

	// Step 1: Use fast lookup endpoint to resolve slug/UUID to session UUID
	// This is ~100x faster than loading all sessions
	const lookupResult = await safeFetch<SessionLookupResult>(
		fetch,
		`${API_BASE}/projects/${project_slug}/sessions/lookup?identifier=${encodeURIComponent(session_slug)}`
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
					project_slug,
					session_slug,
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
			project_slug,
			session_slug,
			error: isNotFound
				? `Session not found: ${session_slug}`
				: `Failed to lookup session: ${lookupResult.message}`
		};
	}

	const sessionLookup = lookupResult.data;
	const sessionUuid = sessionLookup.uuid;
	const projectPath = sessionLookup.project_path;

	// Step 4: Fetch detailed session data using UUID
	// Use safeFetch for the main session, fetchWithFallback for supplementary data
	// Plan is optional (404 is not an error), so we use safeFetch and handle it separately
	const [
		sessionResult,
		timelineData,
		fileActivityData,
		subagentsData,
		toolsData,
		tasksData,
		planResult
	] = await Promise.all([
		safeFetch<Record<string, unknown>>(fetch, `${API_BASE}/sessions/${sessionUuid}`),
		fetchWithFallback(fetch, `${API_BASE}/sessions/${sessionUuid}/timeline`, []),
		fetchWithFallback(fetch, `${API_BASE}/sessions/${sessionUuid}/file-activity`, []),
		fetchWithFallback(fetch, `${API_BASE}/sessions/${sessionUuid}/subagents`, []),
		fetchWithFallback(fetch, `${API_BASE}/sessions/${sessionUuid}/tools`, []),
		fetchWithFallback(fetch, `${API_BASE}/sessions/${sessionUuid}/tasks`, []),
		safeFetch<PlanDetail>(fetch, `${API_BASE}/sessions/${sessionUuid}/plan`)
	]);

	if (!sessionResult.ok) {
		console.error('Failed to fetch session:', sessionResult.message);
		return {
			session: null,
			plan: null,
			liveSession: null,
			isStarting: false,
			project_slug,
			session_slug,
			error: `Failed to load session: ${sessionResult.message}`
		};
	}

	const sessionData = sessionResult.data;

	// Transform tools from API format to ToolUsage format [{tool_name, count}]
	const tools_used = (toolsData as Array<{ tool_name: string; count: number }>).map((t) => ({
		tool_name: t.tool_name,
		count: t.count
	}));

	// Transform file activity to files_accessed format
	const filesByPath: Record<
		string,
		{ path: string; operations: Set<string>; read: number; write: number; edit: number }
	> = {};

	(fileActivityData as Array<{ path: string; operation: string }>).forEach((activity) => {
		if (!filesByPath[activity.path]) {
			filesByPath[activity.path] = {
				path: activity.path,
				operations: new Set(),
				read: 0,
				write: 0,
				edit: 0
			};
		}
		const file = filesByPath[activity.path];
		file.operations.add(activity.operation);

		if (activity.operation === 'read') file.read++;
		else if (activity.operation === 'write') file.write++;
		else if (activity.operation === 'edit') file.edit++;
	});

	const files_accessed = Object.values(filesByPath).map((f) => ({
		path: f.path,
		operations: Array.from(f.operations),
		read_count: f.read,
		write_count: f.write,
		edit_count: f.edit
	}));

	// Extract messages from timeline for the Messages tab
	const messages = (
		timelineData as Array<{
			event_type: string;
			actor_type: string;
			metadata?: { full_content?: string; full_text?: string };
			summary?: string;
			timestamp: string;
		}>
	)
		.filter((e) => e.event_type === 'prompt' || e.event_type === 'response')
		.map((e) => ({
			role: e.actor_type === 'user' ? 'user' : 'assistant',
			content: e.metadata?.full_content || e.metadata?.full_text || e.summary || '',
			timestamp: e.timestamp
		}));

	// Extract plan data (null if 404 or error - plan is optional)
	const plan = planResult.ok ? planResult.data : null;

	// Combine all data into session object
	const session = {
		...sessionData,
		project_path: projectPath,
		tools_used,
		files_accessed,
		file_activity: fileActivityData,
		timeline: timelineData,
		messages,
		subagents: subagentsData,
		tasks: tasksData
	};

	return {
		session,
		plan,
		liveSession: null,
		isStarting: false,
		project_slug,
		session_slug,
		error: null
	};
}

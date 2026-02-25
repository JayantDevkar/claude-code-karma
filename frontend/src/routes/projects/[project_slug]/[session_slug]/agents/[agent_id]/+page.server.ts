import type {
	SubagentSessionDetail,
	TimelineEvent,
	FileActivity,
	ToolUsage,
	Task
} from '$lib/api-types';
import { API_BASE } from '$lib/config';
import { safeFetch, fetchWithFallback } from '$lib/utils/api-fetch';

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
	const { project_slug, session_slug, agent_id } = params;

	// Step 1: Use fast lookup endpoint to resolve slug/UUID to session UUID
	// This is ~350x faster than loading all sessions via /projects/{project_slug}
	const lookupResult = await safeFetch<SessionLookupResult>(
		fetch,
		`${API_BASE}/projects/${project_slug}/sessions/lookup?identifier=${encodeURIComponent(session_slug)}`
	);

	if (!lookupResult.ok) {
		return {
			agent: null,
			timeline: [],
			fileActivity: [],
			tools: [],
			tasks: [],
			project_slug,
			session_slug,
			session_uuid: null,
			parent_session_slug: session_slug,
			project_path: null,
			error: `Session not found: ${session_slug}`
		};
	}

	const sessionLookup = lookupResult.data;
	const sessionUuid = sessionLookup.uuid;
	const encodedName = sessionLookup.project_encoded_name;
	const agentBaseUrl = `${API_BASE}/agents/${encodedName}/${sessionUuid}/agents/${agent_id}`;

	// Step 3: Fetch all agent data in parallel
	const [agentResult, timelineData, fileActivityData, toolsData, tasksData] = await Promise.all([
		safeFetch<SubagentSessionDetail>(fetch, agentBaseUrl),
		fetchWithFallback<TimelineEvent[]>(fetch, `${agentBaseUrl}/timeline`, []),
		fetchWithFallback<FileActivity[]>(fetch, `${agentBaseUrl}/file-activity`, []),
		fetchWithFallback<Array<{ tool_name: string; count: number }>>(
			fetch,
			`${agentBaseUrl}/tools`,
			[]
		),
		fetchWithFallback<Task[]>(fetch, `${agentBaseUrl}/tasks`, [])
	]);

	if (!agentResult.ok) {
		console.error('Failed to fetch agent:', agentResult.message);
		return {
			agent: null,
			timeline: [],
			fileActivity: [],
			tools: [],
			tasks: [],
			project_slug,
			session_slug,
			session_uuid: sessionUuid,
			parent_session_slug: sessionLookup.slug || sessionUuid.slice(0, 8),
			project_path: sessionLookup.project_path,
			error: `Agent not found: ${agentResult.message}`
		};
	}

	// Transform tools from API format to component format
	const tools_used: ToolUsage[] = toolsData.map((t) => ({
		tool_name: t.tool_name,
		count: t.count
	}));

	return {
		agent: agentResult.data,
		timeline: timelineData,
		fileActivity: fileActivityData,
		tools: tools_used,
		tasks: tasksData,
		project_slug,
		session_slug,
		session_uuid: sessionUuid,
		parent_session_slug: sessionLookup.slug || sessionUuid.slice(0, 8),
		project_path: sessionLookup.project_path,
		error: null
	};
}

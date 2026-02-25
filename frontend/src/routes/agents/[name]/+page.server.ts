import type {
	AgentUsageDetail,
	AgentInvocationHistoryResponse,
	Project,
	AgentInfo,
	SessionWithContext,
	UsageTrendResponse
} from '$lib/api-types';
import { API_BASE } from '$lib/config';
import { fetchWithFallback } from '$lib/utils/api-fetch';

const PER_PAGE = 20;

interface AgentSessionsResponse {
	subagent_type: string;
	sessions: SessionWithContext[];
	total_count: number;
}

export async function load({ params, fetch, url }) {
	const subagentType = decodeURIComponent(params.name);
	const page = parseInt(url.searchParams.get('page') || '1', 10);

	const [detail, historyData, projects, agentInfo, sessionsData, trendData] = await Promise.all([
		fetchWithFallback<AgentUsageDetail | null>(
			fetch,
			`${API_BASE}/agents/usage/${encodeURIComponent(subagentType)}`,
			null
		),
		fetchWithFallback<AgentInvocationHistoryResponse>(
			fetch,
			`${API_BASE}/agents/usage/${encodeURIComponent(subagentType)}/history?page=${page}&per_page=${PER_PAGE}`,
			{ items: [], total: 0, page: 1, per_page: PER_PAGE, total_pages: 0 }
		),
		fetchWithFallback<Project[]>(fetch, `${API_BASE}/projects`, []),
		fetchWithFallback<AgentInfo | null>(
			fetch,
			`${API_BASE}/agents/info/${encodeURIComponent(subagentType)}`,
			null
		),
		fetchWithFallback<AgentSessionsResponse>(
			fetch,
			`${API_BASE}/agents/usage/${encodeURIComponent(subagentType)}/sessions?limit=100`,
			{ subagent_type: subagentType, sessions: [], total_count: 0 }
		),
		fetchWithFallback<UsageTrendResponse>(
			fetch,
			`${API_BASE}/agents/usage/${encodeURIComponent(subagentType)}/trend?period=quarter`,
			{ total: 0, by_item: {}, trend: [], first_used: null, last_used: null }
		)
	]);

	// Create a mapping from encoded_name to project name (last segment of path)
	const projectNameMap: Record<string, string> = {};
	for (const project of projects) {
		const name = project.path.split('/').pop() || project.path;
		projectNameMap[project.encoded_name] = name;
	}

	// Enrich sessions with project context
	// eslint-disable-next-line @typescript-eslint/no-explicit-any
	const sessionsWithContext: SessionWithContext[] = sessionsData.sessions.map((s: any) => ({
		...s,
		project_path: projectNameMap[s.project_encoded_name] || s.project_encoded_name,
		project_name: projectNameMap[s.project_encoded_name] || s.project_encoded_name
	}));

	return {
		subagentType,
		detail,
		history: historyData.items,
		pagination: {
			total: historyData.total,
			page: historyData.page,
			perPage: historyData.per_page,
			totalPages: historyData.total_pages
		},
		projectNameMap,
		agentInfo,
		sessions: sessionsWithContext,
		sessionsTotalCount: sessionsData.total_count,
		trend: trendData.trend
	};
}

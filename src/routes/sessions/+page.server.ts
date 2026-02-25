import type {
	AllSessionsResponseWithFilters,
	LiveSessionSummary,
	SearchScope,
	SessionStatusFilter
} from '$lib/api-types';
import { API_BASE } from '$lib/config';
import { safeFetch, fetchWithFallback } from '$lib/utils/api-fetch';

export async function load({ fetch, url }) {
	// Extract query parameters for filtering
	const search = url.searchParams.get('search') || url.searchParams.get('q') || undefined;
	const project = url.searchParams.get('project') || undefined;
	const branch = url.searchParams.get('branch') || undefined;

	const page = parseInt(url.searchParams.get('page') || '1', 10);
	const perPage = parseInt(url.searchParams.get('per_page') || '50', 10);

	// Additional filter params (kept in URL for shareability)
	// Search and scope are forwarded to API; status/date/live filters are applied client-side
	const scope = (url.searchParams.get('scope') as SearchScope) || undefined;
	const status = (url.searchParams.get('status') as SessionStatusFilter) || undefined;
	const start_ts = url.searchParams.get('start_ts') || undefined;
	const end_ts = url.searchParams.get('end_ts') || undefined;

	// Build query string
	const params = new URLSearchParams();
	// Server-side search is now fast (title cache eliminates N+1 JSONL loading)
	if (search) params.set('search', search);
	if (scope) params.set('scope', scope);
	if (project) params.set('project', project);
	if (branch) params.set('branch', branch);
	params.set('page', page.toString());
	params.set('per_page', perPage.toString());

	const filters = { search, project, branch, scope, status, start_ts, end_ts, page, perPage };

	if (status) params.set('status', status);
	if (start_ts) params.set('start_ts', start_ts);
	if (end_ts) params.set('end_ts', end_ts);

	// Fetch sessions and live sessions in parallel
	const [sessionsResult, liveSessionsData] = await Promise.all([
		safeFetch<AllSessionsResponseWithFilters>(
			fetch,
			`${API_BASE}/sessions/all?${params.toString()}`
		),
		fetchWithFallback<{ sessions: LiveSessionSummary[] }>(fetch, `${API_BASE}/live-sessions`, {
			sessions: []
		})
	]);

	if (!sessionsResult.ok) {
		console.error('Failed to fetch sessions:', sessionsResult.message);
		return {
			sessions: [],
			total: 0,
			projects: [],
			statusOptions: [],
			liveSessions: [],
			error: sessionsResult.message,
			filters
		};
	}

	const data = sessionsResult.data;

	return {
		sessions: data.sessions,
		total: data.total,
		projects: data.projects,
		statusOptions: data.status_options || [],
		liveSessions: liveSessionsData.sessions || [],
		error: null,
		filters
	};
}

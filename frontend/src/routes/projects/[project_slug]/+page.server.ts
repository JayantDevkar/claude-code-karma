import type {
	Project,
	BranchesData,
	ProjectArchivedResponse,
	LiveSessionSummary
} from '$lib/api-types';
import { API_BASE } from '$lib/config';
import { safeFetch, fetchWithFallback } from '$lib/utils/api-fetch';

export async function load({ params, fetch, url }) {
	// Extract timestamp filters from URL (Unix milliseconds)
	const startTs = url.searchParams.get('start_ts');
	const endTs = url.searchParams.get('end_ts');
	const tzOffset = url.searchParams.get('tz_offset');

	// Extract pagination params
	const page = parseInt(url.searchParams.get('page') || '1', 10);
	const perPage = parseInt(url.searchParams.get('per_page') || '50', 10);

	// Build analytics URL with timestamp params
	const analyticsParams = new URLSearchParams();
	if (startTs) analyticsParams.set('start_ts', startTs);
	if (endTs) analyticsParams.set('end_ts', endTs);
	if (tzOffset) analyticsParams.set('tz_offset', tzOffset);

	// Build project URL with pagination params
	const projectParams = new URLSearchParams();
	projectParams.set('page', page.toString());
	projectParams.set('per_page', perPage.toString());

	const emptyArchived: ProjectArchivedResponse = {
		project_name: '',
		project_path: '',
		sessions: [],
		total_sessions: 0,
		total_prompts: 0
	};

	const emptyBranches: BranchesData = {
		branches: [],
		active_branches: [],
		sessions_by_branch: {}
	};

	// Fetch project (required) and supplementary data (optional) in parallel
	// Analytics is excluded - will be fetched client-side on-demand for better initial load performance
	const [projectResult, branches, archived, liveSessions] = await Promise.all([
		safeFetch<Project>(fetch, `${API_BASE}/projects/${params.project_slug}?${projectParams}`),
		fetchWithFallback<BranchesData>(
			fetch,
			`${API_BASE}/projects/${params.project_slug}/branches`,
			emptyBranches
		),
		fetchWithFallback<ProjectArchivedResponse>(
			fetch,
			`${API_BASE}/history/archived/${params.project_slug}`,
			emptyArchived
		),
		fetchWithFallback<LiveSessionSummary[]>(
			fetch,
			`${API_BASE}/live-sessions/project/${params.project_slug}`,
			[]
		)
	]);

	if (!projectResult.ok) {
		console.error('Failed to fetch project:', projectResult.message);
		return {
			project: null,
			branches: emptyBranches,
			analytics: null,
			archived: emptyArchived,
			liveSessions: [] as LiveSessionSummary[],
			pagination: { page, perPage },
			error: `Project not found: ${projectResult.message}`,
			analyticsUrlParams: { startTs, endTs, tzOffset }
		};
	}

	return {
		project: projectResult.data,
		branches,
		analytics: null, // Fetched client-side on-demand
		archived,
		liveSessions,
		pagination: { page, perPage },
		error: null,
		// Pass analytics URL params for client-side fetch
		analyticsUrlParams: {
			startTs,
			endTs,
			tzOffset
		}
	};
}

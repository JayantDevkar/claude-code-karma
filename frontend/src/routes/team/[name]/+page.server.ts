import type { PageServerLoad } from './$types';
import { API_BASE } from '$lib/config';
import { safeFetch, fetchWithFallback } from '$lib/utils/api-fetch';
import type {
	SyncTeam,
	SyncStatusResponse,
	SyncEvent
} from '$lib/api-types';

interface ProjectSummary {
	encoded_name: string;
	path: string;
	slug?: string;
	display_name?: string;
	session_count: number;
	git_remote_url?: string;
}

export const load: PageServerLoad = async ({ fetch, params }) => {
	const teamName = params.name;
	const teamNameEnc = encodeURIComponent(teamName);

	// Fetch in parallel: team detail (includes members+projects+subscriptions), sync status, activity, all projects
	const [teamResult, syncStatus, activityData, allProjects] = await Promise.all([
		safeFetch<SyncTeam>(fetch, `${API_BASE}/sync/teams/${teamNameEnc}`),
		fetchWithFallback<SyncStatusResponse>(fetch, `${API_BASE}/sync/status`, {
			configured: false
		}),
		fetchWithFallback<{ events: SyncEvent[] }>(
			fetch,
			`${API_BASE}/sync/teams/${teamNameEnc}/activity?limit=20`,
			{ events: [] }
		),
		fetchWithFallback<ProjectSummary[]>(
			fetch,
			`${API_BASE}/projects`,
			[]
		)
	]);

	const team = teamResult.ok ? teamResult.data : null;

	return {
		teamName,
		team,
		syncStatus,
		activity: activityData.events ?? [],
		allProjects: allProjects.map((p) => ({
			encoded_name: p.encoded_name,
			name: p.display_name || p.slug || p.encoded_name,
			path: p.path,
			git_remote_url: p.git_remote_url ?? null
		}))
	};
};

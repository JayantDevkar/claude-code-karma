import type { PageServerLoad } from './$types';
import { API_BASE } from '$lib/config';
import { safeFetch } from '$lib/utils/api-fetch';

export const load: PageServerLoad = async ({ fetch, url }) => {
	// Extract timestamp filters (Unix milliseconds)
	const startTs = url.searchParams.get('start_ts');
	const endTs = url.searchParams.get('end_ts');
	const tzOffset = url.searchParams.get('tz_offset');

	// Build API URL with timestamp params
	const params = new URLSearchParams();
	if (startTs) params.set('start_ts', startTs);
	if (endTs) params.set('end_ts', endTs);
	if (tzOffset) params.set('tz_offset', tzOffset);

	const apiUrl = params.toString() ? `${API_BASE}/analytics?${params}` : `${API_BASE}/analytics`;

	const [result, projectsResult] = await Promise.all([
		safeFetch<Record<string, unknown>>(fetch, apiUrl),
		safeFetch<Array<{ path: string; encoded_name: string; session_count: number; display_name?: string }>>(fetch, `${API_BASE}/projects`)
	]);

	if (!result.ok) {
		console.error('Failed to fetch analytics:', result.message);
		return { analytics: null, topProjects: [], error: result.message };
	}

	const topProjects = projectsResult.ok
		? [...(projectsResult.data ?? [])]
				.sort((a, b) => (b.session_count ?? 0) - (a.session_count ?? 0))
				.slice(0, 5)
		: [];

	return { analytics: result.data, topProjects, error: null };
};

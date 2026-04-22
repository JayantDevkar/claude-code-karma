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

	// Fetch analytics and reports in parallel
	const [analyticsResult, reportsResult] = await Promise.all([
		safeFetch<Record<string, unknown>>(fetch, apiUrl),
		safeFetch<unknown[]>(fetch, `${API_BASE}/analytics/report`),
	]);

	if (!analyticsResult.ok) {
		console.error('Failed to fetch analytics:', analyticsResult.message);
		return { analytics: null, reports: [], error: analyticsResult.message };
	}

	return {
		analytics: analyticsResult.data,
		reports: reportsResult.ok ? (reportsResult.data ?? []) : [],
		error: null
	};
};

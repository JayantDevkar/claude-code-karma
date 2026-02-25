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

	const result = await safeFetch<Record<string, unknown>>(fetch, apiUrl);

	if (!result.ok) {
		console.error('Failed to fetch analytics:', result.message);
		return { analytics: null, error: result.message };
	}

	return { analytics: result.data, error: null };
};

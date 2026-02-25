import { API_BASE } from '$lib/config';
import { fetchWithFallback } from '$lib/utils/api-fetch';
import type { HooksOverview } from '$lib/api-types';

export async function load({ fetch }) {
	const data = await fetchWithFallback<HooksOverview>(fetch, `${API_BASE}/hooks`, {
		sources: [],
		event_summaries: [],
		registrations: [],
		stats: { total_sources: 0, total_registrations: 0, blocking_hooks: 0 }
	});
	return { hooks: data };
}

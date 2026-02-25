import { API_BASE } from '$lib/config';
import { fetchWithFallback } from '$lib/utils/api-fetch';
import type { HookSourceDetail } from '$lib/api-types';

export async function load({ params, fetch }) {
	const data = await fetchWithFallback<HookSourceDetail>(
		fetch,
		`${API_BASE}/hooks/sources/${encodeURIComponent(params.source_id)}`,
		{
			source: {
				source_type: 'global',
				source_name: params.source_id,
				source_id: params.source_id,
				plugin_id: null,
				scripts: [],
				total_registrations: 0,
				event_types_covered: [],
				blocking_hooks_count: 0
			},
			scripts: [],
			coverage_matrix: {}
		}
	);
	return { detail: data, source_id: params.source_id };
}

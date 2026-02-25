import { API_BASE } from '$lib/config';
import { fetchWithFallback } from '$lib/utils/api-fetch';
import type { HookEventDetail } from '$lib/api-types';

export async function load({ params, fetch }) {
	const data = await fetchWithFallback<HookEventDetail>(
		fetch,
		`${API_BASE}/hooks/${encodeURIComponent(params.event_type)}`,
		{
			event: {
				event_type: params.event_type,
				phase: '',
				can_block: false,
				description: '',
				total_registrations: 0,
				sources: [],
				registrations: []
			},
			schema_info: null,
			related_events: []
		}
	);
	return { detail: data, event_type: params.event_type };
}

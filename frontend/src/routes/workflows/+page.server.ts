import type { Workflow } from '$lib/api-types';
import { API_BASE } from '$lib/config';
import { fetchWithFallback } from '$lib/utils/api-fetch';

export async function load({ fetch }) {
	const workflows = await fetchWithFallback<Workflow[]>(fetch, `${API_BASE}/workflows`, []);
	return { workflows };
}

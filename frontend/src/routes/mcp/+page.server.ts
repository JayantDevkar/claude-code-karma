import type { McpToolsOverview } from '$lib/api-types';
import { API_BASE } from '$lib/config';
import { fetchWithFallback } from '$lib/utils/api-fetch';

export async function load({ fetch }) {
	const overview = await fetchWithFallback<McpToolsOverview>(fetch, `${API_BASE}/tools`, {
		total_servers: 0,
		total_tools: 0,
		total_calls: 0,
		total_sessions: 0,
		servers: []
	});

	return { overview };
}

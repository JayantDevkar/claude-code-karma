import type { McpServerDetail } from '$lib/api-types';
import { API_BASE } from '$lib/config';
import { fetchWithFallback } from '$lib/utils/api-fetch';

export async function load({ params, fetch }) {
	const serverName = params.server_name;

	const detail = await fetchWithFallback<McpServerDetail | null>(
		fetch,
		`${API_BASE}/tools/${encodeURIComponent(serverName)}?per_page=100`,
		null
	);

	return { serverName, detail };
}

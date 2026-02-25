import type { McpToolDetail } from '$lib/api-types';
import { API_BASE } from '$lib/config';
import { fetchWithFallback } from '$lib/utils/api-fetch';

export async function load({ params, fetch }) {
	const serverName = params.server_name;
	const toolName = params.tool_name;

	const detail = await fetchWithFallback<McpToolDetail | null>(
		fetch,
		`${API_BASE}/tools/${encodeURIComponent(serverName)}/${encodeURIComponent(toolName)}?per_page=100`,
		null
	);

	return { serverName, toolName, detail };
}

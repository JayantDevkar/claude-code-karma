import type { McpToolDetail } from '$lib/api-types';
import { API_BASE } from '$lib/config';
import { fetchWithFallback } from '$lib/utils/api-fetch';
import { joinTitle } from '$lib/page-title';

export async function load({ params, fetch }) {
	const serverName = params.server_name;
	const toolName = params.tool_name;

	const detail = await fetchWithFallback<McpToolDetail | null>(
		fetch,
		`${API_BASE}/tools/${encodeURIComponent(serverName)}/${encodeURIComponent(toolName)}?per_page=100`,
		null
	);

	return {
		serverName,
		toolName,
		detail,
		title: joinTitle([detail?.name ?? toolName, detail?.server_display_name ?? serverName])
	};
}

import type { AgentUsageListResponse } from '$lib/api-types';
import { API_BASE } from '$lib/config';
import { fetchWithFallback } from '$lib/utils/api-fetch';

interface AgentDefinition {
	name: string;
	size_bytes: number;
	modified_at: string;
}

export async function load({ fetch }) {
	// Load all agents once — category/search filtering happens client-side
	// to avoid goto() → navigation → skeleton flash on every tab switch.
	// This matches the tools page pattern (no pagination).
	const [definitions, usage] = await Promise.all([
		fetchWithFallback<AgentDefinition[]>(fetch, `${API_BASE}/agents`, []),
		fetchWithFallback<AgentUsageListResponse>(fetch, `${API_BASE}/agents/usage`, {
			agents: [],
			total: 0,
			page: 1,
			per_page: 0,
			total_pages: 0,
			total_runs: 0,
			total_cost_usd: 0,
			by_category: {}
		})
	]);

	return { definitions, usage };
}

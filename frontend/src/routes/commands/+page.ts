import type { CommandUsage } from '$lib/api-types';
import { API_BASE } from '$lib/config';
import { fetchWithFallback } from '$lib/utils/api-fetch';

export async function load({ fetch }) {
	const usage = await fetchWithFallback<CommandUsage[]>(fetch, `${API_BASE}/commands/usage`, []);

	return {
		usage
	};
}

import type { SkillUsage } from '$lib/api-types';
import { API_BASE } from '$lib/config';
import { fetchWithFallback } from '$lib/utils/api-fetch';

export async function load({ fetch }) {
	// Fetch skill usage statistics
	const usage = await fetchWithFallback<SkillUsage[]>(fetch, `${API_BASE}/skills/usage`, []);

	return {
		usage
	};
}

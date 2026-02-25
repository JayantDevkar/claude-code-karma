import type { ArchivedPromptsResponse } from '$lib/api-types';
import { API_BASE } from '$lib/config';
import { safeFetch } from '$lib/utils/api-fetch';

export async function load({ fetch }) {
	const result = await safeFetch<ArchivedPromptsResponse>(fetch, `${API_BASE}/history/archived`);

	if (!result.ok) {
		console.error('Failed to fetch archived prompts:', result.message);
		return {
			archived: { projects: [], total_archived_sessions: 0, total_archived_prompts: 0 },
			error: result.message
		};
	}

	return { archived: result.data, error: null };
}

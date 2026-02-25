import { API_BASE } from '$lib/config';
import { safeFetch } from '$lib/utils/api-fetch';

interface Project {
	encoded_name: string;
	path: string;
	session_count: number;
	total_cost: number;
	total_tokens: number;
	latest_session_time: string | null;
}

export async function load({ fetch }) {
	const result = await safeFetch<Project[]>(fetch, `${API_BASE}/projects`);

	if (!result.ok) {
		console.error('Failed to fetch projects:', result.message);
		return { projects: [], error: result.message };
	}

	return { projects: result.data, error: null };
}

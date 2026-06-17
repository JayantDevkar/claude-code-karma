import { API_BASE } from '$lib/config';
import { fetchWithFallback } from '$lib/utils/api-fetch';

interface MemoryProjectRow {
	encoded: string;
	label: string;
	path: string;
	note_count: number;
	has_index: boolean;
}

interface MemoryIndexResponse {
	projects: MemoryProjectRow[];
	total_projects: number;
	total_notes: number;
}

export async function load({ fetch }) {
	const data = await fetchWithFallback<MemoryIndexResponse>(fetch, `${API_BASE}/memory`, {
		projects: [],
		total_projects: 0,
		total_notes: 0
	});

	return {
		projects: data?.projects ?? [],
		totalProjects: data?.total_projects ?? 0,
		totalNotes: data?.total_notes ?? 0,
	};
}

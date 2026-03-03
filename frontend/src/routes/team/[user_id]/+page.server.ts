import type { PageServerLoad } from './$types';
import { API_BASE } from '$lib/config';
import { safeFetch } from '$lib/utils/api-fetch';

interface RemoteProject {
	encoded_name: string;
	session_count: number;
	synced_at: string | null;
	machine_id: string | null;
}

export const load: PageServerLoad = async ({ params, fetch }) => {
	const result = await safeFetch<RemoteProject[]>(
		fetch,
		`${API_BASE}/remote/users/${encodeURIComponent(params.user_id)}/projects`
	);
	if (!result.ok) {
		console.error('Failed to fetch user projects:', result.message);
		return { user_id: params.user_id, projects: [], error: result.message };
	}
	return { user_id: params.user_id, projects: result.data, error: null };
};

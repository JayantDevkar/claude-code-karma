import type { PageServerLoad } from './$types';
import { API_BASE } from '$lib/config';
import { fetchWithFallback } from '$lib/utils/api-fetch';

interface RemoteProject {
	encoded_name: string;
	session_count: number;
	synced_at: string | null;
	machine_id: string | null;
}

export const load: PageServerLoad = async ({ params, fetch }) => {
	const projects = await fetchWithFallback<RemoteProject[]>(
		fetch,
		`${API_BASE}/remote/users/${encodeURIComponent(params.user_id)}/projects`,
		[]
	);

	return {
		user_id: params.user_id,
		projects
	};
};

import type { PageServerLoad } from './$types';
import { API_BASE } from '$lib/config';
import { fetchWithFallback } from '$lib/utils/api-fetch';

interface RemoteUser {
	user_id: string;
	project_count: number;
	total_sessions: number;
}

export const load: PageServerLoad = async ({ fetch }) => {
	const users = await fetchWithFallback<RemoteUser[]>(fetch, `${API_BASE}/remote/users`, []);
	return { users };
};

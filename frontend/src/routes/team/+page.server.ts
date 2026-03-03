import type { PageServerLoad } from './$types';
import { API_BASE } from '$lib/config';
import { safeFetch } from '$lib/utils/api-fetch';

interface RemoteUser {
	user_id: string;
	project_count: number;
	total_sessions: number;
}

export const load: PageServerLoad = async ({ fetch }) => {
	const result = await safeFetch<RemoteUser[]>(fetch, `${API_BASE}/remote/users`);
	if (!result.ok) {
		console.error('Failed to fetch remote users:', result.message);
		return { users: [], error: result.message };
	}
	return { users: result.data, error: null };
};

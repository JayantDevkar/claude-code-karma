import type { PageServerLoad } from './$types';
import { API_BASE } from '$lib/config';
import { safeFetch } from '$lib/utils/api-fetch';

interface MemberListItem {
	name: string;
	device_id: string;
	connected: boolean;
	is_you: boolean;
	team_count: number;
	teams: string[];
	added_at: string;
}

interface MembersResponse {
	members: MemberListItem[];
	total: number;
}

export const load: PageServerLoad = async ({ fetch }) => {
	const result = await safeFetch<MembersResponse>(fetch, `${API_BASE}/sync/members`);

	return {
		members: result.ok ? result.data.members : [],
		total: result.ok ? result.data.total : 0,
		error: result.ok ? null : result.message
	};
};

import type { PageServerLoad } from './$types';
import { API_BASE } from '$lib/config';
import { safeFetch } from '$lib/utils/api-fetch';
import type { MemberProfile } from '$lib/api-types';

export const load: PageServerLoad = async ({ fetch, params }) => {
	const userId = params.user_id;

	const profileResult = await safeFetch<MemberProfile>(
		fetch,
		`${API_BASE}/sync/members/${encodeURIComponent(userId)}`
	);

	return {
		userId,
		profile: profileResult.ok ? profileResult.data : null,
		error: profileResult.ok ? null : profileResult.message
	};
};

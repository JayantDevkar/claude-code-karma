import type { PageServerLoad } from './$types';
import { API_BASE } from '$lib/config';
import { safeFetch, fetchWithFallback } from '$lib/utils/api-fetch';
import type { MemberProfile, SyncDevice, RemoteSessionUser } from '$lib/api-types';

export const load: PageServerLoad = async ({ fetch, params }) => {
	const userId = params.user_id;

	const [profileResult, devicesData, remoteUserData] = await Promise.all([
		safeFetch<MemberProfile>(fetch, `${API_BASE}/sync/members/${encodeURIComponent(userId)}`),
		fetchWithFallback<{ devices: SyncDevice[] }>(fetch, `${API_BASE}/sync/devices`, {
			devices: []
		}),
		fetchWithFallback<RemoteSessionUser[]>(fetch, `${API_BASE}/remote/users`, [])
	]);

	const remoteUser = (Array.isArray(remoteUserData) ? remoteUserData : []).find(
		(u) => u.user_id === userId
	);

	return {
		userId,
		profile: profileResult.ok ? profileResult.data : null,
		error: profileResult.ok ? null : profileResult.message,
		devices: devicesData.devices ?? [],
		remoteUser: remoteUser ?? null
	};
};

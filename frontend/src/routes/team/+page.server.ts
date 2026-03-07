import type { PageServerLoad } from './$types';
import { API_BASE } from '$lib/config';
import { fetchAllWithFallbacks } from '$lib/utils/api-fetch';
import type { SyncStatusResponse, SyncTeam } from '$lib/api-types';

export const load: PageServerLoad = async ({ fetch }) => {
	const [syncStatus, teamsData] = await fetchAllWithFallbacks(fetch, [
		{
			url: `${API_BASE}/sync/status`,
			fallback: { configured: false } as SyncStatusResponse
		},
		{
			url: `${API_BASE}/sync/teams`,
			fallback: { teams: [] as SyncTeam[] }
		}
	] as const);

	return {
		syncStatus,
		teams: teamsData.teams ?? []
	};
};

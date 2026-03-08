import type { PageServerLoad } from './$types';
import { API_BASE } from '$lib/config';
import { fetchAllWithFallbacks } from '$lib/utils/api-fetch';
import type { SyncStatusResponse, SyncTeam, PendingDevice } from '$lib/api-types';

export const load: PageServerLoad = async ({ fetch }) => {
	const [syncStatus, teamsData, pendingData] = await fetchAllWithFallbacks(fetch, [
		{
			url: `${API_BASE}/sync/status`,
			fallback: { configured: false } as SyncStatusResponse
		},
		{
			url: `${API_BASE}/sync/teams`,
			fallback: { teams: [] as SyncTeam[] }
		},
		{
			url: `${API_BASE}/sync/pending-devices`,
			fallback: { devices: [] as PendingDevice[] }
		}
	] as const);

	return {
		syncStatus,
		teams: teamsData.teams ?? [],
		pendingDevices: pendingData.devices ?? []
	};
};

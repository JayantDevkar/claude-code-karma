import type { PageServerLoad } from './$types';
import { API_BASE } from '$lib/config';
import { fetchAllWithFallbacks } from '$lib/utils/api-fetch';
import type { SyncStatusResponse, SyncTeam, PendingDevice } from '$lib/api-types';

export const load: PageServerLoad = async ({ fetch }) => {
	// Fetch sync status + pending-devices first. The pending-devices endpoint
	// triggers auto-accept of karma peers, which may add new team members.
	const [syncStatus, pendingData] = await fetchAllWithFallbacks(fetch, [
		{
			url: `${API_BASE}/sync/status`,
			fallback: { configured: false } as SyncStatusResponse
		},
		{
			url: `${API_BASE}/sync/pending-devices`,
			fallback: { devices: [] as PendingDevice[], auto_accepted: 0 }
		}
	] as const);

	// Fetch teams AFTER auto-accept so member counts are up-to-date
	const [teamsData] = await fetchAllWithFallbacks(fetch, [
		{
			url: `${API_BASE}/sync/teams`,
			fallback: { teams: [] as SyncTeam[] }
		}
	] as const);

	return {
		syncStatus,
		teams: teamsData.teams ?? [],
		pendingDevices: pendingData.devices ?? [],
		autoAccepted: (pendingData as any).auto_accepted ?? 0
	};
};

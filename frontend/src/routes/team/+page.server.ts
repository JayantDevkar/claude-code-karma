import type { PageServerLoad } from './$types';
import { API_BASE } from '$lib/config';
import { fetchAllWithFallbacks } from '$lib/utils/api-fetch';
import type { SyncStatusResponse, SyncTeam, SyncSubscription } from '$lib/api-types';

export const load: PageServerLoad = async ({ fetch }) => {
	const [syncStatus, teamsData, subsData] = await fetchAllWithFallbacks(fetch, [
		{
			url: `${API_BASE}/sync/status`,
			fallback: { configured: false } as SyncStatusResponse
		},
		{
			url: `${API_BASE}/sync/teams`,
			fallback: { teams: [] as SyncTeam[] }
		},
		{
			url: `${API_BASE}/sync/subscriptions`,
			fallback: { subscriptions: [] as SyncSubscription[] }
		}
	] as const);

	// Count offered subscriptions per team
	const subs: SyncSubscription[] = subsData.subscriptions ?? [];
	const pendingByTeam: Record<string, number> = {};
	for (const s of subs) {
		if (s.status === 'offered') {
			pendingByTeam[s.team_name] = (pendingByTeam[s.team_name] ?? 0) + 1;
		}
	}

	return {
		syncStatus,
		teams: teamsData.teams ?? [],
		pendingByTeam
	};
};

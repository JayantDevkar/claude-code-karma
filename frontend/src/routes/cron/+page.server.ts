import type { CronListResponse, CronProjectRollupResponse } from '$lib/api-types';
import { API_BASE } from '$lib/config';
import { fetchWithFallback } from '$lib/utils/api-fetch';

export async function load({ url, fetch }) {
	const project = url.searchParams.get('project') ?? '';
	const active_only = url.searchParams.get('active_only') ?? '';
	const limit = url.searchParams.get('limit') ?? '200';

	const qs = new URLSearchParams();
	if (project) qs.set('project', project);
	if (active_only) qs.set('active_only', active_only);
	if (limit) qs.set('limit', limit);
	const queryString = qs.toString();

	const [cronData, rollupData] = await Promise.all([
		fetchWithFallback<CronListResponse>(
			fetch,
			`${API_BASE}/cron${queryString ? `?${queryString}` : ''}`,
			{ jobs: [], count: 0 }
		),
		fetchWithFallback<CronProjectRollupResponse>(fetch, `${API_BASE}/cron/project-rollup`, {
			projects: [],
			count: 0
		})
	]);

	return {
		jobs: cronData?.jobs ?? [],
		count: cronData?.count ?? 0,
		rollup: rollupData?.projects ?? [],
		filters: { project, active_only, limit }
	};
}

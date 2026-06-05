import type { ShellsListResponse, ShellsProjectRollupResponse } from '$lib/api-types';
import { API_BASE } from '$lib/config';
import { fetchWithFallback } from '$lib/utils/api-fetch';

export async function load({ url, fetch }) {
	const project = url.searchParams.get('project') ?? '';
	const status = url.searchParams.get('status') ?? '';
	const tool = url.searchParams.get('tool') ?? '';
	const limit = url.searchParams.get('limit') ?? '200';

	const qs = new URLSearchParams();
	if (project) qs.set('project', project);
	if (status) qs.set('status', status);
	if (tool) qs.set('tool', tool);
	if (limit) qs.set('limit', limit);
	const queryString = qs.toString();

	const [shellsData, rollupData] = await Promise.all([
		fetchWithFallback<ShellsListResponse>(
			fetch,
			`${API_BASE}/shells${queryString ? `?${queryString}` : ''}`,
			{ shells: [], count: 0 }
		),
		fetchWithFallback<ShellsProjectRollupResponse>(fetch, `${API_BASE}/shells/project-rollup`, {
			projects: [],
			count: 0
		})
	]);

	return {
		shells: shellsData?.shells ?? [],
		count: shellsData?.count ?? 0,
		rollup: rollupData?.projects ?? [],
		filters: { project, status, tool, limit }
	};
}

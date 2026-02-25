import type { PlanListResponse, Project } from '$lib/api-types';
import { API_BASE } from '$lib/config';
import { fetchWithFallback } from '$lib/utils/api-fetch';

export async function load({ fetch, url }) {
	const search = url.searchParams.get('search') || '';
	const project = url.searchParams.get('project') || '';
	const branch = url.searchParams.get('branch') || '';
	const page = parseInt(url.searchParams.get('page') || '1', 10);
	const perPage = parseInt(url.searchParams.get('per_page') || '24', 10);

	// Build query params for API
	const params = new URLSearchParams();
	if (search) params.set('search', search);
	if (project) params.set('project', project);
	if (branch) params.set('branch', branch);
	params.set('page', page.toString());
	params.set('per_page', perPage.toString());

	const [plansResponse, projects] = await Promise.all([
		fetchWithFallback<PlanListResponse>(fetch, `${API_BASE}/plans/with-context?${params}`, {
			plans: [],
			total: 0,
			page: 1,
			per_page: 24,
			total_pages: 0
		}),
		fetchWithFallback<Project[]>(fetch, `${API_BASE}/projects`, [])
	]);

	return { plansResponse, projects, search, project, branch, page, perPage };
}

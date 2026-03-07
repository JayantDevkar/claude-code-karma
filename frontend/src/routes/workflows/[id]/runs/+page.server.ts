import type { WorkflowRun, Workflow } from '$lib/api-types';
import { API_BASE } from '$lib/config';
import { fetchWithFallback } from '$lib/utils/api-fetch';
import { error } from '@sveltejs/kit';

export async function load({ fetch, params }) {
	const [workflow, runs] = await Promise.all([
		fetch(`${API_BASE}/workflows/${params.id}`).then((r) => {
			if (!r.ok) throw error(404, 'Workflow not found');
			return r.json() as Promise<Workflow>;
		}),
		fetchWithFallback<WorkflowRun[]>(fetch, `${API_BASE}/workflows/${params.id}/runs`, [])
	]);
	return { workflow, runs };
}

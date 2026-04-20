import type { WorkflowRun, Workflow } from '$lib/api-types';
import { API_BASE } from '$lib/config';
import { error } from '@sveltejs/kit';

export async function load({ fetch, params }) {
	const [workflow, run] = await Promise.all([
		fetch(`${API_BASE}/workflows/${params.id}`).then((r) => {
			if (!r.ok) throw error(404, 'Workflow not found');
			return r.json() as Promise<Workflow>;
		}),
		fetch(`${API_BASE}/workflows/${params.id}/runs/${params.run_id}`).then((r) => {
			if (!r.ok) throw error(404, 'Run not found');
			return r.json() as Promise<WorkflowRun>;
		})
	]);
	return { workflow, run };
}

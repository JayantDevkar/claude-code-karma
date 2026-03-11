import type { Workflow } from '$lib/api-types';
import { API_BASE } from '$lib/config';
import { error } from '@sveltejs/kit';

export async function load({ fetch, params }) {
	const resp = await fetch(`${API_BASE}/workflows/${params.id}`);
	if (!resp.ok) {
		throw error(404, 'Workflow not found');
	}
	const workflow: Workflow = await resp.json();
	return { workflow };
}

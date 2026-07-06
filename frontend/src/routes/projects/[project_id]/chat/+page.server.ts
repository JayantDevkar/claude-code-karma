import type { Project } from '$lib/api-types';
import { API_BASE } from '$lib/config';

export async function load({ params, fetch }) {
	try {
		const res = await fetch(`${API_BASE}/projects/${params.project_id}`);
		if (!res.ok) return { project: null, project_id: params.project_id };
		const project: Project = await res.json();
		return { project, project_id: params.project_id };
	} catch {
		return { project: null, project_id: params.project_id };
	}
}

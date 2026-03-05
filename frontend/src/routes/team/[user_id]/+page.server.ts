import type { PageServerLoad } from './$types';
import { API_BASE } from '$lib/config';
import { safeFetch } from '$lib/utils/api-fetch';

interface RemoteProject {
	encoded_name: string;
	session_count: number;
	synced_at: string | null;
	machine_id: string | null;
}

interface RemoteSession {
	uuid: string;
	mtime: string;
	size_bytes: number;
}

interface ProjectWithSessions extends RemoteProject {
	sessions: RemoteSession[];
}

export const load: PageServerLoad = async ({ params, fetch }) => {
	const userId = encodeURIComponent(params.user_id);
	const result = await safeFetch<RemoteProject[]>(
		fetch,
		`${API_BASE}/remote/users/${userId}/projects`
	);
	if (!result.ok) {
		console.error('Failed to fetch user projects:', result.message);
		return { user_id: params.user_id, projects: [], error: result.message };
	}

	// Fetch sessions for each project
	const projects: ProjectWithSessions[] = await Promise.all(
		result.data.map(async (project) => {
			const sessResult = await safeFetch<RemoteSession[]>(
				fetch,
				`${API_BASE}/remote/users/${userId}/projects/${encodeURIComponent(project.encoded_name)}/sessions`
			);
			return {
				...project,
				sessions: sessResult.ok ? sessResult.data : []
			};
		})
	);

	return { user_id: params.user_id, projects, error: null };
};

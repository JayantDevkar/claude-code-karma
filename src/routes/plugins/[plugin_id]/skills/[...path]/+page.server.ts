import type { PageServerLoad } from './$types';

const API_BASE = 'http://localhost:8000';

export const load: PageServerLoad = async ({ params, fetch }) => {
	const { plugin_id, path } = params;
	const decodedPluginId = decodeURIComponent(plugin_id);

	try {
		const url = new URL(`${API_BASE}/plugins/${plugin_id}/skills/content`);
		url.searchParams.set('path', path);

		const res = await fetch(url);

		if (!res.ok) {
			return {
				plugin_id: decodedPluginId,
				path,
				skill: null,
				error: res.status === 404 ? 'Skill not found' : 'Failed to load skill'
			};
		}

		const skill = await res.json();
		return {
			plugin_id: decodedPluginId,
			path,
			skill,
			error: null
		};
	} catch (error) {
		console.error('Failed to fetch skill content:', error);
		return {
			plugin_id: decodedPluginId,
			path,
			skill: null,
			error: 'Failed to load skill content'
		};
	}
};

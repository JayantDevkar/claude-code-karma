import type { PageServerLoad } from './$types';
import { API_BASE } from '$lib/config';
import { joinTitle } from '$lib/page-title';

export const load: PageServerLoad = async ({ params, fetch }) => {
	const { plugin_id, path } = params;
	const decodedPluginId = decodeURIComponent(plugin_id);
	const title = joinTitle([path.split('/').pop(), decodedPluginId.split('@')[0]]);

	try {
		const url = new URL(`${API_BASE}/plugins/${plugin_id}/skills/content`);
		url.searchParams.set('path', path);

		const res = await fetch(url);

		if (!res.ok) {
			return {
				plugin_id: decodedPluginId,
				path,
				skill: null,
				title: res.status === 404 ? 'Skill not found' : title,
				error: res.status === 404 ? 'Skill not found' : 'Failed to load skill'
			};
		}

		const skill = await res.json();
		return {
			plugin_id: decodedPluginId,
			path,
			skill,
			title,
			error: null
		};
	} catch (error) {
		console.error('Failed to fetch skill content:', error);
		return {
			plugin_id: decodedPluginId,
			path,
			skill: null,
			title,
			error: 'Failed to load skill content'
		};
	}
};

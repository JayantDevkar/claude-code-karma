import type { PageServerLoad } from './$types';
import { API_BASE } from '$lib/config';
import { joinTitle } from '$lib/page-title';

export const load: PageServerLoad = async ({ params, fetch }) => {
	const { plugin_id } = params;
	const decodedPluginId = decodeURIComponent(plugin_id);
	const title = joinTitle([`${decodedPluginId.split('@')[0]} Skills`, 'Plugins']);

	try {
		// Fetch plugin details and skills in parallel
		const [pluginRes, skillsRes] = await Promise.all([
			fetch(`${API_BASE}/plugins/${plugin_id}`),
			fetch(`${API_BASE}/plugins/${plugin_id}/skills`)
		]);

		const plugin = pluginRes.ok ? await pluginRes.json() : null;
		const skills = skillsRes.ok ? await skillsRes.json() : [];

		return {
			plugin_id: decodedPluginId,
			plugin,
			skills,
			title: pluginRes.ok ? title : 'Plugin not found',
			error: !pluginRes.ok ? 'Plugin not found' : null
		};
	} catch (error) {
		console.error('Failed to fetch plugin skills:', error);
		return {
			plugin_id: decodedPluginId,
			plugin: null,
			skills: [],
			title,
			error: 'Failed to load plugin skills'
		};
	}
};

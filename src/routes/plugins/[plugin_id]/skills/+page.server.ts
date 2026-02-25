import type { PageServerLoad } from './$types';

const API_BASE = 'http://localhost:8000';

export const load: PageServerLoad = async ({ params, fetch }) => {
	const { plugin_id } = params;
	const decodedPluginId = decodeURIComponent(plugin_id);

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
			error: !pluginRes.ok ? 'Plugin not found' : null
		};
	} catch (error) {
		console.error('Failed to fetch plugin skills:', error);
		return {
			plugin_id: decodedPluginId,
			plugin: null,
			skills: [],
			error: 'Failed to load plugin skills'
		};
	}
};

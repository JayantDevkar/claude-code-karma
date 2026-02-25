import { API_BASE } from '$lib/config';
import type { PluginDetail } from '$lib/api-types';
import { error } from '@sveltejs/kit';

export async function load({ params, fetch }) {
	const pluginName = decodeURIComponent(params.plugin_name);

	try {
		const res = await fetch(`${API_BASE}/plugins/${encodeURIComponent(pluginName)}`);

		if (res.status === 404) {
			throw error(404, `Plugin '${pluginName}' not found`);
		}

		if (!res.ok) {
			throw error(500, 'Failed to load plugin details');
		}

		const plugin: PluginDetail = await res.json();
		return { plugin };
	} catch (err) {
		if ((err as { status?: number }).status) {
			throw err;
		}
		throw error(500, 'Failed to connect to API');
	}
}

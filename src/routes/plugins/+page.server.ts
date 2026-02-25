import { API_BASE } from '$lib/config';
import type { PluginsOverview } from '$lib/api-types';

export async function load({ fetch }) {
	try {
		const res = await fetch(`${API_BASE}/plugins?include_usage=false`);
		if (!res.ok) {
			console.error('Failed to fetch plugins:', res.status);
			return { plugins: null, error: 'Failed to load plugins' };
		}
		const data: PluginsOverview = await res.json();
		return { plugins: data, error: null };
	} catch (err) {
		console.error('Error fetching plugins:', err);
		return { plugins: null, error: 'Failed to connect to API' };
	}
}

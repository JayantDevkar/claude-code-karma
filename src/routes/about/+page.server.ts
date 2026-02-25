import { API_BASE } from '$lib/config';
import { safeFetch } from '$lib/utils/api-fetch';

interface DocItem {
	name: string;
	title: string;
	path: string;
	size_bytes: number;
	modified_at: string;
}

interface DocsListResponse {
	docs: DocItem[];
}

export async function load({ fetch }) {
	const result = await safeFetch<DocsListResponse>(fetch, `${API_BASE}/docs/about`);

	if (!result.ok) {
		return { docs: [], error: result.message };
	}

	return { docs: result.data?.docs ?? [], error: null };
}

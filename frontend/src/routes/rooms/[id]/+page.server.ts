import type { RoomDetail } from '$lib/api-types';
import { API_BASE } from '$lib/config';
import { safeFetch } from '$lib/utils/api-fetch';
import { error } from '@sveltejs/kit';

export async function load({ fetch, params }) {
	const result = await safeFetch<RoomDetail>(
		fetch,
		`${API_BASE}/rooms/${encodeURIComponent(params.id)}`
	);

	if (!result.ok) {
		if (result.status === 404) {
			throw error(404, `Room not found: ${params.id}`);
		}
		throw error(result.status || 500, result.message);
	}

	return {
		detail: result.data
	};
}

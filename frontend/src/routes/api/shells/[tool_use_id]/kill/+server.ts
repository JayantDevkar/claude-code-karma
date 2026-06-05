import { API_BASE } from '$lib/config';
import { json } from '@sveltejs/kit';
import type { RequestHandler } from './$types';

export const POST: RequestHandler = async ({ params }) => {
	const res = await fetch(`${API_BASE}/shells/${encodeURIComponent(params.tool_use_id)}/kill`, {
		method: 'POST'
	});
	const data = await res.json();
	return json(data, { status: res.status });
};

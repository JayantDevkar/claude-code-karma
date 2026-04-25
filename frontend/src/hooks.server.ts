import type { Handle } from '@sveltejs/kit';

export const handle: Handle = async ({ event, resolve }) => {
	const apiBase = process.env.KARMA_API_URL || 'http://localhost:8000';
	return resolve(event, {
		transformPageChunk: ({ html }) => html.replace('%karma_api_base%', apiBase)
	});
};

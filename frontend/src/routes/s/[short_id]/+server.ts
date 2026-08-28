import { error, redirect } from '@sveltejs/kit';
import { API_BASE } from '$lib/config';
import type { RequestHandler } from './$types';

interface SessionResolveResult {
	uuid: string;
	project_encoded_name: string;
	slug: string | null;
}

/**
 * Short session links: /s/{uuid-or-prefix} → the session's project page.
 *
 * Compact enough for a terminal statusline or the `karma` shell command
 * (the first 8 hex chars of the session UUID are all it takes).
 */
export const GET: RequestHandler = async ({ params, fetch }) => {
	let res: Response;
	try {
		res = await fetch(`${API_BASE}/sessions/resolve/${encodeURIComponent(params.short_id)}`);
	} catch {
		error(502, 'Could not reach the Karma API to resolve this session link.');
	}

	if (res.status === 404) {
		error(404, `No session matches "${params.short_id}".`);
	}
	if (!res.ok) {
		error(502, `Could not resolve session link "${params.short_id}".`);
	}

	const session: SessionResolveResult = await res.json();
	// UUID prefix as the identifier — the project session page accepts it and,
	// unlike the slug, it never collides within a resumed chain. Lands on the
	// Timeline tab, matching the dock/switcher's own session links.
	redirect(
		302,
		`/projects/${session.project_encoded_name}/${session.uuid.slice(0, 8)}?tab=timeline`
	);
};

import type { PlanDetail, PlanRelatedSession, PlanSessionContext } from '$lib/api-types';
import { API_BASE } from '$lib/config';
import { safeFetch, fetchWithFallback } from '$lib/utils/api-fetch';
import { error } from '@sveltejs/kit';

export async function load({ params, fetch }) {
	const { slug } = params;

	// Fetch plan detail + context (fast, required for initial render)
	const [planResult, sessionContext] = await Promise.all([
		safeFetch<PlanDetail>(fetch, `${API_BASE}/plans/${slug}`),
		fetchWithFallback<PlanSessionContext | null>(
			fetch,
			`${API_BASE}/plans/${slug}/context`,
			null
		)
	]);

	if (!planResult.ok) {
		if (planResult.status === 404) {
			error(404, {
				message: `Plan "${slug}" not found`
			});
		}
		error(planResult.status || 500, {
			message: planResult.message || 'Failed to load plan'
		});
	}

	// Related sessions are slow (scans all sessions) — stream without blocking page render
	const relatedSessions = fetchWithFallback<PlanRelatedSession[]>(
		fetch,
		`${API_BASE}/plans/${slug}/sessions`,
		[]
	);

	return {
		plan: planResult.data,
		slug,
		sessionContext,
		relatedSessions
	};
}

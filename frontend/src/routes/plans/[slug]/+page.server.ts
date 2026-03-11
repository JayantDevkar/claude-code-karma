import type { PlanDetail, PlanRelatedSession, PlanSessionContext } from '$lib/api-types';
import { API_BASE } from '$lib/config';
import { safeFetch, fetchWithFallback } from '$lib/utils/api-fetch';
import { error } from '@sveltejs/kit';

export async function load({ params, fetch, url }) {
	const { slug } = params;
	const remoteUser = url.searchParams.get('remote_user') || '';

	// Build plan URL (with remote_user param for remote plans)
	const planUrl = remoteUser
		? `${API_BASE}/plans/${slug}?remote_user=${encodeURIComponent(remoteUser)}`
		: `${API_BASE}/plans/${slug}`;

	// Fetch plan detail + context (fast, required for initial render)
	const [planResult, sessionContext] = await Promise.all([
		safeFetch<PlanDetail>(fetch, planUrl),
		// Remote plans don't have local session context
		remoteUser
			? Promise.resolve(null)
			: fetchWithFallback<PlanSessionContext | null>(
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

	// Related sessions: for remote plans, use linked_sessions from the response;
	// for local plans, stream from the sessions endpoint
	const relatedSessions = remoteUser
		? Promise.resolve([])
		: fetchWithFallback<PlanRelatedSession[]>(
				fetch,
				`${API_BASE}/plans/${slug}/sessions`,
				[]
			);

	return {
		plan: planResult.data,
		slug,
		sessionContext,
		relatedSessions,
		remoteUser: remoteUser || null,
		// For remote plans, linked_sessions come embedded in the plan response
		linkedSessions: (planResult.data as any)?.linked_sessions ?? []
	};
}

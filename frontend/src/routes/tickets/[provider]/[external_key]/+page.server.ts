import type { Ticket } from '$lib/api-types';
import { API_BASE } from '$lib/config';
import { safeFetch, fetchWithFallback } from '$lib/utils/api-fetch';

interface TicketSessionRow {
	link_id: number;
	session_uuid: string;
	session_slug: string | null;
	link_source: 'branch' | 'slash_command' | 'dashboard';
	linked_at: string;
	sessions_slug: string | null;
	project_encoded_name: string | null;
	start_time: string | null;
	end_time: string | null;
	initial_prompt: string | null;
}

export async function load({ params, fetch }) {
	const { provider, external_key } = params;
	// external_key may contain '/' for GitHub-style refs; SvelteKit's
	// dynamic param won't capture beyond the next segment. The route
	// dir nests as /tickets/[provider]/[external_key] so this works for
	// Linear/Jira; for GitHub the URL must be percent-encoded ('%2F' or
	// alternatively the index uses encodeURIComponent on the link).
	const keyEncoded = encodeURIComponent(external_key);

	const [ticketResult, sessions] = await Promise.all([
		safeFetch<Ticket>(fetch, `${API_BASE}/tickets/${provider}/${keyEncoded}`),
		fetchWithFallback<TicketSessionRow[]>(
			fetch,
			`${API_BASE}/tickets/${provider}/${keyEncoded}/sessions`,
			[]
		)
	]);

	if (!ticketResult.ok) {
		return {
			ticket: null,
			sessions: [] as TicketSessionRow[],
			provider,
			external_key,
			error: ticketResult.message ?? 'Ticket not found'
		};
	}

	return {
		ticket: ticketResult.data,
		sessions: sessions ?? [],
		provider,
		external_key,
		error: null
	};
}

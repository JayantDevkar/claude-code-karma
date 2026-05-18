import type { TicketListItem } from '$lib/api-types';
import { API_BASE } from '$lib/config';
import { fetchWithFallback } from '$lib/utils/api-fetch';

export async function load({ url, fetch }) {
	const provider = url.searchParams.get('provider') ?? '';
	const q = url.searchParams.get('q') ?? '';
	const project = url.searchParams.get('project') ?? '';

	const qs = new URLSearchParams();
	if (provider) qs.set('provider', provider);
	if (q) qs.set('q', q);
	if (project) qs.set('project', project);
	const queryString = qs.toString();

	const tickets = await fetchWithFallback<TicketListItem[]>(
		fetch,
		`${API_BASE}/tickets${queryString ? `?${queryString}` : ''}`,
		[]
	);

	return {
		tickets: tickets ?? [],
		filters: { provider, q, project }
	};
}

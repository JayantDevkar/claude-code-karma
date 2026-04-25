import type { RoomListResponse, RoomStatus } from '$lib/api-types';
import { API_BASE } from '$lib/config';
import { safeFetch } from '$lib/utils/api-fetch';

export async function load({ fetch, url }) {
	const status = (url.searchParams.get('status') as RoomStatus | null) ?? null;
	const search = url.searchParams.get('search') ?? '';
	const sort = (url.searchParams.get('sort') as 'activity' | 'created' | null) ?? 'activity';

	const params = new URLSearchParams();
	if (status) params.set('status', status);
	if (search) params.set('search', search);
	params.set('sort', sort);

	const result = await safeFetch<RoomListResponse>(
		fetch,
		`${API_BASE}/rooms?${params.toString()}`
	);

	if (!result.ok) {
		return {
			rooms: [],
			total: 0,
			error: result.message,
			filters: { status, search, sort }
		};
	}

	return {
		rooms: result.data.rooms,
		total: result.data.total,
		error: null,
		filters: { status, search, sort }
	};
}

import { API_BASE } from '$lib/config';
import { fetchWithFallback } from '$lib/utils/api-fetch';

interface DashboardStats {
	period: 'today' | 'yesterday' | 'this_week' | 'none';
	start_date: string;
	end_date: string;
	sessions_count: number;
	projects_active: number;
	duration_seconds: number;
}

export async function load({ fetch }) {
	const stats = await fetchWithFallback<DashboardStats | null>(fetch, `${API_BASE}/analytics/dashboard`, null);
	return { stats };
}

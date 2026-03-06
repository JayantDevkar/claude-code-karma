import type { PageServerLoad } from './$types';
import { API_BASE } from '$lib/config';
import { safeFetch } from '$lib/utils/api-fetch';

// Type definitions for API responses
interface SyncDetect {
	installed: boolean;
	running: boolean;
	version: string | null;
	device_id: string | null;
	uptime: number | null;
}

interface SyncStatusResponse {
	configured: boolean;
	user_id?: string;
	machine_id?: string;
	teams?: Record<string, unknown>;
}

export const load: PageServerLoad = async ({ fetch, url }) => {
	const [detectResult, statusResult] = await Promise.all([
		safeFetch<SyncDetect>(fetch, `${API_BASE}/sync/detect`),
		safeFetch<SyncStatusResponse>(fetch, `${API_BASE}/sync/status`)
	]);

	const activeTab = url.searchParams.get('tab') || null;

	return {
		detect: detectResult.ok ? detectResult.data : null,
		status: statusResult.ok ? statusResult.data : null,
		activeTab
	};
};

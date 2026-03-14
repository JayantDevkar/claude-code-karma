import type { PageServerLoad } from './$types';
import type { SyncDetect, SyncStatusResponse } from '$lib/api-types';
import { API_BASE } from '$lib/config';
import { safeFetch } from '$lib/utils/api-fetch';

export const load: PageServerLoad = async ({ fetch }) => {
	const [detectResult, statusResult] = await Promise.all([
		safeFetch<SyncDetect>(fetch, `${API_BASE}/sync/detect`),
		safeFetch<SyncStatusResponse>(fetch, `${API_BASE}/sync/status`)
	]);

	return {
		detect: detectResult.ok ? detectResult.data : null,
		status: statusResult.ok ? statusResult.data : null
	};
};

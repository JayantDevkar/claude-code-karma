import type { PageServerLoad } from './$types';
import type { SyncDetect, SyncStatusResponse, SyncWatchStatus } from '$lib/api-types';
import { API_BASE } from '$lib/config';
import { safeFetch } from '$lib/utils/api-fetch';

export const load: PageServerLoad = async ({ fetch }) => {
	const [detectResult, statusResult, watchResult] = await Promise.all([
		safeFetch<SyncDetect>(fetch, `${API_BASE}/sync/detect`),
		safeFetch<SyncStatusResponse>(fetch, `${API_BASE}/sync/status`),
		safeFetch<SyncWatchStatus>(fetch, `${API_BASE}/sync/watch/status`)
	]);

	return {
		detect: detectResult.ok ? detectResult.data : null,
		status: statusResult.ok ? statusResult.data : null,
		watchStatus: watchResult.ok ? watchResult.data : null
	};
};

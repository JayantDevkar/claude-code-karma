import type { PageServerLoad } from './$types';
import type { SyncDetect, SyncStatusResponse, SyncWatchStatus, SyncPendingFolder } from '$lib/api-types';
import { API_BASE } from '$lib/config';
import { safeFetch } from '$lib/utils/api-fetch';

export const load: PageServerLoad = async ({ fetch }) => {
	const [detectResult, statusResult, watchResult, pendingResult] = await Promise.all([
		safeFetch<SyncDetect>(fetch, `${API_BASE}/sync/detect`),
		safeFetch<SyncStatusResponse>(fetch, `${API_BASE}/sync/status`),
		safeFetch<SyncWatchStatus>(fetch, `${API_BASE}/sync/watch/status`),
		safeFetch<{ pending: SyncPendingFolder[] }>(fetch, `${API_BASE}/sync/pending`)
	]);

	return {
		detect: detectResult.ok ? detectResult.data : null,
		status: statusResult.ok ? statusResult.data : null,
		watchStatus: watchResult.ok ? watchResult.data : null,
		pending: pendingResult.ok ? pendingResult.data?.pending ?? [] : []
	};
};

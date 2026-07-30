/**
 * Shared live-sessions polling feed — ref-counted so the poll runs once no
 * matter how many consumers (dock, switcher, LIVE NOW sections) are mounted.
 */

import { writable } from 'svelte/store';
import { API_BASE, POLLING_INTERVALS } from '$lib/config';
import type { LiveSessionSummary } from '$lib/api-types';

export interface LiveSessionsFeedStatus {
	loading: boolean;
	error: string | null;
}

function createLiveSessionsFeed() {
	const { subscribe, set } = writable<LiveSessionSummary[]>([]);
	const status = writable<LiveSessionsFeedStatus>({ loading: true, error: null });

	let refCount = 0;
	let interval: ReturnType<typeof setInterval> | null = null;
	let abortController: AbortController | null = null;

	async function fetchOnce() {
		abortController?.abort();
		abortController = new AbortController();
		try {
			const res = await fetch(`${API_BASE}/live-sessions/active`, {
				signal: abortController.signal
			});
			if (res.ok) {
				set(await res.json());
				status.set({ loading: false, error: null });
			} else {
				status.set({
					loading: false,
					error: res.status === 404 ? 'API not available' : 'Failed to fetch'
				});
			}
		} catch (e) {
			if (e instanceof Error && e.name === 'AbortError') return;
			// Best-effort — leave the last known list in place on transient errors.
			status.set({ loading: false, error: 'Cannot connect to API' });
		}
	}

	function start() {
		refCount++;
		if (refCount === 1) {
			fetchOnce();
			interval = setInterval(fetchOnce, POLLING_INTERVALS.LIVE_SESSIONS);
		}
	}

	function stop() {
		refCount = Math.max(0, refCount - 1);
		if (refCount === 0 && interval) {
			clearInterval(interval);
			interval = null;
			abortController?.abort();
		}
	}

	return { subscribe, status: { subscribe: status.subscribe }, start, stop, refresh: fetchOnce };
}

export const liveSessionsFeed = createLiveSessionsFeed();

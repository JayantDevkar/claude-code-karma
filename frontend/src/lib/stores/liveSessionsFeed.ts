/**
 * Shared live-sessions polling feed.
 *
 * LiveSessionsDock and SessionSwitcher both need the same active-session
 * list; this ref-counts subscribers so the poll runs once regardless of how
 * many consumers are mounted, and stops when none are.
 */

import { writable } from 'svelte/store';
import { API_BASE, POLLING_INTERVALS } from '$lib/config';
import type { LiveSessionSummary } from '$lib/api-types';

function createLiveSessionsFeed() {
	const { subscribe, set } = writable<LiveSessionSummary[]>([]);

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
			}
		} catch (e) {
			if (e instanceof Error && e.name === 'AbortError') return;
			// Best-effort — leave the last known list in place on transient errors.
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

	return { subscribe, start, stop, refresh: fetchOnce };
}

export const liveSessionsFeed = createLiveSessionsFeed();

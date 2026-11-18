import { untrack } from 'svelte';
import { IndexStillRebuildingError, fetchWhenIndexed, isAbort } from './indexRebuilding';

/** loading: first request; rebuilding: waiting on the index; stalled: gave up waiting; error: final failure */
export type IndexedTabStatus = 'idle' | 'loading' | 'rebuilding' | 'stalled' | 'error' | 'loaded';

/** Loads a tab's data once the tab is shown, waiting out an index rebuild; call during component init. */
export function createIndexedTab<T>(getUrl: () => string, isActive: () => boolean) {
	let status = $state<IndexedTabStatus>('idle');
	let data = $state<T | null>(null);
	let error = $state<string | null>(null);
	let attempt = $state(0);

	$effect(() => {
		void attempt;
		// Hidden tab panels stay mounted, so nothing is requested until the tab is actually shown.
		if (!isActive()) return;
		const settled = untrack(
			() => status === 'loaded' || status === 'error' || status === 'stalled'
		);
		if (settled) return;

		const controller = new AbortController();
		status = 'loading';
		fetchWhenIndexed<T>(getUrl(), {
			signal: controller.signal,
			onRebuilding: (rebuilding) => {
				if (!controller.signal.aborted) status = rebuilding ? 'rebuilding' : 'loading';
			}
		})
			.then((result) => {
				data = result;
				status = 'loaded';
			})
			.catch((e) => {
				if (isAbort(e) || controller.signal.aborted) return;
				if (e instanceof IndexStillRebuildingError) {
					status = 'stalled';
					return;
				}
				error = e instanceof Error ? e.message : String(e);
				status = 'error';
			});
		// Leaving the tab, or the page, stops the wait; coming back starts it again.
		return () => controller.abort();
	});

	return {
		get status() {
			return status;
		},
		get data() {
			return data;
		},
		get error() {
			return error;
		},
		/** Start over after a stalled wait or an error. */
		retry() {
			error = null;
			status = 'idle';
			attempt += 1;
		}
	};
}

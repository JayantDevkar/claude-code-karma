import { browser } from '$app/environment';

/**
 * Create a pair of $effect callbacks for syncing a view mode to/from URL `?view=` param.
 * Call both returned functions inside your component's `<script>` block as `$effect` bodies.
 *
 * Usage:
 *   const { initFromUrl, syncToUrl } = createUrlViewState('groups', validViews, () => activeView, (v) => activeView = v);
 *   $effect(initFromUrl);
 *   $effect(syncToUrl);
 */
export function createUrlViewState<T extends string>(
	defaultView: T,
	validViews: readonly T[],
	getView: () => T,
	setView: (v: T) => void
): { ready: { value: boolean }; initFromUrl: () => void; syncToUrl: () => void } {
	const ready = { value: false };

	function initFromUrl() {
		if (!browser || ready.value) return;
		const params = new URLSearchParams(window.location.search);
		const view = params.get('view');
		if (view && (validViews as readonly string[]).includes(view)) {
			setView(view as T);
		}
		ready.value = true;
	}

	function syncToUrl() {
		if (!browser || !ready.value) return;
		const current = getView();
		const url = new URL(window.location.href);
		if (current === defaultView) url.searchParams.delete('view');
		else url.searchParams.set('view', current);
		history.replaceState({}, '', url.toString());
	}

	return { ready, initFromUrl, syncToUrl };
}

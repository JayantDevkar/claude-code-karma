/**
 * Svelte action that post-processes a rendered markdown container to convert
 * `[text](some-file.md)` anchors into in-app interactive references.
 *
 * For every `<a href="...something.md">` inside the container:
 *   1. If the basename matches a known file in `params.files`, mark it as a
 *      memory link, attach hover/leave/click listeners, prevent default
 *      navigation, and add styling hooks.
 *   2. If the basename does NOT match, mark it as a broken memory link
 *      (dashed muted underline, native title tooltip).
 *
 * The action stores per-anchor listener references so cleanup is precise and
 * doesn't leak. `update()` re-runs the wiring whenever params (most importantly
 * the files list) change, and on each {@html} content swap (the parent calls
 * `update` by passing fresh params via `use:rewriteMemoryLinks={...}`).
 *
 * Hover delay (150ms before showing the popover) is intentionally NOT
 * implemented here — it lives in the parent shell, which receives the immediate
 * onHover call and debounces visually. The action's job is only DOM wiring.
 */

import type { MemoryFileMeta } from '$lib/api-types';

export interface RewriteMemoryLinksParams {
	files: MemoryFileMeta[];
	onHover: (filename: string, rect: DOMRect) => void;
	onLeave: () => void;
	onSelect: (filename: string) => void;
}

interface AttachedListeners {
	enter: (e: MouseEvent) => void;
	leave: (e: MouseEvent) => void;
	click: (e: MouseEvent) => void;
}

const MEMORY_LINK_CLASS = 'memory-link';
const MEMORY_LINK_BROKEN_CLASS = 'memory-link--broken';

/**
 * Extract the basename of a markdown link href, ignoring any fragment/query.
 * Returns null if href doesn't end with `.md` (after stripping #/?).
 */
function extractMdBasename(href: string): string | null {
	if (!href) return null;
	// Strip fragment and query
	const cleaned = href.split('#')[0].split('?')[0];
	if (!cleaned.toLowerCase().endsWith('.md')) return null;
	// Take basename
	const idx = cleaned.lastIndexOf('/');
	const base = idx >= 0 ? cleaned.slice(idx + 1) : cleaned;
	return base || null;
}

export function rewriteMemoryLinks(node: HTMLElement, params: RewriteMemoryLinksParams) {
	let current = params;
	const attached = new Map<HTMLAnchorElement, AttachedListeners>();

	function teardownAll() {
		attached.forEach((listeners, anchor) => {
			anchor.removeEventListener('mouseenter', listeners.enter);
			anchor.removeEventListener('mouseleave', listeners.leave);
			anchor.removeEventListener('click', listeners.click);
			anchor.classList.remove(MEMORY_LINK_CLASS);
			anchor.classList.remove(MEMORY_LINK_BROKEN_CLASS);
			anchor.removeAttribute('data-memory-file');
		});
		attached.clear();
	}

	function rewire() {
		teardownAll();

		const filenameSet = new Set(current.files.map((f) => f.filename));
		const anchors = node.querySelectorAll<HTMLAnchorElement>('a');

		anchors.forEach((anchor) => {
			const rawHref = anchor.getAttribute('href');
			if (!rawHref) return;
			const basename = extractMdBasename(rawHref);
			if (!basename) return;

			if (filenameSet.has(basename)) {
				anchor.classList.add(MEMORY_LINK_CLASS);
				anchor.setAttribute('data-memory-file', basename);

				const enter = (_e: MouseEvent) => {
					const rect = anchor.getBoundingClientRect();
					current.onHover(basename, rect);
				};
				const leave = (_e: MouseEvent) => {
					current.onLeave();
				};
				const click = (e: MouseEvent) => {
					e.preventDefault();
					e.stopPropagation();
					current.onSelect(basename);
				};

				anchor.addEventListener('mouseenter', enter);
				anchor.addEventListener('mouseleave', leave);
				anchor.addEventListener('click', click);
				attached.set(anchor, { enter, leave, click });
			} else {
				// Unknown .md target — mark as broken so it picks up muted styling
				anchor.classList.add(MEMORY_LINK_BROKEN_CLASS);
				anchor.setAttribute('title', 'file not found in memory directory');
			}
		});
	}

	// MutationObserver: re-wire whenever {@html} swaps the container's children.
	// Watch direct children only (matches markdownCopyButtons pattern) so our
	// own class/attribute mutations don't trigger feedback loops.
	const observer = new MutationObserver((mutations) => {
		const hasContentChange = mutations.some((m) =>
			Array.from(m.addedNodes).some((n) => n instanceof Element)
		);
		if (hasContentChange) {
			// Defer to next microtask so the new DOM is fully attached
			setTimeout(rewire, 0);
		}
	});
	observer.observe(node, { childList: true, subtree: false });

	// Initial wiring (in case content is already populated on mount)
	if (node.children.length > 0) {
		rewire();
	}

	return {
		update(newParams: RewriteMemoryLinksParams) {
			current = newParams;
			rewire();
		},
		destroy() {
			observer.disconnect();
			teardownAll();
		}
	};
}

import type { SessionSummary, LiveSessionSummary } from '$lib/api-types';

/**
 * Compute the URL path segment used by SessionCard.svelte when linking to a
 * session detail page. The project-scoped last-opened-highlight on the back-nav
 * route compares against this so it matches the exact card the user clicked.
 *
 * - Chain sessions use a 12-char UUID prefix to disambiguate (bumped from 8:
 *   with 8 hex chars the birthday collision probability is non-trivial across
 *   large session histories; 12 chars brings it to effectively zero).
 * - Non-chain sessions prefer the live slug, then the stored slug,
 *   then fall back to the UUID prefix.
 *
 * Note: GlobalSessionCard.svelte uses `getSessionDisplayLabel` from this module
 * for display, and `getSessionUrlIdentifier` for URL/navigation identifiers.
 */
export function getSessionUrlIdentifier(
	session: SessionSummary,
	liveSession?: LiveSessionSummary | null
): string {
	const isPartOfChain = session.chain_info !== undefined && session.chain_info !== null;
	if (isPartOfChain) {
		return session.uuid.slice(0, 12);
	}
	const displaySlug = liveSession?.slug ?? session.slug;
	return displaySlug || session.uuid.slice(0, 12);
}

/**
 * Returns a short human-readable label for a session to use in list/card displays.
 * Prefers the live slug, then stored slug, then a 12-char UUID prefix.
 * Centralizes the display logic so GlobalSessionCard and LiveSessionsTerminal
 * don't inline their own `slice(0, 8)` calls.
 */
export function getSessionDisplayLabel(
	uuid: string,
	slug?: string | null,
	liveSlug?: string | null
): string {
	return liveSlug ?? slug ?? uuid.slice(0, 12);
}

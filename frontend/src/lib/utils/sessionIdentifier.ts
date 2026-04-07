import type { SessionSummary, LiveSessionSummary } from '$lib/api-types';

/**
 * Compute the URL path segment used by SessionCard.svelte when linking to a
 * session detail page. The project-scoped last-opened-highlight on the back-nav
 * route compares against this so it matches the exact card the user clicked.
 *
 * - Chain sessions always use an 8-char UUID prefix (to disambiguate).
 * - Non-chain sessions prefer the live slug, then the stored slug,
 *   then fall back to the UUID prefix.
 *
 * Note: GlobalSessionCard.svelte uses `session.uuid.slice(0, 8)` unconditionally
 * and does not call this helper — its navigation behavior is intentionally
 * uuid-only, so the global /sessions highlight comparison uses the raw prefix.
 */
export function getSessionUrlIdentifier(
	session: SessionSummary,
	liveSession?: LiveSessionSummary | null
): string {
	const isPartOfChain = session.chain_info !== undefined && session.chain_info !== null;
	if (isPartOfChain) {
		return session.uuid.slice(0, 8);
	}
	const displaySlug = liveSession?.slug ?? session.slug;
	return displaySlug || session.uuid.slice(0, 8);
}

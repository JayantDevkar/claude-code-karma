/**
 * Shared visual + semantic helpers for the ticket feature.
 *
 * Keeps the per-provider color / letter-mark / glyph and the status
 * normalization in one place so badges, inputs, the index page, and the
 * detail page all agree.
 */

import type { TicketProvider } from '$lib/api-types';

export interface ProviderMeta {
	label: string; // "Linear"
	short: string; // "LIN" — letter-mark used on the colored chip
	/** CSS var name for the industry-flavored background color. */
	colorVar: string;
	/** CSS var name for the same color at low alpha. */
	subtleVar: string;
	/** CSS var name for the foreground (letter-mark text) color.
	 * Flips per-mode so chips stay AA-legible in dark mode — GitHub's silver
	 * bg needs dark text, Jira's lightened blue does too. */
	fgVar: string;
}

export const PROVIDER_META: Record<TicketProvider, ProviderMeta> = {
	linear: {
		label: 'Linear',
		short: 'LIN',
		colorVar: '--provider-linear',
		subtleVar: '--provider-linear-subtle',
		fgVar: '--provider-linear-fg'
	},
	jira: {
		label: 'Jira',
		short: 'JIR',
		colorVar: '--provider-jira',
		subtleVar: '--provider-jira-subtle',
		fgVar: '--provider-jira-fg'
	},
	github: {
		label: 'GitHub',
		short: 'GH',
		colorVar: '--provider-github',
		subtleVar: '--provider-github-subtle',
		fgVar: '--provider-github-fg'
	}
};

/** Normalized status keys used to pick a status-dot color. */
export type StatusKey =
	| 'todo'
	| 'active'
	| 'review'
	| 'done'
	| 'closed'
	| 'unknown';

const STATUS_COLOR_VARS: Record<StatusKey, string> = {
	todo: '--status-todo',
	active: '--status-active',
	review: '--status-review',
	done: '--status-done',
	closed: '--status-closed',
	unknown: '--text-faint'
};

export function statusColorVar(k: StatusKey): string {
	return STATUS_COLOR_VARS[k];
}

/**
 * Map each provider's native status vocabulary onto a small shared set,
 * preserving the verbatim string so the UI can render both a normalized
 * dot and the original label side-by-side.
 *
 * Unknown / future statuses fall through to 'active' (visible signal)
 * rather than 'unknown' (gray) to avoid making in-flight work look stale.
 */
export interface NormalizedStatus {
	key: StatusKey;
	verbatim: string | null;
}

export function normalizeStatus(status: string | null | undefined): NormalizedStatus {
	if (!status) return { key: 'unknown', verbatim: null };
	const s = status.toLowerCase().trim();
	if (s === 'open' || s === 'to do' || s === 'todo' || s === 'backlog' || s === 'triage') {
		return { key: 'todo', verbatim: status };
	}
	if (s === 'in progress' || s === 'doing' || s === 'in development') {
		return { key: 'active', verbatim: status };
	}
	if (s === 'in review' || s === 'review' || s === 'code review') {
		return { key: 'review', verbatim: status };
	}
	if (s === 'closed') {
		return { key: 'closed', verbatim: status };
	}
	if (s === 'done' || s === 'resolved' || s === 'merged') {
		return { key: 'done', verbatim: status };
	}
	if (s === 'canceled' || s === 'cancelled' || s === 'wontfix' || s === "won't fix") {
		return { key: 'closed', verbatim: status };
	}
	return { key: 'active', verbatim: status };
}

/**
 * GitHub-specific ticket subtype derived from the stored URL.
 *
 * GitHub uses one numbering namespace for issues and pull requests but
 * distinct URL paths (`/issues/N` vs `/pull/N`) and distinct semantics
 * — PRs carry draft/merged state, issues don't. The backend stores the
 * URL verbatim from the parser; the UI derives the kind from the URL
 * at render time. This avoids a schema asymmetry (Linear/Jira have no
 * equivalent concept) and stays accurate without an extra DB column.
 *
 * Returns `'pull_request'` only when the URL is unambiguously a PR
 * (contains `/pull/<digits>`). Bare/unknown URLs fall through to
 * `'issue'` since GitHub auto-redirects `/issues/N` to `/pull/N` when
 * N is actually a PR — those rows are visually-correct-but-imprecise,
 * not broken.
 */
export type GithubKind = 'issue' | 'pull_request';

export function githubKindFromUrl(url: string | null | undefined): GithubKind {
	if (!url) return 'issue';
	// Parse to URL so the `/pull/N` check only ever looks at the pathname.
	// A regex over the raw string would false-positive on URLs that happen
	// to contain `/pull/<digits>` inside a query string (e.g. an issue URL
	// with `?file=/pull/9`). Backend canonical URLs are stripped of query
	// strings today, so this is defensive — but the regex was wider than
	// the test claimed, which is a class of patchy we shouldn't keep.
	try {
		const path = new URL(url).pathname;
		return /^\/[^/]+\/[^/]+\/pull\/\d+(?:\/|$)/i.test(path)
			? 'pull_request'
			: 'issue';
	} catch {
		// Malformed URL — fall back to 'issue' (the safe default per the
		// docstring above).
		return 'issue';
	}
}

/** Client-side parse so the link input can auto-detect provider as the user types. */
export function detectProviderFromRef(ref: string): TicketProvider | null {
	const s = ref.trim();
	if (!s) return null;
	if (/linear\.app/i.test(s)) return 'linear';
	if (/\.atlassian\.(net|com)/i.test(s)) return 'jira';
	if (/github\.com/i.test(s)) return 'github';
	if (/^[\w.-]+\/[\w.-]+#\d+$/.test(s)) return 'github';
	return null;
}

/** True if `ref` is a bare alphanumeric key (e.g. `OCC-1284`) — needs a provider hint. */
export function isAmbiguousKey(ref: string): boolean {
	const s = ref.trim();
	return s.length > 0 && /^[A-Z][A-Z0-9_]*-\d+$/i.test(s);
}

/**
 * Best-effort relative-time formatter — matches the style used elsewhere
 * in the dashboard (e.g. "9m ago", "2h ago", "3d ago").
 */
export function formatRelative(iso: string | null | undefined): string {
	if (!iso) return '—';
	const d = new Date(iso);
	const diff = Date.now() - d.getTime();
	const mins = Math.floor(diff / 60000);
	if (mins < 1) return 'just now';
	if (mins < 60) return `${mins}m ago`;
	const hrs = Math.floor(mins / 60);
	if (hrs < 24) return `${hrs}h ago`;
	const days = Math.floor(hrs / 24);
	if (days < 30) return `${days}d ago`;
	return d.toLocaleDateString();
}

/** project_encoded_name → short display ("-Users-x-GitHub-claude-karma" → "claude-karma"). */
export function projectDisplayName(encoded: string | null | undefined): string {
	if (!encoded) return 'Unindexed';
	const parts = encoded.split('-').filter(Boolean);
	return parts.length > 0 ? parts[parts.length - 1] : encoded;
}

/**
 * Shared type badge helpers for memory file type labels.
 *
 * Used by MemoryHoverCard, MemoryFilePanel, and MemoryOrphanList to
 * render a consistent pill badge per memory type (user/feedback/project/
 * reference) or a muted fallback when the type is null.
 *
 * Tailwind utility classes are used directly (rather than CSS custom
 * properties) because the four accent colors do not have corresponding
 * tokens in app.css. The `/15` alpha tint reads correctly in both light
 * and dark themes.
 */

import type { MemoryFileType } from '$lib/api-types';

const BADGE_BASE =
	'inline-flex items-center rounded-full px-2 py-0.5 text-[10px] font-medium uppercase tracking-wide ring-1';

export const TYPE_BADGE_CLASSES: Record<MemoryFileType, string> = {
	user: 'bg-blue-500/15 text-blue-600 dark:text-blue-400 ring-blue-500/20',
	feedback: 'bg-amber-500/15 text-amber-600 dark:text-amber-400 ring-amber-500/20',
	project: 'bg-violet-500/15 text-violet-600 dark:text-violet-400 ring-violet-500/20',
	reference: 'bg-emerald-500/15 text-emerald-600 dark:text-emerald-400 ring-emerald-500/20'
};

export const TYPE_LABELS: Record<MemoryFileType, string> = {
	user: 'User',
	feedback: 'Feedback',
	project: 'Project',
	reference: 'Reference'
};

/**
 * Returns the complete Tailwind class string for a memory type badge.
 *
 * @param type  - Memory file type (null → neutral muted styling)
 * @param extra - Optional extra classes appended after the base
 *                (e.g. `'shrink-0'` for rows where the badge must not flex)
 */
export function badgeClass(type: MemoryFileType | null, extra = ''): string {
	const base = extra ? `${BADGE_BASE} ${extra}` : BADGE_BASE;
	if (type === null) {
		return `${base} bg-[var(--bg-muted)] text-[var(--text-muted)] ring-[var(--border)]`;
	}
	return `${base} ${TYPE_BADGE_CLASSES[type]}`;
}

/**
 * Returns the human-readable label for a memory type badge.
 * Falls back to an em dash for null types.
 */
export function badgeLabel(type: MemoryFileType | null): string {
	return type === null ? '—' : TYPE_LABELS[type];
}

/**
 * Shared display helpers for live session lists — used by LiveSessionsSection,
 * LiveSessionsDock, and SessionSwitcher so all three render sessions identically.
 */

import type { LiveSessionSummary } from '$lib/api-types';
import { projectHrefFromSession } from '$lib/utils/project-url';

export function formatDuration(seconds: number): string {
	const mins = Math.floor(seconds / 60);
	const hrs = Math.floor(mins / 60);
	if (hrs > 0) return `${hrs}h ${mins % 60}m`;
	if (mins > 0) return `${mins}m`;
	return `${Math.floor(seconds)}s`;
}

export function formatIdleTime(seconds: number): string {
	if (seconds < 60) return `${Math.floor(seconds)}s`;
	const mins = Math.floor(seconds / 60);
	return `${mins}m`;
}

const SKIP_DIRS = ['Users', 'home', 'Documents', 'GitHub', 'Projects', 'repos', 'src'];
const NESTED_DIRS = new Set(['frontend', 'backend', 'api', 'src', 'app']);

export function getProjectDisplayName(session: LiveSessionSummary): string {
	const parts = session.cwd.split('/').filter(Boolean);

	for (let i = parts.length - 1; i >= 0; i--) {
		const part = parts[i];
		if (!SKIP_DIRS.includes(part) && part.length > 2) {
			if (i > 0 && NESTED_DIRS.has(part)) {
				return parts[i - 1] || part;
			}
			return part;
		}
	}

	return parts[parts.length - 1] || 'Unknown';
}

export function canNavigate(session: LiveSessionSummary): boolean {
	return !!session.project_encoded_name;
}

export function getSessionUrl(session: LiveSessionSummary, tab?: string): string {
	if (!session.project_encoded_name) {
		return '#';
	}
	const identifier = session.slug || session.session_id.slice(0, 8);
	const suffix = tab ? `/${identifier}?tab=${tab}` : `/${identifier}`;
	return projectHrefFromSession(session, suffix);
}

export function getDisplayName(session: LiveSessionSummary): string {
	return session.slug || session.session_id.slice(0, 8);
}

/** Sessions worth showing: not ended, and not ghosts whose transcript never materialized. */
export function visibleLiveSessions(sessions: LiveSessionSummary[]): LiveSessionSummary[] {
	return sessions.filter((s) => s.status !== 'ended' && s.transcript_exists !== false);
}

/** True when the current route (`/projects/[id]/[session_slug]`) points at this session. */
export function matchesRoute(pathname: string, session: LiveSessionSummary): boolean {
	const parts = pathname.split('/').filter(Boolean);
	if (parts[0] !== 'projects' || parts.length < 3) return false;
	// Slugs are LLM-generated and collide across projects — the project segment must match too.
	const projectMatches =
		parts[1] === session.project_slug || parts[1] === session.project_encoded_name;
	if (!projectMatches) return false;
	const routeIdentifier = parts[2];
	return routeIdentifier === session.slug || routeIdentifier === session.session_id.slice(0, 8);
}

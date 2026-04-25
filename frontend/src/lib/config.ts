/**
 * Centralized configuration for Claude Code Karma frontend.
 *
 * API Base URL:
 * - Uses PUBLIC_API_URL environment variable if set
 * - Falls back to http://localhost:8000 for local development
 *
 * To configure in production:
 * - Set PUBLIC_API_URL in your .env file
 * - Or set it in your deployment environment
 */

/**
 * API base URL for all backend requests.
 * @example
 * ```ts
 * import { API_BASE } from '$lib/config';
 * const response = await fetch(`${API_BASE}/projects`);
 * ```
 */
// Server-side (SSR): KARMA_API_URL is injected into process.env by bin/start.js at launch.
// Client-side: __KARMA_API_BASE__ is injected into HTML by hooks.server.ts at request time.
// Dev mode fallback: Vite's PUBLIC_API_URL env var or localhost default.
type KarmaWindow = Window & { __KARMA_API_BASE__?: string };
export const API_BASE: string =
	typeof window === 'undefined'
		? (process.env.KARMA_API_URL ?? 'http://localhost:8000')
		: (window as KarmaWindow).__KARMA_API_BASE__ &&
			  (window as KarmaWindow).__KARMA_API_BASE__ !== '%karma_api_base%'
			? (window as KarmaWindow).__KARMA_API_BASE__!
			: import.meta.env.PUBLIC_API_URL ?? 'http://localhost:8000';

/**
 * API request timeout in milliseconds (default: 30 seconds)
 */
export const API_TIMEOUT = 30_000;

/**
 * Polling intervals for real-time data
 */
export const POLLING_INTERVALS = {
	/** Live sessions polling interval (ms) */
	LIVE_SESSIONS: 2_000,
	/** Historical data polling interval (ms) */
	HISTORICAL_DATA: 30_000
} as const;

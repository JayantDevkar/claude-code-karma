/**
 * Centralized configuration for Claude Code Karma frontend.
 *
 * API Base URL:
 * - Uses PUBLIC_API_URL environment variable if set
 * - In the browser, falls back to /backend, which Vite proxies to the API
 * - During SSR, falls back to http://localhost:8020
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
export const API_BASE =
	typeof window === 'undefined'
		? // SSR runs next to the API inside the container.
			'http://localhost:8020'
		: // The browser must not hardcode localhost: served under a domain that
			// address points at the visitor's own machine, and the API would reject
			// the cross-origin request anyway. /backend is proxied by Vite.
			import.meta.env.PUBLIC_API_URL || '/backend';

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

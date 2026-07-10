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
import { env } from '$env/dynamic/public';

// PUBLIC_API_URL via SvelteKit's dynamic public env: import.meta.env never
// exposes PUBLIC_-prefixed vars (only VITE_), so the documented override
// silently never worked and every deployment leaned on the fallback.
export const API_BASE =
	env.PUBLIC_API_URL || import.meta.env.PUBLIC_API_URL || 'http://localhost:8020';

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
	HISTORICAL_DATA: 30_000,
	/** Sync status polling interval (ms) */
	SYNC_STATUS: 10_000
} as const;

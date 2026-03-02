/**
 * Centralized configuration for Claude Code Karma frontend.
 *
 * API Base URL:
 * - Browser: Uses PUBLIC_API_URL env var, or `/api` (for Caddy reverse proxy)
 * - SSR: Uses INTERNAL_API_URL env var (e.g. `http://api:8000` in Docker),
 *   or falls back to `http://localhost:8000` for local development
 *
 * Local dev: Set PUBLIC_API_URL=http://localhost:8000 in .env
 * Docker: INTERNAL_API_URL is set via docker-compose environment
 */

/**
 * API base URL for all backend requests.
 *
 * Two contexts need different URLs:
 * - Browser: relative `/api` (routed by Caddy) or PUBLIC_API_URL for local dev
 * - SSR (Node server): Docker internal `http://api:8000` via INTERNAL_API_URL
 *
 * @example
 * ```ts
 * import { API_BASE } from '$lib/config';
 * const response = await fetch(`${API_BASE}/projects`);
 * ```
 */
const BROWSER_API = import.meta.env.PUBLIC_API_URL || '/api';
const SERVER_API = (() => {
	try {
		return process.env.INTERNAL_API_URL || 'http://localhost:8000';
	} catch {
		return 'http://localhost:8000';
	}
})();

export const API_BASE = typeof window !== 'undefined' ? BROWSER_API : SERVER_API;

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

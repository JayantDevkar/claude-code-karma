/**
 * Safe API fetch utilities with proper error handling.
 *
 * Handles:
 * - Network errors (API unreachable)
 * - Non-JSON responses (e.g., "Internal Server Error" text)
 * - HTTP error status codes
 */

export interface ApiResult<T> {
	ok: true;
	data: T;
}

export interface ApiError {
	ok: false;
	status: number;
	message: string;
}

export type ApiResponse<T> = ApiResult<T> | ApiError;

/**
 * Safely fetch JSON from an API endpoint.
 *
 * Unlike raw fetch, this:
 * - Catches network errors
 * - Handles non-JSON error responses
 * - Returns a typed result object
 *
 * @param fetchFn - The fetch function (from SvelteKit load context)
 * @param url - API endpoint URL
 * @returns ApiResponse with either data or error info
 */
export async function safeFetch<T>(fetchFn: typeof fetch, url: string): Promise<ApiResponse<T>> {
	try {
		const response = await fetchFn(url);

		if (!response.ok) {
			// Try to get error detail from response body
			let message = `API error: ${response.status} ${response.statusText}`;
			try {
				const text = await response.text();
				// Check if it's JSON with a detail field
				if (text.startsWith('{')) {
					const json = JSON.parse(text);
					if (json.detail) {
						message = json.detail;
					}
				} else if (text.length < 200) {
					// Short text error message
					message = text || message;
				}
			} catch {
				// Ignore parse errors, use default message
			}

			return {
				ok: false,
				status: response.status,
				message
			};
		}

		// Parse JSON safely
		try {
			const data = await response.json();
			return { ok: true, data };
		} catch {
			return {
				ok: false,
				status: response.status,
				message: `Invalid JSON response from ${url}`
			};
		}
	} catch (networkError) {
		// Network error (API unreachable, CORS, etc.)
		return {
			ok: false,
			status: 0,
			message:
				networkError instanceof Error
					? networkError.message
					: 'Failed to connect to API server'
		};
	}
}

/**
 * Fetch with fallback value on error.
 *
 * Useful for optional/supplementary data that shouldn't fail the whole page.
 *
 * @param fetchFn - The fetch function
 * @param url - API endpoint URL
 * @param fallback - Value to return on error
 * @returns Data on success, fallback on error
 */
export async function fetchWithFallback<T>(
	fetchFn: typeof fetch,
	url: string,
	fallback: T
): Promise<T> {
	const result = await safeFetch<T>(fetchFn, url);
	if (result.ok) {
		return result.data;
	}
	console.warn(`API fetch failed for ${url}: ${result.message}`);
	return fallback;
}

/**
 * Parallel fetch multiple endpoints with individual fallbacks.
 *
 * Returns an array of results in the same order as inputs.
 * Each endpoint that fails returns its fallback value.
 */
export async function fetchAllWithFallbacks<T extends readonly unknown[]>(
	fetchFn: typeof fetch,
	requests: { [K in keyof T]: { url: string; fallback: T[K] } }
): Promise<T> {
	const results = await Promise.all(
		requests.map(({ url, fallback }) => fetchWithFallback(fetchFn, url, fallback))
	);
	return results as unknown as T;
}

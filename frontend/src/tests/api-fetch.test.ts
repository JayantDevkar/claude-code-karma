import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { safeFetch, fetchWithFallback, fetchAllWithFallbacks } from '$lib/utils/api-fetch';

// ============================================================
// Helpers to build mock fetch functions
// ============================================================

function mockFetchOk(data: unknown, contentType = 'application/json'): typeof fetch {
	return vi.fn().mockResolvedValue({
		ok: true,
		status: 200,
		statusText: 'OK',
		json: async () => data,
		text: async () => JSON.stringify(data),
		headers: new Headers({ 'content-type': contentType })
	} as unknown as Response);
}

function mockFetchHttpError(status: number, body: string, statusText = 'Error'): typeof fetch {
	return vi.fn().mockResolvedValue({
		ok: false,
		status,
		statusText,
		json: async () => { throw new Error('not json'); },
		text: async () => body
	} as unknown as Response);
}

function mockFetchNetworkError(message: string): typeof fetch {
	return vi.fn().mockRejectedValue(new Error(message));
}

function mockFetchInvalidJson(): typeof fetch {
	return vi.fn().mockResolvedValue({
		ok: true,
		status: 200,
		statusText: 'OK',
		json: async () => { throw new SyntaxError('Unexpected token'); },
		text: async () => 'not-json-at-all'
	} as unknown as Response);
}

// ============================================================
// safeFetch
// ============================================================
describe('safeFetch', () => {
	it('returns ok: true with data on successful JSON response', async () => {
		const payload = { sessions: [1, 2, 3] };
		const fetchFn = mockFetchOk(payload);
		const result = await safeFetch(fetchFn, '/api/sessions');
		expect(result.ok).toBe(true);
		if (result.ok) {
			expect(result.data).toEqual(payload);
		}
	});

	it('returns ok: false with JSON detail message on HTTP error', async () => {
		const fetchFn = mockFetchHttpError(404, JSON.stringify({ detail: 'Session not found' }), 'Not Found');
		const result = await safeFetch(fetchFn, '/api/sessions/bad-id');
		expect(result.ok).toBe(false);
		if (!result.ok) {
			expect(result.status).toBe(404);
			expect(result.message).toBe('Session not found');
		}
	});

	it('returns ok: false with text message on HTTP error with non-JSON body', async () => {
		const fetchFn = mockFetchHttpError(500, 'Internal Server Error', 'Internal Server Error');
		const result = await safeFetch(fetchFn, '/api/crash');
		expect(result.ok).toBe(false);
		if (!result.ok) {
			expect(result.status).toBe(500);
			expect(result.message).toBe('Internal Server Error');
		}
	});

	it('uses default message for HTTP error with long text body (>200 chars)', async () => {
		const longBody = 'x'.repeat(300);
		const fetchFn = mockFetchHttpError(503, longBody, 'Service Unavailable');
		const result = await safeFetch(fetchFn, '/api/something');
		expect(result.ok).toBe(false);
		if (!result.ok) {
			expect(result.status).toBe(503);
			// Long body is not used; falls back to default message
			expect(result.message).toContain('503');
		}
	});

	it('returns ok: false with status 0 on network error', async () => {
		const fetchFn = mockFetchNetworkError('Failed to fetch');
		const result = await safeFetch(fetchFn, '/api/anything');
		expect(result.ok).toBe(false);
		if (!result.ok) {
			expect(result.status).toBe(0);
			expect(result.message).toBe('Failed to fetch');
		}
	});

	it('returns ok: false on invalid JSON response (parse error)', async () => {
		const fetchFn = mockFetchInvalidJson();
		const result = await safeFetch(fetchFn, '/api/bad-json');
		expect(result.ok).toBe(false);
		if (!result.ok) {
			expect(result.message).toContain('Invalid JSON');
		}
	});

	it('returns generic error message when network error is not an Error instance', async () => {
		const fetchFn = vi.fn().mockRejectedValue('string error') as unknown as typeof fetch;
		const result = await safeFetch(fetchFn, '/api/anything');
		expect(result.ok).toBe(false);
		if (!result.ok) {
			expect(result.message).toBe('Failed to connect to API server');
		}
	});
});

// ============================================================
// fetchWithFallback
// ============================================================
describe('fetchWithFallback', () => {
	it('returns data on successful fetch', async () => {
		const payload = { count: 42 };
		const fetchFn = mockFetchOk(payload);
		const result = await fetchWithFallback(fetchFn, '/api/data', { count: 0 });
		expect(result).toEqual(payload);
	});

	it('returns fallback on HTTP error', async () => {
		const fetchFn = mockFetchHttpError(404, 'not found');
		const fallback = { items: [] };
		const result = await fetchWithFallback(fetchFn, '/api/missing', fallback);
		expect(result).toEqual(fallback);
	});

	it('returns fallback on network error', async () => {
		const fetchFn = mockFetchNetworkError('connection refused');
		const result = await fetchWithFallback(fetchFn, '/api/down', null);
		expect(result).toBeNull();
	});

	it('returns correct typed fallback (number)', async () => {
		const fetchFn = mockFetchNetworkError('error');
		const result = await fetchWithFallback(fetchFn, '/api/count', 0);
		expect(result).toBe(0);
	});

	it('returns correct typed fallback (empty array)', async () => {
		const fetchFn = mockFetchNetworkError('error');
		const result = await fetchWithFallback(fetchFn, '/api/list', []);
		expect(result).toEqual([]);
	});
});

// ============================================================
// fetchAllWithFallbacks
// ============================================================
describe('fetchAllWithFallbacks', () => {
	it('returns all data when all fetches succeed', async () => {
		const fetchFn = vi.fn()
			.mockResolvedValueOnce({
				ok: true, status: 200, json: async () => ({ a: 1 }), text: async () => ''
			})
			.mockResolvedValueOnce({
				ok: true, status: 200, json: async () => ({ b: 2 }), text: async () => ''
			}) as unknown as typeof fetch;

		const result = await fetchAllWithFallbacks(fetchFn, [
			{ url: '/api/a', fallback: { a: 0 } },
			{ url: '/api/b', fallback: { b: 0 } }
		] as any);

		expect(result[0]).toEqual({ a: 1 });
		expect(result[1]).toEqual({ b: 2 });
	});

	it('returns fallback for failed requests and data for successful ones', async () => {
		const fetchFn = vi.fn()
			.mockResolvedValueOnce({
				ok: true, status: 200, json: async () => ['item1'], text: async () => ''
			})
			.mockRejectedValueOnce(new Error('Network failure')) as unknown as typeof fetch;

		const result = await fetchAllWithFallbacks(fetchFn, [
			{ url: '/api/items', fallback: [] },
			{ url: '/api/other', fallback: ['fallback-item'] }
		] as any);

		expect(result[0]).toEqual(['item1']);
		expect(result[1]).toEqual(['fallback-item']);
	});

	it('returns all fallbacks when all requests fail', async () => {
		const fetchFn = vi.fn().mockRejectedValue(new Error('all down')) as unknown as typeof fetch;

		const result = await fetchAllWithFallbacks(fetchFn, [
			{ url: '/api/a', fallback: null },
			{ url: '/api/b', fallback: 0 },
			{ url: '/api/c', fallback: [] }
		] as any);

		expect(result[0]).toBeNull();
		expect(result[1]).toBe(0);
		expect(result[2]).toEqual([]);
	});

	it('returns empty array for empty requests', async () => {
		const fetchFn = vi.fn() as unknown as typeof fetch;
		const result = await fetchAllWithFallbacks(fetchFn, [] as any);
		expect(result).toEqual([]);
	});

	it('executes requests in parallel (all mocks called)', async () => {
		const fetchFn = vi.fn().mockResolvedValue({
			ok: true, status: 200, json: async () => ({}), text: async () => ''
		}) as unknown as typeof fetch;

		await fetchAllWithFallbacks(fetchFn, [
			{ url: '/api/1', fallback: {} },
			{ url: '/api/2', fallback: {} },
			{ url: '/api/3', fallback: {} }
		] as any);

		expect(fetchFn).toHaveBeenCalledTimes(3);
	});
});

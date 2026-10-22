import { describe, it, expect, vi, beforeEach } from 'vitest';
import {
	loadTabResource,
	peekTabResource,
	invalidateTabResource,
	clearTabResourceCache,
	cachedTabSessions
} from '$lib/components/conversation/tabData';

function okResponse(data: unknown): Response {
	return { ok: true, status: 200, json: async () => data } as unknown as Response;
}

function deferred<T>() {
	let resolve!: (value: T) => void;
	let reject!: (reason?: unknown) => void;
	const promise = new Promise<T>((res, rej) => {
		resolve = res;
		reject = rej;
	});
	return { promise, resolve, reject };
}

describe('loadTabResource', () => {
	beforeEach(() => {
		clearTabResourceCache();
	});

	it('shares one request between concurrent callers', async () => {
		const gate = deferred<Response>();
		const fetchFn = vi.fn(() => gate.promise);

		const a = loadTabResource('s1', 'timeline', '/t', fetchFn);
		const b = loadTabResource('s1', 'timeline', '/t', fetchFn);
		gate.resolve(okResponse([1, 2, 3]));

		const [ra, rb] = await Promise.all([a, b]);
		expect(fetchFn).toHaveBeenCalledTimes(1);
		expect(ra.data).toEqual([1, 2, 3]);
		expect(rb.data).toBe(ra.data);
	});

	it('serves a second call from the cache without fetching', async () => {
		const fetchFn = vi.fn(async () => okResponse(['x']));
		await loadTabResource('s1', 'subagents', '/s', fetchFn);
		const again = await loadTabResource('s1', 'subagents', '/s', fetchFn);

		expect(fetchFn).toHaveBeenCalledTimes(1);
		expect(again.data).toEqual(['x']);
		expect(peekTabResource('s1', 'subagents')).toEqual(['x']);
	});

	it('keeps kinds of one session apart', async () => {
		const fetchFn = vi.fn(async (url: string) => okResponse(url));
		await loadTabResource('s1', 'timeline', '/timeline', fetchFn);
		await loadTabResource('s1', 'file-activity', '/files', fetchFn);

		expect(fetchFn).toHaveBeenCalledTimes(2);
		expect(peekTabResource('s1', 'timeline')).toBe('/timeline');
		expect(peekTabResource('s1', 'file-activity')).toBe('/files');
	});

	it('evicts the least recently used session when a fourth is cached', async () => {
		const fetchFn = vi.fn(async () => okResponse([]));
		await loadTabResource('s1', 'timeline', '/1', fetchFn);
		await loadTabResource('s2', 'timeline', '/2', fetchFn);
		await loadTabResource('s3', 'timeline', '/3', fetchFn);
		// Reading s1 makes s2 the oldest
		expect(peekTabResource('s1', 'timeline')).toEqual([]);
		await loadTabResource('s4', 'timeline', '/4', fetchFn);

		expect(cachedTabSessions()).toEqual(['s3', 's1', 's4']);
		expect(peekTabResource('s2', 'timeline')).toBeUndefined();

		await loadTabResource('s2', 'timeline', '/2', fetchFn);
		expect(fetchFn).toHaveBeenCalledTimes(5);
	});

	it('refetches after invalidate', async () => {
		let n = 0;
		const fetchFn = vi.fn(async () => okResponse(++n));
		await loadTabResource('s1', 'timeline', '/t', fetchFn);
		await loadTabResource('s1', 'file-activity', '/f', fetchFn);

		invalidateTabResource('s1', 'timeline');
		expect(peekTabResource('s1', 'timeline')).toBeUndefined();
		expect(peekTabResource('s1', 'file-activity')).toBe(2);

		const fresh = await loadTabResource('s1', 'timeline', '/t', fetchFn);
		expect(fresh.data).toBe(3);
		expect(fetchFn).toHaveBeenCalledTimes(3);

		invalidateTabResource('s1');
		expect(peekTabResource('s1', 'timeline')).toBeUndefined();
		expect(peekTabResource('s1', 'file-activity')).toBeUndefined();
	});

	it('does not cache a response that was invalidated while in flight', async () => {
		const gate = deferred<Response>();
		const fetchFn = vi.fn(() => gate.promise);
		const pending = loadTabResource('s1', 'timeline', '/t', fetchFn);

		invalidateTabResource('s1', 'timeline');
		gate.resolve(okResponse(['old']));
		await pending;

		expect(peekTabResource('s1', 'timeline')).toBeUndefined();
	});

	it('tags each result with its session so a caller can drop a stale one', async () => {
		const slow = deferred<Response>();
		const fetchFn = vi.fn((url: string) =>
			url === '/a' ? slow.promise : Promise.resolve(okResponse(['b']))
		);

		let current = 'a';
		const forA = loadTabResource('a', 'timeline', '/a', fetchFn);
		current = 'b';
		const forB = await loadTabResource('b', 'timeline', '/b', fetchFn);
		slow.resolve(okResponse(['a']));
		const lateA = await forA;

		expect(forB.uuid).toBe(current);
		expect(lateA.uuid).toBe('a');
		expect(lateA.kind).toBe('timeline');
		expect(lateA.uuid === current).toBe(false);
	});

	it('rejects on an HTTP error and lets the next call retry', async () => {
		const fetchFn = vi
			.fn()
			.mockResolvedValueOnce({ ok: false, status: 500, json: async () => ({}) } as Response)
			.mockResolvedValueOnce(okResponse(['ok']));

		await expect(loadTabResource('s1', 'subagents', '/s', fetchFn)).rejects.toThrow('500');
		expect(peekTabResource('s1', 'subagents')).toBeUndefined();

		const retry = await loadTabResource('s1', 'subagents', '/s', fetchFn);
		expect(retry.data).toEqual(['ok']);
		expect(fetchFn).toHaveBeenCalledTimes(2);
	});
});

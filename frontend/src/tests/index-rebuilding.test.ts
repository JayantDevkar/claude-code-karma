import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, cleanup, fireEvent, waitFor } from '@testing-library/svelte';
import {
	INDEX_REBUILDING_MESSAGE,
	INDEX_STILL_REBUILDING_MESSAGE,
	IndexStillRebuildingError,
	MAX_WAIT_MS,
	fetchWhenIndexed,
	isAbort,
	isIndexRebuilding,
	retryAfterSeconds,
	retryDelayMs
} from '$lib/utils/indexRebuilding';
import SessionShellsSection from '$lib/components/shells/SessionShellsSection.svelte';
import SessionCronSection from '$lib/components/cron/SessionCronSection.svelte';

const rebuildingBody = { detail: 'The index is rebuilding. Try again in a moment.' };
const disabledBody = { detail: 'The SQLite index is turned off.' };

function json(status: number, body: unknown, headers: Record<string, string> = {}): Response {
	return new Response(JSON.stringify(body), {
		status,
		headers: { 'content-type': 'application/json', ...headers }
	});
}
const rebuilding = (retryAfter?: string) =>
	json(503, rebuildingBody, retryAfter ? { 'Retry-After': retryAfter } : {});

describe('index rebuilding responses', () => {
	it('reads the delay from Retry-After, with a floor, a ceiling and a 5 second fallback', () => {
		expect(retryAfterSeconds(rebuilding('2'))).toBe(2);
		expect(retryAfterSeconds(rebuilding())).toBe(5);
		expect(retryAfterSeconds(rebuilding('soon'))).toBe(5);
		expect(retryAfterSeconds(rebuilding('0.01'))).toBe(1);
		expect(retryAfterSeconds(rebuilding('9999'))).toBe(30);
	});

	it('backs off from the asked delay and never passes the ceiling', () => {
		expect(retryDelayMs(rebuilding('2'), 0)).toBe(2000);
		expect(retryDelayMs(rebuilding('2'), 1)).toBe(3000);
		expect(retryDelayMs(rebuilding('2'), 2)).toBe(4500);
		expect(retryDelayMs(rebuilding('2'), 20)).toBe(30000);
	});

	it('goes by what the answer says, not by the header alone', async () => {
		expect(await isIndexRebuilding(rebuilding())).toBe(true);
		expect(await isIndexRebuilding(json(503, disabledBody, { 'Retry-After': '5' }))).toBe(
			false
		);
		expect(await isIndexRebuilding(json(503, {}, { 'Retry-After': '5' }))).toBe(false);
		expect(await isIndexRebuilding(json(500, rebuildingBody))).toBe(false);
		expect(
			await isIndexRebuilding(new Response('<html>bad gateway</html>', { status: 503 }))
		).toBe(false);
	});
});

describe('fetchWhenIndexed', () => {
	beforeEach(() => vi.useFakeTimers());
	afterEach(() => vi.useRealTimers());

	it('waits the asked delay, then longer each time, until the data loads', async () => {
		const fetchFn = vi
			.fn()
			.mockResolvedValueOnce(rebuilding('2'))
			.mockResolvedValueOnce(rebuilding('2'))
			.mockResolvedValueOnce(json(200, { shells: [] }));
		const states: boolean[] = [];
		const result = fetchWhenIndexed<{ shells: unknown[] }>('/x', {
			fetchFn,
			onRebuilding: (value) => states.push(value)
		});

		await vi.advanceTimersByTimeAsync(1999);
		expect(fetchFn).toHaveBeenCalledTimes(1);
		await vi.advanceTimersByTimeAsync(1);
		expect(fetchFn).toHaveBeenCalledTimes(2);
		await vi.advanceTimersByTimeAsync(2999);
		expect(fetchFn).toHaveBeenCalledTimes(2);
		await vi.advanceTimersByTimeAsync(1);
		await expect(result).resolves.toEqual({ shells: [] });
		expect(states).toEqual([true, false]);
	});

	it('does not report rebuilding when the first answer is the data', async () => {
		const onRebuilding = vi.fn();
		const fetchFn = vi.fn().mockResolvedValue(json(200, { jobs: [] }));
		await expect(fetchWhenIndexed('/x', { fetchFn, onRebuilding })).resolves.toEqual({
			jobs: []
		});
		expect(onRebuilding).not.toHaveBeenCalled();
	});

	it('gives up after the cap instead of polling forever', async () => {
		const fetchFn = vi.fn().mockImplementation(async () => rebuilding('5'));
		const states: boolean[] = [];
		const result = fetchWhenIndexed('/x', { fetchFn, onRebuilding: (v) => states.push(v) });
		const settled = result.catch((e) => e);
		await vi.advanceTimersByTimeAsync(MAX_WAIT_MS + 1000);
		expect(await settled).toBeInstanceOf(IndexStillRebuildingError);
		const calls = fetchFn.mock.calls.length;
		expect(calls).toBeGreaterThan(3);
		expect(calls).toBeLessThan(20);
		await vi.advanceTimersByTimeAsync(MAX_WAIT_MS);
		expect(fetchFn).toHaveBeenCalledTimes(calls);
		expect(states).toEqual([true, false]);
	});

	it('treats any other answer as final and passes on what the API said', async () => {
		const fetchFn = vi.fn().mockImplementation(async () => json(503, disabledBody));
		await expect(fetchWhenIndexed('/x', { fetchFn })).rejects.toThrow(
			'The SQLite index is turned off.'
		);
		expect(fetchFn).toHaveBeenCalledTimes(1);
		fetchFn.mockImplementation(async () => json(500, {}));
		await expect(fetchWhenIndexed('/x', { fetchFn })).rejects.toThrow('API 500');
	});

	it('stops retrying when aborted', async () => {
		const controller = new AbortController();
		const fetchFn = vi.fn().mockImplementation(async () => rebuilding());
		const result = fetchWhenIndexed('/x', { fetchFn, signal: controller.signal });
		const settled = result.catch((e) => e);
		await vi.advanceTimersByTimeAsync(100);
		controller.abort();
		expect(isAbort(await settled)).toBe(true);
		await vi.advanceTimersByTimeAsync(60000);
		expect(fetchFn).toHaveBeenCalledTimes(1);
	});

	it('does not leave an abort listener behind for each retry', async () => {
		const controller = new AbortController();
		const add = vi.spyOn(controller.signal, 'addEventListener');
		const remove = vi.spyOn(controller.signal, 'removeEventListener');
		const fetchFn = vi
			.fn()
			.mockResolvedValueOnce(rebuilding('1'))
			.mockResolvedValueOnce(rebuilding('1'))
			.mockResolvedValueOnce(rebuilding('1'))
			.mockResolvedValueOnce(json(200, {}));
		const result = fetchWhenIndexed('/x', { fetchFn, signal: controller.signal });
		await vi.advanceTimersByTimeAsync(10000);
		await result;
		expect(add).toHaveBeenCalledTimes(3);
		expect(remove).toHaveBeenCalledTimes(3);
	});
});

describe('tabs that read the index', () => {
	let fetchMock: ReturnType<typeof vi.fn>;
	const props = { sessionUuid: '00000000-0000-4000-8000-000000000001' };

	beforeEach(() => {
		fetchMock = vi.fn();
		vi.stubGlobal('fetch', fetchMock);
	});

	afterEach(() => {
		cleanup();
		vi.unstubAllGlobals();
		vi.useRealTimers();
	});

	const cases = [
		{
			name: 'Shells',
			component: SessionShellsSection,
			data: { shells: [] },
			empty: /No background shells/
		},
		{
			name: 'Cron',
			component: SessionCronSection,
			data: { jobs: [] },
			empty: /No scheduled jobs/
		}
	];

	for (const tab of cases) {
		it(`${tab.name}: requests nothing while its tab is hidden, and loads when shown`, async () => {
			fetchMock.mockImplementation(async () => json(200, tab.data));
			const { container, rerender } = render(tab.component, {
				props: { ...props, active: false }
			});
			await new Promise((resolve) => setTimeout(resolve, 20));
			expect(fetchMock).not.toHaveBeenCalled();
			await rerender({ ...props, active: true });
			await waitFor(() => expect(container).toHaveTextContent(tab.empty));
			expect(fetchMock).toHaveBeenCalledTimes(1);
		});

		it(`${tab.name}: says the index is rebuilding, then loads without a reload`, async () => {
			fetchMock
				.mockResolvedValueOnce(rebuilding('1'))
				.mockImplementation(async () => json(200, tab.data));
			const { getByRole, queryByRole, container } = render(tab.component, { props });
			await waitFor(() =>
				expect(getByRole('status')).toHaveTextContent(INDEX_REBUILDING_MESSAGE)
			);
			expect(container).not.toHaveTextContent(/Failed to load/);
			await waitFor(() => expect(queryByRole('status')).toBeNull(), { timeout: 3000 });
			await waitFor(() => expect(container).toHaveTextContent(tab.empty));
			expect(fetchMock).toHaveBeenCalledTimes(2);
		});

		it(`${tab.name}: stops waiting when its tab is hidden again`, async () => {
			fetchMock.mockImplementation(async () => rebuilding('1'));
			const { getByRole, rerender } = render(tab.component, { props });
			await waitFor(() =>
				expect(getByRole('status')).toHaveTextContent(INDEX_REBUILDING_MESSAGE)
			);
			await rerender({ ...props, active: false });
			const calls = fetchMock.mock.calls.length;
			await new Promise((resolve) => setTimeout(resolve, 1300));
			expect(fetchMock).toHaveBeenCalledTimes(calls);
		});

		it(`${tab.name}: after the cap, says so and offers "Try again"`, async () => {
			vi.useFakeTimers({ shouldAdvanceTime: true });
			fetchMock.mockImplementation(async () => rebuilding('30'));
			const { getByRole, container } = render(tab.component, { props });
			await waitFor(() =>
				expect(getByRole('status')).toHaveTextContent(INDEX_REBUILDING_MESSAGE)
			);
			await vi.advanceTimersByTimeAsync(MAX_WAIT_MS + 1000);
			await waitFor(() =>
				expect(getByRole('status')).toHaveTextContent(INDEX_STILL_REBUILDING_MESSAGE)
			);
			const stalledCalls = fetchMock.mock.calls.length;

			fetchMock.mockImplementation(async () => json(200, tab.data));
			await fireEvent.click(getByRole('button', { name: 'Try again' }));
			await waitFor(() => expect(container).toHaveTextContent(tab.empty));
			expect(fetchMock).toHaveBeenCalledTimes(stalledCalls + 1);
		});

		it(`${tab.name}: shows a final answer, such as the index being off, as an error`, async () => {
			fetchMock.mockImplementation(async () => json(503, disabledBody));
			const { container, queryByRole } = render(tab.component, { props });
			await waitFor(() =>
				expect(container).toHaveTextContent('The SQLite index is turned off.')
			);
			expect(container).toHaveTextContent(/Failed to load/);
			expect(queryByRole('status')).toBeNull();
			expect(fetchMock).toHaveBeenCalledTimes(1);
		});
	}
});

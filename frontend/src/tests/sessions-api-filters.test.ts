import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { sessionsApiFilters } from '$lib/search';

describe('sessionsApiFilters', () => {
	beforeEach(() => {
		vi.useFakeTimers();
		vi.setSystemTime(new Date(2026, 9, 23, 15, 30, 0));
	});

	afterEach(() => {
		vi.useRealTimers();
	});

	it('never sends Live (the API status enum has no live value)', () => {
		expect(sessionsApiFilters('live', 'all')).toEqual({
			status: undefined,
			start_ts: undefined,
			end_ts: undefined
		});
	});

	it('passes Completed through and omits All', () => {
		expect(sessionsApiFilters('completed', 'all').status).toBe('completed');
		expect(sessionsApiFilters('all', 'all').status).toBeUndefined();
	});

	it('turns Today into a start_ts at local midnight', () => {
		expect(sessionsApiFilters('all', 'today')).toEqual({
			status: undefined,
			start_ts: String(new Date(2026, 9, 23).getTime()),
			end_ts: undefined
		});
	});

	it('turns Last 7 days into a start_ts seven days back, keeping Live client-side', () => {
		const week = 7 * 24 * 60 * 60 * 1000;
		expect(sessionsApiFilters('live', '7d')).toEqual({
			status: undefined,
			start_ts: String(new Date(2026, 9, 23, 15, 30, 0).getTime() - week),
			end_ts: undefined
		});
	});
});

import { describe, it, expect } from 'vitest';
import { endedByLabel } from '$lib/utils/endedBy';

const now = new Date('2026-01-10T11:00:00Z');

describe('endedByLabel', () => {
	it('shows reset time while it is in the future', () => {
		const r = endedByLabel('limit', '2026-01-10T12:00:00+00:00', now)!;
		expect(r.label).toMatch(/^Stopped by limit · resets /);
		expect(r.tone).toBe('warning');
	});

	it('drops reset time once passed or missing', () => {
		expect(endedByLabel('limit', '2026-01-10T10:00:00+00:00', now)!.label).toBe('Stopped by limit');
		expect(endedByLabel('limit', null, now)!.label).toBe('Stopped by limit');
		expect(endedByLabel('limit', 'garbage', now)!.label).toBe('Stopped by limit');
	});

	it('maps refusal and api_error', () => {
		const refusal = endedByLabel('refusal', null, now)!;
		expect(refusal.label).toBe('Refused');
		expect(refusal.tone).toBe('error');
		const err = endedByLabel('api_error', null, now)!;
		expect(err.label).toBe('Ended on API error');
		expect(err.tone).toBe('muted');
	});

	it('returns null when not ended by anything', () => {
		expect(endedByLabel(null, null, now)).toBeNull();
		expect(endedByLabel(undefined, null, now)).toBeNull();
	});
});

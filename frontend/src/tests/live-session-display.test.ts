import { describe, it, expect } from 'vitest';
import type { LiveSessionSummary } from '$lib/api-types';
import { getProjectDisplayName } from '$lib/utils/live-session-display';

const withCwd = (cwd: string) => ({ cwd }) as LiveSessionSummary;

describe('getProjectDisplayName', () => {
	it('names a Windows cwd by its folder, not the whole path', () => {
		expect(getProjectDisplayName(withCwd('C:\\Users\\me\\ClaudKarma'))).toBe('ClaudKarma');
	});

	it('uses the parent folder for a nested Windows subdir', () => {
		expect(getProjectDisplayName(withCwd('C:\\Users\\me\\ClaudKarma\\frontend'))).toBe(
			'ClaudKarma'
		);
	});
});

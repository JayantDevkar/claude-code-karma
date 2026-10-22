import { describe, it, expect } from 'vitest';
import { APP_NAME, formatTitle, joinTitle, routeTitle } from '$lib/page-title';

describe('formatTitle', () => {
	it('returns the app name with no parts', () => {
		expect(formatTitle([])).toBe(APP_NAME);
		expect(formatTitle([null, undefined, '  '])).toBe(APP_NAME);
	});

	it('returns just the app name for a null page part', () => {
		expect(formatTitle([null])).toBe('Claude Karma');
	});

	it('appends the app name to one part', () => {
		expect(formatTitle(['Projects'])).toBe('Projects · Claude Karma');
	});

	it('joins two parts and the app name', () => {
		expect(formatTitle(['ENG-42', 'Tickets'])).toBe('ENG-42 · Tickets · Claude Karma');
	});

	it('keeps a pre-joined load title intact', () => {
		expect(formatTitle([joinTitle(['ENG-42', null, 'Tickets'])])).toBe(
			'ENG-42 · Tickets · Claude Karma'
		);
	});
});

describe('routeTitle', () => {
	it('leaves the home page unlabelled', () => {
		expect(routeTitle('/')).toBeNull();
		expect(formatTitle([routeTitle('/')])).toBe('Claude Karma');
	});

	it('falls back to the first segment for nested paths', () => {
		expect(routeTitle('/projects/abc')).toBe('Projects');
		expect(routeTitle('/projects/abc/def/agents/x')).toBe('Projects');
	});

	it('returns null for unknown sections', () => {
		expect(routeTitle('/unknown')).toBeNull();
		expect(routeTitle('/constructor')).toBeNull();
	});
});

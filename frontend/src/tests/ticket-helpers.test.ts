import { describe, it, expect } from 'vitest';
import { githubKindFromUrl } from '$lib/ticket-helpers';

describe('githubKindFromUrl', () => {
	it('returns "pull_request" for /pull/N URLs', () => {
		expect(
			githubKindFromUrl('https://github.com/octocat/repo/pull/42')
		).toBe('pull_request');
	});

	it('returns "issue" for /issues/N URLs', () => {
		expect(
			githubKindFromUrl('https://github.com/octocat/repo/issues/42')
		).toBe('issue');
	});

	it('returns "pull_request" even with query and fragment trailing', () => {
		expect(
			githubKindFromUrl('https://github.com/octocat/repo/pull/9?diff=1#x')
		).toBe('pull_request');
	});

	it('defaults to "issue" for null / empty / unrecognized URLs', () => {
		// We pick "issue" as the safe default — GitHub redirects /issues/N
		// to /pull/N when N is actually a PR, so the link still resolves.
		expect(githubKindFromUrl(null)).toBe('issue');
		expect(githubKindFromUrl(undefined)).toBe('issue');
		expect(githubKindFromUrl('')).toBe('issue');
		expect(githubKindFromUrl('https://linear.app/team/issue/ABC-1')).toBe(
			'issue'
		);
	});

	it('does not false-match a literal "/pull/" elsewhere in the path', () => {
		// Guards against /someuser/pull/request-repo/issues/1 nonsense.
		// Our regex requires /pull/<digits> followed by end-or-delimiter.
		expect(
			githubKindFromUrl('https://github.com/owner/repo/issues/1?file=/pull/x')
		).toBe('issue');
	});
});

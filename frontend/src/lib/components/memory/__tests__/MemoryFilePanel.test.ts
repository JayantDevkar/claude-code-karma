import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, cleanup, waitFor } from '@testing-library/svelte';
import MemoryFilePanel from '../MemoryFilePanel.svelte';
import type { ProjectMemoryFile } from '$lib/api-types';

const ENCODED = '-Users-test-project';

function makeFile(overrides: Partial<ProjectMemoryFile> = {}): ProjectMemoryFile {
	return {
		filename: 'example.md',
		name: 'Example file',
		description: 'A description',
		type: 'project',
		content: '# Example\n\nThis is the body content.',
		word_count: 200,
		size_bytes: 1000,
		modified: '2026-04-01T00:00:00Z',
		...overrides
	};
}

describe('MemoryFilePanel', () => {
	beforeEach(() => {
		// noop
	});

	afterEach(() => {
		vi.unstubAllGlobals();
		cleanup();
	});

	it('does not fetch when filename is null', () => {
		const fetchMock = vi.fn();
		vi.stubGlobal('fetch', fetchMock);
		render(MemoryFilePanel, {
			props: { filename: null, projectEncodedName: ENCODED, onClose: () => {} }
		});
		expect(fetchMock).not.toHaveBeenCalled();
	});

	it('fetches the file content when filename is set', async () => {
		const fetchMock = vi.fn().mockResolvedValue({
			ok: true,
			status: 200,
			json: async () => makeFile()
		});
		vi.stubGlobal('fetch', fetchMock);

		render(MemoryFilePanel, {
			props: {
				filename: 'example.md',
				projectEncodedName: ENCODED,
				onClose: () => {}
			}
		});
		await waitFor(() => {
			expect(fetchMock).toHaveBeenCalled();
		});
		const calledUrl = (fetchMock.mock.calls[0]?.[0] ?? '') as string;
		expect(calledUrl).toContain(`/projects/${ENCODED}/memory/files/example.md`);
	});

	it('URL-encodes the filename', async () => {
		const fetchMock = vi.fn().mockResolvedValue({
			ok: true,
			status: 200,
			json: async () => makeFile({ filename: 'with space.md' })
		});
		vi.stubGlobal('fetch', fetchMock);

		render(MemoryFilePanel, {
			props: {
				filename: 'with space.md',
				projectEncodedName: ENCODED,
				onClose: () => {}
			}
		});
		await waitFor(() => {
			expect(fetchMock).toHaveBeenCalled();
		});
		const calledUrl = (fetchMock.mock.calls[0]?.[0] ?? '') as string;
		expect(calledUrl).toContain('with%20space.md');
	});

	it('shows file content after successful fetch', async () => {
		vi.stubGlobal(
			'fetch',
			vi.fn().mockResolvedValue({
				ok: true,
				status: 200,
				json: async () => makeFile({ name: 'My File Title' })
			})
		);

		const { findAllByText } = render(MemoryFilePanel, {
			props: {
				filename: 'example.md',
				projectEncodedName: ENCODED,
				onClose: () => {}
			}
		});
		// Title is rendered in the panel header (Dialog.Portal renders to body)
		const matches = await findAllByText('My File Title');
		expect(matches.length).toBeGreaterThan(0);
	});

	it('shows "no longer exists" error on 404', async () => {
		vi.stubGlobal(
			'fetch',
			vi.fn().mockResolvedValue({
				ok: false,
				status: 404,
				json: async () => ({})
			})
		);

		const { findAllByText } = render(MemoryFilePanel, {
			props: {
				filename: 'gone.md',
				projectEncodedName: ENCODED,
				onClose: () => {}
			}
		});
		const matches = await findAllByText('This memory file no longer exists.');
		expect(matches.length).toBeGreaterThan(0);
	});

	it('shows "Invalid memory file name" on 400', async () => {
		vi.stubGlobal(
			'fetch',
			vi.fn().mockResolvedValue({
				ok: false,
				status: 400,
				json: async () => ({})
			})
		);

		const { findAllByText } = render(MemoryFilePanel, {
			props: {
				filename: 'bad.md',
				projectEncodedName: ENCODED,
				onClose: () => {}
			}
		});
		const matches = await findAllByText('Invalid memory file name.');
		expect(matches.length).toBeGreaterThan(0);
	});

	it('shows "Failed to load" on network error', async () => {
		vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('boom')));

		const { findAllByText } = render(MemoryFilePanel, {
			props: {
				filename: 'broken.md',
				projectEncodedName: ENCODED,
				onClose: () => {}
			}
		});
		const matches = await findAllByText('Failed to load this memory file.');
		expect(matches.length).toBeGreaterThan(0);
	});

	it('refetches when filename prop changes', async () => {
		const fetchMock = vi.fn().mockResolvedValue({
			ok: true,
			status: 200,
			json: async () => makeFile()
		});
		vi.stubGlobal('fetch', fetchMock);

		const { rerender } = render(MemoryFilePanel, {
			props: {
				filename: 'first.md',
				projectEncodedName: ENCODED,
				onClose: () => {}
			}
		});
		await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
		expect((fetchMock.mock.calls[0]?.[0] ?? '') as string).toContain('first.md');

		await rerender({
			filename: 'second.md',
			projectEncodedName: ENCODED,
			onClose: () => {}
		});
		await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));
		expect((fetchMock.mock.calls[1]?.[0] ?? '') as string).toContain('second.md');
	});

	// Regression test for the fetch lifecycle race documented in the systematic
	// debugging session 2026-04-07. Without lifecycle management, a stale fetch
	// that resolves after a newer one was triggered will overwrite fileData
	// with the older content — the user sees the wrong file permanently.
	it('does not clobber current content when an older fetch resolves later', async () => {
		// Manually-controlled promise for the FIRST fetch — we resolve it later.
		let resolveFirst: (value: unknown) => void = () => {};
		const firstPromise = new Promise<unknown>((resolve) => {
			resolveFirst = resolve;
		});

		const secondResponse = {
			ok: true,
			status: 200,
			json: async () =>
				makeFile({
					filename: 'second.md',
					name: 'SECOND TITLE',
					content: '# Second body'
				})
		};

		const fetchMock = vi.fn().mockImplementation((url: string) => {
			if (url.includes('first.md')) return firstPromise;
			if (url.includes('second.md')) return Promise.resolve(secondResponse);
			return Promise.reject(new Error(`unexpected url: ${url}`));
		});
		vi.stubGlobal('fetch', fetchMock);

		const { rerender, queryByText } = render(MemoryFilePanel, {
			props: {
				filename: 'first.md',
				projectEncodedName: ENCODED,
				onClose: () => {}
			}
		});

		// User immediately clicks the second link before the first fetch returns.
		await rerender({
			filename: 'second.md',
			projectEncodedName: ENCODED,
			onClose: () => {}
		});

		// Second fetch resolves immediately → panel should display SECOND TITLE.
		await waitFor(() => {
			expect(queryByText('SECOND TITLE')).not.toBeNull();
		});

		// Now the older first.md fetch finally resolves (out-of-order).
		resolveFirst({
			ok: true,
			status: 200,
			json: async () =>
				makeFile({
					filename: 'first.md',
					name: 'FIRST TITLE',
					content: '# First body'
				})
		});

		// Give microtasks + the 80ms bodyFading timer time to settle.
		await new Promise((r) => setTimeout(r, 150));

		// CRITICAL: panel must still show SECOND, not FIRST.
		expect(queryByText('SECOND TITLE')).not.toBeNull();
		expect(queryByText('FIRST TITLE')).toBeNull();
	});
});

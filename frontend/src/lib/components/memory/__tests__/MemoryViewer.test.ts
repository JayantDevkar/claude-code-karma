import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, cleanup, waitFor } from '@testing-library/svelte';
import MemoryViewer from '../MemoryViewer.svelte';
import type { ProjectMemory } from '$lib/api-types';

const ENCODED = '-Users-test-project';

function mockFetchOnce(payload: ProjectMemory, status = 200) {
	const fetchMock = vi.fn().mockResolvedValue({
		ok: status >= 200 && status < 300,
		status,
		json: async () => payload
	});
	vi.stubGlobal('fetch', fetchMock);
	return fetchMock;
}

function mockFetchError() {
	const fetchMock = vi.fn().mockRejectedValue(new Error('network'));
	vi.stubGlobal('fetch', fetchMock);
	return fetchMock;
}

describe('MemoryViewer', () => {
	beforeEach(() => {
		vi.useFakeTimers({ shouldAdvanceTime: true });
	});

	afterEach(() => {
		vi.useRealTimers();
		vi.unstubAllGlobals();
		cleanup();
	});

	it('shows loading spinner before fetch resolves', async () => {
		// Pending fetch — never resolves
		const fetchMock = vi.fn().mockReturnValue(new Promise(() => {}));
		vi.stubGlobal('fetch', fetchMock);

		const { container } = render(MemoryViewer, {
			props: { projectEncodedName: ENCODED }
		});
		// Spinner is the only thing visible while loading
		expect(container.querySelector('.animate-spin')).toBeTruthy();
	});

	it('renders empty state when index missing and no children', async () => {
		mockFetchOnce({
			index: { content: '', word_count: 0, size_bytes: 0, modified: '', exists: false },
			files: []
		});

		const { findByTestId, getByText } = render(MemoryViewer, {
			props: { projectEncodedName: ENCODED }
		});
		await findByTestId('memory-empty-state');
		expect(getByText('No Project Memory Yet')).toBeTruthy();
	});

	it('renders index when MEMORY.md exists with no children', async () => {
		mockFetchOnce({
			index: {
				content: '# Project Memory\n\nSome notes here.',
				word_count: 4,
				size_bytes: 35,
				modified: '2026-04-01T12:00:00Z',
				exists: true
			},
			files: []
		});

		const { findByTestId, container } = render(MemoryViewer, {
			props: { projectEncodedName: ENCODED }
		});
		await findByTestId('memory-loaded');
		await waitFor(() => {
			expect(container.querySelector('[data-testid="memory-index-content"]')).toBeTruthy();
		});
		expect(container.querySelector('[data-testid="memory-orphan-list"]')).toBeNull();
	});

	it('renders error state on fetch failure', async () => {
		mockFetchError();
		const { findByText } = render(MemoryViewer, {
			props: { projectEncodedName: ENCODED }
		});
		await findByText('Failed to load project memory.');
	});

	it('renders orphans-only state when index missing but children present', async () => {
		mockFetchOnce({
			index: { content: '', word_count: 0, size_bytes: 0, modified: '', exists: false },
			files: [
				{
					filename: 'a.md',
					name: 'A',
					description: 'desc',
					type: 'project',
					word_count: 100,
					size_bytes: 500,
					modified: '2026-04-01T00:00:00Z',
					linked_from_index: false
				}
			]
		});

		const { findByTestId, getByText } = render(MemoryViewer, {
			props: { projectEncodedName: ENCODED }
		});
		await findByTestId('memory-orphans-only');
		expect(getByText('Orphan memory files')).toBeTruthy();
	});

	it('renders orphan list when index references some files but not others', async () => {
		mockFetchOnce({
			index: {
				content: '# Index\n\n- [Linked](linked.md)\n',
				word_count: 5,
				size_bytes: 30,
				modified: '2026-04-01T00:00:00Z',
				exists: true
			},
			files: [
				{
					filename: 'linked.md',
					name: 'Linked',
					description: 'in the index',
					type: 'project',
					word_count: 100,
					size_bytes: 500,
					modified: '2026-04-01T00:00:00Z',
					linked_from_index: true
				},
				{
					filename: 'orphan.md',
					name: 'Orphan',
					description: 'not in index',
					type: 'reference',
					word_count: 50,
					size_bytes: 200,
					modified: '2026-04-02T00:00:00Z',
					linked_from_index: false
				}
			]
		});

		const { findByTestId } = render(MemoryViewer, {
			props: { projectEncodedName: ENCODED }
		});
		await findByTestId('memory-loaded');
		const orphanList = await findByTestId('memory-orphan-list');
		expect(orphanList.textContent).toContain('Other memory files');
		expect(orphanList.textContent).toContain('(1)');
	});

	it('fetches the memory endpoint with the encoded project name', async () => {
		const fetchMock = mockFetchOnce({
			index: { content: '', word_count: 0, size_bytes: 0, modified: '', exists: false },
			files: []
		});

		render(MemoryViewer, { props: { projectEncodedName: ENCODED } });
		await waitFor(() => {
			expect(fetchMock).toHaveBeenCalled();
		});
		const calledUrl = (fetchMock.mock.calls[0]?.[0] ?? '') as string;
		expect(calledUrl).toContain(`/projects/${ENCODED}/memory`);
	});
});

import { describe, it, expect, beforeEach } from 'vitest';
import { render, cleanup } from '@testing-library/svelte';
import MemoryHoverCard from '../MemoryHoverCard.svelte';
import type { MemoryFileMeta, MemoryFileType } from '$lib/api-types';

function makeFile(type: MemoryFileType | null, overrides: Partial<MemoryFileMeta> = {}): MemoryFileMeta {
	return {
		filename: 'example.md',
		name: 'Example memory file',
		description: 'This is the description hook.',
		type,
		word_count: 1234,
		size_bytes: 5000,
		modified: '2026-04-01T10:00:00Z',
		linked_from_index: true,
		...overrides
	};
}

function makeRect(): DOMRect {
	return {
		x: 100,
		y: 100,
		top: 100,
		bottom: 120,
		left: 100,
		right: 200,
		width: 100,
		height: 20,
		toJSON: () => ({})
	} as DOMRect;
}

describe('MemoryHoverCard', () => {
	beforeEach(() => {
		cleanup();
	});

	it('renders nothing when file is null', () => {
		const { container } = render(MemoryHoverCard, {
			props: { file: null, anchorRect: makeRect() }
		});
		expect(container.querySelector('[data-testid="memory-hover-card"]')).toBeNull();
	});

	it('renders nothing when anchorRect is null', () => {
		const { container } = render(MemoryHoverCard, {
			props: { file: makeFile('project'), anchorRect: null }
		});
		expect(container.querySelector('[data-testid="memory-hover-card"]')).toBeNull();
	});

	it('renders card with project type badge', () => {
		const { getByTestId, container } = render(MemoryHoverCard, {
			props: { file: makeFile('project'), anchorRect: makeRect() }
		});
		const card = getByTestId('memory-hover-card');
		expect(card).toBeTruthy();
		const badge = getByTestId('hover-card-badge');
		expect(badge.textContent?.trim()).toBe('Project');
		expect(container.textContent).toContain('Example memory file');
		expect(container.textContent).toContain('This is the description hook.');
		expect(container.textContent).toContain('1,234 words');
	});

	it('renders "User" badge for user type', () => {
		const { getByTestId } = render(MemoryHoverCard, {
			props: { file: makeFile('user'), anchorRect: makeRect() }
		});
		expect(getByTestId('hover-card-badge').textContent?.trim()).toBe('User');
	});

	it('renders "Feedback" badge for feedback type', () => {
		const { getByTestId } = render(MemoryHoverCard, {
			props: { file: makeFile('feedback'), anchorRect: makeRect() }
		});
		expect(getByTestId('hover-card-badge').textContent?.trim()).toBe('Feedback');
	});

	it('renders "Reference" badge for reference type', () => {
		const { getByTestId } = render(MemoryHoverCard, {
			props: { file: makeFile('reference'), anchorRect: makeRect() }
		});
		expect(getByTestId('hover-card-badge').textContent?.trim()).toBe('Reference');
	});

	it('renders em-dash badge for null type', () => {
		const { getByTestId } = render(MemoryHoverCard, {
			props: { file: makeFile(null), anchorRect: makeRect() }
		});
		expect(getByTestId('hover-card-badge').textContent?.trim()).toBe('—');
	});

	it('positions the card based on anchor rect', () => {
		const { getByTestId } = render(MemoryHoverCard, {
			props: { file: makeFile('project'), anchorRect: makeRect() }
		});
		const card = getByTestId('memory-hover-card') as HTMLElement;
		expect(card.style.left).toBeTruthy();
		expect(card.style.top).toBeTruthy();
	});
});

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { rewriteMemoryLinks } from '$lib/actions/rewriteMemoryLinks';
import type { MemoryFileMeta } from '$lib/api-types';

function makeFile(overrides: Partial<MemoryFileMeta> = {}): MemoryFileMeta {
	return {
		filename: 'example.md',
		name: 'Example',
		description: 'desc',
		type: 'project',
		word_count: 100,
		size_bytes: 500,
		modified: '2026-04-07T00:00:00Z',
		linked_from_index: true,
		...overrides
	};
}

type HoverFn = (filename: string, rect: DOMRect) => void;
type LeaveFn = () => void;
type SelectFn = (filename: string) => void;

describe('rewriteMemoryLinks action', () => {
	let container: HTMLDivElement;
	let onHover: ReturnType<typeof vi.fn<HoverFn>>;
	let onLeave: ReturnType<typeof vi.fn<LeaveFn>>;
	let onSelect: ReturnType<typeof vi.fn<SelectFn>>;

	beforeEach(() => {
		container = document.createElement('div');
		document.body.appendChild(container);
		onHover = vi.fn<HoverFn>();
		onLeave = vi.fn<LeaveFn>();
		onSelect = vi.fn<SelectFn>();
	});

	afterEach(() => {
		container.remove();
	});

	it('marks matched .md anchors with memory-link class', () => {
		container.innerHTML =
			'<p><a href="example.md">Example</a> <a href="other.md">Other</a></p>';
		const action = rewriteMemoryLinks(container, {
			files: [makeFile({ filename: 'example.md' })],
			onHover,
			onLeave,
			onSelect
		});

		const anchors = container.querySelectorAll('a');
		expect(anchors[0].classList.contains('memory-link')).toBe(true);
		expect(anchors[0].getAttribute('data-memory-file')).toBe('example.md');
		expect(anchors[1].classList.contains('memory-link')).toBe(false);
		expect(anchors[1].classList.contains('memory-link--broken')).toBe(true);

		action.destroy();
	});

	it('extracts basename from nested path', () => {
		container.innerHTML = '<p><a href="./subdir/example.md">Example</a></p>';
		const action = rewriteMemoryLinks(container, {
			files: [makeFile({ filename: 'example.md' })],
			onHover,
			onLeave,
			onSelect
		});

		const anchor = container.querySelector('a')!;
		expect(anchor.classList.contains('memory-link')).toBe(true);
		expect(anchor.getAttribute('data-memory-file')).toBe('example.md');

		action.destroy();
	});

	it('strips fragment and query before matching basename', () => {
		container.innerHTML =
			'<p><a href="example.md#section">A</a><a href="example.md?v=1">B</a></p>';
		const action = rewriteMemoryLinks(container, {
			files: [makeFile({ filename: 'example.md' })],
			onHover,
			onLeave,
			onSelect
		});

		const anchors = container.querySelectorAll('a');
		expect(anchors[0].classList.contains('memory-link')).toBe(true);
		expect(anchors[1].classList.contains('memory-link')).toBe(true);

		action.destroy();
	});

	it('ignores non-.md anchors', () => {
		container.innerHTML =
			'<p><a href="https://example.com">Site</a><a href="page.html">Page</a></p>';
		const action = rewriteMemoryLinks(container, {
			files: [makeFile()],
			onHover,
			onLeave,
			onSelect
		});

		const anchors = container.querySelectorAll('a');
		expect(anchors[0].classList.contains('memory-link')).toBe(false);
		expect(anchors[0].classList.contains('memory-link--broken')).toBe(false);
		expect(anchors[1].classList.contains('memory-link')).toBe(false);

		action.destroy();
	});

	it('marks unknown .md links as broken with title attribute', () => {
		container.innerHTML = '<p><a href="missing.md">Missing</a></p>';
		const action = rewriteMemoryLinks(container, {
			files: [makeFile({ filename: 'example.md' })],
			onHover,
			onLeave,
			onSelect
		});

		const anchor = container.querySelector('a')!;
		expect(anchor.classList.contains('memory-link--broken')).toBe(true);
		expect(anchor.getAttribute('title')).toBe('file not found in memory directory');

		action.destroy();
	});

	it('fires onHover with filename and DOMRect on mouseenter', () => {
		container.innerHTML = '<p><a href="example.md">Example</a></p>';
		const action = rewriteMemoryLinks(container, {
			files: [makeFile({ filename: 'example.md' })],
			onHover,
			onLeave,
			onSelect
		});

		const anchor = container.querySelector('a')!;
		anchor.dispatchEvent(new MouseEvent('mouseenter'));

		expect(onHover).toHaveBeenCalledTimes(1);
		expect(onHover).toHaveBeenCalledWith('example.md', expect.any(Object));

		action.destroy();
	});

	it('fires onLeave on mouseleave', () => {
		container.innerHTML = '<p><a href="example.md">Example</a></p>';
		const action = rewriteMemoryLinks(container, {
			files: [makeFile({ filename: 'example.md' })],
			onHover,
			onLeave,
			onSelect
		});

		const anchor = container.querySelector('a')!;
		anchor.dispatchEvent(new MouseEvent('mouseleave'));

		expect(onLeave).toHaveBeenCalledTimes(1);
		action.destroy();
	});

	it('fires onSelect and prevents default on click', () => {
		container.innerHTML = '<p><a href="example.md">Example</a></p>';
		const action = rewriteMemoryLinks(container, {
			files: [makeFile({ filename: 'example.md' })],
			onHover,
			onLeave,
			onSelect
		});

		const anchor = container.querySelector('a')!;
		const event = new MouseEvent('click', { cancelable: true, bubbles: true });
		anchor.dispatchEvent(event);

		expect(onSelect).toHaveBeenCalledWith('example.md');
		expect(event.defaultPrevented).toBe(true);

		action.destroy();
	});

	it('update() re-runs wiring with new files list', () => {
		container.innerHTML = '<p><a href="a.md">A</a><a href="b.md">B</a></p>';
		const action = rewriteMemoryLinks(container, {
			files: [makeFile({ filename: 'a.md' })],
			onHover,
			onLeave,
			onSelect
		});

		let anchors = container.querySelectorAll('a');
		expect(anchors[0].classList.contains('memory-link')).toBe(true);
		expect(anchors[1].classList.contains('memory-link--broken')).toBe(true);

		action.update({
			files: [makeFile({ filename: 'b.md' })],
			onHover,
			onLeave,
			onSelect
		});

		anchors = container.querySelectorAll('a');
		expect(anchors[0].classList.contains('memory-link')).toBe(false);
		expect(anchors[0].classList.contains('memory-link--broken')).toBe(true);
		expect(anchors[1].classList.contains('memory-link')).toBe(true);

		action.destroy();
	});

	it('destroy() removes listeners and class markers', () => {
		container.innerHTML = '<p><a href="example.md">Example</a></p>';
		const action = rewriteMemoryLinks(container, {
			files: [makeFile({ filename: 'example.md' })],
			onHover,
			onLeave,
			onSelect
		});

		const anchor = container.querySelector('a')!;
		expect(anchor.classList.contains('memory-link')).toBe(true);

		action.destroy();

		expect(anchor.classList.contains('memory-link')).toBe(false);
		expect(anchor.getAttribute('data-memory-file')).toBeNull();

		// listeners should also be gone — no onHover after destroy
		anchor.dispatchEvent(new MouseEvent('mouseenter'));
		expect(onHover).not.toHaveBeenCalled();
	});

	it('handles empty container gracefully', () => {
		const action = rewriteMemoryLinks(container, {
			files: [makeFile()],
			onHover,
			onLeave,
			onSelect
		});
		expect(container.querySelectorAll('a').length).toBe(0);
		action.destroy();
	});

	it('handles anchors with no href', () => {
		container.innerHTML = '<p><a>No href</a></p>';
		const action = rewriteMemoryLinks(container, {
			files: [makeFile()],
			onHover,
			onLeave,
			onSelect
		});

		const anchor = container.querySelector('a')!;
		expect(anchor.classList.contains('memory-link')).toBe(false);
		expect(anchor.classList.contains('memory-link--broken')).toBe(false);

		action.destroy();
	});

	it('matches case-insensitively on .md extension', () => {
		container.innerHTML = '<p><a href="example.MD">Caps</a></p>';
		const action = rewriteMemoryLinks(container, {
			files: [makeFile({ filename: 'example.MD' })],
			onHover,
			onLeave,
			onSelect
		});

		const anchor = container.querySelector('a')!;
		expect(anchor.classList.contains('memory-link')).toBe(true);

		action.destroy();
	});
});

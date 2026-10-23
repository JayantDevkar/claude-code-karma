import { describe, it, expect, vi, afterEach } from 'vitest';
import { render, cleanup, fireEvent } from '@testing-library/svelte';
import SegmentedControl from '../SegmentedControl.svelte';

const OPTIONS = [
	{ label: 'All', value: 'all' },
	{ label: 'Built-in', value: 'builtin' },
	{ label: 'Custom', value: 'custom' }
];

function setup(props: { value?: string; disabled?: boolean; size?: 'sm' | 'md' } = {}) {
	const onchange = vi.fn();
	const { getAllByRole, getByRole } = render(SegmentedControl, {
		props: { options: OPTIONS, 'aria-label': 'Category', onchange, ...props }
	});
	return { onchange, radios: getAllByRole('radio'), group: getByRole('radiogroup') };
}

const tabStops = (radios: HTMLElement[]) => radios.map((r) => r.getAttribute('tabindex'));
const checked = (radios: HTMLElement[]) => radios.map((r) => r.getAttribute('aria-checked'));

describe('SegmentedControl', () => {
	afterEach(() => cleanup());

	it('keeps the radiogroup name and makes only the checked option tabbable', () => {
		const { group, radios } = setup({ value: 'builtin' });
		expect(group).toHaveAccessibleName('Category');
		expect(tabStops(radios)).toEqual(['-1', '0', '-1']);
		expect(checked(radios)).toEqual(['false', 'true', 'false']);
	});

	it('falls back to the first option as the tab stop when nothing is checked', () => {
		const { radios } = setup({ value: 'missing' });
		expect(tabStops(radios)).toEqual(['0', '-1', '-1']);
	});

	it('ArrowRight and ArrowDown select and focus the next option, wrapping at the end', async () => {
		const { radios, onchange } = setup({ value: 'builtin' });

		await fireEvent.keyDown(radios[1], { key: 'ArrowRight' });
		expect(onchange).toHaveBeenLastCalledWith('custom');
		expect(document.activeElement).toBe(radios[2]);
		expect(tabStops(radios)).toEqual(['-1', '-1', '0']);

		await fireEvent.keyDown(radios[2], { key: 'ArrowDown' });
		expect(onchange).toHaveBeenLastCalledWith('all');
		expect(document.activeElement).toBe(radios[0]);
		expect(checked(radios)).toEqual(['true', 'false', 'false']);
	});

	it('ArrowLeft and ArrowUp select and focus the previous option, wrapping at the start', async () => {
		const { radios, onchange } = setup({ value: 'all' });

		await fireEvent.keyDown(radios[0], { key: 'ArrowLeft' });
		expect(onchange).toHaveBeenLastCalledWith('custom');
		expect(document.activeElement).toBe(radios[2]);

		await fireEvent.keyDown(radios[2], { key: 'ArrowUp' });
		expect(onchange).toHaveBeenLastCalledWith('builtin');
		expect(document.activeElement).toBe(radios[1]);
	});

	it('Home and End jump to the first and last options', async () => {
		const { radios, onchange } = setup({ value: 'builtin' });

		await fireEvent.keyDown(radios[1], { key: 'End' });
		expect(onchange).toHaveBeenLastCalledWith('custom');
		expect(document.activeElement).toBe(radios[2]);

		await fireEvent.keyDown(radios[2], { key: 'Home' });
		expect(onchange).toHaveBeenLastCalledWith('all');
		expect(document.activeElement).toBe(radios[0]);
	});

	it('ignores other keys and modified arrows', async () => {
		const { radios, onchange } = setup({ value: 'all' });
		await fireEvent.keyDown(radios[0], { key: 'a' });
		await fireEvent.keyDown(radios[0], { key: 'ArrowRight', altKey: true });
		expect(onchange).not.toHaveBeenCalled();
		expect(checked(radios)).toEqual(['true', 'false', 'false']);
	});

	it('does nothing when disabled', async () => {
		const { radios, onchange } = setup({ value: 'all', disabled: true });
		await fireEvent.keyDown(radios[0], { key: 'ArrowRight' });
		await fireEvent.click(radios[1]);
		expect(onchange).not.toHaveBeenCalled();
	});

	it('still selects on click', async () => {
		const { radios, onchange } = setup({ value: 'all', size: 'sm' });
		await fireEvent.click(radios[2]);
		expect(onchange).toHaveBeenCalledWith('custom');
		expect(checked(radios)).toEqual(['false', 'false', 'true']);
	});
});

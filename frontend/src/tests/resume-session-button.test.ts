import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, cleanup, fireEvent, waitFor } from '@testing-library/svelte';
import ResumeSessionButton from '$lib/components/ResumeSessionButton.svelte';

const UUID = '0b6f2c1e-5d4a-4c8e-9f3b-7a1d2e3f4a5b';

describe('ResumeSessionButton', () => {
	let writeText: ReturnType<typeof vi.fn>;
	let fetchMock: ReturnType<typeof vi.fn>;

	beforeEach(() => {
		writeText = vi.fn().mockResolvedValue(undefined);
		Object.defineProperty(navigator, 'clipboard', { value: { writeText }, configurable: true });
		fetchMock = vi.fn();
		vi.stubGlobal('fetch', fetchMock);
	});

	afterEach(() => {
		cleanup();
		vi.unstubAllGlobals();
	});

	function setup(props: { sessionUuid: string; machine?: string | null }) {
		const { container, getByRole } = render(ResumeSessionButton, { props });
		return {
			button: getByRole('button'),
			label: () => container.querySelector('.resume-label')?.textContent?.trim(),
			live: container.querySelector('[aria-live="polite"]')
		};
	}

	it('copies the resume command and never posts for a synced session', async () => {
		const machine = 'macbook-pro-of-someone-with-a-very-long-hostname.local';
		const { button, label, live } = setup({ sessionUuid: UUID, machine });

		expect(button).toHaveAccessibleName(
			`Copy the claude --resume command (session synced from ${machine})`
		);
		expect(button.title).toBe(
			`Synced from ${machine}: resume it there. Click copies the claude --resume command.`
		);
		expect(label()).toBe('copy');

		await fireEvent.click(button);

		await waitFor(() => expect(writeText).toHaveBeenCalledWith(`claude --resume ${UUID}`));
		await waitFor(() => expect(label()).toBe('copied!'));
		expect(live).toHaveTextContent('Copied the claude --resume command');
		expect(fetchMock).not.toHaveBeenCalled();
	});

	it('announces a copy failure and never posts when the clipboard rejects', async () => {
		writeText.mockRejectedValue(new Error('denied'));
		const { button, label, live } = setup({ sessionUuid: UUID, machine: 'other-mac.local' });

		await fireEvent.click(button);

		await waitFor(() => expect(label()).toBe('failed'));
		expect(live).toHaveTextContent(`Run this manually: claude --resume ${UUID}`);
		expect(fetchMock).not.toHaveBeenCalled();
	});

	it('announces the API detail when the resume is refused', async () => {
		const detail = 'This session was synced from x; resume it there.';
		fetchMock.mockResolvedValue({ ok: false, status: 409, json: async () => ({ detail }) });
		const { button, label, live } = setup({ sessionUuid: UUID });

		expect(button).toHaveAccessibleName('Resume this session in a terminal');
		await fireEvent.click(button);

		await waitFor(() => expect(live).toHaveTextContent(detail));
		expect(label()).toBe('failed');
		expect(button.title).toBe(detail);
		expect(fetchMock).toHaveBeenCalledWith(
			expect.stringContaining(`/sessions/${UUID}/resume-in-terminal`),
			expect.objectContaining({ method: 'POST' })
		);
		expect(writeText).not.toHaveBeenCalled();
	});

	it('falls back to the generic announcement when the API is unreachable', async () => {
		fetchMock.mockRejectedValue(new TypeError('Failed to fetch'));
		const { button, label, live } = setup({ sessionUuid: UUID, machine: null });

		await fireEvent.click(button);

		await waitFor(() => expect(live).toHaveTextContent('Could not resume the session'));
		expect(label()).toBe('failed');
	});
});

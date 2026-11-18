import { describe, it, expect, afterEach, beforeEach, vi } from 'vitest';
import { render, cleanup, fireEvent, within } from '@testing-library/svelte';
import type { SubagentSummary } from '$lib/api-types';
import SubagentCard from '$lib/components/subagents/SubagentCard.svelte';
import {
	getAgentColorVars,
	getAgentDisplayName,
	getAgentFullName,
	getAgentIdentityColors,
	getAgentLabel,
	getModelTag
} from '$lib/utils/agent-identity';

const routeProps = { projectEncoded: '-Users-me-repo', sessionSlug: 'abc12345' };

beforeEach(() => {
	Object.defineProperty(navigator, 'clipboard', {
		value: { writeText: vi.fn().mockResolvedValue(undefined) },
		configurable: true
	});
});

function agent(overrides: Partial<SubagentSummary> = {}): SubagentSummary {
	return {
		agent_id: 'areview-api-0f1e2d3c4b5a6978',
		slug: 'quiet-amber-river',
		subagent_type: 'general-purpose',
		tools_used: { Bash: 3, Read: 2 },
		message_count: 12,
		initial_prompt: 'Review the backend half of the branch.',
		...overrides
	};
}

function setup(subagent: SubagentSummary, props: Record<string, unknown> = routeProps) {
	const result = render(SubagentCard, { props: { subagent, ...props } });
	const card = result.container.querySelector<HTMLElement>('[data-agent-id]')!;
	return { ...result, card };
}

const tint = (el: Element | null) => (el as HTMLElement | null)?.style.color;

describe('SubagentCard: named agent', () => {
	afterEach(cleanup);

	const named = agent({
		name: 'review-api',
		color: 'blue',
		team_name: 'checkout-team',
		model: 'opus',
		description: 'Review the backend changes'
	});

	it('titles the card with the name, in the colour the timeline uses for that agent', () => {
		const { card } = setup(named);
		const link = within(card).getByRole('link', { name: /review-api/ });
		expect(link).toHaveTextContent(/^review-api$/);
		expect(tint(link)).toBe('var(--agent-blue)');
		expect(tint(link)).toBe(getAgentColorVars('blue', 'general-purpose', 'review-api').color);
		expect(card.style.borderLeftColor).toBe('var(--agent-blue)');
	});

	it('keeps the type visible as its own badge', () => {
		const { card } = setup(named);
		expect(card).toHaveTextContent('general-purpose');
	});

	it('keeps the full id on the card to copy, and links with it encoded', () => {
		const { card } = setup(named);
		expect(within(card).getByText('areview-api-0f1e2d3c4b5a6978')).toBeInTheDocument();
		expect(within(card).getByRole('button', { name: 'Copy agent id' })).toBeInTheDocument();
		expect(within(card).getByRole('link', { name: /review-api/ })).toHaveAttribute(
			'href',
			'/projects/-Users-me-repo/abc12345/agents/areview-api-0f1e2d3c4b5a6978'
		);
	});

	it('shows the description, then the prompt, with team and model tags', () => {
		const { card } = setup(named);
		const description = within(card).getByText('Review the backend changes');
		const prompt = within(card).getByText('Review the backend half of the branch.');
		expect(
			description.compareDocumentPosition(prompt) & Node.DOCUMENT_POSITION_FOLLOWING
		).toBeTruthy();
		expect(card).toHaveTextContent('team checkout-team');
		expect(card).toHaveTextContent('opus');
	});

	it('hides a model tag that says nothing', () => {
		for (const model of ['inherit', 'Inherit', '', '  ', null]) {
			const { card, unmount } = setup(agent({ ...named, model }));
			expect(card).toHaveTextContent('team checkout-team');
			expect(card).not.toHaveTextContent(/inherit/i);
			unmount();
		}
		expect(getModelTag('opus')).toBe('opus');
		expect(getModelTag(' inherit ')).toBeNull();
	});

	it('gives two agents of the same type their own colours', () => {
		const frontend = agent({
			agent_id: 'areview-web-0123456789abcdef',
			name: 'review-web',
			color: 'green'
		});
		expect(getAgentIdentityColors(named).color).toBe('var(--agent-blue)');
		expect(getAgentIdentityColors(frontend).color).toBe('var(--agent-green)');
	});
});

describe('SubagentCard: unnamed agent', () => {
	afterEach(cleanup);

	it('titles the card with a short readable id when there is no name', () => {
		const { card } = setup(agent({ agent_id: 'aui-check-0a1b2c3d4e5f6071' }));
		expect(within(card).getByRole('link', { name: /ui-check/ })).toHaveTextContent(
			/^ui-check$/
		);
		expect(within(card).getByText('aui-check-0a1b2c3d4e5f6071')).toBeInTheDocument();
	});

	it('titles an unnamed agent by its type, with the id beneath and no repeated type badge', () => {
		const plain = agent({ agent_id: 'a9f8e7d6c5b4a3f2e', subagent_type: 'Explore' });
		const { card } = setup(plain);
		const link = within(card).getByRole('link', { name: /Explore/ });
		expect(link).toHaveTextContent(/^Explore$/);
		expect(tint(link)).toBe('var(--subagent-explore)');
		expect(within(card).getByText('a9f8e7d6c5b4a3f2e')).toBeInTheDocument();
		expect(within(card).getAllByText('Explore')).toHaveLength(1);
	});

	it('never shows an internal type marker as a badge', () => {
		const { card } = setup(agent({ name: 'reviewer-a', subagent_type: '_teammate' }));
		expect(card).toHaveTextContent('reviewer-a');
		expect(card).not.toHaveTextContent('_teammate');
	});

	it('hides a team tag that is only the session itself', () => {
		const { card } = setup(
			agent({ name: 'reviewer-a', team_name: 'session-4e5f6a7b', model: 'opus' })
		);
		expect(card).toHaveTextContent('opus');
		expect(card).not.toHaveTextContent('session-4e5f6a7b');
	});

	it('renders without optional fields: no tags, no description, no link without a route', () => {
		const { card } = setup(agent({ agent_id: 'a9f8e7d6c5b4a3f2e', initial_prompt: null }), {});
		expect(within(card).queryByRole('link')).toBeNull();
		expect(card).toHaveTextContent('a9f8e7d6');
		expect(card).not.toHaveTextContent('team ');
	});

	it('names every agent by one rule: name, id-embedded name, type plus short id, short id', () => {
		expect(
			getAgentLabel({ agent_id: 'areviewer-a-0123456789abcdef', name: 'reviewer-a' })
		).toEqual({
			label: 'reviewer-a',
			secondary: null
		});
		expect(
			getAgentLabel({
				agent_id: 'abuilder-b-0b0b0b0b0b0b0b0b',
				subagent_type: 'general-purpose'
			})
		).toEqual({
			label: 'builder-b',
			secondary: null
		});
		expect(
			getAgentLabel({ agent_id: 'a5e4d3c2b1a0f9e8d', subagent_type: 'general-purpose' })
		).toEqual({
			label: 'general-purpose',
			secondary: 'a5e4d3c2'
		});
		expect(
			getAgentLabel({
				agent_id: 'a5e4d3c2b1a0f9e8d',
				name: 'general-purpose',
				subagent_type: 'general-purpose'
			})
		).toEqual({ label: 'general-purpose', secondary: 'a5e4d3c2' });
		expect(
			getAgentLabel({ agent_id: 'a5e4d3c2b1a0f9e8d', subagent_type: '_teammate' })
		).toEqual({
			label: 'a5e4d3c2',
			secondary: null
		});
		expect(getAgentLabel({ agent_id: 'aprompt_suggestion-7796cd0011223344' })).toEqual({
			label: 'Prompt Suggestion',
			secondary: '7796cd00'
		});
		const unnamed = { agent_id: 'a5e4d3c2b1a0f9e8d', subagent_type: 'general-purpose' };
		expect(getAgentFullName(unnamed)).toBe('general-purpose a5e4d3c2');
		expect(
			getAgentFullName({ agent_id: 'areviewer-a-0123456789abcdef', name: 'reviewer-a' })
		).toBe('reviewer-a');
		expect(
			getAgentDisplayName({ agent_id: 'a5e4d3c2b1a0f9e8d', subagent_type: 'Explore' })
		).toBe('Explore');
	});
});

describe('SubagentCard: long name', () => {
	afterEach(cleanup);

	const longName = 'a-very-long-agent-name-that-keeps-going-well-past-the-width-of-one-card';

	it('shows the whole name and lets it wrap instead of truncating it', () => {
		const { card } = setup(agent({ name: longName, color: 'pink' }));
		const link = within(card).getByRole('link', { name: new RegExp(longName) });
		const label = within(link).getByText(longName);
		expect(label.className).toContain('overflow-wrap:anywhere');
		expect(label.className).not.toContain('truncate');
		expect(link.className).toContain('max-w-full');
	});
});

describe('SubagentCard: expanding', () => {
	afterEach(cleanup);

	const long = agent({ name: 'reviewer-a', initial_prompt: 'x'.repeat(300) });

	it('expands from a real button and not from a role=button container', async () => {
		const { card } = setup(long);
		expect(card.getAttribute('role')).toBeNull();
		const toggle = within(card).getByRole('button', { name: 'Show details for reviewer-a' });
		expect(toggle).toHaveAttribute('aria-expanded', 'false');
		await fireEvent.click(toggle);
		expect(
			within(card).getByRole('button', { name: 'Hide details for reviewer-a' })
		).toHaveAttribute('aria-expanded', 'true');
	});

	it('does not expand when the name link or the copy button is clicked', async () => {
		const { card } = setup(long);
		const link = within(card).getByRole('link', { name: /reviewer-a/ });
		link.addEventListener('click', (e) => e.preventDefault());
		await fireEvent.click(link);
		await fireEvent.click(within(card).getByRole('button', { name: 'Copy agent id' }));
		expect(
			within(card).getByRole('button', { name: /details for reviewer-a/ })
		).toHaveAttribute('aria-expanded', 'false');
	});
});

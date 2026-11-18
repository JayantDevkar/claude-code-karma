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
		agent_id: 'areview-backend-dfe067fd7904abc2',
		slug: 'velvet-sauteeing-mist',
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
		name: 'review-backend',
		color: 'blue',
		team_name: 'wind-tunnel',
		model: 'opus',
		description: 'Review the backend changes'
	});

	it('titles the card with the name, in the colour the timeline uses for that agent', () => {
		const { card } = setup(named);
		const link = within(card).getByRole('link', { name: /review-backend/ });
		expect(link).toHaveTextContent(/^review-backend$/);
		expect(tint(link)).toBe('var(--agent-blue)');
		expect(tint(link)).toBe(
			getAgentColorVars('blue', 'general-purpose', 'review-backend').color
		);
		expect(card.style.borderLeftColor).toBe('var(--agent-blue)');
	});

	it('keeps the type visible as its own badge', () => {
		const { card } = setup(named);
		expect(card).toHaveTextContent('general-purpose');
	});

	it('keeps the full id on the card to copy, and links with it encoded', () => {
		const { card } = setup(named);
		expect(within(card).getByText('areview-backend-dfe067fd7904abc2')).toBeInTheDocument();
		expect(within(card).getByRole('button', { name: 'Copy agent id' })).toBeInTheDocument();
		expect(within(card).getByRole('link', { name: /review-backend/ })).toHaveAttribute(
			'href',
			'/projects/-Users-me-repo/abc12345/agents/areview-backend-dfe067fd7904abc2'
		);
	});

	it('shows the description, then the prompt, with team and model tags', () => {
		const { card } = setup(named);
		const description = within(card).getByText('Review the backend changes');
		const prompt = within(card).getByText('Review the backend half of the branch.');
		expect(
			description.compareDocumentPosition(prompt) & Node.DOCUMENT_POSITION_FOLLOWING
		).toBeTruthy();
		expect(card).toHaveTextContent('team wind-tunnel');
		expect(card).toHaveTextContent('opus');
	});

	it('hides a model tag that says nothing', () => {
		for (const model of ['inherit', 'Inherit', '', '  ', null]) {
			const { card, unmount } = setup(agent({ ...named, model }));
			expect(card).toHaveTextContent('team wind-tunnel');
			expect(card).not.toHaveTextContent(/inherit/i);
			unmount();
		}
		expect(getModelTag('opus')).toBe('opus');
		expect(getModelTag(' inherit ')).toBeNull();
	});

	it('gives two agents of the same type their own colours', () => {
		const frontend = agent({
			agent_id: 'areview-frontend-0123456789abcdef',
			name: 'review-frontend',
			color: 'green'
		});
		expect(getAgentIdentityColors(named).color).toBe('var(--agent-blue)');
		expect(getAgentIdentityColors(frontend).color).toBe('var(--agent-green)');
	});
});

describe('SubagentCard: unnamed agent', () => {
	afterEach(cleanup);

	it('titles the card with a short readable id when there is no name', () => {
		const { card } = setup(agent({ agent_id: 'aui-review-57f8a08c8c69f14f' }));
		expect(within(card).getByRole('link', { name: /ui-review/ })).toHaveTextContent(
			/^ui-review$/
		);
		expect(within(card).getByText('aui-review-57f8a08c8c69f14f')).toBeInTheDocument();
	});

	it('titles an unnamed agent by its type, with the id beneath and no repeated type badge', () => {
		const plain = agent({ agent_id: 'a030ff016e8febfee', subagent_type: 'Explore' });
		const { card } = setup(plain);
		const link = within(card).getByRole('link', { name: /Explore/ });
		expect(link).toHaveTextContent(/^Explore$/);
		expect(tint(link)).toBe('var(--subagent-explore)');
		expect(within(card).getByText('a030ff016e8febfee')).toBeInTheDocument();
		expect(within(card).getAllByText('Explore')).toHaveLength(1);
	});

	it('hides a team tag that is only the session itself', () => {
		const { card } = setup(
			agent({ name: 'rev-m6', team_name: 'session-650f4fe4', model: 'opus' })
		);
		expect(card).toHaveTextContent('opus');
		expect(card).not.toHaveTextContent('session-650f4fe4');
	});

	it('renders without optional fields: no tags, no description, no link without a route', () => {
		const { card } = setup(agent({ agent_id: 'a030ff016e8febfee', initial_prompt: null }), {});
		expect(within(card).queryByRole('link')).toBeNull();
		expect(card).toHaveTextContent('a030ff01');
		expect(card).not.toHaveTextContent('team ');
	});

	it('names every agent by one rule: name, id-embedded name, type plus short id, short id', () => {
		expect(getAgentLabel({ agent_id: 'arev-m6-0123456789abcdef', name: 'rev-m6' })).toEqual({
			label: 'rev-m6',
			secondary: null
		});
		expect(
			getAgentLabel({
				agent_id: 'aimpl-t28-e4a00898e0a882a3',
				subagent_type: 'general-purpose'
			})
		).toEqual({
			label: 'impl-t28',
			secondary: null
		});
		expect(
			getAgentLabel({ agent_id: 'af57af573db6a9d4d', subagent_type: 'general-purpose' })
		).toEqual({
			label: 'general-purpose',
			secondary: 'af57af57'
		});
		expect(
			getAgentLabel({
				agent_id: 'af57af573db6a9d4d',
				name: 'general-purpose',
				subagent_type: 'general-purpose'
			})
		).toEqual({ label: 'general-purpose', secondary: 'af57af57' });
		expect(
			getAgentLabel({ agent_id: 'af57af573db6a9d4d', subagent_type: '_teammate' })
		).toEqual({
			label: 'af57af57',
			secondary: null
		});
		expect(getAgentLabel({ agent_id: 'aprompt_suggestion-7796cd0011223344' })).toEqual({
			label: 'Prompt Suggestion',
			secondary: '7796cd00'
		});
		const unnamed = { agent_id: 'af57af573db6a9d4d', subagent_type: 'general-purpose' };
		expect(getAgentFullName(unnamed)).toBe('general-purpose af57af57');
		expect(getAgentFullName({ agent_id: 'arev-m6-0123456789abcdef', name: 'rev-m6' })).toBe(
			'rev-m6'
		);
		expect(
			getAgentDisplayName({ agent_id: 'af57af573db6a9d4d', subagent_type: 'Explore' })
		).toBe('Explore');
	});
});

describe('SubagentCard: long name', () => {
	afterEach(cleanup);

	const longName = 'final-fix-wave-2-residual-rereview-of-the-notification-threading-change';

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

	const long = agent({ name: 'rev-m6', initial_prompt: 'x'.repeat(300) });

	it('expands from a real button and not from a role=button container', async () => {
		const { card } = setup(long);
		expect(card.getAttribute('role')).toBeNull();
		const toggle = within(card).getByRole('button', { name: 'Show details for rev-m6' });
		expect(toggle).toHaveAttribute('aria-expanded', 'false');
		await fireEvent.click(toggle);
		expect(
			within(card).getByRole('button', { name: 'Hide details for rev-m6' })
		).toHaveAttribute('aria-expanded', 'true');
	});

	it('does not expand when the name link or the copy button is clicked', async () => {
		const { card } = setup(long);
		const link = within(card).getByRole('link', { name: /rev-m6/ });
		link.addEventListener('click', (e) => e.preventDefault());
		await fireEvent.click(link);
		await fireEvent.click(within(card).getByRole('button', { name: 'Copy agent id' }));
		expect(within(card).getByRole('button', { name: /details for rev-m6/ })).toHaveAttribute(
			'aria-expanded',
			'false'
		);
	});
});

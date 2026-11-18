import { describe, it, expect, afterEach } from 'vitest';
import { render, cleanup, fireEvent, within, waitFor } from '@testing-library/svelte';
import type { TimelineEvent } from '$lib/api-types';
import TimelineRail from '$lib/components/timeline/TimelineRail.svelte';
import { timelineFixture } from './fixtures/timeline-events';

const routeProps = { projectEncoded: '-Users-me-repo', sessionSlug: 'abc12345' };

function setup(events: TimelineEvent[] = timelineFixture) {
	return render(TimelineRail, { props: { events, ...routeProps } });
}

const rows = (container: HTMLElement, type?: string) =>
	Array.from(
		container.querySelectorAll<HTMLElement>(
			type ? `[data-event-type="${type}"]` : '[data-event-index]'
		)
	);
const row = (container: HTMLElement, type: string) => rows(container, type)[0] ?? null;
const rowWithText = (container: HTMLElement, text: string) =>
	rows(container).find((r) => r.textContent?.includes(text)) ?? null;

const systemEvents = timelineFixture.filter((e) => e.event_type === 'system_context');
const shownByDefault = timelineFixture.length - systemEvents.length;
const systemToggleName = /^System/;

function event(id: string): TimelineEvent {
	const found = timelineFixture.find((e) => e.id === id);
	if (!found) throw new Error(`no fixture event ${id}`);
	return found;
}

describe('TimelineRail with the sender-aware event types', () => {
	afterEach(cleanup);

	it('leaves system events out by default, with no gap for them', () => {
		const { container, getByRole, queryByText } = setup();
		expect(row(container, 'system_context')).toBeNull();
		expect(queryByText(/hidden \(/)).toBeNull();
		expect(rows(container)).toHaveLength(shownByDefault);
		expect(getByRole('button', { name: systemToggleName })).toHaveAttribute(
			'aria-pressed',
			'false'
		);
		expect(container).toHaveTextContent(new RegExp(`${shownByDefault} events`));
	});

	it('System selected alone shows only the system events, as full cards', async () => {
		const { container, getByRole } = setup();
		await fireEvent.click(getByRole('button', { name: systemToggleName }));
		expect(getByRole('button', { name: systemToggleName })).toHaveAttribute(
			'aria-pressed',
			'true'
		);
		expect(rows(container)).toHaveLength(systemEvents.length);
		expect(rows(container).every((r) => r.dataset.eventType === 'system_context')).toBe(true);
		const reminder = rowWithText(container, 'System reminder')!;
		expect(reminder).toHaveTextContent('The user message contains a skill name');
		expect(reminder.querySelector('.border-dashed')).toBeNull();
		expect(container).toHaveTextContent(/hidden \(\d+\)/);
		expect(container).toHaveTextContent(
			new RegExp(`${systemEvents.length}\\s*of\\s*${timelineFixture.length}\\s*events`)
		);
	});

	it('System with Messages shows both kinds', async () => {
		const { container, getByRole } = setup();
		await fireEvent.click(getByRole('button', { name: systemToggleName }));
		await fireEvent.click(getByRole('button', { name: /^Messages/ }));
		const shown = rows(container).map((r) => r.dataset.eventType);
		const messages = timelineFixture.filter((e) => e.event_type === 'message').length;
		expect(shown.filter((t) => t === 'system_context')).toHaveLength(systemEvents.length);
		expect(shown.filter((t) => t === 'message')).toHaveLength(messages);
		expect(shown).toHaveLength(systemEvents.length + messages);
	});

	it('Clear clears System like any other filter', async () => {
		const { container, getByRole } = setup();
		await fireEvent.click(getByRole('button', { name: systemToggleName }));
		await fireEvent.click(getByRole('button', { name: 'Clear' }));
		expect(getByRole('button', { name: systemToggleName })).toHaveAttribute(
			'aria-pressed',
			'false'
		);
		expect(rows(container)).toHaveLength(shownByDefault);
		expect(row(container, 'system_context')).toBeNull();
	});

	it('reports the count it works with, without left-out system events', async () => {
		const counts: number[] = [];
		const { getByRole } = render(TimelineRail, {
			props: { events: timelineFixture, onEventCountChange: (n: number) => counts.push(n) }
		});
		await waitFor(() => expect(counts.at(-1)).toBe(shownByDefault));
		await fireEvent.click(getByRole('button', { name: systemToggleName }));
		await waitFor(() => expect(counts.at(-1)).toBe(timelineFixture.length));
	});

	it('renders a message as a route between named parties', () => {
		const { container } = setup();
		const out = rowWithText(container, 'Fix round is at 3161b7d')!;
		expect(out).toHaveTextContent('this session');
		expect(within(out).getByRole('link', { name: /rev-m6/ })).toHaveAttribute(
			'href',
			'/projects/-Users-me-repo/abc12345/agents/a0ae946093e2cb8e5'
		);
		const incoming = rowWithText(container, '[ASK] Why did the triage')!;
		expect(incoming).toHaveTextContent('occu-orchestration-airflow-72');
		expect(incoming).toHaveTextContent('relayed');
		expect(incoming).not.toHaveTextContent('queued');
	});

	it('calls the parent session "main session", never "main"', () => {
		const { container } = setup();
		const fromMain = rowWithText(container, 'Also cover the retry path.')!;
		expect(fromMain).toHaveTextContent('main session');
		expect(within(fromMain).queryByRole('link')).toBeNull();
	});

	it('names agents instead of showing raw ids', async () => {
		const { container, getByRole } = setup();
		const spawn = row(container, 'subagent_spawn')!;
		expect(spawn).toHaveTextContent('Spawn general-purpose subagent');
		expect(spawn).toHaveTextContent('rev-m6');
		expect(spawn).toHaveTextContent('team wind-tunnel');
		expect(spawn).toHaveTextContent('background');
		expect(container.textContent).not.toContain('a0ae946093e2cb8e5');
		await fireEvent.click(getByRole('button', { name: systemToggleName }));
		expect(container.textContent).not.toContain('e4a00898e0a882a3');
	});

	it('colours a typed agent with no colour by its type, on badges and task rows', () => {
		const typed: TimelineEvent[] = [
			{ ...event('evt-15'), actor_color: null, actor_agent_type: 'Explore' },
			{
				...event('evt-7'),
				metadata: { ...event('evt-7').metadata, agent_color: null, agent_type: 'Explore' }
			}
		];
		const { container } = setup(typed);
		const badges = within(container).getAllByRole('link', { name: /rev-m6/ });
		expect(badges).toHaveLength(2);
		for (const badge of badges) expect(badge.style.color).toBe('var(--subagent-explore)');
	});

	it('hides an "inherit" model tag on a spawn card', () => {
		const fork: TimelineEvent = {
			...event('evt-4'),
			metadata: { ...event('evt-4').metadata, agent_model: 'inherit' }
		};
		const { container } = setup([fork]);
		const spawn = row(container, 'subagent_spawn')!;
		expect(spawn).toHaveTextContent('team wind-tunnel');
		expect(spawn).not.toHaveTextContent('inherit');
	});

	it('says "sent while Claude was working" on a prompt only, never "queued" on a task', () => {
		const { container } = setup();
		expect(rowWithText(container, 'use the branch jay/wt-reply-shape')).toHaveTextContent(
			'sent while Claude was working'
		);
		expect(rowWithText(container, 'Run all five test suites')).not.toHaveTextContent(
			/queued|sent while/
		);
		expect(rowWithText(container, 'Monitor event:')).not.toHaveTextContent(/queued|sent while/);
	});

	it('hides the team tag when the team is just the session itself', () => {
		const implicit: TimelineEvent = {
			...event('evt-4'),
			metadata: { ...event('evt-4').metadata, team_name: 'session-18e94b57' }
		};
		const { container } = setup([implicit]);
		const spawn = row(container, 'subagent_spawn')!;
		expect(spawn).toHaveTextContent('opus');
		expect(spawn).not.toHaveTextContent('session-18e94b57');
	});

	it('labels an unnamed agent by its type with the short id beside it', () => {
		const unnamed: TimelineEvent = {
			...event('evt-15'),
			actor: 'af57af573db6a9d4d',
			actor_name: null,
			actor_color: null,
			actor_agent_type: 'general-purpose'
		};
		const { container } = setup([unnamed]);
		const badge = within(container).getByRole('link', { name: /general-purpose/ });
		expect(badge).toHaveTextContent('general-purpose');
		expect(badge).toHaveTextContent('af57af57');
		expect(badge.getAttribute('title')).toContain('general-purpose af57af57');
		expect(container.textContent).not.toContain('af57af573db6a9d4d');
	});

	it('shows the team lead on an agent page as the main session, keeping its role name', () => {
		const prompt: TimelineEvent = {
			...event('evt-1'),
			id: 'task-prompt',
			actor: 'session',
			actor_type: 'session',
			actor_name: 'team-lead',
			title: 'Task prompt',
			metadata: { full_content: 'Implement Task 9', is_task_prompt: true }
		};
		const followUp: TimelineEvent = {
			...event('evt-20'),
			metadata: { ...event('evt-20').metadata, peer_name: 'team-lead' }
		};
		const { container } = render(TimelineRail, {
			props: {
				events: [prompt, followUp],
				currentAgentId: 'aimpl-m9-cd8b2c9698c4cb70',
				...routeProps
			}
		});
		const task = row(container, 'prompt')!;
		expect(task).toHaveTextContent('Task prompt');
		expect(task).toHaveTextContent('from main session (team-lead)');
		const message = row(container, 'message')!;
		expect(message).toHaveTextContent('main session (team-lead)');
		expect(message).toHaveTextContent('this agent');
		// On an agent page the lead links back to the parent session.
		const parent = '/projects/-Users-me-repo/abc12345';
		expect(
			within(message).getByRole('link', { name: /main session \(team-lead\)/ })
		).toHaveAttribute('href', parent);
		expect(
			within(task).getByRole('link', { name: /main session \(team-lead\)/ })
		).toHaveAttribute('href', parent);
	});

	it('labels background events by kind and status', () => {
		const { container } = setup();
		expect(rowWithText(container, 'Review plan-2 Task 6 finished')).toHaveTextContent(
			'Agent finished'
		);
		expect(rowWithText(container, 'Wait until PR #6 is merged')).toHaveTextContent(
			'Background command failed'
		);
		const monitor = rowWithText(container, 'Monitor event:')!;
		expect(monitor).toHaveTextContent('Monitor update');
		expect(monitor).not.toHaveTextContent('finished');
		expect(rowWithText(container, 'Run all five test suites')).toHaveTextContent(
			'Background command finished'
		);
	});

	it('shows an idle teammate as a system event, named', async () => {
		const { container, getByRole } = setup();
		expect(rowWithText(container, 'is idle')).toBeNull();
		await fireEvent.click(getByRole('button', { name: systemToggleName }));
		const idle = rowWithText(container, 'is idle')!;
		expect(idle.dataset.eventType).toBe('system_context');
		expect(idle).toHaveTextContent('impl-t28');
		expect(idle).not.toHaveTextContent('added for Claude');
		expect(idle).not.toHaveTextContent('(available)');
	});

	it('shows an interruption with nothing to expand', () => {
		const { container } = setup();
		const interrupted = rowWithText(container, 'You interrupted Claude')!;
		expect(interrupted).not.toHaveTextContent('Request interrupted by user');
		expect(within(interrupted).queryByRole('button', { name: /details/ })).toBeNull();
	});

	it('shows which models a fallback notice switched between', () => {
		const { container } = setup();
		const fallback = rowWithText(container, 'Model switched after a safeguard flag')!;
		expect(fallback).toHaveTextContent('claude-fable-5-1 to claude-opus-4-8');
		expect(fallback).toHaveTextContent('warning');
	});

	it('renders compaction, shell, recap and scheduled events in plain words', () => {
		const { container } = setup();
		expect(row(container, 'compaction')).toHaveTextContent('Context compacted');
		expect(row(container, 'compaction')).toHaveTextContent('155k tokens before');
		expect(row(container, 'shell_command')).toHaveTextContent('$ slack app install');
		expect(rowWithText(container, 'Recap while you were away')).not.toBeNull();
		expect(row(container, 'scheduled_fire')).toHaveTextContent('Scheduled task fired');
	});

	it('renders an unknown event type as a plain card', () => {
		const { container } = setup();
		expect(row(container, 'brand_new_type')).toHaveTextContent(
			'Something Claude Code added later'
		);
	});

	it('filters by the new chips', async () => {
		const { container, getByRole } = setup();
		const count = (types: string[]) =>
			timelineFixture.filter((e) => types.includes(e.event_type)).length;
		const messages = getByRole('button', { name: /^Messages/ });
		await fireEvent.click(messages);
		expect(rows(container)).toHaveLength(count(['message']));
		expect(rows(container).every((r) => r.dataset.eventType === 'message')).toBe(true);
		await fireEvent.click(messages);
		await fireEvent.click(getByRole('button', { name: /^Background/ }));
		expect(rows(container)).toHaveLength(count(['task_notification', 'scheduled_fire']));
	});
});

describe('filter bar', () => {
	afterEach(cleanup);

	it('gives every chip a visible label, so its name is never a bare count', () => {
		const { container } = setup();
		const chips = Array.from(container.querySelectorAll<HTMLElement>('button[aria-pressed]'));
		expect(chips.length).toBeGreaterThan(5);
		for (const chip of chips) {
			expect(chip.textContent?.trim()).toMatch(/^[A-Za-z][A-Za-z ]+\s+\d+$/);
			expect(chip.querySelector('.hidden')).toBeNull();
		}
	});

	it('draws System as a normal chip and explains it only in its description', () => {
		const { getByRole } = setup();
		const system = getByRole('button', { name: systemToggleName });
		expect(system).toHaveTextContent(new RegExp(`^System\\s*${systemEvents.length}$`));
		expect(system.className).not.toContain('border-dashed');
		expect(system).toHaveAccessibleDescription(/Not shown unless selected/);
	});

	it('writes a gap list with commas against the words', async () => {
		const { container, getByRole } = setup();
		await fireEvent.click(getByRole('button', { name: /^Prompts/ }));
		const gap = Array.from(container.querySelectorAll('div')).find(
			(d) => /^\s*hidden \(\d+\)/.test(d.textContent ?? '') && d.querySelector('button')
		)!;
		const text = gap.textContent!.replace(/\s+/g, ' ');
		expect(text).toMatch(/\w,/);
		expect(text).not.toMatch(/\s,/);
	});
});

describe('popup', () => {
	afterEach(cleanup);

	async function openPopupFor(container: HTMLElement, text: string) {
		const target = rowWithText(container, text)!;
		await fireEvent.click(within(target).getByRole('button', { name: /^Show details/ }));
		return waitFor(() => {
			const found = document.querySelector<HTMLElement>('[role="dialog"]');
			if (!found) throw new Error('popup not open');
			return found;
		});
	}

	it('carries the same title and sender as the card', async () => {
		const { container } = setup();
		const card = rowWithText(container, 'Review plan-2 Task 6 finished')!;
		const dialog = await openPopupFor(container, 'Review plan-2 Task 6 finished');
		const heading = within(dialog).getByRole('heading', { level: 2 });
		expect(heading).toHaveTextContent('Agent finished');
		expect(within(heading).getByRole('link', { name: /rev-m6/ })).toHaveAttribute(
			'href',
			within(card)
				.getByRole('link', { name: /rev-m6/ })
				.getAttribute('href')
		);
	});

	it('words a spawn the way its card does', async () => {
		const { container } = setup();
		const dialog = await openPopupFor(container, 'Review plan-2 Task 6');
		const heading = within(dialog).getByRole('heading', { level: 2 });
		expect(heading).toHaveTextContent('Spawn general-purpose subagent');
		expect(heading).toHaveTextContent('rev-m6');
		expect(heading).toHaveTextContent('team wind-tunnel');
	});

	it('keeps single line breaks in a message body', async () => {
		const lines: TimelineEvent = {
			...event('evt-6'),
			id: 'lines',
			summary: 'three lines',
			metadata: {
				...event('evt-6').metadata,
				full_content: 'ANSWER: yes\n(1) first point\n(2) second point'
			}
		};
		const { container } = setup([lines]);
		const dialog = await openPopupFor(container, 'three lines');
		const body = dialog.querySelector('.markdown-preview')!;
		expect(body.querySelectorAll('br')).toHaveLength(2);
	});

	it('shows a JSON body as code and holds back a very long one until asked', async () => {
		const big = JSON.stringify({
			lanes: Array.from({ length: 2000 }, (_, i) => ({ id: i, s: 'ok' }))
		});
		const workflow: TimelineEvent = {
			...event('evt-16'),
			id: 'wf',
			title: 'Workflow completed',
			summary: 'Workflow finished',
			metadata: {
				task_kind: 'workflow',
				task_status: 'completed',
				task_summary: 'Workflow finished',
				full_content: big
			}
		};
		const { container } = setup([workflow]);
		const dialog = await openPopupFor(container, 'Workflow finished');
		const code = dialog.querySelector('pre')!;
		expect(code.textContent).toContain('"lanes": [');
		expect(code.textContent!.length).toBeLessThan(7000);
		expect(dialog).toHaveTextContent(/more characters/);
		await fireEvent.click(within(dialog).getByRole('button', { name: 'Show all' }));
		expect(dialog.querySelector('pre')!.textContent!.length).toBeGreaterThan(big.length);
	});
});

describe('keyboard and screen-reader structure', () => {
	afterEach(cleanup);

	it('names the hide control after its event', () => {
		const { container } = setup();
		const shell = row(container, 'shell_command')!;
		expect(
			within(shell).getByRole('button', { name: 'Hide event: Shell command' })
		).toBeInTheDocument();
	});

	it('opens an event from a real button, not a role=button container', () => {
		const { container } = setup();
		expect(container.querySelector('[data-event-index] [role="button"]')).toBeNull();
		const shell = row(container, 'shell_command')!;
		const expand = within(shell).getByRole('button', { name: 'Show details: Shell command' });
		expect(expand.tagName).toBe('BUTTON');
		expect(expand).toHaveAttribute('aria-haspopup', 'dialog');
	});

	it('does not open the event when a link inside the card is clicked', async () => {
		const { container } = setup();
		const out = rowWithText(container, 'Fix round is at 3161b7d')!;
		const link = within(out).getByRole('link', { name: /rev-m6/ });
		// jsdom cannot navigate; the click still has to reach the card's handler.
		link.addEventListener('click', (e) => e.preventDefault());
		await fireEvent.click(link);
		expect(document.querySelector('[role="dialog"]')).toBeNull();
	});
});

describe('untrusted names and bodies', () => {
	afterEach(cleanup);

	const hostileName = '<img src=x onerror="window.__pwned=1">';
	const hostile: TimelineEvent = {
		...event('evt-6'),
		id: 'evt-hostile',
		actor: hostileName,
		actor_name: hostileName,
		summary: '<script>window.__pwned=1</script>',
		metadata: {
			...event('evt-6').metadata,
			peer_name: hostileName,
			full_content:
				'<div style="position:fixed;inset:0">overlay</div>\n\n![pixel](https://evil.example/p.png)'
		}
	};

	it('renders a hostile peer name and summary as text', () => {
		const { container } = setup([hostile]);
		expect(container.querySelector('img')).toBeNull();
		expect(container.querySelector('script')).toBeNull();
		expect(row(container, 'message')).toHaveTextContent(hostileName);
	});

	it('also treats it as text in the search-highlighted path', () => {
		const { container } = render(TimelineRail, {
			props: { events: [hostile], searchQuery: 'onerror', ...routeProps }
		});
		expect(container.querySelector('img')).toBeNull();
		expect(container.querySelector('mark')).toHaveTextContent('onerror');
	});

	it('renders a hostile body without inline styles or remote images', async () => {
		const { container } = setup([hostile]);
		await fireEvent.click(within(container).getByRole('button', { name: /^Show details/ }));
		const dialog = await waitFor(() => {
			const found = document.querySelector<HTMLElement>('[role="dialog"]');
			if (!found) throw new Error('popup not open');
			return found;
		});
		expect(dialog).toHaveTextContent('overlay');
		expect(dialog.querySelector('[style*="position"]')).toBeNull();
		expect(dialog.querySelector('img')).toBeNull();
		expect(within(dialog).getByRole('link', { name: 'Image: pixel' })).toHaveAttribute(
			'href',
			'https://evil.example/p.png'
		);
	});
});

describe('when the event list changes between renders', () => {
	afterEach(cleanup);

	const base = [event('evt-1'), event('evt-11'), event('evt-13')];
	const inserted: TimelineEvent = {
		...event('evt-15'),
		id: 'evt-new',
		timestamp: '2026-11-18T10:06:30Z'
	};

	it('keeps a hidden event hidden when a new event arrives before it', async () => {
		const { container, rerender } = setup(base);
		const recap = rowWithText(container, 'Recap while you were away')!;
		await fireEvent.click(
			within(recap).getByRole('button', { name: 'Hide event: Recap while you were away' })
		);
		expect(rowWithText(container, 'Recap while you were away')).toBeNull();

		await rerender({ events: [base[0], inserted, base[1], base[2]], ...routeProps });
		expect(rowWithText(container, 'Recap while you were away')).toBeNull();
		expect(rowWithText(container, 'Read file')).not.toBeNull();
		expect(row(container, 'shell_command')).not.toBeNull();
	});

	it('refreshes an open popup when its event gains content', async () => {
		const running: TimelineEvent = {
			...event('evt-11'),
			metadata: { command: 'make test', result_content: 'running' }
		};
		const { container, rerender } = setup([base[0], running]);
		await fireEvent.click(
			within(row(container, 'shell_command')!).getByRole('button', { name: /^Show details/ })
		);
		const dialog = await waitFor(() => {
			const found = document.querySelector<HTMLElement>('[role="dialog"]');
			if (!found) throw new Error('popup not open');
			return found;
		});
		expect(dialog).toHaveTextContent('running');

		const finished: TimelineEvent = {
			...running,
			metadata: { command: 'make test', result_content: '42 passed', stderr: 'one warning' }
		};
		await rerender({ events: [base[0], inserted, finished], ...routeProps });
		await waitFor(() => expect(dialog).toHaveTextContent('42 passed'));
		expect(dialog).toHaveTextContent('one warning');
	});

	it('finds an event by a name the backend filled in on a later poll', async () => {
		const unnamed: TimelineEvent = {
			...event('evt-5'),
			title: 'Message to uds:/tmp/cc-socks/1.sock',
			metadata: {
				...event('evt-5').metadata,
				peer_name: null,
				peer_agent_id: null,
				peer_address: 'uds:/tmp/cc-socks/1.sock'
			}
		};
		const props = { searchQuery: 'researcher', ...routeProps };
		const { container, rerender } = render(TimelineRail, {
			props: { events: [base[0], unnamed], ...props }
		});
		expect(row(container, 'message')).toBeNull();

		const named: TimelineEvent = {
			...unnamed,
			title: 'Message to researcher',
			metadata: { ...unnamed.metadata, peer_name: 'researcher' }
		};
		await rerender({ events: [base[0], named], ...props });
		expect(row(container, 'message')).toHaveTextContent('researcher');
	});
});

describe('long gaps', () => {
	afterEach(cleanup);

	it('summarises a long run of hidden events by kind and still reveals them', async () => {
		const many: TimelineEvent[] = [event('evt-1')];
		for (let i = 0; i < 30; i++) {
			many.push({
				...event('evt-15'),
				id: `tool-${i}`,
				actor: 'session',
				actor_type: 'session',
				actor_name: null,
				metadata: { tool_name: i < 20 ? 'Bash' : 'Read', has_result: true }
			});
		}
		many.push({ ...event('evt-13'), id: 'recap-end' });
		const { container, getByRole } = setup(many);
		await fireEvent.click(getByRole('button', { name: /^Prompts/ }));

		expect(container).toHaveTextContent('hidden (31)');
		expect(container).toHaveTextContent('20 Bash');
		expect(container).toHaveTextContent('10 Read');
		expect(container).toHaveTextContent('1 notice');
		expect(container.textContent).not.toContain('Tool Bash');

		await fireEvent.click(getByRole('button', { name: /10\s+Read/ }));
		expect(rows(container, 'tool_call')).toHaveLength(10);
	});
});

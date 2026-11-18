import { describe, it, expect } from 'vitest';
import type { TimelineEvent, TimelineEventType } from '$lib/api-types';
import { getAgentIdentityColors } from '$lib/utils/agent-identity';
import {
	buildAgentHref,
	formatCompactTokens,
	getActorColors,
	getAgentColorVars,
	getDisplaySummary,
	getDisplayTitle,
	getEventSections,
	getMessageRoute,
	isEventExpandable,
	isFailedTask,
	shortAgentId
} from '$lib/components/timeline/timeline-display';
import { getEventConfig, unknownEventConfig } from '$lib/components/timeline/tool-icons';

function ev(
	event_type: TimelineEventType,
	metadata: TimelineEvent['metadata'] = {},
	extra: Partial<TimelineEvent> = {}
): TimelineEvent {
	return {
		id: 'evt-1',
		timestamp: '2026-11-18T10:00:00Z',
		event_type,
		title: 'Backend title',
		actor: 'session',
		actor_type: 'session',
		metadata,
		...extra
	};
}

describe('agent identity', () => {
	it('never shows a raw agent id', () => {
		expect(shortAgentId('a9f8e7d6c5b4a3f2e')).toBe('a9f8e7d6');
		expect(shortAgentId('abuilder-b-0b0b0b0b0b0b0b0b')).toBe('builder-b');
		expect(shortAgentId('builder-c')).toBe('builder-c');
	});

	it('encodes the agent id in links and needs the route to build one', () => {
		expect(buildAgentHref('-Users-me-repo', 'abc12345', 'a/b?c#d')).toBe(
			'/projects/-Users-me-repo/abc12345/agents/a%2Fb%3Fc%23d'
		);
		expect(buildAgentHref(undefined, 'abc12345', 'a1')).toBeNull();
	});

	it('maps Claude Code colour names to tokens', () => {
		expect(getAgentColorVars('cyan')).toEqual({
			color: 'var(--agent-cyan)',
			subtle: 'var(--agent-cyan-subtle)'
		});
		expect(getAgentColorVars('Yellow').color).toBe('var(--agent-yellow)');
	});

	it('resolves in one order: own colour, then type colour, then name hash', () => {
		expect(getAgentColorVars('cyan', 'Explore', 'reviewer-a').color).toBe('var(--agent-cyan)');
		expect(getAgentColorVars(null, 'Explore', 'reviewer-a').color).toBe(
			'var(--subagent-explore)'
		);
		expect(getAgentColorVars(null, null, 'reviewer-a').color).toMatch(
			/^var\(--agent-[a-z]+\)$/
		);
	});

	it('colours a named agent with a type and no colour the same in every place', () => {
		const identity = {
			agent_id: 'areviewer-a-0123456789abcdef',
			name: 'reviewer-a',
			subagent_type: 'Explore'
		};
		const card = getAgentIdentityColors(identity);
		expect(card.color).toBe('var(--subagent-explore)');

		const actor = {
			actor: identity.agent_id,
			actor_type: 'subagent',
			actor_name: 'reviewer-a'
		} as const;
		const typed = { ...actor, actor_agent_type: 'Explore' };
		expect(getActorColors(ev('tool_call', {}, typed))).toEqual(card);

		const incoming = ev(
			'message',
			{ direction: 'in', peer_kind: 'agent', peer_name: 'reviewer-a' },
			typed
		);
		expect(getMessageRoute(incoming).from.colors).toEqual(card);

		const outgoing = ev('message', {
			direction: 'out',
			peer_kind: 'agent',
			peer_name: 'reviewer-a',
			peer_agent_type: 'Explore'
		});
		expect(getMessageRoute(outgoing).to.colors).toEqual(card);
	});

	it('matches the subagent card for an agent with no colour, type or name', () => {
		const unnamed = ev(
			'tool_call',
			{},
			{ actor: 'a9f8e7d6c5b4a3f2e', actor_type: 'subagent', actor_name: null }
		);
		expect(getActorColors(unnamed)).toEqual(
			getAgentIdentityColors({ agent_id: 'a9f8e7d6c5b4a3f2e' })
		);
	});

	it('still gives an unnamed peer session a stable colour from its address', () => {
		const anon = ev('message', {
			direction: 'in',
			peer_kind: 'session',
			peer_address: 'uds:/tmp/cc-socks/4101.sock'
		});
		expect(getMessageRoute(anon).from.colors?.color).toMatch(/^var\(--agent-[a-z]+\)$/);
	});

	it('tells named agents of a colourless type apart by their names', () => {
		const a = getAgentColorVars(null, 'general-purpose', 'reviewer-a');
		const b = getAgentColorVars(null, 'general-purpose', 'builder-b');
		expect(a.color).toMatch(/^var\(--agent-[a-z]+\)$/);
		expect(a).toEqual(getAgentColorVars(null, null, 'reviewer-a'));
		expect(a).not.toEqual(b);
		// An unnamed agent of that type keeps the default, and a type with its own colour still wins.
		expect(getAgentColorVars(null, 'general-purpose').color).toBe('var(--subagent-default)');
		expect(getAgentColorVars(null, 'Explore', 'reviewer-a').color).toBe(
			'var(--subagent-explore)'
		);
	});

	it('falls back to the type colour, then a stable name hash, then the default', () => {
		expect(getAgentColorVars(null, 'Explore').color).toBe('var(--subagent-explore)');
		const hashed = getAgentColorVars('not-a-colour', null, 'billing-api-1');
		expect(hashed.color).toMatch(/^var\(--agent-[a-z]+\)$/);
		expect(getAgentColorVars(null, null, 'billing-api-1')).toEqual(hashed);
		expect(getAgentColorVars(null).color).toBe('var(--subagent-default)');
	});
});

describe('messages', () => {
	const incoming = ev(
		'message',
		{
			direction: 'in',
			peer_kind: 'session',
			peer_name: 'billing-api-1',
			peer_address: 'uds:/tmp/cc-socks/4102.sock',
			full_content: '[ASK] What did you learn?'
		},
		{ actor: 'billing-api-1', actor_type: 'peer_session', actor_name: 'billing-api-1' }
	);

	it('titles a message by its other party', () => {
		expect(getDisplayTitle(incoming)).toBe('Message from billing-api-1');
		const out = ev('message', {
			direction: 'out',
			peer_kind: 'agent',
			peer_name: 'reviewer-a'
		});
		expect(getDisplayTitle(out)).toBe('Message to reviewer-a');
	});

	it('routes an incoming message from the peer to this session', () => {
		const route = getMessageRoute(incoming);
		expect(route.from).toMatchObject({ label: 'billing-api-1', kind: 'session' });
		expect(route.to).toEqual({ label: 'this session', kind: 'self' });
	});

	it('routes an outgoing message to a linkable agent', () => {
		const out = ev('message', {
			direction: 'out',
			peer_kind: 'agent',
			peer_name: 'reviewer-a',
			peer_agent_id: 'a1c2d3e4f5a6b7c8d',
			peer_color: 'yellow'
		});
		const route = getMessageRoute(out, 'a2b3c4d5e6f7a8b9c');
		expect(route.from).toEqual({ label: 'this agent', kind: 'self' });
		expect(route.to).toMatchObject({
			label: 'reviewer-a',
			kind: 'agent',
			agentId: 'a1c2d3e4f5a6b7c8d',
			colors: { color: 'var(--agent-yellow)' }
		});
	});

	it('falls back to the socket name when the peer has no name', () => {
		const anon = ev('message', {
			direction: 'in',
			peer_kind: 'session',
			peer_address: 'uds:/tmp/cc-socks/4101.sock'
		});
		expect(getMessageRoute(anon).from.label).toBe('4101');
	});

	it('gives the parent session one name and no agent link', () => {
		const fromMain = ev('message', { direction: 'in', peer_kind: 'agent', peer_name: 'main' });
		expect(getDisplayTitle(fromMain)).toBe('Message from main session');
		const route = getMessageRoute(fromMain, 'a2b3c4d5e6f7a8b9c');
		expect(route.from).toMatchObject({ label: 'main session', kind: 'session', agentId: null });
		expect(route.from.colors?.color).toBe('var(--subagent-default)');
	});

	it('shows a delivery result only when delivery failed', () => {
		const sent = {
			direction: 'out' as const,
			full_content: 'hello',
			result_content: "{'type': 'tool_result'}"
		};
		expect(getEventSections(ev('message', { ...sent, result_status: 'success' }))).toHaveLength(
			1
		);
		expect(
			getEventSections(ev('message', { ...sent, result_status: 'error' })).map((s) => s.label)
		).toEqual([undefined, 'Delivery error']);
	});

	it('previews the message summary before the body', () => {
		expect(getDisplaySummary(incoming)).toBe('[ASK] What did you learn?');
		const withSummary = ev('message', {
			message_summary: 'Review round 2',
			full_content: 'long'
		});
		expect(getDisplaySummary(withSummary)).toBe('Review round 2');
	});
});

describe('titles', () => {
	it('labels a background event by its kind and what happened', () => {
		const title = (task_kind: string | null, task_status: string | null) =>
			getDisplayTitle(ev('task_notification', { task_kind, task_status } as never));
		expect(title('shell', 'completed')).toBe('Background command finished');
		expect(title('agent', 'completed')).toBe('Agent finished');
		expect(title('workflow', 'failed')).toBe('Workflow failed');
		expect(title('mcp', 'killed')).toBe('MCP task stopped');
		expect(title(null, 'completed')).toBe('Background task finished');
		expect(title('shell', 'running')).toBe('Background command running');
	});

	it('treats a missing status as an update, not as finished', () => {
		const monitor = ev('task_notification', { task_kind: 'monitor', task_status: null });
		expect(getDisplayTitle(monitor)).toBe('Monitor update');
		expect(getDisplayTitle(ev('task_notification'))).toBe('Background task update');
	});

	it('words an idle teammate by name, in either shape the backend has used', () => {
		const idle = ev(
			'system_context',
			{ kind: 'agent_idle' },
			{
				actor: 'abuilder-b-0b0b0b0b0b0b0b0b',
				actor_type: 'subagent',
				actor_name: 'builder-b'
			}
		);
		expect(getDisplayTitle(idle)).toBe('builder-b is idle');
		expect(getDisplaySummary({ ...idle, summary: 'builder-b is idle (available)' })).toBeNull();
		const legacy = ev('task_notification', { task_status: 'idle', agent_name: 'builder-b' });
		expect(getDisplayTitle(legacy)).toBe('builder-b is idle');
	});

	it('only counts failed statuses as failures', () => {
		expect(isFailedTask(ev('task_notification', { task_status: 'failed' }))).toBe(true);
		expect(isFailedTask(ev('task_notification', { task_status: 'killed' }))).toBe(false);
		expect(isFailedTask(ev('task_notification', { task_status: null }))).toBe(false);
	});

	it('titles an interruption from the user side and gives it nothing to open', () => {
		const interrupted = ev('system_notice', {
			kind: 'interrupted',
			full_content: '[Request interrupted by user]'
		});
		expect(getDisplayTitle(interrupted)).toBe('You interrupted Claude');
		expect(isEventExpandable(interrupted)).toBe(false);
		expect(getEventSections(interrupted)).toEqual([]);
	});

	it('uses fixed copy for harness events', () => {
		expect(getDisplayTitle(ev('compaction'))).toBe('Context compacted');
		expect(getDisplayTitle(ev('system_notice', { kind: 'away_summary' }))).toBe(
			'Recap while you were away'
		);
		expect(getDisplayTitle(ev('system_context', { kind: 'system_reminder' }))).toBe(
			'System reminder'
		);
		expect(getDisplayTitle(ev('system_notice', { kind: 'something_new' }))).toBe(
			'Backend title'
		);
	});

	it('shows a subagent first message as a task prompt', () => {
		expect(getDisplayTitle(ev('prompt', { is_task_prompt: true }))).toBe('Task prompt');
		expect(getDisplayTitle(ev('prompt'))).toBe('Backend title');
	});

	it('keeps the backend title for types it does not know', () => {
		expect(getDisplayTitle(ev('brand_new_type' as TimelineEventType))).toBe('Backend title');
	});
});

describe('expanded content', () => {
	it('splits a shell command into command, output and errors', () => {
		const shell = ev('shell_command', {
			command: 'ls',
			result_content: 'a\nb',
			stderr: 'warn'
		});
		expect(getEventSections(shell)).toEqual([
			{ label: 'Command', content: 'ls', format: 'pre' },
			{ label: 'Output', content: 'a\nb', format: 'pre' },
			{ label: 'Errors', content: 'warn', format: 'pre' }
		]);
		expect(getDisplaySummary(shell)).toBe('$ ls');
	});

	it('shows command output and the skill body after the main content', () => {
		const command = ev('builtin_command', {
			full_content: '/model fable',
			result_content: 'Set model to Fable',
			skill_body: '# Skill'
		});
		expect(getEventSections(command).map((s) => s.label)).toEqual([
			undefined,
			'Output',
			'Skill instructions'
		]);
	});

	it('uses the tool result as the main content when there is nothing else', () => {
		const skill = ev('skill_invocation', { result_content: 'Launching skill: x' });
		expect(getEventSections(skill)).toEqual([
			{ label: undefined, content: 'Launching skill: x', format: 'markdown' }
		]);
	});

	it('marks events with hidden detail as expandable', () => {
		expect(isEventExpandable(ev('tool_call'))).toBe(true);
		expect(isEventExpandable(ev('compaction', { full_content: 'summary' }))).toBe(true);
		expect(isEventExpandable(ev('compaction'))).toBe(false);
		expect(isEventExpandable(ev('skill_invocation', { skill_body: '# Skill' }))).toBe(true);
	});

	it('offers a notice url as a link only when it is plain https', () => {
		const section = (url: string) =>
			getEventSections(
				ev('system_notice', { kind: 'bridge_status', full_content: 'x', url })
			).at(-1);
		expect(section('https://claude.ai/code/session_1')).toEqual({
			label: 'Link',
			content: 'https://claude.ai/code/session_1',
			format: 'link'
		});
		expect(section('javascript:alert(1)')?.format).toBe('pre');
	});

	it('shows a JSON body as code: pretty when it parses, as written when it was cut short', () => {
		const whole = ev('task_notification', { full_content: '{"result":"No events matched"}' });
		expect(getEventSections(whole)[0]).toEqual({
			label: undefined,
			content: '{\n  "result": "No events matched"\n}',
			format: 'pre'
		});
		const cut =
			'{"lanes":[{"lane":"auctions","summary":"cut off he... (full output at /tmp/x.output)';
		expect(getEventSections(ev('task_notification', { full_content: cut }))[0]).toEqual({
			label: undefined,
			content: cut,
			format: 'pre'
		});
		const prose = ev('response', { full_text: 'Use {braces} sparingly.' });
		expect(getEventSections(prose)[0].format).toBe('markdown');
	});

	it('keeps line breaks for message and prompt bodies only', () => {
		const body = 'line one\nline two';
		expect(getEventSections(ev('message', { full_content: body }))[0].keepBreaks).toBe(true);
		expect(getEventSections(ev('prompt', { full_content: body }))[0].keepBreaks).toBe(true);
		expect(getEventSections(ev('response', { full_text: body }))[0].keepBreaks).toBeUndefined();
	});

	it('formats token counts for the compaction row', () => {
		expect(formatCompactTokens(150000)).toBe('150k');
		expect(formatCompactTokens(1_250_000)).toBe('1.3M');
		expect(formatCompactTokens(null)).toBeNull();
	});
});

describe('event config', () => {
	it('gives unknown event types a neutral look instead of failing', () => {
		expect(getEventConfig('brand_new_type')).toBe(unknownEventConfig);
		expect(getEventConfig('message')).not.toBe(unknownEventConfig);
	});
});

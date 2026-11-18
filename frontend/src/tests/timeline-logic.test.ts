import { describe, it, expect } from 'vitest';
import type { TimelineEvent, TimelineEventType } from '$lib/api-types';
import {
	FILTER_CATEGORIES,
	buildViewItems,
	calculateFilterCounts,
	createTimelineLogic,
	isSystemContext,
	matchesFilters,
	matchesSearch,
	matchesSingleFilter,
	selectBaseEvents
} from '$lib/utils/timelineLogic.svelte';

let seq = 0;
function ev(
	event_type: TimelineEventType,
	metadata: TimelineEvent['metadata'] = {},
	extra: Partial<TimelineEvent> = {}
): TimelineEvent {
	seq += 1;
	return {
		id: `evt-${seq}`,
		timestamp: `2026-11-18T10:00:${String(seq % 60).padStart(2, '0')}Z`,
		event_type,
		title: event_type,
		actor: 'session',
		actor_type: 'session',
		metadata,
		...extra
	};
}

const gapsOf = (items: ReturnType<typeof buildViewItems>) =>
	items.filter((i) => 'type' in i && i.type === 'gap');

describe('System filter', () => {
	const events = [
		ev('prompt'),
		ev('system_context', { kind: 'system_reminder' }),
		ev('response'),
		ev('message', { direction: 'in' }),
		ev('system_context', { kind: 'meta' }),
		ev('tool_call', { tool_name: 'Bash' })
	];
	const types = (timeline: ReturnType<typeof createTimelineLogic>) =>
		timeline.viewItems.map((i) => ('type' in i ? `gap:${i.events.length}` : i.event_type));

	it('only treats system_context as left out by default', () => {
		expect(isSystemContext(ev('system_context'))).toBe(true);
		for (const type of ['system_notice', 'compaction', 'task_notification'] as const) {
			expect(isSystemContext(ev(type))).toBe(false);
		}
		expect(selectBaseEvents(events, false).some(isSystemContext)).toBe(false);
		expect(selectBaseEvents(events, true)).toHaveLength(events.length);
	});

	it('by default shows neither system rows nor gaps for them', () => {
		const timeline = createTimelineLogic(() => events);
		expect(timeline.showSystem).toBe(false);
		expect(types(timeline)).toEqual(['prompt', 'response', 'message', 'tool_call']);
		expect(timeline.baseEvents).toHaveLength(4);
		expect(timeline.hasActiveFilter).toBe(false);
	});

	it('still leaves them out, with no gaps, when another filter or a search is active', () => {
		const timeline = createTimelineLogic(() => events);
		timeline.toggleFilter('prompt');
		expect(types(timeline)).toEqual(['prompt', 'gap:3']);
		timeline.clearFilters();
		timeline.setSearchQuery('zzz-no-match');
		expect(types(timeline)).toEqual(['gap:4']);
	});

	it('counts system events on its chip whether or not it is selected', () => {
		const timeline = createTimelineLogic(() => events);
		expect(timeline.counts.system).toBe(2);
		timeline.toggleFilter('system');
		expect(timeline.counts.system).toBe(2);
	});

	it('selected alone, shows only the system events, with gaps for the rest', () => {
		const timeline = createTimelineLogic(() => events);
		timeline.toggleFilter('system');
		expect(timeline.showSystem).toBe(true);
		expect(timeline.hasActiveFilter).toBe(true);
		expect(types(timeline)).toEqual([
			'gap:1',
			'system_context',
			'gap:2',
			'system_context',
			'gap:1'
		]);
		expect(timeline.matchingCount).toBe(2);
		expect(timeline.baseEvents).toHaveLength(events.length);
	});

	it('selected with Messages, shows both kinds', () => {
		const timeline = createTimelineLogic(() => events);
		timeline.toggleFilter('system');
		timeline.toggleFilter('message');
		expect(types(timeline)).toEqual([
			'gap:1',
			'system_context',
			'gap:1',
			'message',
			'system_context',
			'gap:1'
		]);
		expect(timeline.matchingCount).toBe(3);
	});

	it('is cleared by Clear like any other filter', () => {
		const timeline = createTimelineLogic(() => events);
		timeline.toggleFilter('system');
		timeline.clearFilters();
		expect(timeline.showSystem).toBe(false);
		expect(types(timeline)).toEqual(['prompt', 'response', 'message', 'tool_call']);
	});

	it('keeps a system event out of every other chip, even one sent by a subagent', () => {
		const idle = ev(
			'system_context',
			{ kind: 'agent_idle' },
			{ actor: 'a1', actor_type: 'subagent', actor_name: 'builder-b' }
		);
		expect(matchesSingleFilter(idle, 'system')).toBe(true);
		expect(matchesSingleFilter(idle, 'subagent')).toBe(false);
		expect(calculateFilterCounts([idle]).subagent).toBe(0);
	});

	it('does not treat "every other chip selected" as everything while System is selected', () => {
		const timeline = createTimelineLogic(() => events);
		for (const chip of ['prompt', 'response', 'message', 'tool_call'] as const) {
			timeline.toggleFilter(chip);
		}
		expect(timeline.hasActiveFilter).toBe(false);
		timeline.toggleFilter('system');
		expect(timeline.hasActiveFilter).toBe(true);
		expect(timeline.viewItems).toHaveLength(events.length);
	});
});

describe('gaps', () => {
	it('groups filtered-out runs into gaps between visible events', () => {
		const events = [
			ev('prompt'),
			ev('thinking'),
			ev('thinking'),
			ev('response'),
			ev('thinking')
		];
		const items = buildViewItems({
			events,
			hasActiveFilter: true,
			isTailing: false,
			tailCount: 3,
			revealedIds: new Set(),
			hiddenIds: new Set(),
			matches: (e) => e.event_type !== 'thinking'
		});
		expect(items.map((i) => ('type' in i ? `gap:${i.events.length}` : i.event_type))).toEqual([
			'prompt',
			'gap:2',
			'response',
			'gap:1'
		]);
	});

	it('shows only the last N events while tailing without a filter', () => {
		const events = [
			ev('prompt'),
			ev('thinking'),
			ev('response'),
			ev('tool_call'),
			ev('response')
		];
		const items = buildViewItems({
			events,
			hasActiveFilter: false,
			isTailing: true,
			tailCount: 2,
			revealedIds: new Set(),
			hiddenIds: new Set(),
			matches: () => true
		});
		expect(items.map((i) => ('type' in i ? 'gap' : i.event_type))).toEqual([
			'gap',
			'tool_call',
			'response'
		]);
	});
});

describe('filter categories', () => {
	it('merges TodoWrite and the Task tools into Tasks', () => {
		expect(matchesSingleFilter(ev('todo_update'), 'task')).toBe(true);
		for (const tool_name of ['TaskCreate', 'TaskUpdate', 'TaskGet', 'TaskList']) {
			expect(matchesSingleFilter(ev('tool_call', { tool_name }), 'task')).toBe(true);
		}
		expect(matchesSingleFilter(ev('tool_call', { tool_name: 'Bash' }), 'task')).toBe(false);
		expect(FILTER_CATEGORIES).not.toContain('todo_update');
	});

	it('matches Messages for messages in either direction', () => {
		expect(matchesSingleFilter(ev('message', { direction: 'in' }), 'message')).toBe(true);
		expect(
			matchesSingleFilter(
				ev('message', { direction: 'out', tool_name: 'SendMessage' }),
				'message'
			)
		).toBe(true);
		expect(matchesSingleFilter(ev('prompt'), 'message')).toBe(false);
	});

	it('does not count an outgoing message as a tool call', () => {
		const out = ev('message', { direction: 'out', tool_name: 'SendMessage' });
		expect(matchesSingleFilter(out, 'tool_call')).toBe(false);
	});

	it('matches Background for task notifications and scheduled fires', () => {
		expect(matchesSingleFilter(ev('task_notification'), 'background')).toBe(true);
		expect(matchesSingleFilter(ev('scheduled_fire'), 'background')).toBe(true);
		expect(matchesSingleFilter(ev('system_notice'), 'background')).toBe(false);
	});

	it('matches Notices for system notices and compaction', () => {
		expect(matchesSingleFilter(ev('system_notice', { kind: 'away_summary' }), 'notice')).toBe(
			true
		);
		expect(matchesSingleFilter(ev('compaction'), 'notice')).toBe(true);
		expect(matchesSingleFilter(ev('system_context'), 'notice')).toBe(false);
	});

	it('puts shell commands under Commands, not Prompts', () => {
		const shell = ev('shell_command', { command: 'ls' }, { actor: 'user', actor_type: 'user' });
		expect(matchesSingleFilter(shell, 'command')).toBe(true);
		expect(matchesSingleFilter(shell, 'prompt')).toBe(false);
		expect(matchesSingleFilter(ev('builtin_command'), 'command')).toBe(true);
		expect(matchesSingleFilter(ev('command_invocation'), 'command')).toBe(true);
	});

	it('counts a failed background task as an error', () => {
		expect(
			matchesSingleFilter(ev('task_notification', { task_status: 'failed' }), 'error')
		).toBe(true);
		expect(
			matchesSingleFilter(ev('task_notification', { task_status: 'completed' }), 'error')
		).toBe(false);
	});

	it('keeps the agent-view rule for Subagents', () => {
		const own = ev('tool_call', { tool_name: 'Read' }, { actor: 'a1', actor_type: 'subagent' });
		const spawn = ev('subagent_spawn', { spawned_agent_id: 'a2' });
		expect(matchesSingleFilter(own, 'subagent')).toBe(true);
		expect(matchesSingleFilter(own, 'subagent', 'a1')).toBe(false);
		expect(matchesSingleFilter(spawn, 'subagent', 'a1')).toBe(true);
	});

	it('matches nothing for an event type it does not know', () => {
		const unknown = ev('brand_new_type' as TimelineEventType);
		for (const category of FILTER_CATEGORIES) {
			expect(matchesSingleFilter(unknown, category)).toBe(false);
		}
	});
});

describe('calculateFilterCounts', () => {
	it('counts an event under every chip it belongs to', () => {
		const counts = calculateFilterCounts([
			ev('response', { is_big_response: true }),
			ev('response'),
			ev('tool_call', { tool_name: 'mcp__x__y', has_result: true, result_status: 'error' })
		]);
		expect(counts).toMatchObject({
			response: 2,
			big_response: 1,
			tool_call: 1,
			mcp_tool: 1,
			error: 1,
			prompt: 0
		});
	});

	it('has a count for every chip', () => {
		expect(Object.keys(calculateFilterCounts([])).sort()).toEqual(
			[...FILTER_CATEGORIES].sort()
		);
	});
});

describe('search', () => {
	it('does not match on ids and addresses that the card never shows', () => {
		const message = ev('message', {
			direction: 'in',
			peer_kind: 'session',
			peer_name: 'docs-site-2',
			peer_address: 'uds:/tmp/cc-socks/4101.sock',
			peer_agent_id: 'a1c2d3e4f5a6b7c8d',
			peer_session_uuid: '0a1b2c3d-0000-4000-8000-000000000001',
			peer_project_encoded_name: '-Users-me-docs'
		});
		for (const query of ['users', '0a1b2c3d', 'cc-socks', 'a1c2d3e4']) {
			expect(matchesSearch(message, query), query).toBe(false);
		}
		expect(matchesSearch(message, 'docs-site')).toBe(true);
	});

	it('matches the wording shown on the card, not only the backend title', () => {
		const done = ev('task_notification', { task_kind: 'shell', task_status: 'completed' });
		expect(matchesSearch({ ...done, title: 'Background command completed' }, 'finished')).toBe(
			true
		);
	});

	it('sees text the backend changes on a later poll for the same event id', () => {
		const first = ev('shell_command', { command: 'make test', stderr: '' });
		expect(matchesSearch(first, 'deprecated')).toBe(false);
		const later = { ...first, metadata: { command: 'make test', stderr: 'deprecated flag' } };
		expect(matchesSearch(later, 'deprecated')).toBe(true);

		const local = {
			...first,
			event_type: 'builtin_command' as const,
			title: 'Built-in: /model'
		};
		expect(matchesSearch(local, '/model')).toBe(true);
	});
});

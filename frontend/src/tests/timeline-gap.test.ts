import { describe, it, expect } from 'vitest';
import type { TimelineEvent, TimelineEventType } from '$lib/api-types';
import { getGapEventName, summarizeGap } from '$lib/components/timeline/timeline-gap';

let seq = 0;
function ev(event_type: TimelineEventType, tool_name?: string): TimelineEvent {
	seq += 1;
	return {
		id: `e${seq}`,
		timestamp: '2026-11-18T10:00:00Z',
		event_type,
		title: event_type,
		actor: 'session',
		actor_type: 'session',
		metadata: tool_name ? { tool_name } : {}
	};
}

const many = (n: number, make: () => TimelineEvent) => Array.from({ length: n }, make);

describe('summarizeGap', () => {
	it('names the three largest kinds and folds the rest into a count of kinds', () => {
		const events = [
			...many(96, () => ev('response')),
			...many(310, () => ev('thinking')),
			...many(240, () => ev('tool_call', 'Bash')),
			...many(5, () => ev('tool_call', 'Read')),
			...many(2, () => ev('message')),
			ev('compaction')
		];
		const summary = summarizeGap(events);
		expect(summary.groups.map((g) => `${g.count} ${g.label}`)).toEqual([
			'310 thinking',
			'240 Bash',
			'96 responses'
		]);
		expect(summary.otherKinds).toBe(3);
		expect(summary.otherCount).toBe(8);
	});

	it('keeps the ids of each kind so one kind can be revealed', () => {
		const bash = many(3, () => ev('tool_call', 'Bash'));
		const summary = summarizeGap([...bash, ev('thinking')]);
		expect(summary.groups[0].ids).toEqual(bash.map((e) => e.id));
	});

	it('names a single leftover kind instead of calling it "1 other kind"', () => {
		const events = [
			...many(4, () => ev('thinking')),
			...many(3, () => ev('response')),
			...many(2, () => ev('message')),
			ev('compaction')
		];
		const summary = summarizeGap(events);
		expect(summary.groups.map((g) => g.label)).toEqual([
			'thinking',
			'responses',
			'messages',
			'compaction'
		]);
		expect(summary.otherKinds).toBe(0);
	});

	it('uses the singular for one event and plain words for unknown kinds', () => {
		const summary = summarizeGap([ev('message'), ev('brand_new_type' as TimelineEventType)]);
		expect(summary.groups.map((g) => g.label)).toEqual(['message', 'brand new type']);
	});
});

describe('getGapEventName', () => {
	it('names a hidden event the way short gaps list them', () => {
		expect(getGapEventName(ev('tool_call', 'Bash'))).toBe('Tool Bash');
		expect(getGapEventName(ev('task_notification'))).toBe('Background task');
		expect(getGapEventName(ev('system_context'))).toBe('System event');
	});
});

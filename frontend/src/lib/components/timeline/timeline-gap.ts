import type { TimelineEvent } from '$lib/api-types';

/** Above this many hidden events a gap shows counts per kind instead of every event. */
export const GAP_LIST_LIMIT = 12;

// Kinds named in a long gap before the rest is folded into "other kinds".
const GAP_TOP_KINDS = 3;

// [singular, plural]; tool calls are named by their tool instead.
const KIND_NAMES: Record<string, [string, string]> = {
	prompt: ['prompt', 'prompts'],
	thinking: ['thinking', 'thinking'],
	response: ['response', 'responses'],
	subagent_spawn: ['subagent', 'subagents'],
	todo_update: ['todo update', 'todo updates'],
	skill_invocation: ['skill', 'skills'],
	command_invocation: ['command', 'commands'],
	builtin_command: ['built-in command', 'built-in commands'],
	api_error: ['API error', 'API errors'],
	message: ['message', 'messages'],
	task_notification: ['background task', 'background tasks'],
	scheduled_fire: ['scheduled task', 'scheduled tasks'],
	compaction: ['compaction', 'compactions'],
	shell_command: ['shell command', 'shell commands'],
	system_notice: ['notice', 'notices'],
	system_context: ['system event', 'system events']
};

function kindKey(event: TimelineEvent): string {
	if (event.event_type === 'tool_call') return `tool:${event.metadata?.tool_name || 'Tool'}`;
	return event.event_type;
}

function kindLabel(key: string, count: number): string {
	if (key.startsWith('tool:')) return key.slice(5);
	const names = KIND_NAMES[key];
	if (names) return count === 1 ? names[0] : names[1];
	return key.replace(/_/g, ' ');
}

/** Name of one hidden event in a short gap. */
export function getGapEventName(event: TimelineEvent): string {
	if (event.event_type === 'tool_call') return `Tool ${event.metadata?.tool_name || 'Tool'}`;
	if (event.metadata?.result_status === 'error' && !KIND_NAMES[event.event_type]) return 'Error';
	const label = kindLabel(event.event_type, 1);
	return label.charAt(0).toUpperCase() + label.slice(1);
}

export interface GapGroup {
	key: string;
	label: string;
	count: number;
	ids: string[];
}

export interface GapSummary {
	groups: GapGroup[];
	otherKinds: number;
	otherCount: number;
}

/** Group a long gap by kind, largest first, e.g. 310 thinking, 240 Bash, 96 responses. */
export function summarizeGap(events: TimelineEvent[]): GapSummary {
	const byKind = new Map<string, string[]>();
	for (const event of events) {
		const key = kindKey(event);
		const ids = byKind.get(key);
		if (ids) ids.push(event.id);
		else byKind.set(key, [event.id]);
	}
	const all = [...byKind.entries()]
		.map(([key, ids]) => ({ key, ids, count: ids.length, label: kindLabel(key, ids.length) }))
		.sort((a, b) => b.count - a.count);
	// One leftover kind is simply named; folding it into "1 other kind" would hide more than it saves.
	const top = all.length <= GAP_TOP_KINDS + 1 ? all : all.slice(0, GAP_TOP_KINDS);
	const rest = all.slice(top.length);
	return {
		groups: top,
		otherKinds: rest.length,
		otherCount: rest.reduce((sum, g) => sum + g.count, 0)
	};
}

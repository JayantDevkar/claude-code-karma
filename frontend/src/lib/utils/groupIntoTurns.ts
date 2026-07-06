import type { TimelineEvent } from '$lib/api-types';

export interface ToolChip {
	label: string;
	count: number;
	hasError: boolean;
	isAgent: boolean;
	isThinking: boolean;
}

export interface TurnGroup {
	id: string;
	turnNumber: number;
	prompt: TimelineEvent;
	workEvents: TimelineEvent[];
	response: TimelineEvent | null;
	isLive: boolean;
	hasErrors: boolean;
	errorCount: number;
	toolChips: ToolChip[];
	elapsedMs: number;
	turnOffsetMs: number;
	totalEventCount: number;
}

function getChipLabel(ev: TimelineEvent): string | null {
	if (ev.event_type === 'thinking') return 'Think';
	if (ev.event_type === 'todo_update') return 'Todo';
	if (ev.event_type === 'skill_invocation') return 'Skill';
	if (ev.event_type === 'subagent_spawn') return 'Agent';
	if (ev.event_type === 'command_invocation' || ev.event_type === 'builtin_command') return 'Cmd';
	if (ev.event_type === 'tool_call') {
		if (ev.metadata?.spawned_agent_id) return 'Agent';
		const name = (ev.metadata?.tool_name as string | undefined) ?? '';
		if (name.startsWith('mcp__')) {
			// mcp__linear__create_issue → "linear"
			return name.split('__')[1] ?? 'mcp';
		}
		if (name === 'MultiEdit' || name === 'StrReplace') return 'Edit';
		return name || 'Tool';
	}
	return null;
}

const CHIP_ORDER = ['Read', 'Write', 'Edit', 'Bash', 'Grep', 'Glob', 'Skill', 'Cmd', 'Todo', 'Think', 'Agent'];

function buildTurn(
	prompt: TimelineEvent,
	workEvents: TimelineEvent[],
	response: TimelineEvent | null,
	turnNumber: number,
	isLive: boolean,
	sessionStartTs: string
): TurnGroup {
	const errors = workEvents.filter(
		(ev) =>
			(ev.metadata?.result_status as string | undefined) === 'error' ||
			(ev.metadata?.is_error as boolean | undefined) === true
	);
	const hasErrors = errors.length > 0;

	const chipMap = new Map<string, { count: number; hasError: boolean; isAgent: boolean; isThinking: boolean }>();
	for (const ev of workEvents) {
		const label = getChipLabel(ev);
		if (!label) continue;
		const isAgent = label === 'Agent';
		const isThinking = ev.event_type === 'thinking';
		const hasErr =
			(ev.metadata?.result_status as string | undefined) === 'error' ||
			(ev.metadata?.is_error as boolean | undefined) === true;
		const existing = chipMap.get(label) ?? { count: 0, hasError: false, isAgent, isThinking };
		chipMap.set(label, {
			count: existing.count + 1,
			hasError: existing.hasError || hasErr,
			isAgent,
			isThinking
		});
	}

	const toolChips: ToolChip[] = Array.from(chipMap.entries())
		.map(([label, data]) => ({ label, ...data }))
		.sort((a, b) => {
			const ai = CHIP_ORDER.indexOf(a.label);
			const bi = CHIP_ORDER.indexOf(b.label);
			if (ai >= 0 && bi >= 0) return ai - bi;
			if (ai >= 0) return -1;
			if (bi >= 0) return 1;
			return a.label.localeCompare(b.label);
		});

	const lastEvent = response || workEvents[workEvents.length - 1] || prompt;
	const elapsedMs = Math.max(
		0,
		new Date(lastEvent.timestamp).getTime() - new Date(prompt.timestamp).getTime()
	);
	const turnOffsetMs = Math.max(
		0,
		new Date(prompt.timestamp).getTime() - new Date(sessionStartTs).getTime()
	);

	return {
		id: prompt.id,
		turnNumber,
		prompt,
		workEvents,
		response,
		isLive,
		hasErrors,
		errorCount: errors.length,
		toolChips,
		elapsedMs,
		turnOffsetMs,
		totalEventCount: workEvents.length + (response ? 1 : 0) + 1
	};
}

export function groupIntoTurns(
	events: TimelineEvent[],
	sessionStartTs: string,
	isLive = false
): TurnGroup[] {
	const turns: TurnGroup[] = [];
	let turnNumber = 0;
	let currentPrompt: TimelineEvent | null = null;
	let workBuffer: TimelineEvent[] = [];

	function flush(response: TimelineEvent | null, live: boolean) {
		if (!currentPrompt) return;
		turns.push(buildTurn(currentPrompt, workBuffer, response, ++turnNumber, live, sessionStartTs));
		currentPrompt = null;
		workBuffer = [];
	}

	for (const ev of events) {
		if (ev.event_type === 'prompt') {
			if (currentPrompt) flush(null, false);
			currentPrompt = ev;
			workBuffer = [];
		} else if (ev.event_type === 'response') {
			if (currentPrompt) {
				flush(ev, false);
			}
		} else if (currentPrompt) {
			workBuffer.push(ev);
		}
	}

	if (currentPrompt) flush(null, isLive);

	return turns;
}

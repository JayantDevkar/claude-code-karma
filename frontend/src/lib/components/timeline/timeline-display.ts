import type { TimelineEvent } from '$lib/api-types';
import {
	buildAgentHref,
	getAgentColorVars,
	getAgentLabel,
	getModelTag,
	getTeamTag,
	shortAgentId,
	type AgentLabel,
	type ColorVars
} from '$lib/utils/agent-identity';

// The agent naming and colour helpers now live in one shared module; re-exported for timeline callers.
export { buildAgentHref, getAgentColorVars, getModelTag, getTeamTag, shortAgentId, type ColorVars };

/** Pure display helpers shared by the timeline card, the popup and the filter logic. */

// On an agent's page its parent shows up as "main", "team-lead" or "coordinator": all the main session.
export const MAIN_SESSION_LABEL = 'main session';
const MAIN_SESSION_NAMES = new Set(['main', 'team-lead', 'coordinator']);

export function isMainSessionName(name: string | null | undefined): boolean {
	return !!name && MAIN_SESSION_NAMES.has(name);
}

/** "main session", keeping the role name the transcript gives when it has one. */
export function getMainSessionLabel(name: string | null | undefined): string {
	return name && name !== 'main' ? `${MAIN_SESSION_LABEL} (${name})` : MAIN_SESSION_LABEL;
}

/** Colour of the event's actor: its own colour, then its type's, then a hash of its given name. */
export function getActorColors(event: TimelineEvent): ColorVars {
	return getAgentColorVars(event.actor_color, event.actor_agent_type, event.actor_name);
}

// The actor as an agent: its name, else its type with the short id beside it.
function getActorAgentLabel(event: TimelineEvent): AgentLabel {
	if (isMainSessionName(event.actor_name)) {
		return { label: getMainSessionLabel(event.actor_name), secondary: null };
	}
	if (event.actor_type !== 'subagent') {
		return { label: event.actor_name || shortAgentId(event.actor), secondary: null };
	}
	return getAgentLabel({
		agent_id: event.actor,
		name: event.actor_name,
		subagent_type: event.actor_agent_type ?? event.metadata?.agent_type
	});
}

/** Name to show for the actor of an event. */
export function getActorLabel(event: TimelineEvent): string {
	return getActorAgentLabel(event).label;
}

// The other party of a message when it is an agent of this session, or null.
function getPeerAgentLabel(event: TimelineEvent): AgentLabel | null {
	const m = event.metadata ?? {};
	if (m.peer_kind === 'session' || isMainSessionName(m.peer_name)) return null;
	const incoming = m.direction !== 'out';
	const name = m.peer_name ?? (incoming ? event.actor_name : null);
	const id =
		m.peer_agent_id ?? (incoming && event.actor_type === 'subagent' ? event.actor : null);
	if (!name && !id) return null;
	if (isMainSessionName(name)) return null;
	return getAgentLabel({
		agent_id: id,
		name,
		subagent_type: m.peer_agent_type ?? (incoming ? event.actor_agent_type : null)
	});
}

function shortAddress(address: string): string {
	const base = address.split('/').pop() ?? address;
	return base.replace(/\.sock$/, '') || address;
}

/** Name of the other party of a message event. */
export function getPeerLabel(event: TimelineEvent): string {
	const m = event.metadata ?? {};
	if (isMainSessionName(m.peer_name)) return getMainSessionLabel(m.peer_name);
	const agent = getPeerAgentLabel(event);
	if (agent) return agent.label;
	if (m.peer_name) return m.peer_name;
	if (m.direction !== 'out' && event.actor_name) return getActorLabel(event);
	if (m.peer_address) return shortAddress(m.peer_address);
	return m.peer_kind === 'session' ? 'another session' : 'an agent';
}

export interface RouteParty {
	label: string;
	/** Short id shown small beside an agent labelled by its type */
	secondary?: string | null;
	kind: 'self' | 'agent' | 'session';
	colors?: ColorVars;
	agentId?: string | null;
	/** True when the party is the parent session of the agent being viewed */
	isMainSession?: boolean;
}

/** Sender and recipient of a message event, for the `sender → recipient` line. */
export function getMessageRoute(
	event: TimelineEvent,
	currentAgentId?: string | null
): { from: RouteParty; to: RouteParty } {
	const m = event.metadata ?? {};
	const isOut = m.direction === 'out';

	let self: RouteParty = { label: currentAgentId ? 'this agent' : 'this session', kind: 'self' };
	// An outgoing message from a subagent other than the one being viewed names that subagent.
	if (isOut && event.actor_type === 'subagent' && event.actor !== currentAgentId) {
		self = {
			...getActorAgentLabel(event),
			kind: 'agent',
			colors: getActorColors(event),
			agentId: event.actor
		};
	}

	const label = getPeerLabel(event);
	const isMain =
		isMainSessionName(m.peer_name) ||
		(!isOut && !m.peer_name && isMainSessionName(event.actor_name));
	const isSession = m.peer_kind === 'session' || isMain;
	// An agent hashes its given name only, like its subagent card; a session has just its label.
	const peerName = m.peer_name ?? (isOut ? null : event.actor_name) ?? (isSession ? label : null);
	const peer: RouteParty = {
		label,
		secondary: getPeerAgentLabel(event)?.secondary ?? null,
		kind: isSession ? 'session' : 'agent',
		// The parent session keeps the default colour, like the task prompt sender.
		colors: isMain
			? getAgentColorVars(null)
			: getAgentColorVars(
					m.peer_color ?? (isOut ? null : event.actor_color),
					m.peer_agent_type ?? (isOut ? null : event.actor_agent_type),
					peerName
				),
		agentId: isMain ? null : (m.peer_agent_id ?? null),
		isMainSession: isMain
	};

	return isOut ? { from: self, to: peer } : { from: peer, to: self };
}

export interface EventBadge {
	label: string;
	/** Short id shown small beside an agent labelled by its type */
	secondary?: string | null;
	kind: 'agent' | 'session';
	colors: ColorVars;
	/** Set when the badge can link to an agent of this session */
	agentId: string | null;
	/** True when the badge is the parent session of the agent being viewed */
	isMainSession?: boolean;
	/** Short word before the name, e.g. "from" */
	prefix?: string;
	/** Tooltip; always carries the full name */
	title: string;
}

export interface EventBadges {
	/** The subagent that did this, when it is not the agent being viewed */
	actor: EventBadge | null;
	/** Who sent a subagent its task prompt */
	sender: EventBadge | null;
	spawned: EventBadge | null;
	/** The agent a background task notification is about */
	taskAgent: EventBadge | null;
	/** The teammate an idle row is about; it replaces the title */
	idle: EventBadge | null;
}

function fullName(label: string, secondary: string | null): string {
	return secondary ? `${label} ${secondary}` : label;
}

/** Who an event is from or about. The card and the popup both render exactly these. */
export function getEventBadges(event: TimelineEvent, currentAgentId?: string | null): EventBadges {
	const m = event.metadata ?? {};
	const type = event.event_type;
	const isIdle = type === 'system_context' && m.kind === 'agent_idle';
	const badges: EventBadges = {
		actor: null,
		sender: null,
		spawned: null,
		taskAgent: null,
		idle: null
	};

	if (isIdle) {
		const { label, secondary } = getActorAgentLabel(event);
		badges.idle = {
			label,
			secondary,
			kind: 'agent',
			colors: getAgentColorVars(
				event.actor_color,
				event.actor_agent_type ?? m.agent_type,
				event.actor_name
			),
			agentId: event.actor_type === 'subagent' ? event.actor : null,
			title: `Agent: ${fullName(label, secondary)}`
		};
		return badges;
	}

	if (
		type !== 'message' &&
		event.actor_type === 'subagent' &&
		!(currentAgentId && event.actor === currentAgentId)
	) {
		const { label, secondary } = getActorAgentLabel(event);
		badges.actor = {
			label,
			secondary,
			kind: 'agent',
			colors: getActorColors(event),
			agentId: event.actor,
			title: `Done by agent: ${fullName(label, secondary)}`
		};
	}

	if (type === 'prompt' && m.is_task_prompt) {
		// A subagent's first message comes from whoever spawned it, not from the user.
		const fromAgent = Boolean(event.actor_name) && !isMainSessionName(event.actor_name);
		const label = fromAgent ? getActorLabel(event) : getMainSessionLabel(event.actor_name);
		badges.sender = {
			label,
			kind: fromAgent ? 'agent' : 'session',
			colors: fromAgent ? getActorColors(event) : getAgentColorVars(null),
			agentId: null,
			isMainSession: !fromAgent,
			prefix: 'from',
			title: fromAgent ? `Sent by agent: ${label}` : `Sent by the ${label}`
		};
	}

	if (m.spawned_agent_id) {
		const { label, secondary } = getAgentLabel({
			agent_id: m.spawned_agent_id,
			name: m.spawned_agent_name,
			subagent_type: m.subagent_type
		});
		badges.spawned = {
			label,
			secondary,
			kind: 'agent',
			colors: getAgentColorVars(m.spawned_agent_color, m.subagent_type, m.spawned_agent_name),
			agentId: m.spawned_agent_id,
			title: `Spawned agent: ${fullName(label, secondary)}`
		};
	}

	if (type === 'task_notification') {
		if (m.agent_name || m.agent_id) {
			const { label, secondary } = getAgentLabel({
				agent_id: m.agent_id,
				name: m.agent_name,
				subagent_type: m.agent_type
			});
			badges.taskAgent = {
				label,
				secondary,
				kind: 'agent',
				colors: getAgentColorVars(m.agent_color, m.agent_type, m.agent_name),
				agentId: m.agent_id ?? null,
				title: `Task run by agent: ${fullName(label, secondary)}`
			};
		}
	}
	return badges;
}

/** Names shown by the badges, for the "is the search match visible" check. */
export function getEventBadgeLabels(badges: EventBadges): string[] {
	return [badges.actor, badges.sender, badges.spawned, badges.taskAgent, badges.idle]
		.filter((b): b is EventBadge => b !== null)
		.map((b) => b.label);
}

/** Small plain-text tags after the title, the same on the card and in the popup. */
export function getEventTags(event: TimelineEvent): string[] {
	const m = event.metadata ?? {};
	const type = event.event_type;
	const list: string[] = [];
	if (type === 'prompt') {
		if (m.prompt_source === 'sdk') list.push('headless');
		// Only a prompt can be "queued" in a way a reader would expect; say what it means.
		if (m.queued === true) list.push('sent while Claude was working');
	}
	if (type === 'message' && m.relayed === true) list.push('relayed');
	if (type === 'subagent_spawn' || m.spawned_agent_id) {
		const team = getTeamTag(m.team_name);
		if (team) list.push(team);
		const model = getModelTag(m.agent_model);
		if (model) list.push(model);
		if (m.run_in_background === true) list.push('background');
	}
	if (type === 'system_notice') {
		if (m.original_model && m.fallback_model)
			list.push(`${m.original_model} to ${m.fallback_model}`);
		if (m.level === 'warning') list.push('warning');
	}
	if (type === 'scheduled_fire' && m.cron) list.push(m.cron);
	if (type === 'compaction') {
		if (m.trigger === 'auto') list.push('automatic');
		else if (m.trigger) list.push(m.trigger);
		const tokens = formatCompactTokens(m.pre_tokens);
		if (tokens) list.push(`${tokens} tokens before`);
	}
	return list;
}

const FAILED_TASK_STATUSES = new Set(['failed', 'error', 'errored', 'timeout', 'timed_out']);
const STOPPED_TASK_STATUSES = new Set(['killed', 'stopped', 'cancelled', 'canceled']);

export function isFailedTask(event: TimelineEvent): boolean {
	if (event.event_type !== 'task_notification') return false;
	return FAILED_TASK_STATUSES.has(String(event.metadata?.task_status ?? '').toLowerCase());
}

const TASK_KIND_LABELS: Record<string, string> = {
	agent: 'Agent',
	shell: 'Background command',
	monitor: 'Monitor',
	workflow: 'Workflow',
	mcp: 'MCP task'
};

/** "Monitor update", "Agent finished", "Workflow failed": the kind, then what happened. */
function getTaskTitle(event: TimelineEvent): string {
	const m = event.metadata ?? {};
	const status = String(m.task_status ?? '').toLowerCase();
	if (status === 'idle') {
		const known = m.agent_name || m.agent_id;
		const name = known
			? getAgentLabel({
					agent_id: m.agent_id,
					name: m.agent_name,
					subagent_type: m.agent_type
				})
			: null;
		return name ? `${name.label} is idle` : 'Agent is idle';
	}
	const kind = TASK_KIND_LABELS[String(m.task_kind ?? '')] ?? 'Background task';
	// No status means the task only reported in; it has not finished.
	if (!status) return `${kind} update`;
	if (FAILED_TASK_STATUSES.has(status)) return `${kind} failed`;
	if (STOPPED_TASK_STATUSES.has(status)) return `${kind} stopped`;
	if (status === 'completed' || status === 'done') return `${kind} finished`;
	return `${kind} ${status.replace(/_/g, ' ')}`;
}

const NOTICE_TITLES: Record<string, string> = {
	away_summary: 'Recap while you were away',
	informational: 'Notice',
	model_refusal_fallback: 'Model switched after a safeguard flag',
	bridge_status: 'Remote control',
	interrupted: 'You interrupted Claude'
};

const CONTEXT_TITLES: Record<string, string> = {
	system_reminder: 'System reminder',
	hook_context: 'Hook context',
	skill_body: 'Skill instructions',
	meta: 'Injected context'
};

/** Title shown on the card and in the popup. */
export function getDisplayTitle(event: TimelineEvent): string {
	const m = event.metadata ?? {};
	switch (event.event_type) {
		case 'message':
			return m.direction === 'out'
				? `Message to ${getPeerLabel(event)}`
				: `Message from ${getPeerLabel(event)}`;
		case 'task_notification':
			return getTaskTitle(event);
		case 'scheduled_fire':
			return m.cron ? 'Scheduled task fired' : 'Scheduled wakeup';
		case 'compaction':
			return 'Context compacted';
		case 'shell_command':
			return 'Shell command';
		case 'system_notice':
			return NOTICE_TITLES[String(m.kind ?? '')] ?? event.title ?? 'Notice';
		case 'system_context':
			if (m.kind === 'agent_idle') return `${getActorLabel(event)} is idle`;
			return CONTEXT_TITLES[String(m.kind ?? '')] ?? event.title ?? 'Injected context';
		case 'prompt':
			return m.is_task_prompt ? 'Task prompt' : event.title;
		default:
			if (m.spawned_agent_id && m.subagent_type) return `Spawn ${m.subagent_type} subagent`;
			return event.title;
	}
}

/** One-line preview under the title, when the event's own summary is not the right text. */
export function getDisplaySummary(event: TimelineEvent): string | null {
	const m = event.metadata ?? {};
	switch (event.event_type) {
		case 'message':
			return m.message_summary || event.summary || m.full_content || null;
		case 'task_notification':
			return m.task_summary || event.summary || null;
		case 'shell_command':
			return m.command ? `$ ${m.command}` : (event.summary ?? null);
		case 'system_context':
			// The idle row's title already says everything its summary would.
			return m.kind === 'agent_idle' ? null : (event.summary ?? null);
		case 'system_notice':
			return m.kind === 'interrupted' ? null : (event.summary ?? null);
		default:
			return event.summary ?? null;
	}
}

export interface EventSection {
	label?: string;
	content: string;
	format: 'markdown' | 'pre' | 'link';
	/** Markdown only: keep single line breaks, for bodies people wrote line by line */
	keepBreaks?: boolean;
}

// An interruption has no content beyond its title.
function hasNoDetail(event: TimelineEvent): boolean {
	return event.event_type === 'system_notice' && event.metadata?.kind === 'interrupted';
}

/** Only plain https links are offered as clickable. */
export function isSafeHttpsUrl(value: unknown): value is string {
	if (typeof value !== 'string') return false;
	try {
		return new URL(value).protocol === 'https:';
	} catch {
		return false;
	}
}

function text(value: unknown): string {
	return typeof value === 'string' ? value : '';
}

/** Pretty-printed JSON when the whole body is a JSON object or array, else null. */
export function prettyJson(content: string): string | null {
	const trimmed = content.trim();
	const open = trimmed[0];
	const close = trimmed[trimmed.length - 1];
	if (!((open === '{' && close === '}') || (open === '[' && close === ']'))) return null;
	try {
		return JSON.stringify(JSON.parse(trimmed), null, 2);
	} catch {
		return null;
	}
}

// A body that opens like JSON but does not parse: usually cut short, with a note after it.
function looksLikeJson(content: string): boolean {
	return /^\s*(\{\s*"|\[\s*[{["])/.test(content);
}

// JSON reads as one endless paragraph in markdown, so it is shown as code: pretty when it parses.
function bodySection(content: string): Pick<EventSection, 'content' | 'format'> {
	const json = prettyJson(content);
	if (json) return { content: json, format: 'pre' };
	return { content, format: looksLikeJson(content) ? 'pre' : 'markdown' };
}

/** Content blocks for the expanded card and the popup (not used for tool_call or todo_update). */
export function getEventSections(event: TimelineEvent): EventSection[] {
	const m = event.metadata ?? {};
	const sections: EventSection[] = [];
	const push = (content: string, format: EventSection['format'], label?: string) => {
		if (content.trim()) sections.push({ label, content, format });
	};

	if (hasNoDetail(event)) return sections;

	if (event.event_type === 'shell_command') {
		push(text(m.command), 'pre', 'Command');
		push(text(m.result_content), 'pre', 'Output');
		push(text(m.stderr), 'pre', 'Errors');
		return sections;
	}

	const main =
		text(m.full_content) || text(m.full_thinking) || text(m.full_text) || text(m.prompt);
	const result = text(m.result_content);
	const fallback = event.event_type === 'task_notification' ? text(m.task_summary) : '';

	if (main) {
		const body = bodySection(main);
		push(body.content, body.format);
		// Messages and prompts are written with plain line breaks; markdown would run them together.
		if (
			body.format === 'markdown' &&
			(event.event_type === 'message' || event.event_type === 'prompt')
		) {
			sections[sections.length - 1].keepBreaks = true;
		}
		// A delivered message's tool result is noise; only a failed delivery is worth showing.
		if (event.event_type === 'message') {
			if (m.result_status === 'error') push(result, 'pre', 'Delivery error');
		} else {
			push(result, 'pre', 'Output');
		}
	} else if (result) {
		const body = bodySection(result);
		push(body.content, body.format);
	} else {
		push(fallback || text(event.summary), 'markdown');
	}

	push(text(m.skill_body), 'markdown', 'Skill instructions');
	if (event.event_type === 'task_notification') push(text(m.output_file), 'pre', 'Output file');
	if (event.event_type === 'system_notice') {
		push(text(m.url), isSafeHttpsUrl(m.url) ? 'link' : 'pre', 'Link');
	}
	return sections;
}

/** True when clicking the card should open more than the collapsed view shows. */
export function isEventExpandable(event: TimelineEvent): boolean {
	if (event.event_type === 'tool_call' || event.event_type === 'todo_update') return true;
	if (hasNoDetail(event)) return false;
	const m = event.metadata ?? {};
	return Boolean(
		m.full_content ||
		m.full_thinking ||
		m.full_text ||
		m.result_content ||
		m.prompt ||
		m.skill_body ||
		m.stderr ||
		(event.summary && event.summary.length > 100)
	);
}

/** Compact token count for the compaction row, e.g. 155206 -> "155k". */
export function formatCompactTokens(tokens: number | null | undefined): string | null {
	if (typeof tokens !== 'number' || !Number.isFinite(tokens) || tokens <= 0) return null;
	if (tokens >= 1_000_000) return `${(tokens / 1_000_000).toFixed(1)}M`;
	if (tokens >= 1_000) return `${Math.round(tokens / 1_000)}k`;
	return String(tokens);
}

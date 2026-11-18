import {
	cleanAgentIdForDisplay,
	getSubagentColorVars,
	getSubagentTypeDisplayName,
	inferSubagentTypeFromId,
	isSystemAgent
} from '$lib/utils';

/** How one agent is named and coloured, shared by the timeline and the subagent views. */

export interface ColorVars {
	color: string;
	subtle: string;
}

// Claude Code's own agent colour names, as written to agent meta.json.
const AGENT_COLOR_NAMES = ['red', 'blue', 'green', 'yellow', 'purple', 'orange', 'pink', 'cyan'];

function agentToken(name: string): ColorVars {
	return { color: `var(--agent-${name})`, subtle: `var(--agent-${name}-subtle)` };
}

/** Agent or peer colour: its own colour name, else the subagent-type colour, else a name hash. */
export function getAgentColorVars(
	colorName?: string | null,
	fallbackType?: string | null,
	fallbackName?: string | null
): ColorVars {
	const normalized = colorName?.toLowerCase();
	if (normalized && AGENT_COLOR_NAMES.includes(normalized)) return agentToken(normalized);
	if (fallbackType) return getSubagentColorVars(fallbackType);
	if (fallbackName) {
		let hash = 0;
		for (let i = 0; i < fallbackName.length; i++) {
			hash = (fallbackName.charCodeAt(i) + ((hash << 5) - hash)) | 0;
		}
		return agentToken(AGENT_COLOR_NAMES[Math.abs(hash) % AGENT_COLOR_NAMES.length]);
	}
	return { color: 'var(--subagent-default)', subtle: 'var(--subagent-default-subtle)' };
}

/** Agent ids are long hex strings, or `a<name>-<hex>` for named agents; never show them raw. */
export function shortAgentId(id: string | null | undefined): string {
	if (!id) return 'agent';
	const named = /^a(.+)-[0-9a-f]{12,}$/i.exec(id);
	if (named) return named[1];
	return /^a?[0-9a-f]{12,}$/i.test(id) ? id.slice(0, 8) : id;
}

/** In-app link to an agent of this session, or null when the route is unknown. */
export function buildAgentHref(
	projectEncoded: string | null | undefined,
	sessionSlug: string | null | undefined,
	agentId: string
): string | null {
	if (!projectEncoded || !sessionSlug) return null;
	return `/projects/${projectEncoded}/${sessionSlug}/agents/${encodeURIComponent(agentId)}`;
}

export interface AgentIdentity {
	agent_id: string;
	name?: string | null;
	color?: string | null;
	subagent_type?: string | null;
}

export interface AgentLabel {
	label: string;
	/** Short id shown small beside the label when the label alone does not tell agents apart */
	secondary: string | null;
}

// Internal placeholders such as "_teammate" are not types a reader would recognise.
function readableType(type: string | null | undefined): string | null {
	return type && !type.startsWith('_') ? type : null;
}

/** One rule for naming an agent everywhere: its name, else its type with a short id beside it. */
export function getAgentLabel(agent: {
	agent_id?: string | null;
	name?: string | null;
	subagent_type?: string | null;
}): AgentLabel {
	const id = agent.agent_id ?? '';
	const type = readableType(agent.subagent_type);
	// A name that only repeats the type is not a name.
	if (agent.name && agent.name !== type) return { label: agent.name, secondary: null };

	const system = isSystemAgent(id);
	// Named agents carry their name in the id: a<name>-<hex>.
	const embedded = system ? null : /^a(.+)-[0-9a-f]{12,}$/i.exec(id);
	if (embedded) return { label: embedded[1], secondary: null };

	const shortId = system ? cleanAgentIdForDisplay(id).slice(0, 8) : shortAgentId(id);
	const effectiveType = type ?? (id ? inferSubagentTypeFromId(id) : null);
	if (effectiveType) {
		return { label: getSubagentTypeDisplayName(effectiveType), secondary: id ? shortId : null };
	}
	return { label: shortId, secondary: null };
}

/** The agent's label alone, where its id is already shown beside it. */
export function getAgentDisplayName(agent: Parameters<typeof getAgentLabel>[0]): string {
	return getAgentLabel(agent).label;
}

/** The label with its short id, for titles that stand alone: "general-purpose af57af57". */
export function getAgentFullName(agent: Parameters<typeof getAgentLabel>[0]): string {
	const { label, secondary } = getAgentLabel(agent);
	return secondary ? `${label} ${secondary}` : label;
}

/** A model worth showing as a tag: forks report "inherit", which says nothing. */
export function getModelTag(model: string | null | undefined): string | null {
	const trimmed = model?.trim();
	if (!trimmed || trimmed.toLowerCase() === 'inherit') return null;
	return trimmed;
}

/** A team worth showing as a tag: the implicit `session-<id>` team is just the session itself. */
export function getTeamTag(team: string | null | undefined): string | null {
	const trimmed = team?.trim();
	if (!trimmed || /^session-[0-9a-f]{6,}$/i.test(trimmed)) return null;
	return `team ${trimmed}`;
}

/** One colour per agent, the same in every view that shows it. */
export function getAgentIdentityColors(agent: AgentIdentity): ColorVars {
	return getAgentColorVars(agent.color, agent.subagent_type, agent.name);
}

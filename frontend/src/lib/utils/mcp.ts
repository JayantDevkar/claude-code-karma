import { getPluginColorVars, getPluginChartHex } from '$lib/utils';

/** Parse MCP tool names: mcp__{server}__{tool} → { server, shortName } */
export function parseMcpTool(name: string): { server: string; shortName: string } | null {
	if (!name.startsWith('mcp__')) return null;
	const parts = name.split('__');
	if (parts.length < 3) return null;
	return { server: parts[1], shortName: parts.slice(2).join('__') };
}

/** Built-in tool category mapping: tool name → category */
export const BUILTIN_TOOL_CATEGORIES: Record<string, string> = {
	Read: 'builtin-file-ops',
	Write: 'builtin-file-ops',
	Edit: 'builtin-file-ops',
	Glob: 'builtin-file-ops',
	Grep: 'builtin-file-ops',
	NotebookEdit: 'builtin-file-ops',
	Bash: 'builtin-execution',
	KillShell: 'builtin-execution',
	Task: 'builtin-agents',
	TaskCreate: 'builtin-agents',
	TaskUpdate: 'builtin-agents',
	TaskOutput: 'builtin-agents',
	TaskList: 'builtin-agents',
	TaskGet: 'builtin-agents',
	TaskStop: 'builtin-agents',
	SendMessage: 'builtin-agents',
	TeamCreate: 'builtin-agents',
	TeamDelete: 'builtin-agents',
	TodoWrite: 'builtin-planning',
	EnterPlanMode: 'builtin-planning',
	ExitPlanMode: 'builtin-planning',
	Skill: 'builtin-planning',
	AskUserQuestion: 'builtin-planning',
	EnterWorktree: 'builtin-planning',
	WebFetch: 'builtin-web',
	WebSearch: 'builtin-web',
	ToolSearch: 'builtin-tools',
	ReadMcpResourceTool: 'builtin-tools',
	ListMcpResourcesTool: 'builtin-tools'
};

/** Parse built-in tool names → { server (category), shortName } */
export function parseBuiltinTool(name: string): { server: string; shortName: string } | null {
	const category = BUILTIN_TOOL_CATEGORIES[name];
	if (!category) return null;
	return { server: category, shortName: name };
}

/** Server accent colors for MCP servers (CSS variables for DOM) */
export const serverColors: Record<string, string> = {
	coderoots: 'var(--nav-blue)',
	plugin_playwright_playwright: 'var(--nav-green)',
	'plane-project-task-manager': 'var(--nav-yellow)',
	'claude-flow': 'var(--nav-purple)',
	plugin_github_github: 'var(--nav-gray)',
	plugin_linear_linear: 'var(--nav-orange)',
	filesystem: 'var(--nav-indigo)',
	analyzer: 'var(--nav-red)',
	context7: 'var(--nav-teal)',
	'builtin-file-ops': 'var(--nav-blue)',
	'builtin-execution': 'var(--nav-orange)',
	'builtin-agents': 'var(--nav-purple)',
	'builtin-planning': 'var(--nav-green)',
	'builtin-web': 'var(--nav-teal)',
	'builtin-tools': 'var(--nav-indigo)'
};

/** Hex equivalents for Chart.js (canvas can't resolve CSS variables) */
const serverChartHex: Record<string, string> = {
	coderoots: '#3b82f6',
	plugin_playwright_playwright: '#10b981',
	'plane-project-task-manager': '#ca8a04',
	'claude-flow': '#8b5cf6',
	plugin_github_github: '#64748b',
	plugin_linear_linear: '#f97316',
	filesystem: '#6366f1',
	analyzer: '#f43f5e',
	context7: '#14b8a6',
	'builtin-file-ops': '#3b82f6',
	'builtin-execution': '#f97316',
	'builtin-agents': '#8b5cf6',
	'builtin-planning': '#10b981',
	'builtin-web': '#14b8a6',
	'builtin-tools': '#6366f1'
};

/** Get accent color for a server name, with teal fallback */
export function getServerColor(name: string): string {
	return serverColors[name] ?? 'var(--nav-teal)';
}

/** Get hex color for Chart.js canvas rendering, using plugin colors when available */
export function getServerChartHex(serverName: string, pluginName?: string | null): string {
	if (pluginName) {
		return getPluginChartHex(pluginName);
	}
	return serverChartHex[serverName] ?? '#14b8a6';
}

/** Get color vars for a server, using plugin dynamic colors when available */
export function getServerColorVars(
	serverName: string,
	pluginName?: string | null
): { color: string; subtle: string } {
	if (pluginName) {
		return getPluginColorVars(pluginName);
	}
	const color = serverColors[serverName] ?? 'var(--nav-teal)';
	return {
		color,
		subtle: `color-mix(in srgb, ${color} 10%, transparent)`
	};
}

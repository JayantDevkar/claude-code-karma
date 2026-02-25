import { getPluginColorVars, getPluginChartHex } from '$lib/utils';

/** Parse MCP tool names: mcp__{server}__{tool} → { server, shortName } */
export function parseMcpTool(name: string): { server: string; shortName: string } | null {
	if (!name.startsWith('mcp__')) return null;
	const parts = name.split('__');
	if (parts.length < 3) return null;
	return { server: parts[1], shortName: parts.slice(2).join('__') };
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
	context7: 'var(--nav-teal)'
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
	context7: '#14b8a6'
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

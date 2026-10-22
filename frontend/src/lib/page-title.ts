export const APP_NAME = 'Claude Karma';

const SEPARATOR = ' · ';

// Labels match each page's H1; the home page has none so its tab reads just the app name.
const ROUTE_TITLES = new Map<string, string>([
	['projects', 'Projects'],
	['sessions', 'Sessions'],
	['agents', 'Agents'],
	['analytics', 'Analytics'],
	['skills', 'Skills'],
	['commands', 'Commands'],
	['hooks', 'Hooks'],
	['mcp', 'MCP Servers'],
	['plugins', 'Plugins'],
	['plans', 'Plans'],
	['memory', 'Memory'],
	['cron', 'Cron Jobs'],
	['shells', 'Background Shells'],
	['tickets', 'Tickets'],
	['archived', 'Archived'],
	['settings', 'Settings'],
	['about', 'About']
]);

// Loads return this as `title`; the root layout appends the app name.
export function joinTitle(parts: (string | null | undefined)[]): string {
	return parts
		.map((part) => part?.trim())
		.filter((part): part is string => !!part)
		.join(SEPARATOR);
}

export function formatTitle(parts: (string | null | undefined)[]): string {
	return joinTitle([...parts, APP_NAME]);
}

export function routeTitle(pathname: string): string | null {
	const segment = pathname.split('/')[1] ?? '';
	return ROUTE_TITLES.get(segment) ?? null;
}

/**
 * WebMCP tool registration for Claude Karma Dashboard.
 *
 * Registers structured tools via navigator.modelContext (Chrome 146+)
 * so AI agents can query projects, search sessions, get analytics,
 * and navigate the dashboard without DOM scraping.
 */
import { goto } from '$app/navigation';
import { API_BASE } from '$lib/config';

interface WebMCPTool {
	name: string;
	description: string;
	inputSchema: object;
	handler: (params: Record<string, unknown>) => Promise<unknown>;
}

interface ModelContextContainer {
	registerTool(tool: WebMCPTool): void;
}

async function apiFetch(path: string): Promise<unknown> {
	const res = await fetch(`${API_BASE}${path}`);
	if (!res.ok) {
		throw new Error(`API ${res.status}: ${res.statusText}`);
	}
	return res.json();
}

export function registerWebMCPTools(): void {
	if (!('modelContext' in navigator)) return;

	const mc = (navigator as Navigator & { modelContext: ModelContextContainer }).modelContext;
	if (!mc) return;

	// 1. list_projects
	mc.registerTool({
		name: 'list_projects',
		description:
			'List all monitored Claude Code projects with session counts, agent counts, and latest session times.',
		inputSchema: {
			type: 'object',
			properties: {
				sort_by: {
					type: 'string',
					enum: ['name', 'sessions', 'recent'],
					description: 'Sort order for projects. Default: recent.'
				}
			}
		},
		async handler(params: Record<string, unknown>) {
			const data = (await apiFetch('/projects')) as {
				projects?: Array<Record<string, unknown>>;
			};
			let projects = Array.isArray(data) ? data : (data.projects ?? []);

			const sortBy = (params.sort_by as string) || 'recent';
			if (sortBy === 'name') {
				projects.sort((a, b) =>
					String(a.encoded_name ?? '').localeCompare(String(b.encoded_name ?? ''))
				);
			} else if (sortBy === 'sessions') {
				projects.sort(
					(a, b) => (Number(b.session_count) || 0) - (Number(a.session_count) || 0)
				);
			} else {
				projects.sort(
					(a, b) =>
						new Date(String(b.latest_session_time ?? 0)).getTime() -
						new Date(String(a.latest_session_time ?? 0)).getTime()
				);
			}

			return { projects };
		}
	});

	// 2. search_sessions
	mc.registerTool({
		name: 'search_sessions',
		description:
			'Search Claude Code sessions by text query, project, scope, and limit. Returns matching sessions with project context.',
		inputSchema: {
			type: 'object',
			properties: {
				query: {
					type: 'string',
					description: 'Text to search for in session titles and prompts.'
				},
				project: {
					type: 'string',
					description: 'Encoded project name to filter by (e.g. "-Users-me-repo").'
				},
				scope: {
					type: 'string',
					enum: ['both', 'titles', 'prompts'],
					description: 'Where to search. Default: both.'
				},
				limit: {
					type: 'number',
					description: 'Max results to return. Default: 20.'
				}
			}
		},
		async handler(params: Record<string, unknown>) {
			const qs = new URLSearchParams();
			if (params.query) qs.set('search', String(params.query));
			if (params.project) qs.set('project', String(params.project));
			if (params.scope) qs.set('scope', String(params.scope));
			qs.set('limit', String(params.limit ?? 20));

			const data = await apiFetch(`/sessions/all?${qs.toString()}`);
			return data;
		}
	});

	// 3. get_session_detail
	mc.registerTool({
		name: 'get_session_detail',
		description:
			'Get full details for a specific session by UUID, including timeline events, tool usage, file activity, subagents, todos, and cost breakdown.',
		inputSchema: {
			type: 'object',
			properties: {
				uuid: {
					type: 'string',
					description: 'Session UUID to retrieve.'
				}
			},
			required: ['uuid']
		},
		async handler(params: Record<string, unknown>) {
			const uuid = String(params.uuid);
			const data = await apiFetch(`/sessions/${encodeURIComponent(uuid)}`);
			return data;
		}
	});

	// 4. get_analytics
	mc.registerTool({
		name: 'get_analytics',
		description:
			'Get analytics data — global or per-project. Includes total sessions, tokens, cost, models used, tools used, temporal heatmap, and work mode distribution.',
		inputSchema: {
			type: 'object',
			properties: {
				project: {
					type: 'string',
					description:
						'Encoded project name for project-specific analytics. Omit for global analytics.'
				},
				period: {
					type: 'string',
					enum: ['all', '6h', '12h', '24h', '48h', 'this_week', 'last_week'],
					description: 'Time period filter. Default: all.'
				}
			}
		},
		async handler(params: Record<string, unknown>) {
			const project = params.project ? String(params.project) : null;
			const period = params.period ? String(params.period) : undefined;

			let path: string;
			if (project) {
				path = `/analytics/projects/${encodeURIComponent(project)}`;
			} else {
				path = '/analytics';
			}

			if (period) {
				path += `?period=${encodeURIComponent(period)}`;
			}

			const data = await apiFetch(path);
			return data;
		}
	});

	// 5. get_live_sessions
	mc.registerTool({
		name: 'get_live_sessions',
		description:
			'Get currently active Claude Code sessions with real-time state, status, working directory, project, duration, and subagent tracking.',
		inputSchema: {
			type: 'object',
			properties: {}
		},
		async handler() {
			const data = await apiFetch('/live-sessions');
			return data;
		}
	});

	// 6. navigate_to_page
	mc.registerTool({
		name: 'navigate_to_page',
		description:
			'Navigate the Claude Karma dashboard to a specific page. Supports deep-linking to projects and sessions.',
		inputSchema: {
			type: 'object',
			properties: {
				page: {
					type: 'string',
					enum: [
						'home',
						'projects',
						'sessions',
						'analytics',
						'agents',
						'skills',
						'plans',
						'settings',
						'history'
					],
					description: 'Target page to navigate to.'
				},
				project: {
					type: 'string',
					description:
						'Encoded project name for deep-linking (used with projects, analytics pages).'
				},
				session_uuid: {
					type: 'string',
					description: 'Session UUID for deep-linking to a specific session.'
				}
			},
			required: ['page']
		},
		async handler(params: Record<string, unknown>) {
			const page = String(params.page);
			const project = params.project ? String(params.project) : undefined;
			const sessionUuid = params.session_uuid ? String(params.session_uuid) : undefined;

			const routes: Record<string, string> = {
				home: '/',
				projects: '/projects',
				sessions: '/sessions',
				analytics: '/analytics',
				agents: '/agents',
				skills: '/skills',
				plans: '/plans',
				settings: '/settings',
				history: '/archived'
			};

			let target = routes[page] ?? '/';

			// Deep-link: project-specific pages
			if (project) {
				const encoded = encodeURIComponent(project);
				if (page === 'projects') {
					target = `/projects/${encoded}`;
				} else if (page === 'analytics') {
					target = `/analytics?project=${encoded}`;
				} else if (page === 'sessions') {
					target = `/sessions?project=${encoded}`;
				} else if (page === 'agents') {
					target = `/projects/${encoded}?tab=agents`;
				} else if (page === 'skills') {
					target = `/projects/${encoded}?tab=skills`;
				}
			}

			// Deep-link: specific session
			if (sessionUuid && project) {
				target = `/projects/${encodeURIComponent(project)}/${encodeURIComponent(sessionUuid)}`;
			}

			await goto(target);
			return { navigated_to: target };
		}
	});
}

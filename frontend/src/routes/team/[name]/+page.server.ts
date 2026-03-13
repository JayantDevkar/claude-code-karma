import type { PageServerLoad } from './$types';
import { API_BASE } from '$lib/config';
import { safeFetch, fetchWithFallback } from '$lib/utils/api-fetch';
import type {
	SyncTeam,
	SyncDevice,
	JoinCodeResponse,
	SyncPendingFolder,
	SyncStatusResponse,
	SyncWatchStatus,
	SyncDetect,
	SyncProjectStatus,
	SyncEvent,
	PendingDevice,
	TeamSessionStat
} from '$lib/api-types';

interface ProjectSummary {
	encoded_name: string;
	path: string;
	slug?: string;
	display_name?: string;
	session_count: number;
}

export const load: PageServerLoad = async ({ fetch, params }) => {
	const teamName = params.name;

	// Trigger auto-accept of pending karma peers before fetching teams,
	// so newly joined members appear immediately.
	const pendingDevicesData = await fetch(`${API_BASE}/sync/pending-devices`)
		.then((r) => r.ok ? r.json() : { devices: [], auto_accepted: 0 })
		.catch(() => ({ devices: [] as PendingDevice[], auto_accepted: 0 }));

	// Fetch in parallel: teams list (to find this team), devices, join code, pending folders, sync status, watch status, detect, project status
	const [teamsData, devices, joinCodeData, pendingFoldersData, syncStatus, watchStatus, detectData, projectStatusData, activityData, sessionStatsData] = await Promise.all([
		safeFetch<{ teams: SyncTeam[] }>(fetch, `${API_BASE}/sync/teams`),
		fetchWithFallback<{ devices: SyncDevice[] }>(fetch, `${API_BASE}/sync/devices`, {
			devices: []
		}),
		safeFetch<JoinCodeResponse>(fetch, `${API_BASE}/sync/teams/${encodeURIComponent(teamName)}/join-code`),
		fetchWithFallback<{ pending: SyncPendingFolder[] }>(fetch, `${API_BASE}/sync/pending`, {
			pending: []
		}),
		fetchWithFallback<SyncStatusResponse>(fetch, `${API_BASE}/sync/status`, {
			configured: false
		}),
		fetchWithFallback<SyncWatchStatus>(fetch, `${API_BASE}/sync/watch/status`, {
			running: false
		} as SyncWatchStatus),
		fetchWithFallback<SyncDetect>(fetch, `${API_BASE}/sync/detect`, {
			installed: false,
			running: false,
			version: null,
			device_id: null
		}),
		fetchWithFallback<{ projects: SyncProjectStatus[] }>(
			fetch,
			`${API_BASE}/sync/teams/${encodeURIComponent(teamName)}/project-status`,
			{ projects: [] }
		),
		fetchWithFallback<{ events: SyncEvent[] }>(
			fetch,
			`${API_BASE}/sync/teams/${encodeURIComponent(teamName)}/activity?limit=20`,
			{ events: [] }
		),
		fetchWithFallback<{ stats: TeamSessionStat[] }>(
			fetch,
			`${API_BASE}/sync/teams/${encodeURIComponent(teamName)}/session-stats?days=30`,
			{ stats: [] }
		)
	]);

	// Find this team from the teams list
	let team: SyncTeam | null = null;
	if (teamsData.ok) {
		team = teamsData.data.teams.find((t) => t.name === teamName) ?? null;
	}

	// Get all projects for the add-project dialog
	// Note: /projects returns a flat array, not { projects: [...] }
	const allProjects = await fetchWithFallback<ProjectSummary[]>(
		fetch,
		`${API_BASE}/projects`,
		[]
	);

	// Filter pending folder offers to this team (sessions and outbox types only)
	const pendingFolders = (pendingFoldersData.pending ?? []).filter(
		(f) => f.from_team === teamName && (f.folder_type === 'sessions' || f.folder_type === 'outbox')
	);

	return {
		teamName,
		team,
		devices: devices.devices,
		joinCode: joinCodeData.ok ? joinCodeData.data.join_code : null,
		pendingFolders,
		pendingDevices: (pendingDevicesData.devices ?? []) as PendingDevice[],
		allProjects: allProjects.map((p) => ({
			encoded_name: p.encoded_name,
			name: p.display_name || p.slug || p.encoded_name,
			path: p.path
		})),
		syncStatus,
		watchStatus,
		detectData,
		projectStatuses: projectStatusData.projects ?? [],
		activity: activityData.events ?? [],
		sessionStats: sessionStatsData.stats ?? []
	};
};

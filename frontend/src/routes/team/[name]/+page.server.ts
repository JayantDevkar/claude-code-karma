import type { PageServerLoad } from './$types';
import { API_BASE } from '$lib/config';
import { safeFetch, fetchWithFallback } from '$lib/utils/api-fetch';
import type {
	SyncTeam,
	SyncDevice,
	JoinCodeResponse,
	PendingDevice,
	SyncStatusResponse
} from '$lib/api-types';

interface ProjectSummary {
	encoded_name: string;
	name: string;
	session_count: number;
}

export const load: PageServerLoad = async ({ fetch, params }) => {
	const teamName = params.name;

	// Fetch in parallel: teams list (to find this team), devices, join code, pending devices, projects, sync status
	const [teamsData, devices, joinCodeData, pendingData, syncStatus] = await Promise.all([
		safeFetch<{ teams: SyncTeam[] }>(fetch, `${API_BASE}/sync/teams`),
		fetchWithFallback<{ devices: SyncDevice[] }>(fetch, `${API_BASE}/sync/devices`, {
			devices: []
		}),
		safeFetch<JoinCodeResponse>(fetch, `${API_BASE}/sync/teams/${encodeURIComponent(teamName)}/join-code`),
		fetchWithFallback<{ devices: PendingDevice[] }>(fetch, `${API_BASE}/sync/pending-devices`, {
			devices: []
		}),
		fetchWithFallback<SyncStatusResponse>(fetch, `${API_BASE}/sync/status`, {
			configured: false
		})
	]);

	// Find this team from the teams list
	let team: SyncTeam | null = null;
	if (teamsData.ok) {
		team = teamsData.data.teams.find((t) => t.name === teamName) ?? null;
	}

	// Get all projects for the add-project dialog
	const allProjects = await fetchWithFallback<{ projects: ProjectSummary[] }>(
		fetch,
		`${API_BASE}/projects`,
		{ projects: [] }
	);

	return {
		teamName,
		team,
		devices: devices.devices,
		joinCode: joinCodeData.ok ? joinCodeData.data.join_code : null,
		pendingDevices: pendingData.devices,
		allProjects: allProjects.projects,
		syncStatus
	};
};

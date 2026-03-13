<script lang="ts">
	import PageHeader from '$lib/components/layout/PageHeader.svelte';
	import SyncStatusBanner from '$lib/components/sync/SyncStatusBanner.svelte';
	import { Tabs } from 'bits-ui';
	import TabsTrigger from '$lib/components/ui/TabsTrigger.svelte';
	import TeamOverviewTab from '$lib/components/team/TeamOverviewTab.svelte';
	import TeamMembersTab from '$lib/components/team/TeamMembersTab.svelte';
	import TeamProjectsTab from '$lib/components/team/TeamProjectsTab.svelte';
	import TeamActivityTab from '$lib/components/team/TeamActivityTab.svelte';
	import TeamSettings from '$lib/components/TeamSettings.svelte';
	import { API_BASE } from '$lib/config';
	import { POLLING_INTERVALS } from '$lib/config';
	import { invalidateAll } from '$app/navigation';
	import { onMount } from 'svelte';
	import { browser } from '$app/environment';
	import {
		Users,
		Contact,
		FolderSync,
		FolderGit2,
		Loader2,
		AlertTriangle,
		CheckCircle2,
		RefreshCw,
		UserPlus,
		Check,
		X,
		LayoutDashboard,
		Activity,
		Settings
	} from 'lucide-svelte';
	import { getTeamMemberHexColor } from '$lib/utils';
	import type { SyncDevice, SyncPendingFolder, SyncProjectStatus, SyncTeam, SyncEvent, PendingDevice, TeamSessionStat } from '$lib/api-types';

	let { data } = $props();

	let deleteConfirm = $state(false);
	let deleting = $state(false);
	let deleteError = $state<string | null>(null);
	let syncError = $state('');
	let isRefreshing = $state(false);

	// Tab state
	const validTabs = ['overview', 'members', 'projects', 'activity', 'settings'];
	let activeTab = $state('overview');
	let tabsReady = $state(false);

	// Team data — $state so polling can update it directly
	let team = $state<SyncTeam | null>(null);
	$effect(() => {
		team = data.team ?? null;
	});
	let members = $derived(team?.members ?? []);
	let projects = $derived(team?.projects ?? []);

	// Per-project sync status
	let projectStatuses = $state<SyncProjectStatus[]>([]);
	$effect(() => {
		projectStatuses = data.projectStatuses ?? [];
	});

	// Activity feed
	let activity = $state<SyncEvent[]>([]);
	$effect(() => { activity = data.activity ?? []; });

	// Session stats
	let sessionStats = $state<TeamSessionStat[]>([]);
	$effect(() => { sessionStats = data.sessionStats ?? []; });

	// Polling state for connection status
	let devices = $state<SyncDevice[]>([]);

	// Pending folder offers for this team
	let pendingFolders = $state<SyncPendingFolder[]>([]);
	let acceptingFolders = $state(false);

	// Sync from server data when it changes (e.g. after invalidateAll)
	$effect(() => {
		devices = data.devices ?? [];
	});
	$effect(() => {
		pendingFolders = data.pendingFolders ?? [];
	});

	let userId = $derived(data.syncStatus?.user_id);
	let sharedProjectNames = $derived(projects.map((p) => p.encoded_name));

	function parseFolderLabel(offer: SyncPendingFolder): string {
		if (offer.label) return offer.label;
		const match = offer.folder_id.match(/^karma-(?:out|in)-[^-]+-(.+)$/);
		if (match) return match[1];
		return offer.folder_id;
	}

	// Track per-folder action state: folder_id -> 'accepting' | 'rejecting'
	let folderActing = $state<Record<string, string>>({});

	async function acceptAllFolders() {
		acceptingFolders = true;
		try {
			await fetch(`${API_BASE}/sync/pending/accept`, { method: 'POST' });
			invalidateAll();
		} finally {
			acceptingFolders = false;
		}
	}

	async function acceptFolder(folderId: string) {
		folderActing = { ...folderActing, [folderId]: 'accepting' };
		try {
			const res = await fetch(`${API_BASE}/sync/pending/accept/${encodeURIComponent(folderId)}`, { method: 'POST' });
			if (res.ok) {
				await fetchTeamData();
			} else {
				folderActing = { ...folderActing, [folderId]: 'error' };
				return;
			}
		} catch {
			folderActing = { ...folderActing, [folderId]: 'error' };
			return;
		}
		const { [folderId]: _, ...rest } = folderActing;
		folderActing = rest;
	}

	async function rejectFolder(folderId: string) {
		folderActing = { ...folderActing, [folderId]: 'rejecting' };
		try {
			const res = await fetch(`${API_BASE}/sync/pending/reject/${encodeURIComponent(folderId)}`, { method: 'POST' });
			if (res.ok) {
				await fetchTeamData();
			} else {
				folderActing = { ...folderActing, [folderId]: 'error' };
				return;
			}
		} catch {
			folderActing = { ...folderActing, [folderId]: 'error' };
			return;
		}
		const { [folderId]: _, ...rest } = folderActing;
		folderActing = rest;
	}

	// Pending device requests
	let pendingDevices = $state<PendingDevice[]>([]);
	$effect(() => {
		pendingDevices = data.pendingDevices ?? [];
	});

	// Track per-device accept state
	let deviceActing = $state<Record<string, string>>({});

	async function acceptDevice(device: PendingDevice) {
		deviceActing = { ...deviceActing, [device.device_id]: 'accepting' };
		try {
			const res = await fetch(
				`${API_BASE}/sync/pending-devices/${encodeURIComponent(device.device_id)}/accept`,
				{
					method: 'POST',
					headers: { 'Content-Type': 'application/json' },
					body: JSON.stringify({ team_name: data.teamName })
				}
			);
			if (res.ok) {
				pendingDevices = pendingDevices.filter((d) => d.device_id !== device.device_id);
				await fetchTeamData();
			} else {
				deviceActing = { ...deviceActing, [device.device_id]: 'error' };
			}
		} catch {
			deviceActing = { ...deviceActing, [device.device_id]: 'error' };
		}
	}

	async function dismissDevice(deviceId: string) {
		deviceActing = { ...deviceActing, [deviceId]: 'dismissing' };
		try {
			await fetch(
				`${API_BASE}/sync/pending-devices/${encodeURIComponent(deviceId)}`,
				{ method: 'DELETE' }
			);
		} catch {
			// best-effort — remove from UI regardless
		}
		pendingDevices = pendingDevices.filter((d) => d.device_id !== deviceId);
		const { [deviceId]: _, ...rest } = deviceActing;
		deviceActing = rest;
	}

	// Fetch all team data (used by both polling and manual refresh)
	async function fetchTeamData(signal?: AbortSignal) {
		const teamNameEnc = encodeURIComponent(data.teamName);
		// pending-devices triggers auto-accept of karma peers, must resolve before teams fetch
		const pendingDevicesRes = await fetch(`${API_BASE}/sync/pending-devices`, { signal }).catch(() => null);
		if (pendingDevicesRes?.ok) {
			const pd = await pendingDevicesRes.json();
			pendingDevices = pd.devices ?? [];
		}
		const [teamsRes, devicesRes, foldersRes, projectStatusRes, activityRes, sessionStatsRes] = await Promise.all([
			fetch(`${API_BASE}/sync/teams`, { signal }),
			fetch(`${API_BASE}/sync/devices`, { signal }),
			fetch(`${API_BASE}/sync/pending`, { signal }),
			fetch(`${API_BASE}/sync/teams/${teamNameEnc}/project-status`, { signal }),
			fetch(`${API_BASE}/sync/teams/${teamNameEnc}/activity?limit=20`, { signal }),
			fetch(`${API_BASE}/sync/teams/${teamNameEnc}/session-stats?days=30`, { signal })
		]);

		if (teamsRes.ok) {
			const td = await teamsRes.json();
			const found = (td.teams ?? []).find((t: SyncTeam) => t.name === data.teamName);
			if (found) team = found;
		}
		if (devicesRes.ok) {
			const dd = await devicesRes.json();
			devices = dd.devices ?? [];
		}
		if (foldersRes.ok) {
			const fd = await foldersRes.json();
			pendingFolders = (fd.pending ?? []).filter(
				(f: SyncPendingFolder) =>
					f.from_team === data.teamName && (f.folder_type === 'sessions' || f.folder_type === 'outbox')
			);
		}
		if (projectStatusRes.ok) {
			const ps = await projectStatusRes.json();
			projectStatuses = ps.projects ?? [];
		}
		if (activityRes.ok) {
			const ad = await activityRes.json();
			activity = ad.events ?? [];
		}
		if (sessionStatsRes.ok) {
			const ss = await sessionStatsRes.json();
			sessionStats = ss.stats ?? [];
		}
	}

	// Poll for team data, devices, pending folders, project status, and activity
	onMount(() => {
		let controller = new AbortController();

		const interval = setInterval(async () => {
			controller.abort();
			controller = new AbortController();
			try {
				await fetchTeamData(controller.signal);
			} catch (e) {
				if (e instanceof DOMException && e.name === 'AbortError') return;
			}
		}, POLLING_INTERVALS.SYNC_STATUS);

		// Tab URL persistence
		const params = new URLSearchParams(window.location.search);
		const tab = params.get('tab');
		if (tab && validTabs.includes(tab)) activeTab = tab;
		tabsReady = true;

		const handlePopstate = () => {
			const p = new URLSearchParams(window.location.search);
			const t = p.get('tab');
			if (t && validTabs.includes(t)) activeTab = t;
		};
		window.addEventListener('popstate', handlePopstate);

		return () => {
			clearInterval(interval);
			controller.abort();
			window.removeEventListener('popstate', handlePopstate);
		};
	});

	// URL sync effect
	$effect(() => {
		if (!browser || !tabsReady) return;
		const url = new URL(window.location.href);
		if (activeTab === 'overview') url.searchParams.delete('tab');
		else url.searchParams.set('tab', activeTab);
		window.history.replaceState(window.history.state, '', url.toString());
	});

	async function handleLeaveTeam() {
		if (deleting) return;
		deleting = true;
		deleteError = null;
		try {
			const res = await fetch(
				`${API_BASE}/sync/teams/${encodeURIComponent(data.teamName)}`,
				{ method: 'DELETE' }
			);
			if (res.ok) {
				window.location.href = '/team';
			} else {
				const body = await res.json().catch(() => ({}));
				deleteError = body.detail || `Failed to leave team (${res.status})`;
			}
		} catch {
			deleteError = 'Network error. Could not leave team.';
		} finally {
			deleting = false;
		}
	}

	async function handleRefresh() {
		if (isRefreshing) return;
		isRefreshing = true;
		try {
			await fetchTeamData();
		} catch {
			// fall back to invalidateAll on error
			invalidateAll();
		} finally {
			isRefreshing = false;
		}
	}
</script>

<PageHeader
	title={data.teamName}
	icon={Users}
	iconColor="--nav-indigo"
	subtitle="Team members, shared projects, and sync status"
	breadcrumbs={[
		{ label: 'Dashboard', href: '/' },
		{ label: 'Teams', href: '/team' },
		{ label: data.teamName }
	]}
>
	{#snippet headerRight()}
		<button
			onclick={handleRefresh}
			disabled={isRefreshing}
			class="flex items-center gap-1.5 px-3 py-1.5 text-sm font-medium rounded-[var(--radius-md)] border border-[var(--border)]
				text-[var(--text-secondary)] hover:bg-[var(--bg-muted)] transition-colors
				disabled:opacity-50 disabled:cursor-not-allowed"
		>
			<RefreshCw size={14} class={isRefreshing ? 'animate-spin' : ''} />
			Refresh
		</button>
	{/snippet}
</PageHeader>

<div class="mb-6">
	<SyncStatusBanner
		running={data.watchStatus?.running ?? false}
		syncthingUp={data.detectData?.running ?? false}
	/>
</div>

<!-- Pending Device Requests (above tabs) -->
{#if pendingDevices.length > 0}
	<section class="mb-6">
		<div class="rounded-lg border border-[var(--border)] overflow-hidden bg-[var(--bg-base)]">
			<div class="h-[3px] bg-[var(--accent)]"></div>

			<!-- Header -->
			<div class="flex items-center gap-2.5 px-5 py-3 border-b border-[var(--border)]/50">
				<UserPlus size={15} class="text-[var(--accent)]" />
				<h2 class="text-sm font-semibold text-[var(--text-primary)]">
					Join Requests
				</h2>
				<span class="flex items-center justify-center min-w-[20px] h-5 px-1 text-[10px] font-bold rounded-full bg-[var(--accent)] text-white">
					{pendingDevices.length}
				</span>
			</div>

			<!-- Requests list -->
			<div class="divide-y divide-[var(--border)]/50">
				{#each pendingDevices as device (device.device_id)}
					{@const acting = deviceActing[device.device_id]}
					{@const name = device.name || 'Unknown device'}
					{@const hexColor = getTeamMemberHexColor(name)}

					<div class="flex items-center gap-4 px-5 py-4">
						<!-- Avatar -->
						<div
							class="w-9 h-9 rounded-full flex items-center justify-center text-sm font-bold shrink-0"
							style="background: {hexColor}; color: white;"
						>
							{name.charAt(0).toUpperCase()}
						</div>

						<!-- Info -->
						<div class="flex-1 min-w-0">
							<p class="text-sm font-medium text-[var(--text-primary)] truncate">
								{name}
							</p>
							<p class="text-[11px] text-[var(--text-muted)] mt-0.5 font-mono">
								{device.device_id.slice(0, 7)}&hellip;{device.device_id.slice(-4)}
							</p>
						</div>

						<!-- Actions -->
						<div class="flex items-center gap-2 shrink-0">
							{#if acting === 'error'}
								<span class="text-[11px] text-[var(--error)] mr-1">Failed</span>
							{/if}
							<button
								onclick={() => acceptDevice(device)}
								disabled={acting === 'accepting'}
								class="flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold rounded-md
									bg-[var(--success)] text-white hover:bg-[var(--success)]/85 transition-colors
									disabled:opacity-50 disabled:cursor-not-allowed"
							>
								{#if acting === 'accepting'}
									<Loader2 size={12} class="animate-spin" />
								{:else}
									<Check size={12} />
								{/if}
								Approve
							</button>
							<button
								onclick={() => dismissDevice(device.device_id)}
								disabled={acting === 'accepting'}
								class="px-2.5 py-1.5 text-xs font-medium rounded-md
									text-[var(--text-muted)] hover:text-[var(--text-primary)] hover:bg-[var(--bg-muted)] transition-colors
									disabled:opacity-50"
							>
								Ignore
							</button>
						</div>
					</div>
				{/each}
			</div>
		</div>
	</section>
{/if}

<!-- Pending Project Shares (above tabs) -->
{#if pendingFolders.length > 0}
	<section class="mb-6">
		<div class="rounded-lg border border-[var(--border)] overflow-hidden bg-[var(--bg-base)]">
			<div class="h-[3px] bg-[var(--warning)]"></div>

			<!-- Header -->
			<div class="flex items-center justify-between px-5 py-3 border-b border-[var(--border)]/50">
				<div class="flex items-center gap-2.5">
					<FolderSync size={15} class="text-[var(--warning)]" />
					<h2 class="text-sm font-semibold text-[var(--text-primary)]">
						Pending Session Shares
					</h2>
					<span class="flex items-center justify-center min-w-[20px] h-5 px-1 text-[10px] font-bold rounded-full bg-[var(--warning)] text-white">
						{pendingFolders.length}
					</span>
				</div>
				<button
					onclick={acceptAllFolders}
					disabled={acceptingFolders}
					class="flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold rounded-md
						bg-[var(--success)] text-white hover:bg-[var(--success)]/85 transition-colors
						disabled:opacity-50 disabled:cursor-not-allowed"
				>
					{#if acceptingFolders}
						<Loader2 size={12} class="animate-spin" />
						Accepting...
					{:else}
						<CheckCircle2 size={12} />
						Accept All
					{/if}
				</button>
			</div>

			<!-- Shares list -->
			<div class="divide-y divide-[var(--border)]/50">
				{#each pendingFolders as offer (offer.folder_id + ':' + offer.from_device)}
					{@const acting = folderActing[offer.folder_id]}
					{@const isOutbox = offer.folder_type === 'outbox'}

					<div class="flex items-center gap-4 px-5 py-4">
						<!-- Folder icon -->
						<div
							class="w-9 h-9 rounded-lg flex items-center justify-center shrink-0
								{isOutbox
									? 'bg-[var(--accent)]/10 text-[var(--accent)]'
									: 'bg-[var(--warning)]/10 text-[var(--warning)]'}"
						>
							<FolderGit2 size={16} />
						</div>

						<!-- Info -->
						<div class="flex-1 min-w-0">
							<p class="text-sm font-medium text-[var(--text-primary)] truncate">
								{offer.description || parseFolderLabel(offer)}
							</p>
							<p class="text-[11px] text-[var(--text-muted)] mt-0.5">
								{#if isOutbox}
									Start sending your sessions for this project
								{:else}
									Receive <span class="font-medium text-[var(--text-secondary)]">{offer.from_member}</span>'s sessions
								{/if}
							</p>
						</div>

						<!-- Actions -->
						<div class="flex items-center gap-2 shrink-0">
							<button
								onclick={() => acceptFolder(offer.folder_id)}
								disabled={!!acting}
								aria-label="Accept project share"
								class="flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold rounded-md
									bg-[var(--success)] text-white hover:bg-[var(--success)]/85 transition-colors
									disabled:opacity-50 disabled:cursor-not-allowed"
							>
								{#if acting === 'accepting'}
									<Loader2 size={12} class="animate-spin" />
								{:else}
									<Check size={12} />
								{/if}
								Accept
							</button>
							<button
								onclick={() => rejectFolder(offer.folder_id)}
								disabled={!!acting}
								aria-label="Reject project share"
								class="px-2.5 py-1.5 text-xs font-medium rounded-md
									text-[var(--text-muted)] hover:text-[var(--error)] hover:bg-[var(--error)]/5 transition-colors
									disabled:opacity-50"
							>
								{#if acting === 'rejecting'}
									<Loader2 size={12} class="animate-spin" />
								{:else}
									Reject
								{/if}
							</button>
						</div>
					</div>
				{/each}
			</div>
		</div>
	</section>
{/if}

{#if team}
	<Tabs.Root bind:value={activeTab} class="space-y-6">
		<Tabs.List class="flex gap-1 p-1 bg-[var(--bg-subtle)] border border-[var(--border)] rounded-lg w-fit mx-auto max-w-full overflow-x-auto">
			<TabsTrigger value="overview" icon={LayoutDashboard}>Overview</TabsTrigger>
			<TabsTrigger value="members" icon={Contact}>Members ({members.length})</TabsTrigger>
			<TabsTrigger value="projects" icon={FolderSync}>Projects ({projects.length})</TabsTrigger>
			<TabsTrigger value="activity" icon={Activity}>Activity</TabsTrigger>
			<TabsTrigger value="settings" icon={Settings}>Settings</TabsTrigger>
		</Tabs.List>

		<Tabs.Content value="overview" class="mt-4">
			<TeamOverviewTab
				{team}
				teamName={data.teamName}
				joinCode={data.joinCode}
				{projectStatuses}
				{sessionStats}
				{deleteConfirm}
				{deleting}
				{deleteError}
				onleave={handleLeaveTeam}
				ondeleteconfirm={(v) => deleteConfirm = v}
				ondeleteerror={(v) => deleteError = v}
			/>
		</Tabs.Content>

		<Tabs.Content value="members" class="mt-4">
			<TeamMembersTab
				{members}
				teamName={data.teamName}
				{devices}
				{userId}
				{sessionStats}
				detectData={data.detectData}
				onrefresh={handleRefresh}
			/>
		</Tabs.Content>

		<Tabs.Content value="projects" class="mt-4">
			<TeamProjectsTab
				{projects}
				teamName={data.teamName}
				{projectStatuses}
				allProjects={data.allProjects}
				{sharedProjectNames}
				syncSessionLimit={data.team?.sync_session_limit ?? 'all'}
				onrefresh={handleRefresh}
			/>
		</Tabs.Content>

		<Tabs.Content value="activity" class="mt-4">
			<TeamActivityTab
				teamName={data.teamName}
				{activity}
				{sessionStats}
				{members}
			/>
		</Tabs.Content>

		<Tabs.Content value="settings" class="mt-4">
			<TeamSettings teamName={data.teamName} />
		</Tabs.Content>
	</Tabs.Root>
{:else}
	<div class="text-center py-16">
		<AlertTriangle size={32} class="mx-auto mb-3 text-[var(--warning)]" />
		<p class="text-[var(--text-primary)] font-medium">Team "{data.teamName}" not found</p>
		<a href="/team" class="text-sm text-[var(--accent)] hover:underline mt-2 inline-block">
			Back to Teams
		</a>
	</div>
{/if}

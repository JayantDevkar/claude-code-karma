<script lang="ts">
	import PageHeader from '$lib/components/layout/PageHeader.svelte';
	import SyncStatusBanner from '$lib/components/sync/SyncStatusBanner.svelte';
	import { Tabs } from 'bits-ui';
	import TabsTrigger from '$lib/components/ui/TabsTrigger.svelte';
	import TeamOverviewTab from '$lib/components/team/TeamOverviewTab.svelte';
	import TeamMembersTab from '$lib/components/team/TeamMembersTab.svelte';
	import TeamProjectsTab from '$lib/components/team/TeamProjectsTab.svelte';
	import TeamActivityTab from '$lib/components/team/TeamActivityTab.svelte';
	import { API_BASE } from '$lib/config';
	import { POLLING_INTERVALS } from '$lib/config';
	import { invalidateAll } from '$app/navigation';
	import { onMount } from 'svelte';
	import { browser } from '$app/environment';
	import {
		Users,
		FolderSync,
		FolderGit2,
		Loader2,
		AlertTriangle,
		CheckCircle2,
		RefreshCw,
		Radio,
		X,
		LayoutDashboard,
		Activity
	} from 'lucide-svelte';
	import type { SyncDevice, SyncPendingFolder, SyncProjectStatus, SyncTeam, SyncEvent, PendingDevice, TeamSessionStat } from '$lib/api-types';

	let { data } = $props();

	let deleteConfirm = $state(false);
	let deleting = $state(false);
	let deleteError = $state<string | null>(null);
	let syncError = $state('');
	let isRefreshing = $state(false);

	// Tab state
	const validTabs = ['overview', 'members', 'projects', 'activity'];
	let activeTab = $state('overview');
	let tabsReady = $state(false);

	// Team data — $state so polling can update it directly
	// Initialize from data directly (not via $effect) so SSR renders correctly
	let team = $state<SyncTeam | null>(data.team ?? null);
	$effect(() => {
		team = data.team ?? null;
	});
	let members = $derived(team?.members ?? []);
	let projects = $derived(team?.projects ?? []);

	// Per-project sync status
	let projectStatuses = $state<SyncProjectStatus[]>(data.projectStatuses ?? []);
	$effect(() => {
		projectStatuses = data.projectStatuses ?? [];
	});

	// Activity feed
	let activity = $state<SyncEvent[]>(data.activity ?? []);
	$effect(() => { activity = data.activity ?? []; });

	// Session stats
	let sessionStats = $state<TeamSessionStat[]>(data.sessionStats ?? []);
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
		const [teamsRes, devicesRes, foldersRes, projectStatusRes, activityRes] = await Promise.all([
			fetch(`${API_BASE}/sync/teams`, { signal }),
			fetch(`${API_BASE}/sync/devices`, { signal }),
			fetch(`${API_BASE}/sync/pending`, { signal }),
			fetch(`${API_BASE}/sync/teams/${teamNameEnc}/project-status`, { signal }),
			fetch(`${API_BASE}/sync/teams/${teamNameEnc}/activity?limit=20`, { signal })
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
	iconColor="--nav-purple"
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
		<div class="flex items-center justify-between mb-3">
			<div class="flex items-center gap-2">
				<h2 class="text-sm font-semibold text-[var(--text-primary)] uppercase tracking-wider">
					Pending Requests
				</h2>
				<span class="px-1.5 py-0.5 text-[10px] font-medium rounded bg-[var(--warning)]/15 text-[var(--warning)] border border-[var(--warning)]/25">
					{pendingDevices.length}
				</span>
			</div>
		</div>
		<div class="space-y-2">
			{#each pendingDevices as device (device.device_id)}
				{@const acting = deviceActing[device.device_id]}
				<div class="flex items-center gap-3 p-3 rounded-lg border border-[var(--warning)]/20 bg-[var(--warning)]/5">
					<Radio size={16} class="text-[var(--warning)] shrink-0" />
					<div class="flex-1 min-w-0">
						<p class="text-sm font-medium text-[var(--text-primary)] truncate">
							{device.name || 'Unknown device'} wants to join
						</p>
						<p class="text-xs text-[var(--text-muted)] mt-0.5">
							Accept to add this device as a team member and start syncing sessions
						</p>
					</div>
					<div class="flex items-center gap-1.5 shrink-0">
						{#if acting === 'error'}
							<span class="text-xs text-[var(--error)] mr-1">Failed</span>
						{/if}
						<button
							onclick={() => acceptDevice(device)}
							disabled={acting === 'accepting'}
							class="flex items-center gap-1 px-2.5 py-1.5 text-xs font-medium rounded-[var(--radius)]
								bg-[var(--accent)] text-white hover:bg-[var(--accent-hover)] transition-colors
								disabled:opacity-50 disabled:cursor-not-allowed"
						>
							{#if acting === 'accepting'}
								<Loader2 size={11} class="animate-spin" />
							{:else}
								<CheckCircle2 size={11} />
							{/if}
							Accept
						</button>
						<button
							onclick={() => dismissDevice(device.device_id)}
							disabled={acting === 'accepting'}
							class="flex items-center gap-1 px-2 py-1.5 text-xs font-medium rounded-[var(--radius)]
								border border-[var(--border)] text-[var(--text-muted)] hover:bg-[var(--bg-muted)] transition-colors
								disabled:opacity-50 disabled:cursor-not-allowed"
						>
							<X size={11} />
							Dismiss
						</button>
					</div>
				</div>
			{/each}
		</div>
	</section>
{/if}

<!-- Pending Project Shares (above tabs) -->
{#if pendingFolders.length > 0}
	<section class="mb-6">
		<div class="flex items-center justify-between mb-3">
			<div class="flex items-center gap-2">
				<h2 class="text-sm font-semibold text-[var(--text-primary)] uppercase tracking-wider">
					Pending Session Shares
				</h2>
				<span class="px-1.5 py-0.5 text-[10px] font-medium rounded bg-[var(--warning)]/15 text-[var(--warning)] border border-[var(--warning)]/25">
					{pendingFolders.length}
				</span>
			</div>
			<button
				onclick={acceptAllFolders}
				disabled={acceptingFolders}
				class="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-[var(--radius-md)]
					bg-[var(--accent)] text-white hover:bg-[var(--accent-hover)] transition-colors
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
		<div class="space-y-2">
			{#each pendingFolders as offer (offer.folder_id)}
				{@const acting = folderActing[offer.folder_id]}
				{@const isOutbox = offer.folder_type === 'outbox'}
				<div class="flex items-center gap-3 p-3 rounded-lg border {isOutbox ? 'border-[var(--accent)]/20 bg-[var(--accent)]/5' : 'border-[var(--warning)]/20 bg-[var(--warning)]/5'}">
					<FolderGit2 size={16} class="{isOutbox ? 'text-[var(--accent)]' : 'text-[var(--warning)]'} shrink-0" />
					<div class="flex-1 min-w-0">
						<p class="text-sm font-medium text-[var(--text-primary)] truncate">
							{offer.description || parseFolderLabel(offer)}
						</p>
						<p class="text-xs text-[var(--text-muted)] mt-0.5">
							{#if isOutbox}
								Accept to start sending your sessions for this project
							{:else}
								Accept to start receiving <span class="text-[var(--text-secondary)]">{offer.from_member}</span>'s sessions for this project
							{/if}
						</p>
					</div>
					<div class="flex items-center gap-1.5 shrink-0">
						<button
							onclick={() => acceptFolder(offer.folder_id)}
							disabled={!!acting}
							aria-label="Accept project share"
							class="flex items-center gap-1 px-2.5 py-1.5 text-xs font-medium rounded-[var(--radius)]
								bg-[var(--accent)] text-white hover:bg-[var(--accent-hover)] transition-colors
								disabled:opacity-50 disabled:cursor-not-allowed"
						>
							{#if acting === 'accepting'}
								<Loader2 size={11} class="animate-spin" />
							{:else}
								<CheckCircle2 size={11} />
							{/if}
							Accept
						</button>
						<button
							onclick={() => rejectFolder(offer.folder_id)}
							disabled={!!acting}
							aria-label="Reject project share"
							class="flex items-center gap-1 px-2 py-1.5 text-xs font-medium rounded-[var(--radius)]
								border border-[var(--error)]/30 text-[var(--error)] hover:bg-[var(--error)]/10 transition-colors
								disabled:opacity-50 disabled:cursor-not-allowed"
						>
							{#if acting === 'rejecting'}
								<Loader2 size={11} class="animate-spin" />
							{:else}
								<X size={11} />
							{/if}
							Reject
						</button>
					</div>
				</div>
			{/each}
		</div>
	</section>
{/if}

{#if team}
	<Tabs.Root bind:value={activeTab} class="space-y-6">
		<Tabs.List class="flex gap-1 p-1 bg-[var(--bg-subtle)] border border-[var(--border)] rounded-lg w-fit mx-auto">
			<TabsTrigger value="overview" icon={LayoutDashboard}>Overview</TabsTrigger>
			<TabsTrigger value="members" icon={Users}>Members ({members.length})</TabsTrigger>
			<TabsTrigger value="projects" icon={FolderSync}>Projects ({projects.length})</TabsTrigger>
			<TabsTrigger value="activity" icon={Activity}>Activity</TabsTrigger>
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

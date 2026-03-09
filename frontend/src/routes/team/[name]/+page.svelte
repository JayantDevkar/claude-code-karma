<script lang="ts">
	import PageHeader from '$lib/components/layout/PageHeader.svelte';
	import SyncStatusBanner from '$lib/components/sync/SyncStatusBanner.svelte';
	import JoinCodeCard from '$lib/components/team/JoinCodeCard.svelte';
	import TeamMemberCard from '$lib/components/team/TeamMemberCard.svelte';
	import AddProjectDialog from '$lib/components/team/AddProjectDialog.svelte';
	import TeamActivityFeed from '$lib/components/team/TeamActivityFeed.svelte';
	import SessionLimitSelector from '$lib/components/team/SessionLimitSelector.svelte';
	import { API_BASE } from '$lib/config';
	import { POLLING_INTERVALS } from '$lib/config';
	import { invalidateAll } from '$app/navigation';
	import { onMount } from 'svelte';
	import {
		Users,
		FolderSync,
		FolderGit2,
		Plus,
		Trash2,
		Loader2,
		AlertTriangle,
		CheckCircle2,
		RefreshCw,
		Radio,
		X
	} from 'lucide-svelte';
	import type { SyncDevice, SyncPendingFolder, SyncProjectStatus, SyncTeam, SyncEvent, PendingDevice } from '$lib/api-types';

	let { data } = $props();

	let showAddProject = $state(false);
	let deleteConfirm = $state(false);
	let deleting = $state(false);
	let deleteError = $state<string | null>(null);
	let removeProjectConfirm = $state<string | null>(null);
	let syncAllActing = $state(false);
	let syncError = $state('');
	let isRefreshing = $state(false);
	let removeProjectError = $state<string | null>(null);

	// Team data — $state so polling can update it directly
	let team = $state<SyncTeam | null>(null);
	$effect(() => { team = data.team ?? null; });
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

	function getProjectStatus(encodedName: string): SyncProjectStatus | undefined {
		return projectStatuses.find((p) => p.encoded_name === encodedName);
	}

	async function syncAllNow() {
		syncAllActing = true;
		syncError = '';
		try {
			const res = await fetch(
				`${API_BASE}/sync/teams/${encodeURIComponent(data.teamName)}/sync-now`,
				{ method: 'POST' }
			);
			if (!res.ok) {
				syncError = 'Sync failed — try again';
			} else {
				invalidateAll();
			}
		} catch {
			syncError = 'Network error';
		} finally {
			syncAllActing = false;
		}
	}

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

		return () => {
			clearInterval(interval);
			controller.abort();
		};
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

	async function handleRemoveProject(encodedName: string) {
		removeProjectError = null;
		try {
			const res = await fetch(
				`${API_BASE}/sync/teams/${encodeURIComponent(data.teamName)}/projects/${encodeURIComponent(encodedName)}`,
				{ method: 'DELETE' }
			);
			if (res.ok) {
				removeProjectConfirm = null;
				removeProjectError = null;
				invalidateAll();
			} else {
				removeProjectError = `Failed to remove project (${res.status})`;
			}
		} catch {
			removeProjectError = 'Network error — could not remove project';
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

{#if !team}
	<div class="text-center py-16">
		<AlertTriangle size={32} class="mx-auto mb-3 text-[var(--warning)]" />
		<p class="text-[var(--text-primary)] font-medium">Team "{data.teamName}" not found</p>
		<a href="/team" class="text-sm text-[var(--accent)] hover:underline mt-2 inline-block">
			Back to Teams
		</a>
	</div>
{:else}
	<div class="space-y-8">
		<!-- Join Code -->
		{#if data.joinCode}
			<section>
				<h2 class="text-sm font-semibold text-[var(--text-primary)] mb-3 uppercase tracking-wider">
					Join Code
				</h2>
				<JoinCodeCard code={data.joinCode} />
			</section>
		{/if}

		<!-- Pending Device Requests -->
		{#if pendingDevices.length > 0}
			<section>
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

		<!-- Pending Project Shares -->
		{#if pendingFolders.length > 0}
			<section>
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

		<!-- Members -->
		<section>
			<div class="flex items-center justify-between mb-3">
				<h2 class="text-sm font-semibold text-[var(--text-primary)] uppercase tracking-wider">
					Members ({members.length})
				</h2>
			</div>
			<div class="space-y-2">
				{#each members as member (member.name)}
					<TeamMemberCard
						{member}
						teamName={data.teamName}
						{devices}
						isSelf={member.name === userId}
						onremoved={handleRefresh}
					/>
				{/each}
				{#if members.length === 0}
					<p class="text-sm text-[var(--text-muted)] py-4 text-center">
						No members yet. Share your join code or add members manually.
					</p>
				{/if}
			</div>

			<!-- Diagnostic hints when waiting for members -->
			{#if members.length <= 1 && pendingDevices.length === 0 && pendingFolders.length === 0}
				<div class="mt-4 p-4 rounded-lg border border-[var(--border)]/50 bg-[var(--bg-subtle)]">
					<p class="text-xs font-semibold text-[var(--text-secondary)] uppercase tracking-wider mb-2">
						Waiting for members?
					</p>
					<ul class="space-y-1.5 text-xs text-[var(--text-muted)]">
						<li class="flex items-start gap-2">
							<span class="shrink-0 mt-0.5 w-1 h-1 rounded-full bg-[var(--text-muted)]"></span>
							Share the join code above with your teammate
						</li>
						<li class="flex items-start gap-2">
							<span class="shrink-0 mt-0.5 w-1 h-1 rounded-full bg-[var(--text-muted)]"></span>
							Both machines need <span class="font-medium text-[var(--text-secondary)]">Syncthing running</span> — check with <code class="px-1 py-0.5 rounded bg-[var(--bg-muted)] text-[10px] font-mono">brew services info syncthing</code>
						</li>
						<li class="flex items-start gap-2">
							<span class="shrink-0 mt-0.5 w-1 h-1 rounded-full bg-[var(--text-muted)]"></span>
							Discovery via relay can take 15-60 seconds after joining
						</li>
						<li class="flex items-start gap-2">
							<span class="shrink-0 mt-0.5 w-1 h-1 rounded-full bg-[var(--text-muted)]"></span>
							If the request doesn't appear, ask the member to restart Syncthing: <code class="px-1 py-0.5 rounded bg-[var(--bg-muted)] text-[10px] font-mono">brew services restart syncthing</code>
						</li>
					</ul>
					<div class="mt-3 flex items-center gap-2 text-xs">
						{#if data.detectData?.running}
							<span class="flex items-center gap-1 text-[var(--success)]">
								<span class="w-1.5 h-1.5 rounded-full bg-[var(--success)]"></span>
								Your Syncthing is running
							</span>
						{:else}
							<span class="flex items-center gap-1 text-[var(--error)]">
								<span class="w-1.5 h-1.5 rounded-full bg-[var(--error)]"></span>
								Your Syncthing is not running
							</span>
							<span class="text-[var(--text-muted)]"> — start with</span>
							<code class="px-1 py-0.5 rounded bg-[var(--bg-muted)] text-[10px] font-mono">brew services start syncthing</code>
						{/if}
					</div>
				</div>
			{/if}
		</section>

		<!-- Shared Projects -->
		<section>
			<div class="flex items-center justify-between mb-3">
				<h2 class="text-sm font-semibold text-[var(--text-primary)] uppercase tracking-wider">
					Shared Projects ({projects.length})
				</h2>
				<div class="flex items-center gap-2">
					{#if projects.length > 0}
						<button
							onclick={syncAllNow}
							disabled={syncAllActing}
							class="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-[var(--radius-md)]
								bg-[var(--accent)] text-white hover:bg-[var(--accent-hover)] transition-colors
								disabled:opacity-50 disabled:cursor-not-allowed"
						>
							{#if syncAllActing}
								<Loader2 size={12} class="animate-spin" />
								Syncing...
							{:else}
								<RefreshCw size={12} />
								Sync Now
							{/if}
						</button>
					{/if}
					<button
						onclick={() => (showAddProject = true)}
						class="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-[var(--radius-md)]
							border border-[var(--border)] text-[var(--text-secondary)]
							hover:bg-[var(--bg-muted)] hover:text-[var(--text-primary)] transition-colors"
					>
						<Plus size={13} />
						Add Projects
					</button>
				</div>
			</div>
			{#if syncError}
				<p class="text-xs text-[var(--error)] mb-2" aria-live="polite">{syncError}</p>
			{/if}
			<div class="space-y-2">
				{#each projects as project (project.encoded_name)}
					{@const status = getProjectStatus(project.encoded_name)}
					<div
						class="flex items-center justify-between p-3 rounded-lg border border-[var(--border)] bg-[var(--bg-base)]"
					>
						<div class="flex items-center gap-3 min-w-0">
							<FolderSync size={16} class="text-[var(--text-muted)] shrink-0" />
							<div class="min-w-0">
								<a
									href="/projects/{project.encoded_name}"
									class="text-sm font-medium text-[var(--text-primary)] hover:text-[var(--accent)] transition-colors truncate block"
								>
									{project.name || project.encoded_name}
								</a>
								{#if project.path}
									<p class="text-[11px] text-[var(--text-muted)] truncate">{project.path}</p>
								{/if}
								{#if status}
									<p class="text-[11px] text-[var(--text-muted)] mt-0.5">
										{status.packaged_count}/{status.local_count} sessions packaged
									</p>
								{/if}
							</div>
						</div>
						<div class="flex items-center gap-2 shrink-0">
							{#if status}
								{#if status.gap === 0}
									<span class="flex items-center gap-1 px-2 py-1 text-[11px] font-medium rounded-full bg-[var(--success)]/10 text-[var(--success)] border border-[var(--success)]/20">
										<CheckCircle2 size={11} />
										In Sync
									</span>
								{:else}
									<span class="flex items-center gap-1 px-2 py-1 text-[11px] font-medium rounded-full bg-[var(--warning)]/10 text-[var(--warning)] border border-[var(--warning)]/20">
										{status.gap} behind
									</span>
								{/if}
							{/if}
							{#if removeProjectConfirm === project.encoded_name}
								<div class="flex items-center gap-1.5">
									<button
										onclick={() => handleRemoveProject(project.encoded_name)}
										class="px-2 py-1 text-xs font-medium rounded bg-[var(--error)] text-white hover:bg-[var(--error)]/80 transition-colors"
									>
										Remove
									</button>
									<button
										onclick={() => (removeProjectConfirm = null)}
										class="px-2 py-1 text-xs rounded text-[var(--text-muted)] hover:bg-[var(--bg-muted)] transition-colors"
									>
										Cancel
									</button>
								</div>
							{:else}
								<button
									onclick={() => (removeProjectConfirm = project.encoded_name)}
									class="p-1.5 rounded text-[var(--text-muted)] hover:text-[var(--error)] hover:bg-[var(--error)]/10 transition-colors"
									title="Remove from team"
									aria-label="Remove project {project.name || project.encoded_name}"
								>
									<Trash2 size={14} />
								</button>
							{/if}
						</div>
					</div>
				{/each}
				{#if projects.length === 0}
					<p class="text-sm text-[var(--text-muted)] py-4 text-center">
						No projects shared yet. Add projects to start syncing sessions.
					</p>
				{/if}
			</div>
			<!-- Session limit setting -->
			{#if projects.length > 0}
				<div class="mt-3 pt-3 border-t border-[var(--border)]/50">
					<SessionLimitSelector
						teamName={data.teamName}
						currentLimit={data.team?.sync_session_limit ?? 'all'}
					/>
				</div>
			{/if}
		</section>

		<!-- Activity -->
		<section class="pt-4 border-t border-[var(--border)]">
			<TeamActivityFeed
				events={activity}
				teamName={data.teamName}
			/>
		</section>

		<!-- Danger Zone -->
		<section class="pt-4 border-t border-[var(--border)]">
			<h2 class="text-sm font-semibold text-[var(--error)] mb-3 uppercase tracking-wider">
				Danger Zone
			</h2>
			{#if deleteConfirm}
				<div class="space-y-2">
					<div class="flex items-center gap-3 p-4 rounded-lg border border-[var(--error)]/20 bg-[var(--error)]/5">
						<AlertTriangle size={16} class="text-[var(--error)] shrink-0" />
						<p class="text-sm text-[var(--text-primary)] flex-1">
							Leave team "{data.teamName}"? This will stop syncing with all members and clean up Syncthing folders.
						</p>
						<div class="flex items-center gap-2 shrink-0">
							<button
								onclick={handleLeaveTeam}
								disabled={deleting}
								class="px-3 py-1.5 text-xs font-medium rounded bg-[var(--error)] text-white hover:bg-[var(--error)]/80 transition-colors disabled:opacity-50"
							>
								{#if deleting}
									<Loader2 size={12} class="animate-spin" />
								{:else}
									Leave
								{/if}
							</button>
							<button
								onclick={() => { deleteConfirm = false; deleteError = null; }}
								class="px-3 py-1.5 text-xs rounded text-[var(--text-muted)] hover:bg-[var(--bg-muted)] transition-colors"
							>
								Cancel
							</button>
						</div>
					</div>
					{#if deleteError}
						<p class="text-xs text-[var(--error)]" aria-live="polite">{deleteError}</p>
					{/if}
				</div>
			{:else}
				<button
					onclick={() => (deleteConfirm = true)}
					class="px-4 py-2 text-sm font-medium rounded-[var(--radius-md)] border border-[var(--error)]/30
						text-[var(--error)] hover:bg-[var(--error)]/10 transition-colors"
				>
					Leave Team
				</button>
			{/if}
		</section>
	</div>
{/if}

<AddProjectDialog
	bind:open={showAddProject}
	teamName={data.teamName}
	allProjects={data.allProjects}
	{sharedProjectNames}
	onadded={handleRefresh}
/>

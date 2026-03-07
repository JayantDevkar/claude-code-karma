<script lang="ts">
	import PageHeader from '$lib/components/layout/PageHeader.svelte';
	import JoinCodeCard from '$lib/components/team/JoinCodeCard.svelte';
	import PendingDeviceCard from '$lib/components/team/PendingDeviceCard.svelte';
	import TeamMemberCard from '$lib/components/team/TeamMemberCard.svelte';
	import AddMemberDialog from '$lib/components/team/AddMemberDialog.svelte';
	import AddProjectDialog from '$lib/components/team/AddProjectDialog.svelte';
	import { API_BASE } from '$lib/config';
	import { POLLING_INTERVALS } from '$lib/config';
	import { invalidateAll } from '$app/navigation';
	import { onMount } from 'svelte';
	import {
		Users,
		UserPlus,
		FolderSync,
		Plus,
		Trash2,
		Loader2,
		AlertTriangle
	} from 'lucide-svelte';
	import type { PendingDevice, SyncDevice } from '$lib/api-types';

	let { data } = $props();

	let showAddMember = $state(false);
	let showAddProject = $state(false);
	let deleteConfirm = $state(false);
	let deleting = $state(false);
	let deleteError = $state<string | null>(null);
	let removeProjectConfirm = $state<string | null>(null);

	// Polling state for pending devices and connection status
	let pendingDevices = $state<PendingDevice[]>([]);
	let devices = $state<SyncDevice[]>([]);

	// Sync from server data when it changes (e.g. after invalidateAll)
	$effect(() => {
		pendingDevices = data.pendingDevices ?? [];
	});
	$effect(() => {
		devices = data.devices ?? [];
	});

	let team = $derived(data.team);
	let members = $derived(team?.members ?? []);
	let projects = $derived(team?.projects ?? []);
	let userId = $derived(data.syncStatus?.user_id);
	let sharedProjectNames = $derived(projects.map((p) => p.encoded_name));

	// Poll for pending devices and device status
	onMount(() => {
		const interval = setInterval(async () => {
			try {
				const [pendingRes, devicesRes] = await Promise.all([
					fetch(`${API_BASE}/sync/pending-devices`),
					fetch(`${API_BASE}/sync/devices`)
				]);
				if (pendingRes.ok) {
					const pd = await pendingRes.json();
					pendingDevices = pd.devices ?? [];
				}
				if (devicesRes.ok) {
					const dd = await devicesRes.json();
					devices = dd.devices ?? [];
				}
			} catch {
				// polling errors are non-critical
			}
		}, POLLING_INTERVALS.SYNC_STATUS);

		return () => clearInterval(interval);
	});

	async function handleDeleteTeam() {
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
				deleteError = body.detail || `Failed to delete team (${res.status})`;
			}
		} catch {
			deleteError = 'Network error. Could not delete team.';
		} finally {
			deleting = false;
		}
	}

	async function handleRemoveProject(encodedName: string) {
		try {
			const res = await fetch(
				`${API_BASE}/sync/teams/${encodeURIComponent(data.teamName)}/projects/${encodeURIComponent(encodedName)}`,
				{ method: 'DELETE' }
			);
			if (res.ok) {
				removeProjectConfirm = null;
				invalidateAll();
			}
		} catch {
			// best-effort
		}
	}

	function handleRefresh() {
		invalidateAll();
	}
</script>

<PageHeader
	title={data.teamName}
	icon={Users}
	iconColor="--nav-purple"
	breadcrumbs={[
		{ label: 'Dashboard', href: '/' },
		{ label: 'Teams', href: '/team' },
		{ label: data.teamName }
	]}
>
	{#snippet headerRight()}
		<button
			onclick={handleRefresh}
			class="px-3 py-1.5 text-sm font-medium rounded-[var(--radius-md)] border border-[var(--border)]
				text-[var(--text-secondary)] hover:bg-[var(--bg-muted)] transition-colors"
		>
			Refresh
		</button>
	{/snippet}
</PageHeader>

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

		<!-- Pending Connections -->
		{#if pendingDevices.length > 0}
			<section>
				<h2 class="text-sm font-semibold text-[var(--text-primary)] mb-3 uppercase tracking-wider">
					Pending Connections
				</h2>
				<div class="space-y-3">
					{#each pendingDevices as device (device.device_id)}
						<PendingDeviceCard
							{device}
							teamName={data.teamName}
							onaccepted={handleRefresh}
						/>
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
				<button
					onclick={() => (showAddMember = true)}
					class="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-[var(--radius-md)]
						border border-[var(--border)] text-[var(--text-secondary)]
						hover:bg-[var(--bg-muted)] hover:text-[var(--text-primary)] transition-colors"
				>
					<UserPlus size={13} />
					Add Member
				</button>
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
		</section>

		<!-- Shared Projects -->
		<section>
			<div class="flex items-center justify-between mb-3">
				<h2 class="text-sm font-semibold text-[var(--text-primary)] uppercase tracking-wider">
					Shared Projects ({projects.length})
				</h2>
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
			<div class="space-y-2">
				{#each projects as project (project.encoded_name)}
					<div
						class="flex items-center justify-between p-3 rounded-lg border border-[var(--border)] bg-[var(--bg-base)]"
					>
						<div class="flex items-center gap-3 min-w-0">
							<FolderSync size={16} class="text-[var(--text-muted)] shrink-0" />
							<div class="min-w-0">
								<p class="text-sm font-medium text-[var(--text-primary)] truncate">
									{project.name || project.encoded_name}
								</p>
								{#if project.path}
									<p class="text-[11px] text-[var(--text-muted)] truncate">{project.path}</p>
								{/if}
							</div>
						</div>
						<div class="shrink-0">
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
							Delete team "{data.teamName}"? This will remove all members and project assignments.
						</p>
						<div class="flex items-center gap-2 shrink-0">
							<button
								onclick={handleDeleteTeam}
								disabled={deleting}
								class="px-3 py-1.5 text-xs font-medium rounded bg-[var(--error)] text-white hover:bg-[var(--error)]/80 transition-colors disabled:opacity-50"
							>
								{#if deleting}
									<Loader2 size={12} class="animate-spin" />
								{:else}
									Delete
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
					Delete Team
				</button>
			{/if}
		</section>
	</div>
{/if}

<AddMemberDialog bind:open={showAddMember} teamName={data.teamName} onadded={handleRefresh} />
<AddProjectDialog
	bind:open={showAddProject}
	teamName={data.teamName}
	allProjects={data.allProjects}
	{sharedProjectNames}
	onadded={handleRefresh}
/>

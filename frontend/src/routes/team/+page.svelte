<script lang="ts">
	import PageHeader from '$lib/components/layout/PageHeader.svelte';
	import TeamCard from '$lib/components/team/TeamCard.svelte';
	import CreateTeamDialog from '$lib/components/team/CreateTeamDialog.svelte';
	import JoinTeamDialog from '$lib/components/team/JoinTeamDialog.svelte';
	import { API_BASE } from '$lib/config';
	import { Users, Plus, UserPlus, ArrowRight, Radio, Loader2 } from 'lucide-svelte';
	import { goto, invalidateAll } from '$app/navigation';
	import type { JoinTeamResponse, PendingDevice } from '$lib/api-types';

	let { data } = $props();

	let showCreateDialog = $state(false);
	let showJoinDialog = $state(false);

	let configured = $derived(data.syncStatus?.configured ?? false);
	let teams = $derived(data.teams ?? []);
	let pendingDevices = $state<PendingDevice[]>([]);

	$effect(() => {
		pendingDevices = data.pendingDevices ?? [];
	});

	// Accept pending device: create team + add device as member
	let acceptingDevice = $state<string | null>(null);
	let acceptTeamName = $state('');
	let acceptMemberName = $state('');
	let acceptError = $state<string | null>(null);

	function startAccept(device: PendingDevice) {
		acceptingDevice = device.device_id;
		acceptMemberName = device.name || '';
		acceptTeamName = '';
		acceptError = null;
	}

	function cancelAccept() {
		acceptingDevice = null;
		acceptError = null;
	}

	async function confirmAccept(device: PendingDevice) {
		if (!acceptTeamName.trim() || !acceptMemberName.trim()) return;
		acceptError = null;

		try {
			// 1. Create team (also adds self as member via our fix)
			const createRes = await fetch(`${API_BASE}/sync/teams`, {
				method: 'POST',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify({ name: acceptTeamName.trim(), backend: 'syncthing' })
			});
			if (!createRes.ok) {
				const err = await createRes.json().catch(() => ({}));
				acceptError = err.detail || `Failed to create team (${createRes.status})`;
				return;
			}

			// 2. Add device as member (also pairs in Syncthing + auto-shares folders)
			const addRes = await fetch(
				`${API_BASE}/sync/teams/${encodeURIComponent(acceptTeamName.trim())}/members`,
				{
					method: 'POST',
					headers: { 'Content-Type': 'application/json' },
					body: JSON.stringify({ name: acceptMemberName.trim(), device_id: device.device_id })
				}
			);
			if (!addRes.ok) {
				const err = await addRes.json().catch(() => ({}));
				acceptError = err.detail || `Failed to add member (${addRes.status})`;
				return;
			}

			acceptingDevice = null;
			invalidateAll();
			goto(`/team/${encodeURIComponent(acceptTeamName.trim())}`);
		} catch (e) {
			acceptError = e instanceof Error ? e.message : 'Network error';
		}
	}

	function handleTeamCreated(teamName: string) {
		invalidateAll();
		if (teamName) goto(`/team/${encodeURIComponent(teamName)}`);
	}

	function handleTeamJoined(result: JoinTeamResponse) {
		// Stay on dialog to show the "share your code back" CTA
		// Navigation happens when they close the dialog
		invalidateAll();
	}
</script>

<PageHeader
	title="Teams"
	icon={Users}
	iconColor="--nav-indigo"
	breadcrumbs={[{ label: 'Dashboard', href: '/' }, { label: 'Teams' }]}
	subtitle="Create and manage teams to share sessions with teammates &middot; Sync status on /sync"
>
	{#snippet headerRight()}
		{#if configured && teams.length > 0}
			<div class="flex items-center gap-2">
				<button
					onclick={() => (showCreateDialog = true)}
					class="flex items-center gap-1.5 px-3 py-1.5 text-sm font-medium rounded-[var(--radius-md)]
						bg-[var(--accent)] text-white hover:bg-[var(--accent-hover)] transition-colors"
				>
					<Plus size={14} />
					Create Team
				</button>
				<button
					onclick={() => (showJoinDialog = true)}
					class="flex items-center gap-1.5 px-3 py-1.5 text-sm font-medium rounded-[var(--radius-md)]
						border border-[var(--border)] text-[var(--text-secondary)]
						hover:bg-[var(--bg-muted)] hover:text-[var(--text-primary)] transition-colors"
				>
					<UserPlus size={14} />
					Join Team
				</button>
			</div>
		{/if}
	{/snippet}
</PageHeader>

<div class="max-w-5xl mx-auto space-y-6">
	{#if !configured}
		<!-- State 1: Sync not configured -->
		<div class="flex flex-col items-center justify-center py-16 text-center">
			<div
				class="w-16 h-16 rounded-2xl flex items-center justify-center bg-[var(--nav-indigo-subtle)] text-[var(--nav-indigo)] mb-5"
			>
				<Users size={32} strokeWidth={1.5} />
			</div>
			<h3 class="text-lg font-semibold text-[var(--text-primary)] mb-2">Set up sync first</h3>
			<p class="text-sm text-[var(--text-muted)] mb-6 max-w-sm">
				Before creating or joining a team, you need to install Syncthing and initialize sync.
			</p>
			<a
				href="/sync"
				class="inline-flex items-center gap-2 px-5 py-2.5 text-sm font-medium rounded-lg
					bg-[var(--accent)] text-white hover:bg-[var(--accent-hover)] transition-colors"
			>
				Go to Sync Setup
				<ArrowRight size={16} />
			</a>
		</div>
	{:else if teams.length === 0}
		<!-- Pending connections (shown even with 0 teams) -->
		{#if pendingDevices.length > 0}
			<div class="space-y-3 mb-8">
				<h2 class="text-sm font-semibold text-[var(--text-primary)] uppercase tracking-wider">
					Incoming Connections
				</h2>
				{#each pendingDevices as device (device.device_id)}
					<div class="p-4 rounded-lg border border-[var(--warning)]/20 bg-[var(--warning)]/5">
						<div class="flex items-start gap-3">
							<div class="mt-0.5">
								<Radio size={16} class="text-[var(--warning)]" />
							</div>
							<div class="flex-1 space-y-3">
								<div>
									<p class="text-sm font-medium text-[var(--text-primary)]">
										{device.name || 'Unknown device'} wants to connect
									</p>
									<p class="text-xs font-mono text-[var(--text-muted)] mt-0.5">
										{device.device_id.length > 24 ? device.device_id.slice(0, 24) + '...' : device.device_id}
									</p>
								</div>

								{#if acceptingDevice === device.device_id}
									<div class="space-y-2">
										<div class="grid grid-cols-2 gap-2">
											<div class="space-y-1">
												<label for="team-{device.device_id}" class="block text-xs font-medium text-[var(--text-secondary)]">
													Team Name
												</label>
												<input
													id="team-{device.device_id}"
													type="text"
													bind:value={acceptTeamName}
													placeholder="my-team"
													class="w-full px-3 py-1.5 text-sm rounded-[var(--radius-md)] border border-[var(--border)]
														bg-[var(--bg-base)] text-[var(--text-primary)] placeholder:text-[var(--text-muted)]
														focus:outline-none focus:ring-2 focus:ring-[var(--accent)]/40 focus:border-[var(--accent)]
														transition-colors"
												/>
											</div>
											<div class="space-y-1">
												<label for="member-{device.device_id}" class="block text-xs font-medium text-[var(--text-secondary)]">
													Their Name
												</label>
												<input
													id="member-{device.device_id}"
													type="text"
													bind:value={acceptMemberName}
													placeholder="alice"
													class="w-full px-3 py-1.5 text-sm rounded-[var(--radius-md)] border border-[var(--border)]
														bg-[var(--bg-base)] text-[var(--text-primary)] placeholder:text-[var(--text-muted)]
														focus:outline-none focus:ring-2 focus:ring-[var(--accent)]/40 focus:border-[var(--accent)]
														transition-colors"
												/>
											</div>
										</div>
										{#if acceptError}
											<p class="text-xs text-[var(--error)]">{acceptError}</p>
										{/if}
										<div class="flex items-center gap-2">
											<button
												onclick={() => confirmAccept(device)}
												disabled={!acceptTeamName.trim() || !acceptMemberName.trim()}
												class="flex items-center gap-1.5 px-3 py-1.5 text-sm font-medium rounded-[var(--radius-md)]
													bg-[var(--accent)] text-white hover:bg-[var(--accent-hover)] transition-colors
													disabled:opacity-50 disabled:cursor-not-allowed"
											>
												<UserPlus size={14} />
												Create Team & Accept
											</button>
											<button
												onclick={cancelAccept}
												class="px-3 py-1.5 text-sm rounded-[var(--radius-md)] text-[var(--text-muted)]
													hover:bg-[var(--bg-muted)] transition-colors"
											>
												Cancel
											</button>
										</div>
									</div>
								{:else}
									<button
										onclick={() => startAccept(device)}
										class="flex items-center gap-1.5 px-3 py-1.5 text-sm font-medium rounded-[var(--radius-md)]
											bg-[var(--accent)] text-white hover:bg-[var(--accent-hover)] transition-colors"
									>
										<UserPlus size={14} />
										Accept & Create Team
									</button>
								{/if}
							</div>
						</div>
					</div>
				{/each}
			</div>
		{/if}

		<!-- State 2: No teams yet -->
		<div class="flex flex-col items-center justify-center py-16 text-center">
			<div
				class="w-16 h-16 rounded-2xl flex items-center justify-center bg-[var(--nav-indigo-subtle)] text-[var(--nav-indigo)] mb-5"
			>
				<Users size={32} strokeWidth={1.5} />
			</div>
			<h3 class="text-lg font-semibold text-[var(--text-primary)] mb-2">No teams yet</h3>
			<p class="text-sm text-[var(--text-muted)] mb-6 max-w-sm">
				Create a team to start sharing sessions with teammates, or join an existing team.
			</p>
			<div class="flex items-center gap-3">
				<button
					onclick={() => (showCreateDialog = true)}
					class="inline-flex items-center gap-2 px-5 py-2.5 text-sm font-medium rounded-lg
						bg-[var(--accent)] text-white hover:bg-[var(--accent-hover)] transition-colors"
				>
					<Plus size={16} />
					Create Team
				</button>
				<button
					onclick={() => (showJoinDialog = true)}
					class="inline-flex items-center gap-2 px-5 py-2.5 text-sm font-medium rounded-lg
						border border-[var(--border)] text-[var(--text-secondary)]
						hover:bg-[var(--bg-muted)] hover:text-[var(--text-primary)] transition-colors"
				>
					<UserPlus size={16} />
					Join Team
				</button>
			</div>
		</div>
	{:else}
		<!-- Pending connections (shown above teams) -->
		{#if pendingDevices.length > 0}
			<div class="space-y-3 mb-6">
				<h2 class="text-sm font-semibold text-[var(--text-primary)] uppercase tracking-wider">
					Incoming Connections
				</h2>
				{#each pendingDevices as device (device.device_id)}
					<div class="p-4 rounded-lg border border-[var(--warning)]/20 bg-[var(--warning)]/5">
						<div class="flex items-center gap-3">
							<Radio size={16} class="text-[var(--warning)] shrink-0" />
							<div class="flex-1 min-w-0">
								<p class="text-sm font-medium text-[var(--text-primary)]">
									{device.name || 'Unknown device'} wants to connect
								</p>
								<p class="text-xs font-mono text-[var(--text-muted)] truncate">
									{device.device_id.length > 24 ? device.device_id.slice(0, 24) + '...' : device.device_id}
								</p>
							</div>
							<p class="text-xs text-[var(--text-muted)] shrink-0">
								Accept on a team page or use their join code
							</p>
						</div>
					</div>
				{/each}
			</div>
		{/if}

		<!-- State 3: Has teams -->
		<div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
			{#each teams as team (team.name)}
				<TeamCard {team} />
			{/each}
		</div>
	{/if}
</div>

<CreateTeamDialog bind:open={showCreateDialog} oncreated={handleTeamCreated} />
<JoinTeamDialog bind:open={showJoinDialog} onjoined={handleTeamJoined} />

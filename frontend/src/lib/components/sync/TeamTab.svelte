<script lang="ts">
	import { untrack } from 'svelte';
	import { Users, XCircle, Plus, Loader2, Trash2, CheckCircle2, Copy, CheckCircle, Sparkles, FolderGit2, X } from 'lucide-svelte';
	import type { SyncDetect, SyncTeam, SyncTeamMember, SyncDevice, SyncTeamProject } from '$lib/api-types';
	import { API_BASE } from '$lib/config';
	import { pushSyncAction } from '$lib/stores/syncActions.svelte';
	import DeviceCard from './DeviceCard.svelte';

	let {
		detect,
		active = false,
		teamName = null,
		onteamchange
	}: {
		detect: SyncDetect | null;
		active?: boolean;
		teamName: string | null;
		onteamchange?: () => void;
	} = $props();

	// Data state
	let teams = $state<SyncTeam[]>([]);
	let deviceMap = $state<Map<string, SyncDevice>>(new Map());
	let loading = $state(true);
	let error = $state<string | null>(null);

	// Derived: find the team matching the teamName prop
	let activeTeam = $derived(teamName ? (teams.find((t) => t.name === teamName) ?? null) : null);

	// Derived: members enriched with live device connection data
	let members = $derived<SyncDevice[]>(
		(activeTeam?.members ?? []).map((m: SyncTeamMember): SyncDevice => {
			const live = deviceMap.get(m.device_id);
			return {
				device_id: m.device_id,
				name: m.name,
				connected: live?.connected ?? m.connected,
				address: live?.address,
				type: live?.type,
				crypto: live?.crypto,
				in_bytes_total: live?.in_bytes_total ?? m.in_bytes_total,
				out_bytes_total: live?.out_bytes_total ?? m.out_bytes_total,
				is_self: detect?.device_id ? m.device_id === detect.device_id : false
			};
		})
	);

	// Derived: projects shared with this team
	let teamProjects = $derived<SyncTeamProject[]>(activeTeam?.projects ?? []);

	// All available projects (for adding new ones)
	interface ApiProject { display_name: string | null; encoded_name: string; }
	let allProjects = $state<ApiProject[]>([]);
	let removingProject = $state<string | null>(null);

	// Team delete state
	let deletingTeam = $state(false);
	let deleteConfirm = $state(false);

	// Add member form state
	let newMemberDeviceId = $state('');
	let newMemberName = $state('');
	let addingMember = $state(false);
	let addError = $state<string | null>(null);

	// Remove state
	let removingMemberName = $state<string | null>(null);
	let removeConfirmName = $state<string | null>(null);

	// Flash message
	let flashMessage = $state<string | null>(null);
	let flashTimeout: ReturnType<typeof setTimeout> | null = null;

	// Copy device ID state
	let copiedSelfId = $state(false);

	function showFlash(msg: string) {
		flashMessage = msg;
		if (flashTimeout) clearTimeout(flashTimeout);
		flashTimeout = setTimeout(() => (flashMessage = null), 3000);
	}

	function copySelfId() {
		const id = detect?.device_id ?? '';
		if (!id) return;
		navigator.clipboard
			.writeText(id)
			.then(() => {
				copiedSelfId = true;
				setTimeout(() => (copiedSelfId = false), 2000);
			})
			.catch(() => {});
	}

	async function deleteTeam() {
		if (!teamName) return;
		deletingTeam = true;
		try {
			const res = await fetch(`${API_BASE}/sync/teams/${encodeURIComponent(teamName)}`, {
				method: 'DELETE'
			});
			if (res.ok) {
				deleteConfirm = false;
				pushSyncAction('team_deleted', `Team "${teamName}" deleted`);
				showFlash(`Team "${teamName}" deleted`);
				onteamchange?.();
			}
		} catch {
			// ignore
		} finally {
			deletingTeam = false;
		}
	}

	async function loadData() {
		if (teams.length === 0) loading = true;
		error = null;
		try {
			const [teamsRes, devicesRes, projectsRes] = await Promise.all([
				fetch(`${API_BASE}/sync/teams`),
				fetch(`${API_BASE}/sync/devices`),
				fetch(`${API_BASE}/projects`).catch(() => null)
			]);

			if (!teamsRes.ok) {
				error = 'Could not load team data.';
				return;
			}

			const teamsBody = await teamsRes.json();
			teams = Array.isArray(teamsBody) ? teamsBody : (teamsBody.teams ?? []);

			if (devicesRes.ok) {
				const devicesBody = await devicesRes.json();
				const deviceList: SyncDevice[] = devicesBody.devices ?? [];
				deviceMap = new Map(deviceList.map((d) => [d.device_id, d]));
			}

			if (projectsRes?.ok) {
				allProjects = await projectsRes.json();
			}
		} catch {
			error = 'Cannot reach backend. Is the API running?';
		} finally {
			loading = false;
		}
	}

	// Derived: projects available to add (not already in team)
	let syncedEncodedNames = $derived(new Set(teamProjects.map((p) => p.encoded_name)));
	let availableProjects = $derived(allProjects.filter((p) => !syncedEncodedNames.has(p.encoded_name)));

	async function addProjectToTeam(encodedName: string) {
		if (!teamName) return;
		try {
			await fetch(`${API_BASE}/sync/teams/${encodeURIComponent(teamName)}/projects`, {
				method: 'POST',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify({ name: encodedName, encoded_name: encodedName, path: '' })
			});
			await loadData();
			const proj = allProjects.find((p) => p.encoded_name === encodedName);
			const projName = proj?.display_name ?? encodedName;
			pushSyncAction('project_added', `Project "${projName}" added to team`, teamName ?? '');
			showFlash(`Added "${projName}" to team`);
		} catch {
			// ignore
		}
	}

	async function removeProjectFromTeam(encodedName: string) {
		if (!teamName) return;
		removingProject = encodedName;
		try {
			await fetch(
				`${API_BASE}/sync/teams/${encodeURIComponent(teamName)}/projects/${encodeURIComponent(encodedName)}`,
				{ method: 'DELETE' }
			);
			await loadData();
			pushSyncAction('project_removed', 'Project removed from team', teamName ?? '');
			showFlash('Project removed from team');
		} catch {
			// ignore
		} finally {
			removingProject = null;
		}
	}

	async function addMember() {
		if (!teamName) return;
		if (!newMemberDeviceId.trim()) return;
		addingMember = true;
		addError = null;
		try {
			const res = await fetch(`${API_BASE}/sync/teams/${encodeURIComponent(teamName)}/members`, {
				method: 'POST',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify({
					device_id: newMemberDeviceId.trim().toUpperCase(),
					name: newMemberName.trim() || newMemberDeviceId.trim()
				})
			});
			if (res.ok) {
				const addedName = newMemberName.trim() || 'Member';
				newMemberDeviceId = '';
				newMemberName = '';
				await loadData();
				pushSyncAction('member_added', `${addedName} added to team`, teamName ?? '');
				showFlash(`${addedName} added to team`);
			} else {
				const body = await res.json().catch(() => ({}));
				addError = body?.detail ?? 'Failed to add member.';
			}
		} catch {
			addError = 'Cannot reach backend.';
		} finally {
			addingMember = false;
		}
	}

	async function removeMember(memberName: string) {
		if (!teamName) return;
		removingMemberName = memberName;
		try {
			const res = await fetch(
				`${API_BASE}/sync/teams/${encodeURIComponent(teamName)}/members/${encodeURIComponent(memberName)}`,
				{ method: 'DELETE' }
			);
			if (res.ok) {
				await loadData();
				pushSyncAction('member_removed', `${memberName} removed from team`, teamName ?? '');
				showFlash(`${memberName} removed from team`);
			}
		} catch {
			// ignore
		} finally {
			removingMemberName = null;
			removeConfirmName = null;
		}
	}

	// Reload when tab becomes active or teamName changes
	$effect(() => {
		if (active && teamName) {
			untrack(() => loadData());
		}
	});
</script>

<div class="p-6 space-y-4">
	<!-- Flash message -->
	{#if flashMessage}
		<div
			class="flex items-center gap-2 px-4 py-2.5 rounded-[var(--radius-lg)] bg-[var(--success)]/10 border border-[var(--success)]/20 text-xs font-medium text-[var(--success)]"
		>
			<CheckCircle2 size={14} class="shrink-0" />
			{flashMessage}
		</div>
	{/if}

	{#if !teamName}
		<!-- No team selected -->
		<div
			class="py-12 flex flex-col items-center gap-3 text-center border border-dashed border-[var(--border)] rounded-[var(--radius-lg)]"
		>
			<Users size={28} class="text-[var(--text-muted)]" />
			<p class="text-sm text-[var(--text-muted)]">Select a team to manage members</p>
		</div>
	{:else}
		<!-- Team Header Card -->
		<div class="rounded-[var(--radius-lg)] border border-[var(--border)] bg-[var(--bg-subtle)] p-4">
			<div class="flex items-center justify-between">
				<div class="flex items-center gap-2 min-w-0">
					<Users size={16} class="shrink-0 text-[var(--accent)]" />
					<div class="min-w-0">
						<p class="text-sm font-semibold text-[var(--text-primary)] truncate">{teamName}</p>
						<p class="text-xs text-[var(--text-muted)]">Syncthing team</p>
					</div>
				</div>
				{#if deleteConfirm}
					<div class="flex items-center gap-1.5 bg-[var(--bg-base)] rounded-lg px-2.5 py-1.5 border border-[var(--border)] shadow-md">
						<span class="text-xs text-[var(--text-secondary)]">Delete team?</span>
						<button
							onclick={deleteTeam}
							disabled={deletingTeam}
							class="px-2.5 py-1 text-xs font-medium rounded-md bg-[var(--error)] text-white hover:opacity-90 transition-opacity disabled:opacity-50"
						>
							{deletingTeam ? '...' : 'Yes'}
						</button>
						<button
							onclick={() => (deleteConfirm = false)}
							class="px-2.5 py-1 text-xs font-medium rounded-md border border-[var(--border)] text-[var(--text-muted)] hover:text-[var(--text-primary)] transition-colors"
						>
							No
						</button>
					</div>
				{:else}
					<button
						onclick={() => (deleteConfirm = true)}
						aria-label="Delete team"
						class="shrink-0 flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-[var(--radius)] border border-[var(--error)]/30 text-[var(--error)] hover:bg-[var(--error-subtle)] transition-colors"
					>
						<Trash2 size={12} />
						Delete
					</button>
				{/if}
			</div>
		</div>

		<!-- Your Sync ID section -->
		{#if detect?.device_id}
			<div class="rounded-[var(--radius-lg)] border border-[var(--border)] bg-[var(--bg-subtle)] p-4">
				<p class="text-xs font-semibold text-[var(--text-secondary)] uppercase tracking-wide mb-2">
					Your Sync ID
				</p>
				<div class="flex items-center gap-2">
					<code
						class="flex-1 px-3 py-2 text-xs font-mono rounded-[var(--radius)] border border-[var(--border)] bg-[var(--bg-base)] text-[var(--text-secondary)] truncate"
					>
						{detect.device_id}
					</code>
					<button
						onclick={copySelfId}
						aria-label="Copy your device ID to clipboard"
						class="shrink-0 p-2 rounded-[var(--radius)] border border-[var(--border)] bg-[var(--bg-base)] text-[var(--text-muted)] hover:text-[var(--text-primary)] hover:bg-[var(--bg-muted)] transition-colors"
					>
						{#if copiedSelfId}
							<CheckCircle size={14} class="text-[var(--success)]" />
							<span class="sr-only">Copied</span>
						{:else}
							<Copy size={14} />
						{/if}
					</button>
				</div>
				<p class="text-[11px] text-[var(--text-muted)] mt-1.5">
					Share this with teammates so they can add you to their team
				</p>
			</div>
		{/if}

		{#if loading}
			<!-- Skeleton -->
			<div class="space-y-3">
				{#each [1, 2, 3] as _}
					<div
						class="h-12 rounded-[var(--radius-lg)] bg-[var(--bg-muted)] animate-pulse"
						aria-hidden="true"
					></div>
				{/each}
			</div>
		{:else if error}
			<!-- Error state -->
			<div
				class="flex items-center gap-3 p-4 rounded-[var(--radius-lg)] border border-[var(--error)]/20 bg-[var(--error-subtle)] text-xs text-[var(--error)]"
			>
				<XCircle size={14} class="shrink-0" />
				<span class="flex-1">{error}</span>
				<button
					onclick={loadData}
					class="ml-auto underline hover:no-underline text-[var(--error)] font-medium"
				>
					Retry
				</button>
			</div>
		{:else if members.length === 0}
			<!-- Empty state -->
			<div
				class="py-10 flex flex-col items-center gap-3 text-center border border-dashed border-[var(--border)] rounded-[var(--radius-lg)]"
			>
				<Users size={28} class="text-[var(--text-muted)]" />
				<p class="text-sm font-medium text-[var(--text-secondary)]">No team members yet</p>
				<p class="text-xs text-[var(--text-muted)] max-w-[280px]">
					Add a teammate below using their Sync ID, or share yours so they can add you.
				</p>
			</div>

			<!-- Getting Started -->
			<div class="rounded-[var(--radius-lg)] border border-dashed border-[var(--accent)]/30 bg-[var(--accent)]/5 p-5 space-y-3">
				<div class="flex items-center gap-2">
					<Sparkles size={14} class="text-[var(--accent)]" />
					<h3 class="text-sm font-semibold text-[var(--text-primary)]">Getting Started</h3>
				</div>
				<ol class="space-y-2 ml-1">
					<li class="flex items-start gap-2.5">
						<span class="shrink-0 w-5 h-5 rounded-full bg-[var(--accent)]/10 text-[var(--accent)] text-xs font-semibold flex items-center justify-center mt-0.5">1</span>
						<div>
							<p class="text-sm font-medium text-[var(--text-primary)]">Add a teammate</p>
							<p class="text-xs text-[var(--text-muted)]">Paste their Sync ID in the form below</p>
						</div>
					</li>
					<li class="flex items-start gap-2.5">
						<span class="shrink-0 w-5 h-5 rounded-full bg-[var(--accent)]/10 text-[var(--accent)] text-xs font-semibold flex items-center justify-center mt-0.5">2</span>
						<div>
							<p class="text-sm font-medium text-[var(--text-primary)]">Enable project sync</p>
							<p class="text-xs text-[var(--text-muted)]">Switch to the Projects tab to choose which projects to sync</p>
						</div>
					</li>
					<li class="flex items-start gap-2.5">
						<span class="shrink-0 w-5 h-5 rounded-full bg-[var(--accent)]/10 text-[var(--accent)] text-xs font-semibold flex items-center justify-center mt-0.5">3</span>
						<div>
							<p class="text-sm font-medium text-[var(--text-primary)]">Start the sync engine</p>
							<p class="text-xs text-[var(--text-muted)]">Go to Overview and click Start to begin watching for changes</p>
						</div>
					</li>
				</ol>
			</div>
		{:else}
			<!-- Member list -->
			<div class="space-y-2">
				{#each members as member (member.device_id)}
					<div class="relative group">
						<DeviceCard device={member} />
						{#if !member.is_self}
							<!-- Remove button / confirm overlay -->
							{#if removeConfirmName === member.name}
								<div
									class="absolute top-1.5 right-1.5 flex items-center gap-1.5 bg-[var(--bg-base)] rounded-lg px-2.5 py-1.5 border border-[var(--border)] shadow-md z-10"
								>
									<span class="text-xs text-[var(--text-secondary)]">Remove?</span>
									<button
										onclick={() => removeMember(member.name)}
										disabled={removingMemberName === member.name}
										class="px-2.5 py-1 text-xs font-medium rounded-md bg-[var(--error)] text-white hover:opacity-90 transition-opacity disabled:opacity-50"
									>
										{removingMemberName === member.name ? '...' : 'Yes'}
									</button>
									<button
										onclick={() => (removeConfirmName = null)}
										class="px-2.5 py-1 text-xs font-medium rounded-md border border-[var(--border)] text-[var(--text-muted)] hover:text-[var(--text-primary)] transition-colors"
									>
										No
									</button>
								</div>
							{:else}
								<button
									onclick={() => (removeConfirmName = member.name)}
									aria-label="Remove member {member.name}"
									class="absolute top-2 right-2 opacity-0 group-hover:opacity-100 p-1.5 rounded-[var(--radius)] text-[var(--text-muted)] hover:text-[var(--error)] hover:bg-[var(--error-subtle)] transition-all"
								>
									<Trash2 size={14} />
								</button>
							{/if}
						{/if}
					</div>
				{/each}
			</div>
		{/if}

		<!-- Shared Projects -->
		{#if !loading && !error}
			<div class="mt-6">
				<div class="flex items-center justify-between mb-3">
					<h3 class="text-sm font-semibold text-[var(--text-primary)]">Shared Projects</h3>
					<span class="text-xs text-[var(--text-muted)]">{teamProjects.length} project{teamProjects.length !== 1 ? 's' : ''}</span>
				</div>

				{#if teamProjects.length === 0}
					<div class="py-6 flex flex-col items-center gap-2 text-center border border-dashed border-[var(--border)] rounded-[var(--radius-lg)]">
						<FolderGit2 size={24} class="text-[var(--text-muted)]" />
						<p class="text-xs text-[var(--text-muted)]">No projects synced with this team yet</p>
					</div>
				{:else}
					<div class="space-y-1.5">
						{#each teamProjects as project (project.encoded_name)}
							<div class="flex items-center justify-between gap-2 px-3 py-2 rounded-[var(--radius)] border border-[var(--border)] bg-[var(--bg-subtle)] group">
								<div class="flex items-center gap-2 min-w-0">
									<FolderGit2 size={14} class="shrink-0 text-[var(--text-muted)]" />
									<span class="text-sm text-[var(--text-primary)] truncate">{project.name || project.encoded_name}</span>
								</div>
								<button
									onclick={() => removeProjectFromTeam(project.encoded_name)}
									disabled={removingProject === project.encoded_name}
									aria-label="Remove project {project.name}"
									class="shrink-0 opacity-0 group-hover:opacity-100 p-1 rounded text-[var(--text-muted)] hover:text-[var(--error)] hover:bg-[var(--error-subtle)] transition-all disabled:opacity-50"
								>
									{#if removingProject === project.encoded_name}
										<Loader2 size={12} class="animate-spin" />
									{:else}
										<X size={12} />
									{/if}
								</button>
							</div>
						{/each}
					</div>
				{/if}

				<!-- Add project dropdown -->
				{#if availableProjects.length > 0}
					<div class="mt-3">
						<select
							onchange={(e) => {
								const target = e.target as HTMLSelectElement;
								if (target.value) {
									addProjectToTeam(target.value);
									target.value = '';
								}
							}}
							class="w-full px-3 py-2 text-sm rounded-[var(--radius)] border border-[var(--border)] bg-[var(--bg-base)] text-[var(--text-primary)] focus:outline-none focus:ring-2 focus:ring-[var(--accent)]/40 focus:border-[var(--accent)] transition-colors"
						>
							<option value="">+ Add project to team...</option>
							{#each availableProjects as project (project.encoded_name)}
								<option value={project.encoded_name}>{project.display_name ?? project.encoded_name}</option>
							{/each}
						</select>
					</div>
				{/if}
			</div>
		{/if}

		<!-- Add Member form -->
		<div class="mt-6">
			<h3 class="text-sm font-semibold text-[var(--text-primary)] mb-3">Add Member</h3>
			<div
				class="rounded-[var(--radius-lg)] border border-[var(--border)] bg-[var(--bg-subtle)] p-5 space-y-4"
			>
				<div class="grid grid-cols-1 gap-3 sm:grid-cols-2">
					<div class="space-y-1.5">
						<label for="new-member-device-id" class="block text-xs font-medium text-[var(--text-secondary)]">
							Sync ID
						</label>
						<input
							id="new-member-device-id"
							type="text"
							bind:value={newMemberDeviceId}
							placeholder="Paste their Sync ID here"
							class="w-full px-3 py-2 text-sm font-mono rounded-[var(--radius)] border border-[var(--border)] bg-[var(--bg-base)] text-[var(--text-primary)] placeholder:text-[var(--text-muted)] focus:outline-none focus:ring-2 focus:ring-[var(--accent)]/40 focus:border-[var(--accent)] transition-colors uppercase"
						/>
						<p class="text-[11px] text-[var(--text-muted)]">
							Ask your teammate to copy their Sync ID from their dashboard
						</p>
					</div>
					<div class="space-y-1.5">
						<label for="new-member-name" class="block text-xs font-medium text-[var(--text-secondary)]">
							Member Name
						</label>
						<input
							id="new-member-name"
							type="text"
							bind:value={newMemberName}
							placeholder="e.g. alice-laptop"
							class="w-full px-3 py-2 text-sm rounded-[var(--radius)] border border-[var(--border)] bg-[var(--bg-base)] text-[var(--text-primary)] placeholder:text-[var(--text-muted)] focus:outline-none focus:ring-2 focus:ring-[var(--accent)]/40 focus:border-[var(--accent)] transition-colors"
						/>
					</div>
				</div>

				{#if addError}
					<p class="text-xs text-[var(--error)]">{addError}</p>
				{/if}

				<button
					onclick={addMember}
					disabled={addingMember || !newMemberDeviceId.trim() || !teamName}
					class="flex items-center gap-2 px-4 py-2 text-sm font-medium rounded-[var(--radius)] bg-[var(--accent)] text-white hover:bg-[var(--accent-hover)] transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
				>
					{#if addingMember}
						<Loader2 size={14} class="animate-spin" />
						Adding...
					{:else}
						<Plus size={14} />
						Add Member
					{/if}
				</button>
			</div>
		</div>
	{/if}
</div>

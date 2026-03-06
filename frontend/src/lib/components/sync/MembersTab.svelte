<script lang="ts">
	import { Users, XCircle, Plus, Loader2, Trash2, CheckCircle2, Copy, CheckCircle } from 'lucide-svelte';
	import type { SyncDetect, SyncTeam, SyncTeamMember, SyncDevice } from '$lib/api-types';
	import { API_BASE } from '$lib/config';
	import DeviceCard from './DeviceCard.svelte';

	let {
		detect,
		active = false,
		teamName = null
	}: { detect: SyncDetect | null; active?: boolean; teamName: string | null } = $props();

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

	async function loadData() {
		loading = true;
		error = null;
		try {
			const [teamsRes, devicesRes] = await Promise.all([
				fetch(`${API_BASE}/sync/teams`),
				fetch(`${API_BASE}/sync/devices`)
			]);

			if (!teamsRes.ok) {
				error = 'Could not load team data.';
				return;
			}

			const teamsBody = await teamsRes.json();
			// API may return { teams: [...] } or a direct array
			teams = Array.isArray(teamsBody) ? teamsBody : (teamsBody.teams ?? []);

			if (devicesRes.ok) {
				const devicesBody = await devicesRes.json();
				const deviceList: SyncDevice[] = devicesBody.devices ?? [];
				deviceMap = new Map(deviceList.map((d) => [d.device_id, d]));
			}
		} catch {
			error = 'Cannot reach backend. Is the API running?';
		} finally {
			loading = false;
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
			loadData();
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
				class="py-12 flex flex-col items-center gap-3 text-center border border-dashed border-[var(--border)] rounded-[var(--radius-lg)]"
			>
				<Users size={28} class="text-[var(--text-muted)]" />
				<p class="text-sm text-[var(--text-muted)]">No team members yet</p>
				<p class="text-xs text-[var(--text-muted)] max-w-[240px]">
					Add a teammate's device ID below to start syncing with them
				</p>
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

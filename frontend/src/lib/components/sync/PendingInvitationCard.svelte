<script lang="ts">
	import { onMount, onDestroy } from 'svelte';
	import { Fingerprint, Loader2, X } from 'lucide-svelte';
	import { API_BASE } from '$lib/config';
	import { formatRelativeTime } from '$lib/utils';

	interface Invitation {
		device_id: string;
		team_name: string;
		leader_user_id: string;
		leader_machine_tag: string;
		leader_member_tag: string;
		projects: string[];
		time: string;
	}

	interface Props {
		onaccepted?: (teamNames: string[]) => void;
	}

	let { onaccepted }: Props = $props();

	// ── State ──────────────────────────────────────────────────────────────
	let invitations = $state<Invitation[]>([]);
	let loading = $state(true);
	let firstLoadDone = $state(false);
	let acceptingId = $state<string | null>(null);
	let dismissingId = $state<string | null>(null);

	// ── Correlation logic ──────────────────────────────────────────────────
	function buildInvitations(
		devices: { device_id: string; name: string; address: string; time: string }[],
		folders: { folder_id: string; label: string; from_device: string; from_member: string; offered_at: string; folder_type: string }[]
	): Invitation[] {
		const results: Invitation[] = [];
		const metaRegex = /^karma-meta--(.+)$/;
		const outRegex = /^karma-out--(.+?)--(.+)$/;
		const seenDevices = new Set<string>();

		// 1) Pending devices — may or may not have folders yet
		for (const device of devices) {
			seenDevices.add(device.device_id);
			const deviceFolders = folders.filter((f) => f.from_device === device.device_id);

			let teamName = '';
			for (const f of deviceFolders) {
				const match = f.folder_id.match(metaRegex);
				if (match) { teamName = match[1]; break; }
			}

			let leaderMemberTag = '';
			const projectSuffixes: string[] = [];
			for (const f of deviceFolders) {
				const match = f.folder_id.match(outRegex);
				if (match) {
					if (!leaderMemberTag) leaderMemberTag = match[1];
					projectSuffixes.push(match[2]);
				}
			}

			let leaderUserId = leaderMemberTag;
			let leaderMachineTag = '';
			const dotIdx = leaderMemberTag.indexOf('.');
			if (dotIdx > 0) {
				leaderUserId = leaderMemberTag.substring(0, dotIdx);
				leaderMachineTag = leaderMemberTag.substring(dotIdx + 1);
			}

			results.push({
				device_id: device.device_id,
				team_name: teamName || '',
				leader_user_id: leaderUserId || device.name.split('.')[0] || 'Unknown',
				leader_machine_tag: leaderMachineTag || device.name || '',
				leader_member_tag: leaderMemberTag || device.name || '',
				projects: projectSuffixes,
				time: device.time
			});
		}

		// 2) Pending folders from already-accepted devices (not in pending devices list).
		//    Group by from_device so we get one invitation per device.
		const orphanFoldersByDevice = new Map<string, typeof folders>();
		for (const f of folders) {
			if (!seenDevices.has(f.from_device)) {
				const arr = orphanFoldersByDevice.get(f.from_device) ?? [];
				arr.push(f);
				orphanFoldersByDevice.set(f.from_device, arr);
			}
		}

		for (const [deviceId, deviceFolders] of orphanFoldersByDevice) {
			let teamName = '';
			for (const f of deviceFolders) {
				const match = f.folder_id.match(metaRegex);
				if (match) { teamName = match[1]; break; }
			}

			let leaderMemberTag = '';
			const projectSuffixes: string[] = [];
			for (const f of deviceFolders) {
				const match = f.folder_id.match(outRegex);
				if (match) {
					if (!leaderMemberTag) leaderMemberTag = match[1];
					projectSuffixes.push(match[2]);
				}
			}

			let leaderUserId = leaderMemberTag;
			let leaderMachineTag = '';
			const dotIdx = leaderMemberTag.indexOf('.');
			if (dotIdx > 0) {
				leaderUserId = leaderMemberTag.substring(0, dotIdx);
				leaderMachineTag = leaderMemberTag.substring(dotIdx + 1);
			}

			results.push({
				device_id: deviceId,
				team_name: teamName || '',
				leader_user_id: leaderUserId || 'Unknown',
				leader_machine_tag: leaderMachineTag || '',
				leader_member_tag: leaderMemberTag || '',
				projects: projectSuffixes,
				time: deviceFolders[0]?.offered_at || ''
			});
		}

		return results;
	}

	// ── Fetching ───────────────────────────────────────────────────────────
	async function fetchPending() {
		try {
			const [devicesRes, foldersRes, teamsRes] = await Promise.all([
				fetch(`${API_BASE}/sync/pending-devices`).catch(() => null),
				fetch(`${API_BASE}/sync/pending`).catch(() => null),
				fetch(`${API_BASE}/sync/teams?include_dissolved=true`).catch(() => null)
			]);

			const devices = devicesRes?.ok ? (await devicesRes.json()).devices ?? [] : [];
			const folders = foldersRes?.ok ? (await foldersRes.json()).folders ?? [] : [];

			// Filter out invitations for teams we already know about locally.
			// After device acceptance, karma-out-- folders stay pending in Syncthing
			// and would otherwise appear as ghost invitations.
			const knownTeams = new Set<string>();
			if (teamsRes?.ok) {
				const teams = (await teamsRes.json()).teams ?? [];
				for (const t of teams) {
					knownTeams.add(t.name);
				}
			}

			invitations = buildInvitations(devices, folders)
				.filter(inv => !inv.team_name || !knownTeams.has(inv.team_name));
		} catch {
			// Non-critical — silently ignore
		} finally {
			loading = false;
			firstLoadDone = true;
		}
	}

	// ── Accept flow ────────────────────────────────────────────────────────
	async function acceptInvitation(inv: Invitation) {
		acceptingId = inv.device_id;
		try {
			let acceptedTeams: string[] = [];

			// Try accepting as a pending device first (auto-accepts karma-meta-- folders)
			const devRes = await fetch(`${API_BASE}/sync/pending-devices/${encodeURIComponent(inv.device_id)}/accept`, {
				method: 'POST',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify({ name: '' })
			});

			if (devRes.ok) {
				const data = await devRes.json();
				acceptedTeams = data.teams ?? (inv.team_name ? [inv.team_name] : []);
			} else if (inv.team_name) {
				// Device already accepted — accept the pending meta folder directly
				const folderId = `karma-meta--${inv.team_name}`;
				const folderRes = await fetch(`${API_BASE}/sync/pending/accept/${encodeURIComponent(folderId)}`, {
					method: 'POST',
					headers: { 'Content-Type': 'application/json' }
				});
				if (folderRes.ok) {
					acceptedTeams = [inv.team_name];
				}
			}

			// Poll for team to appear — reconciliation may need multiple cycles
			// to accept the pending metadata folder and bootstrap the team record
			const teamName = acceptedTeams[0] ?? inv.team_name;
			if (teamName) {
				let teamFound = false;
				for (let attempt = 0; attempt < 4; attempt++) {
					// Trigger reconciliation (accepts pending folders + bootstraps team)
					await fetch(`${API_BASE}/sync/reconcile`, { method: 'POST' }).catch(() => {});

					// Check if team exists now
					const teamRes = await fetch(`${API_BASE}/sync/teams/${encodeURIComponent(teamName)}`).catch(() => null);
					if (teamRes?.ok) {
						teamFound = true;
						break;
					}

					// Wait 3s before next attempt
					if (attempt < 3) {
						await new Promise(r => setTimeout(r, 3000));
					}
				}

				if (teamFound) {
					onaccepted?.([teamName]);
				}
			}

			await fetchPending();
		} catch {
			// Silently handle
		} finally {
			acceptingId = null;
		}
	}

	// ── Dismiss flow ───────────────────────────────────────────────────────
	async function dismissInvitation(inv: Invitation) {
		dismissingId = inv.device_id;
		try {
			await fetch(`${API_BASE}/sync/pending-devices/${encodeURIComponent(inv.device_id)}`, {
				method: 'DELETE'
			});
			await fetchPending();
		} catch {
			// Silently handle
		} finally {
			dismissingId = null;
		}
	}

	// ── Truncate device ID for display ─────────────────────────────────────
	function truncateDeviceId(id: string): string {
		if (id.length <= 12) return id;
		return id.substring(0, 7) + '...' + id.substring(id.length - 4);
	}

	// ── Polling: load on mount, re-poll every 15s ──────────────────────────
	let pollInterval: ReturnType<typeof setInterval> | null = null;

	onMount(() => {
		fetchPending();
		pollInterval = setInterval(fetchPending, 15_000);
	});

	onDestroy(() => {
		if (pollInterval) clearInterval(pollInterval);
	});
</script>

{#if loading && !firstLoadDone}
	<!-- Skeleton loading state -->
	<div class="rounded-[var(--radius-lg)] border border-[var(--border)] bg-[var(--bg-subtle)] p-5">
		<div class="flex items-center gap-3 mb-4">
			<div class="w-10 h-10 rounded-full bg-[var(--bg-muted)] animate-pulse"></div>
			<div class="flex-1 space-y-2">
				<div class="h-4 w-48 rounded bg-[var(--bg-muted)] animate-pulse"></div>
				<div class="h-3 w-36 rounded bg-[var(--bg-muted)] animate-pulse"></div>
			</div>
		</div>
		<div class="space-y-2">
			<div class="h-3 w-full rounded bg-[var(--bg-muted)] animate-pulse"></div>
			<div class="h-3 w-3/4 rounded bg-[var(--bg-muted)] animate-pulse"></div>
		</div>
	</div>
{:else if invitations.length > 0}
	{#each invitations as inv (inv.device_id)}
		{@const isAccepting = acceptingId === inv.device_id}
		{@const isDismissing = dismissingId === inv.device_id}
		{@const isBusy = isAccepting || isDismissing}
		{@const visibleProjects = inv.projects.slice(0, 2)}
		{@const extraCount = inv.projects.length - 2}

		<div class="rounded-[var(--radius-lg)] border border-[var(--accent)]/30 bg-[var(--bg-subtle)]">
			<!-- Header: avatar + title + badge -->
			<div class="flex items-start gap-3.5 px-5 pt-5 pb-3">
				<!-- Avatar circle with first letter of user_id -->
				<div
					class="flex items-center justify-center w-10 h-10 rounded-full shrink-0 bg-[var(--accent)]/15 text-[var(--accent)] font-semibold text-sm uppercase"
				>
					{inv.leader_user_id.charAt(0) || '?'}
				</div>

				<div class="flex-1 min-w-0">
					<div class="flex items-center gap-2">
						<h3 class="text-sm font-semibold text-[var(--text-primary)] truncate">
							{inv.team_name ? `Team invitation — ${inv.team_name}` : 'Device pairing request'}
						</h3>
						<span
							class="shrink-0 px-2 py-0.5 text-[10px] font-medium rounded-full bg-[var(--warning)]/10 text-[var(--warning)] border border-[var(--warning)]/20"
						>
							pending
						</span>
					</div>
					<p class="text-xs text-[var(--text-muted)] mt-0.5">
						<span class="font-mono text-[var(--text-secondary)]">{inv.leader_member_tag || inv.leader_user_id}</span>
						{inv.team_name ? 'wants to sync' : 'wants to connect'}
					</p>
				</div>
			</div>

			<!-- Details -->
			<div class="px-5 pb-4">
				<div class="space-y-2.5 text-xs">
					<div class="flex items-center justify-between">
						<span class="text-[var(--text-muted)] font-medium">Device</span>
						<span class="font-mono text-[var(--text-secondary)]">{truncateDeviceId(inv.device_id)}</span>
					</div>
					<div class="flex items-center justify-between">
						<span class="text-[var(--text-muted)] font-medium">Requested</span>
						<span class="text-[var(--text-secondary)]">{inv.time ? formatRelativeTime(inv.time) : 'Just now'}</span>
					</div>

					{#if inv.projects.length > 0}
						<div class="border-t border-[var(--border-subtle)] pt-2.5">
							<div class="flex items-center gap-2 flex-wrap">
								<span class="text-[var(--text-muted)] font-medium shrink-0">Projects</span>
								{#each visibleProjects as proj (proj)}
									<span class="px-2 py-0.5 text-[11px] font-medium rounded-[var(--radius)] bg-[var(--bg-muted)] text-[var(--text-secondary)] border border-[var(--border-subtle)]">
										{proj}
									</span>
								{/each}
								{#if extraCount > 0}
									<span class="px-2 py-0.5 text-[11px] font-medium rounded-[var(--radius)] bg-[var(--bg-muted)] text-[var(--text-muted)] border border-[var(--border-subtle)]">
										+{extraCount}
									</span>
								{/if}
							</div>
						</div>
					{/if}
				</div>

				<!-- Info note -->
				<div class="flex items-start gap-2 mt-4 p-3 rounded-[var(--radius)] bg-[var(--bg-muted)] border border-[var(--border-subtle)]">
					<Fingerprint size={14} class="shrink-0 text-[var(--accent)] mt-0.5" />
					<p class="text-[11px] text-[var(--text-muted)] leading-relaxed">
						Accepting pairs this device and syncs team metadata. You'll then choose which projects to accept on the team page.
					</p>
				</div>

				<!-- Actions -->
				<div class="flex items-center gap-2.5 mt-4">
					<button
						onclick={() => acceptInvitation(inv)}
						disabled={isBusy}
						class="flex-1 flex items-center justify-center gap-2 px-4 py-2.5 text-sm font-medium rounded-[var(--radius)] bg-[var(--accent)] text-white hover:bg-[var(--accent-hover)] transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
					>
						{#if isAccepting}
							<Loader2 size={14} class="animate-spin" />
							Accepting...
						{:else}
							Accept & Pair
						{/if}
					</button>
					<button
						onclick={() => dismissInvitation(inv)}
						disabled={isBusy}
						class="flex items-center justify-center gap-1.5 px-4 py-2.5 text-sm font-medium rounded-[var(--radius)] border border-[var(--border)] text-[var(--text-muted)] hover:text-[var(--text-primary)] hover:border-[var(--text-muted)] transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
					>
						{#if isDismissing}
							<Loader2 size={14} class="animate-spin" />
						{:else}
							<X size={14} />
						{/if}
						Dismiss
					</button>
				</div>
			</div>
		</div>
	{/each}
{/if}

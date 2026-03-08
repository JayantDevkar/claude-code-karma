<script lang="ts">
	import Modal from '$lib/components/ui/Modal.svelte';
	import JoinCodeCard from './JoinCodeCard.svelte';
	import { API_BASE } from '$lib/config';
	import { goto } from '$app/navigation';
	import { parseJoinCode } from '$lib/utils/join-code';
	import { Loader2, CheckCircle2 } from 'lucide-svelte';
	import type { JoinTeamResponse } from '$lib/api-types';

	let {
		open = $bindable(false),
		onjoined
	}: {
		open?: boolean;
		onjoined?: (result: JoinTeamResponse) => void;
	} = $props();

	let joinCode = $state('');
	let loading = $state(false);
	let error = $state<string | null>(null);
	let joinResult = $state<JoinTeamResponse | null>(null);

	// Live-parse the join code as user types
	let parsed = $derived.by(() => {
		const result = parseJoinCode(joinCode);
		if (!result) return null;
		return { team: result.team, user: result.user, device: result.device.slice(0, 20) + '...' };
	});

	async function handleJoin() {
		if (!joinCode.trim() || loading) return;
		loading = true;
		error = null;

		try {
			const res = await fetch(`${API_BASE}/sync/teams/join`, {
				method: 'POST',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify({ join_code: joinCode.trim() })
			});

			if (!res.ok) {
				const data = await res.json().catch(() => ({}));
				error = data.detail || `Failed to join team (${res.status})`;
				return;
			}

			const result: JoinTeamResponse = await res.json();
			joinResult = result;
			onjoined?.(result);
		} catch (e) {
			error = e instanceof Error ? e.message : 'Network error';
		} finally {
			loading = false;
		}
	}

	function handleClose() {
		open = false;
		joinCode = '';
		error = null;
		joinResult = null;
	}

	function handleGoToTeam() {
		const name = joinResult?.team_name;
		handleClose();
		if (name) goto(`/team/${encodeURIComponent(name)}`);
	}
</script>

<Modal bind:open title={joinResult ? `Joined "${joinResult.team_name}"!` : 'Join Team'} onOpenChange={(v) => { if (!v) handleClose(); }}>
	{#snippet children()}
		{#if joinResult}
			<!-- Success state -->
			<div class="space-y-4">
				<div class="flex items-center gap-3 p-4 rounded-lg bg-[var(--success)]/10 border border-[var(--success)]/20">
					<CheckCircle2 size={20} class="text-[var(--success)] shrink-0" />
					<div class="text-sm">
						<p class="font-medium text-[var(--text-primary)]">Connected to {joinResult.leader_name}'s team</p>
						<p class="text-[var(--text-secondary)] mt-0.5">
							{joinResult.paired ? 'Syncthing paired successfully.' : 'Syncthing pairing pending.'}
							{#if joinResult.accepted_folders > 0}
								Accepted {joinResult.accepted_folders} shared folder{joinResult.accepted_folders > 1 ? 's' : ''}.
							{/if}
						</p>
					</div>
				</div>

				{#if joinResult.your_join_code}
					<JoinCodeCard
						code={joinResult.your_join_code}
						label="Share YOUR code back with {joinResult.leader_name}:"
					/>
				{/if}
			</div>
		{:else}
			<!-- Input state -->
			<div class="space-y-4">
				<div class="space-y-1.5">
					<label for="join-code" class="block text-xs font-medium text-[var(--text-secondary)]">
						Paste the join code from your team creator.
						<span class="text-[var(--text-muted)]">The team must already exist locally — create it on the Teams page first.</span>
					</label>
					<textarea
						id="join-code"
						bind:value={joinCode}
						placeholder="acme:alice:MFZWI3D-BONSGYC-YLTMRWG-..."
						rows={2}
						class="w-full px-3 py-2 text-sm font-mono rounded-[var(--radius-md)] border border-[var(--border)]
							bg-[var(--bg-base)] text-[var(--text-primary)] placeholder:text-[var(--text-muted)]
							focus:outline-none focus:ring-2 focus:ring-[var(--accent)]/40 focus:border-[var(--accent)]
							transition-colors resize-none"
					></textarea>
				</div>

				{#if parsed}
					<div class="p-3 rounded-lg bg-[var(--bg-subtle)] border border-[var(--border)] space-y-1.5">
						<p class="text-[11px] font-medium uppercase tracking-wider text-[var(--text-muted)]">Detected</p>
						<div class="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 text-sm">
							<span class="text-[var(--text-muted)]">Team</span>
							<span class="font-medium text-[var(--text-primary)]">{parsed.team}</span>
							<span class="text-[var(--text-muted)]">Leader</span>
							<span class="font-medium text-[var(--text-primary)]">{parsed.user}</span>
							<span class="text-[var(--text-muted)]">Device</span>
							<span class="font-mono text-xs text-[var(--text-secondary)]">{parsed.device}</span>
						</div>
					</div>
				{/if}

				{#if error}
					<p class="text-xs text-[var(--error)]">{error}</p>
				{/if}
			</div>
		{/if}
	{/snippet}

	{#snippet footer()}
		{#if joinResult}
			<button
				onclick={handleGoToTeam}
				class="px-4 py-2 text-sm font-medium rounded-[var(--radius-md)] bg-[var(--accent)] text-white
					hover:bg-[var(--accent-hover)] transition-colors"
			>
				Go to Team Page
			</button>
		{:else}
			<button
				onclick={handleClose}
				class="px-4 py-2 text-sm font-medium rounded-[var(--radius-md)] text-[var(--text-secondary)]
					hover:bg-[var(--bg-muted)] transition-colors"
			>
				Cancel
			</button>
			<button
				onclick={handleJoin}
				disabled={!joinCode.trim() || loading}
				class="px-4 py-2 text-sm font-medium rounded-[var(--radius-md)] bg-[var(--accent)] text-white
					hover:bg-[var(--accent-hover)] transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
			>
				{#if loading}
					<span class="flex items-center gap-2">
						<Loader2 size={14} class="animate-spin" />
						Joining...
					</span>
				{:else}
					Join Team
				{/if}
			</button>
		{/if}
	{/snippet}
</Modal>

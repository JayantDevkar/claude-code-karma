<script lang="ts">
	import Modal from '$lib/components/ui/Modal.svelte';
	import { API_BASE } from '$lib/config';
	import { Loader2 } from 'lucide-svelte';

	let {
		open = $bindable(false),
		oncreated
	}: {
		open?: boolean;
		oncreated?: (teamName: string) => void;
	} = $props();

	let teamName = $state('');
	let loading = $state(false);
	let error = $state<string | null>(null);

	let isValid = $derived(/^[a-zA-Z0-9_-]+$/.test(teamName) && teamName.length <= 64);

	async function handleCreate() {
		if (!isValid || loading) return;
		loading = true;
		error = null;

		try {
			const res = await fetch(`${API_BASE}/sync/teams`, {
				method: 'POST',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify({ name: teamName, backend: 'syncthing' })
			});

			if (!res.ok) {
				const data = await res.json().catch(() => ({}));
				error = data.detail || `Failed to create team (${res.status})`;
				return;
			}

			const createdName = teamName;
			open = false;
			teamName = '';
			oncreated?.(createdName);
		} catch (e) {
			error = e instanceof Error ? e.message : 'Network error';
		} finally {
			loading = false;
		}
	}
</script>

<Modal bind:open title="Create Team" description="Create a new team to start sharing sessions with teammates.">
	{#snippet children()}
		<div class="space-y-4">
			<div class="space-y-1.5">
				<label for="team-name" class="block text-xs font-medium text-[var(--text-secondary)]">
					Team Name
				</label>
				<input
					id="team-name"
					type="text"
					bind:value={teamName}
					placeholder="my-team"
					class="w-full px-3 py-2 text-sm rounded-[var(--radius-md)] border border-[var(--border)]
						bg-[var(--bg-base)] text-[var(--text-primary)] placeholder:text-[var(--text-muted)]
						focus:outline-none focus:ring-2 focus:ring-[var(--accent)]/40 focus:border-[var(--accent)]
						transition-colors"
					onkeydown={(e) => e.key === 'Enter' && handleCreate()}
				/>
				<p class="text-[11px] text-[var(--text-muted)]">
					Letters, numbers, dashes, underscores. Shared with teammates.
				</p>
			</div>

			{#if error}
				<p class="text-xs text-[var(--error)]">{error}</p>
			{/if}
		</div>
	{/snippet}

	{#snippet footer()}
		<button
			onclick={() => (open = false)}
			class="px-4 py-2 text-sm font-medium rounded-[var(--radius-md)] text-[var(--text-secondary)]
				hover:bg-[var(--bg-muted)] transition-colors"
		>
			Cancel
		</button>
		<button
			onclick={handleCreate}
			disabled={!isValid || loading}
			class="px-4 py-2 text-sm font-medium rounded-[var(--radius-md)] bg-[var(--accent)] text-white
				hover:bg-[var(--accent-hover)] transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
		>
			{#if loading}
				<span class="flex items-center gap-2">
					<Loader2 size={14} class="animate-spin" />
					Creating...
				</span>
			{:else}
				Create
			{/if}
		</button>
	{/snippet}
</Modal>

<script lang="ts">
	import { API_BASE } from '$lib/config';
	import { Loader2, UserPlus, Radio } from 'lucide-svelte';
	import type { PendingDevice } from '$lib/api-types';

	let {
		device,
		teamName,
		onaccepted
	}: {
		device: PendingDevice;
		teamName: string;
		onaccepted?: () => void;
	} = $props();

	let memberName = $state('');
	let loading = $state(false);
	let error = $state<string | null>(null);

	let isValid = $derived(/^[a-zA-Z0-9_-]+$/.test(memberName) && memberName.length > 0);

	async function handleAccept() {
		if (!isValid || loading) return;
		loading = true;
		error = null;

		try {
			const res = await fetch(`${API_BASE}/sync/teams/${encodeURIComponent(teamName)}/members`, {
				method: 'POST',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify({ name: memberName, device_id: device.device_id })
			});

			if (!res.ok) {
				const data = await res.json().catch(() => ({}));
				error = data.detail || `Failed to accept device (${res.status})`;
				return;
			}

			onaccepted?.();
		} catch (e) {
			error = e instanceof Error ? e.message : 'Network error';
		} finally {
			loading = false;
		}
	}
</script>

<div class="p-4 rounded-lg border border-[var(--warning)]/20 bg-[var(--warning)]/5">
	<div class="flex items-start gap-3">
		<div class="mt-0.5">
			<Radio size={16} class="text-[var(--warning)]" />
		</div>
		<div class="flex-1 space-y-3">
			<div>
				<p class="text-sm font-medium text-[var(--text-primary)]">New device trying to connect</p>
				<p class="text-xs font-mono text-[var(--text-muted)] mt-0.5">
					{device.device_id.slice(0, 24)}...
				</p>
			</div>

			<div class="flex items-end gap-2">
				<div class="flex-1 space-y-1">
					<label
						for="member-name-{device.device_id}"
						class="block text-xs font-medium text-[var(--text-secondary)]"
					>
						Name
					</label>
					<input
						id="member-name-{device.device_id}"
						type="text"
						bind:value={memberName}
						placeholder="bob"
						class="w-full px-3 py-1.5 text-sm rounded-[var(--radius)] border border-[var(--border)]
							bg-[var(--bg-base)] text-[var(--text-primary)] placeholder:text-[var(--text-muted)]
							focus:outline-none focus:ring-2 focus:ring-[var(--accent)]/40 focus:border-[var(--accent)]
							transition-colors"
						onkeydown={(e) => e.key === 'Enter' && handleAccept()}
					/>
				</div>
				<button
					onclick={handleAccept}
					disabled={!isValid || loading}
					class="flex items-center gap-1.5 px-3 py-1.5 text-sm font-medium rounded-[var(--radius)]
						bg-[var(--accent)] text-white hover:bg-[var(--accent-hover)] transition-colors
						disabled:opacity-50 disabled:cursor-not-allowed shrink-0"
				>
					{#if loading}
						<Loader2 size={14} class="animate-spin" />
					{:else}
						<UserPlus size={14} />
					{/if}
					Accept
				</button>
			</div>

			{#if error}
				<p class="text-xs text-[var(--error)]">{error}</p>
			{/if}
		</div>
	</div>
</div>

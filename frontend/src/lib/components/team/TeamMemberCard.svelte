<script lang="ts">
	import { API_BASE } from '$lib/config';
	import { Trash2, Loader2, Wifi, WifiOff } from 'lucide-svelte';
	import type { SyncTeamMember, SyncDevice } from '$lib/api-types';

	let {
		member,
		teamName,
		devices = [],
		isSelf = false,
		onremoved
	}: {
		member: SyncTeamMember;
		teamName: string;
		devices?: SyncDevice[];
		isSelf?: boolean;
		onremoved?: () => void;
	} = $props();

	let confirmRemove = $state(false);
	let removing = $state(false);

	// Display name: prefer user_id, then name (v3 compat), then member_tag
	let displayName = $derived(member.user_id || member.name || member.member_tag);

	// Enrich with live device connection data
	let deviceInfo = $derived(devices.find((d) => d.device_id === member.device_id));
	let isConnected = $derived(deviceInfo?.connected ?? member.connected ?? false);

	async function handleRemove() {
		if (removing) return;
		removing = true;

		try {
			const tag = member.member_tag || member.name || '';
			const res = await fetch(
				`${API_BASE}/sync/teams/${encodeURIComponent(teamName)}/members/${encodeURIComponent(tag)}`,
				{ method: 'DELETE' }
			);

			if (res.ok) {
				onremoved?.();
			}
		} catch {
			// best-effort
		} finally {
			removing = false;
			confirmRemove = false;
		}
	}
</script>

<div
	class="flex items-center justify-between p-3 rounded-lg border border-[var(--border)] bg-[var(--bg-base)]"
>
	<div class="flex items-center gap-3">
		<div
			class="w-8 h-8 rounded-full flex items-center justify-center text-xs font-semibold
				{isConnected || isSelf
				? 'bg-[var(--success)]/10 text-[var(--success)]'
				: 'bg-[var(--bg-muted)] text-[var(--text-muted)]'}"
		>
			{displayName.charAt(0).toUpperCase()}
		</div>
		<div>
			<div class="flex items-center gap-2">
				<a
					href="/members/{encodeURIComponent(member.member_tag || member.device_id)}"
					class="text-sm font-medium text-[var(--text-primary)] hover:text-[var(--accent)] transition-colors"
				>
					{displayName}
					{#if isSelf}
						<span class="text-xs text-[var(--text-muted)]">(you)</span>
					{/if}
				</a>
				<span
					class="flex items-center gap-1 text-xs {isConnected || isSelf
						? 'text-[var(--success)]'
						: 'text-[var(--text-muted)]'}"
				>
					{#if isConnected || isSelf}
						<Wifi size={12} />
						Online
					{:else}
						<WifiOff size={12} />
						Offline
					{/if}
				</span>
			</div>
			{#if member.device_id}
				<p class="text-[11px] font-mono text-[var(--text-muted)]">
					{member.device_id.length > 20 ? member.device_id.slice(0, 20) + '...' : member.device_id}
				</p>
			{/if}
		</div>
	</div>

	{#if !isSelf}
		<div class="shrink-0">
			{#if confirmRemove}
				<div class="flex items-center gap-1.5">
					<button
						onclick={handleRemove}
						disabled={removing}
						class="px-2 py-1 text-xs font-medium rounded bg-[var(--error)] text-white hover:bg-[var(--error)]/80 transition-colors disabled:opacity-50"
					>
						{#if removing}
							<Loader2 size={12} class="animate-spin" />
						{:else}
							Remove
						{/if}
					</button>
					<button
						onclick={() => (confirmRemove = false)}
						class="px-2 py-1 text-xs rounded text-[var(--text-muted)] hover:bg-[var(--bg-muted)] transition-colors"
					>
						Cancel
					</button>
				</div>
			{:else}
				<button
					onclick={() => (confirmRemove = true)}
					class="p-1.5 rounded text-[var(--text-muted)] hover:text-[var(--error)] hover:bg-[var(--error)]/10 transition-colors"
					title="Remove member"
					aria-label="Remove member {displayName}"
				>
					<Trash2 size={14} />
				</button>
			{/if}
		</div>
	{/if}
</div>

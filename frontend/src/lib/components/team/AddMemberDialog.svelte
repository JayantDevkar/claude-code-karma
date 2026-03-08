<script lang="ts">
	import Modal from '$lib/components/ui/Modal.svelte';
	import { API_BASE } from '$lib/config';
	import { parseJoinCode } from '$lib/utils/join-code';
	import { Loader2 } from 'lucide-svelte';

	let {
		open = $bindable(false),
		teamName,
		onadded
	}: {
		open?: boolean;
		teamName: string;
		onadded?: () => void;
	} = $props();

	let joinCode = $state('');
	let manualName = $state('');
	let manualDeviceId = $state('');
	let loading = $state(false);
	let error = $state<string | null>(null);

	// Auto-parse join code into name + device_id
	let parsed = $derived.by(() => {
		const result = parseJoinCode(joinCode);
		if (!result) return null;
		return { name: result.user, device_id: result.device };
	});

	// Use parsed values if available, else manual
	let effectiveName = $derived(parsed?.name || manualName);
	let effectiveDeviceId = $derived(parsed?.device_id || manualDeviceId);

	let isValid = $derived(
		/^[a-zA-Z0-9_-]+$/.test(effectiveName) &&
			effectiveName.length > 0 &&
			/^[A-Z0-9-]+$/.test(effectiveDeviceId) &&
			effectiveDeviceId.length > 0
	);

	async function handleAdd() {
		if (!isValid || loading) return;
		loading = true;
		error = null;

		try {
			const res = await fetch(
				`${API_BASE}/sync/teams/${encodeURIComponent(teamName)}/members`,
				{
					method: 'POST',
					headers: { 'Content-Type': 'application/json' },
					body: JSON.stringify({ name: effectiveName, device_id: effectiveDeviceId })
				}
			);

			if (!res.ok) {
				const data = await res.json().catch(() => ({}));
				error = data.detail || `Failed to add member (${res.status})`;
				return;
			}

			open = false;
			joinCode = '';
			manualName = '';
			manualDeviceId = '';
			onadded?.();
		} catch (e) {
			error = e instanceof Error ? e.message : 'Network error';
		} finally {
			loading = false;
		}
	}
</script>

<Modal bind:open title="Add Team Member">
	{#snippet children()}
		<div class="space-y-4">
			<div class="space-y-1.5">
				<label for="member-join-code" class="block text-xs font-medium text-[var(--text-secondary)]">
					Paste their join code
				</label>
				<textarea
					id="member-join-code"
					bind:value={joinCode}
					placeholder="acme:bob:DEF456-GHI789-..."
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
						<span class="text-[var(--text-muted)]">Name</span>
						<span class="font-medium text-[var(--text-primary)]">{parsed.name}</span>
						<span class="text-[var(--text-muted)]">Device</span>
						<span class="font-mono text-xs text-[var(--text-secondary)]">{parsed.device_id.length > 20 ? parsed.device_id.slice(0, 20) + '...' : parsed.device_id}</span>
					</div>
				</div>
			{/if}

			<div class="flex items-center gap-3">
				<div class="flex-1 h-px bg-[var(--border)]"></div>
				<span class="text-xs text-[var(--text-muted)]">or enter manually</span>
				<div class="flex-1 h-px bg-[var(--border)]"></div>
			</div>

			<div class="grid grid-cols-1 gap-3 sm:grid-cols-2">
				<div class="space-y-1.5">
					<label for="manual-name" class="block text-xs font-medium text-[var(--text-secondary)]">Name</label>
					<input
						id="manual-name"
						type="text"
						bind:value={manualName}
						placeholder="bob"
						disabled={!!parsed}
						class="w-full px-3 py-2 text-sm rounded-[var(--radius-md)] border border-[var(--border)]
							bg-[var(--bg-base)] text-[var(--text-primary)] placeholder:text-[var(--text-muted)]
							focus:outline-none focus:ring-2 focus:ring-[var(--accent)]/40 focus:border-[var(--accent)]
							transition-colors disabled:opacity-50"
					/>
				</div>
				<div class="space-y-1.5">
					<label for="manual-device" class="block text-xs font-medium text-[var(--text-secondary)]">Device ID</label>
					<input
						id="manual-device"
						type="text"
						bind:value={manualDeviceId}
						placeholder="DEF456-GHI789-..."
						disabled={!!parsed}
						class="w-full px-3 py-2 text-sm font-mono rounded-[var(--radius-md)] border border-[var(--border)]
							bg-[var(--bg-base)] text-[var(--text-primary)] placeholder:text-[var(--text-muted)]
							focus:outline-none focus:ring-2 focus:ring-[var(--accent)]/40 focus:border-[var(--accent)]
							transition-colors disabled:opacity-50"
					/>
				</div>
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
			onclick={handleAdd}
			disabled={!isValid || loading}
			class="px-4 py-2 text-sm font-medium rounded-[var(--radius-md)] bg-[var(--accent)] text-white
				hover:bg-[var(--accent-hover)] transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
		>
			{#if loading}
				<span class="flex items-center gap-2">
					<Loader2 size={14} class="animate-spin" />
					Adding...
				</span>
			{:else}
				Add Member
			{/if}
		</button>
	{/snippet}
</Modal>

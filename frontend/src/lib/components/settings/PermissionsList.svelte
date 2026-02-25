<script lang="ts">
	import { X, Plus } from 'lucide-svelte';
	import TextInput from '$lib/components/ui/TextInput.svelte';

	interface Props {
		permissions?: string[];
		disabled?: boolean;
		onAdd?: (permission: string) => void;
		onRemove?: (permission: string) => void;
	}

	let { permissions = [], disabled = false, onAdd, onRemove }: Props = $props();

	let newPermission = $state('');

	function handleAdd() {
		const trimmed = newPermission.trim();
		if (trimmed && !permissions.includes(trimmed)) {
			onAdd?.(trimmed);
			newPermission = '';
		}
	}

	function handleRemove(perm: string) {
		onRemove?.(perm);
	}

	function handleKeydown(e: KeyboardEvent) {
		if (e.key === 'Enter') {
			e.preventDefault();
			handleAdd();
		}
	}
</script>

<div class="space-y-3 w-full">
	<!-- Permission List -->
	{#if permissions.length > 0}
		<div class="flex flex-wrap gap-2">
			{#each permissions as perm}
				<div
					class="
						inline-flex items-center gap-1.5 px-2.5 py-1
						bg-[var(--bg-muted)] border border-[var(--border)] rounded-md
						text-xs font-mono text-[var(--text-secondary)]
					"
				>
					<span class="max-w-[200px] truncate" title={perm}>{perm}</span>
					{#if !disabled}
						<button
							onclick={() => handleRemove(perm)}
							class="hover:text-red-500 transition-colors p-0.5 -mr-0.5"
							title="Remove permission"
						>
							<X size={12} />
						</button>
					{/if}
				</div>
			{/each}
		</div>
	{:else}
		<p class="text-sm text-[var(--text-muted)] italic">No permissions configured</p>
	{/if}

	<!-- Add New -->
	{#if !disabled}
		<div class="flex gap-2">
			<TextInput
				bind:value={newPermission}
				placeholder="mcp__server__tool"
				onkeydown={handleKeydown}
				class="flex-1 font-mono text-xs"
			/>
			<button
				onclick={handleAdd}
				disabled={!newPermission.trim()}
				class="
					px-3 py-2 bg-[var(--accent)] text-white rounded-md text-sm font-medium
					hover:opacity-90 disabled:opacity-50 disabled:cursor-not-allowed
					transition-opacity flex items-center gap-1.5
				"
			>
				<Plus size={14} />
				Add
			</button>
		</div>
	{/if}
</div>

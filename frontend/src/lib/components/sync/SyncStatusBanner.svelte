<script lang="ts">
	import { ExternalLink } from 'lucide-svelte';

	let {
		running = false,
		syncthingUp = false
	}: {
		running: boolean;
		syncthingUp: boolean;
	} = $props();
</script>

{#if running}
	<div
		class="flex items-center gap-3 px-4 py-3 rounded-[var(--radius-lg)] border border-[var(--success)]/30 bg-[var(--status-active-bg)]"
	>
		<span
			class="w-2 h-2 rounded-full bg-[var(--success)] shrink-0"
			aria-hidden="true"
		></span>
		<span class="text-sm font-medium text-[var(--text-primary)] flex-1">Sync active</span>
		<a
			href="/sync"
			class="flex items-center gap-1 text-xs font-medium text-[var(--accent)] hover:text-[var(--accent-hover)] transition-colors"
		>
			Manage
			<ExternalLink size={12} />
		</a>
	</div>
{:else}
	<div
		class="flex items-center gap-3 px-4 py-3 rounded-[var(--radius-lg)] border border-[var(--warning)]/30 bg-[var(--status-idle-bg)]"
	>
		<span
			class="w-2 h-2 rounded-full bg-[var(--warning)] shrink-0"
			aria-hidden="true"
		></span>
		<span class="text-sm font-medium text-[var(--text-primary)] flex-1">
			{syncthingUp ? 'Session watcher paused' : 'Syncthing not running'}
		</span>
		<a
			href="/sync"
			class="flex items-center gap-1 text-xs font-medium text-[var(--accent)] hover:text-[var(--accent-hover)] transition-colors"
		>
			Start sync
			<ExternalLink size={12} />
		</a>
	</div>
{/if}

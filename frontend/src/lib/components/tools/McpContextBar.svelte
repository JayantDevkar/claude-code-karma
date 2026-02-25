<script lang="ts">
	interface Props {
		mainCalls: number;
		subagentCalls: number;
		compact?: boolean;
	}

	let { mainCalls, subagentCalls, compact = false }: Props = $props();

	let total = $derived(mainCalls + subagentCalls);
	let mainPct = $derived(total > 0 ? Math.round((mainCalls / total) * 100) : 0);
	let subPct = $derived(total > 0 ? 100 - mainPct : 0);
</script>

{#if total > 0}
	<div
		class="flex items-center gap-2 {compact
			? 'text-[10px]'
			: 'text-xs'} text-[var(--text-muted)]"
	>
		<span class="inline-block w-2 h-2 rounded-full" style="background-color: var(--accent);"
		></span>
		<span>main {mainPct}%</span>
		<span class="inline-block w-2 h-2 rounded-full" style="background-color: var(--nav-teal);"
		></span>
		<span>sub {subPct}%</span>
	</div>
{/if}

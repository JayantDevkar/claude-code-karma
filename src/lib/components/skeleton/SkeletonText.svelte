<script lang="ts">
	interface Props {
		width?: string;
		lines?: number;
		size?: 'xs' | 'sm' | 'base' | 'lg' | 'xl';
		class?: string;
	}

	let { width = '100%', lines = 1, size = 'base', class: className = '' }: Props = $props();

	const sizeMap: Record<string, string> = {
		xs: 'h-3',
		sm: 'h-3.5',
		base: 'h-4',
		lg: 'h-5',
		xl: 'h-6'
	};
</script>

{#if lines === 1}
	<div
		class="skeleton-shimmer rounded-[var(--radius-sm)] {sizeMap[size]} {className}"
		style="width: {width};"
		role="status"
		aria-label="Loading text..."
	></div>
{:else}
	<div class="space-y-2 {className}">
		{#each Array(lines) as _, i}
			<div
				class="skeleton-shimmer rounded-[var(--radius-sm)] {sizeMap[size]}"
				style="width: {i === lines - 1 ? '70%' : '100%'};"
				role="status"
				aria-label="Loading text..."
			></div>
		{/each}
	</div>
{/if}

<script lang="ts">
	interface Props {
		width?: string;
		height?: string;
		rounded?: 'sm' | 'md' | 'lg' | 'full';
		class?: string;
	}

	let {
		width = '100%',
		height = '20px',
		rounded = 'md',
		class: className = ''
	}: Props = $props();

	const roundedMap: Record<string, string> = {
		sm: 'rounded-[var(--radius-sm)]',
		md: 'rounded-[var(--radius-md)]',
		lg: 'rounded-[var(--radius-lg)]',
		full: 'rounded-full'
	};
</script>

<div
	class="skeleton-shimmer {roundedMap[rounded]} {className}"
	style="width: {width}; height: {height};"
	role="status"
	aria-label="Loading..."
></div>

<script lang="ts">
	interface Props {
		size?: string;
		class?: string;
	}

	let { size = '40px', class: className = '' }: Props = $props();
</script>

<div
	class="skeleton-shimmer rounded-full shrink-0 {className}"
	style="width: {size}; height: {size};"
	role="status"
	aria-label="Loading..."
></div>

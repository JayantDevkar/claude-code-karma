<script lang="ts">
	import Icon from '$lib/components/icons/Icon.svelte';
	interface Props { name: string; size?: number; strokeWidth?: number; }
	let { name, size = 24, strokeWidth = 1.5 }: Props = $props();
</script>

<Icon {name} {size} {strokeWidth} />

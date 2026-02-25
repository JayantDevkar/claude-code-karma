<script lang="ts">
	import { Tabs } from 'bits-ui';
	import type { Snippet } from 'svelte';

	interface Props {
		value: string;
		children: Snippet;
		class?: string;
	}

	let { value, children, class: className = '' }: Props = $props();
</script>

<Tabs.Content
	{value}
	class="
		mt-4
		focus-visible:outline-none
		{className}
	"
>
	{@render children()}
</Tabs.Content>

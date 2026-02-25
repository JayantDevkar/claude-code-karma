<script lang="ts">
	import { Tabs } from 'bits-ui';
	import type { Snippet } from 'svelte';

	interface Props {
		children: Snippet;
		class?: string;
	}

	let { children, class: className = '' }: Props = $props();
</script>

<Tabs.List
	class="
		flex items-center gap-1 p-1
		bg-[var(--bg-subtle)]
		border border-[var(--border)]
		rounded-lg w-fit
		{className}
	"
>
	{@render children()}
</Tabs.List>

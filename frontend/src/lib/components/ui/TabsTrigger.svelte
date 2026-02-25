<script lang="ts">
	import { Tabs } from 'bits-ui';
	import type { Snippet } from 'svelte';

	interface Props {
		value: string;
		children: Snippet;
		// Using 'any' for icon to support Lucide icons which have complex signatures in Svelte 5
		// eslint-disable-next-line @typescript-eslint/no-explicit-any
		icon?: any;
		class?: string;
	}

	let { value, children, icon: Icon, class: className = '' }: Props = $props();
</script>

<Tabs.Trigger
	{value}
	class="
		px-4 py-2 text-sm font-medium rounded-md
		transition-all duration-200 ease-out
		flex items-center gap-2
		focus:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent)] focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--bg-base)]
		data-[state=active]:bg-[var(--bg-base)]
		data-[state=active]:text-[var(--text-primary)]
		data-[state=active]:shadow-sm
		data-[state=inactive]:text-[var(--text-secondary)]
		data-[state=inactive]:hover:text-[var(--text-primary)]
		{className}
	"
>
	{#if Icon}
		<Icon size={16} strokeWidth={2} />
	{/if}
	{@render children()}
</Tabs.Trigger>

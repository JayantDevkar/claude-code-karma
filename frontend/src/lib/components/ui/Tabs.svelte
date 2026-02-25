<script lang="ts">
	import { Tabs } from 'bits-ui';
	import type { Snippet } from 'svelte';

	interface Props {
		value?: string;
		onValueChange?: (value: string) => void;
		children: Snippet;
		class?: string;
	}

	let { value = $bindable(), onValueChange, children, class: className = '' }: Props = $props();

	function handleValueChange(newValue: string) {
		value = newValue;
		onValueChange?.(newValue);
	}
</script>

<Tabs.Root {value} onValueChange={handleValueChange} class={className}>
	{@render children()}
</Tabs.Root>

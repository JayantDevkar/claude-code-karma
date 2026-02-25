<script lang="ts">
	import { Switch } from 'bits-ui';
	import { cn } from '$lib/utils';

	interface Props {
		checked?: boolean;
		disabled?: boolean;
		onCheckedChange?: (checked: boolean) => void;
		class?: string;
	}

	// Define props using Svelte 5 $props rune
	let {
		checked = $bindable(false),
		disabled = false,
		onCheckedChange,
		class: className
	}: Props = $props();
</script>

<Switch.Root
	bind:checked
	{disabled}
	{onCheckedChange}
	class={cn(
		'peer inline-flex h-5 w-9 shrink-0 cursor-pointer items-center rounded-full border-2 border-transparent transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background disabled:cursor-not-allowed disabled:opacity-50',
		checked ? 'bg-[var(--accent)]' : 'bg-[var(--border)]',
		className
	)}
>
	<Switch.Thumb
		class={cn(
			'pointer-events-none block h-4 w-4 rounded-full bg-white shadow-sm ring-0 transition-transform duration-200 ease-[cubic-bezier(0.25,1,0.5,1)]',
			checked ? 'translate-x-4' : 'translate-x-0'
		)}
	/>
</Switch.Root>

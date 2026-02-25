<script lang="ts">
	import type { ComponentType, Snippet } from 'svelte';

	interface Props {
		icon: ComponentType;
		title: string;
		description?: string;
		action?: {
			label: string;
			onClick: () => void;
		};
		children?: Snippet;
		class?: string;
	}

	let {
		icon: Icon,
		title,
		description,
		action,
		children,
		class: className = ''
	}: Props = $props();
</script>

<div
	class="
		flex flex-col items-center justify-center py-12 px-4
		text-center rounded-lg border border-dashed
		border-[var(--border)] bg-[var(--bg-subtle)]
		{className}
	"
>
	<Icon size={48} strokeWidth={1.5} class="text-[var(--text-muted)] mb-4" />
	<h3 class="text-lg font-medium text-[var(--text-primary)] mb-2">
		{title}
	</h3>
	{#if description}
		<p class="text-sm text-[var(--text-secondary)] max-w-md">
			{description}
		</p>
	{/if}
	{#if children}
		<div class="mt-4">
			{@render children()}
		</div>
	{:else if action}
		<button
			onclick={action.onClick}
			class="
				mt-4 px-4 py-2
				bg-[var(--accent)] text-white
				rounded-md
				hover:bg-[var(--accent-hover)]
				transition-colors duration-[var(--duration-base)]
				focus:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent)] focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--bg-base)]
			"
		>
			{action.label}
		</button>
	{/if}
</div>

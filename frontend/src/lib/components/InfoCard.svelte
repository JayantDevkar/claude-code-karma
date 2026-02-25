<script lang="ts">
	import type { ComponentType, Snippet } from 'svelte';

	interface Props {
		title: string;
		icon?: ComponentType;
		class?: string;
		children?: Snippet;
	}

	let { title, icon: Icon, class: className, children }: Props = $props();
</script>

<div
	class="
		rounded-lg border border-[var(--border)]
		bg-[var(--bg-subtle)]
		p-4
		{className}
	"
>
	<h3 class="mb-3 text-sm font-medium text-[var(--text-primary)]">
		{#if Icon}
			<span class="flex items-center gap-2">
				<Icon size={14} strokeWidth={2} />
				{title}
			</span>
		{:else}
			{title}
		{/if}
	</h3>
	<div>
		{@render children?.()}
	</div>
</div>

<script lang="ts">
	import type { Snippet } from 'svelte';

	interface Props {
		title: string;
		children: Snippet;
		class?: string;
	}

	let { title, children, class: className = '' }: Props = $props();
</script>

<div
	class="border border-[var(--border)] rounded-lg bg-[var(--bg-surface)] overflow-hidden {className}"
>
	<div class="px-5 py-3 border-b border-[var(--border)] bg-[var(--bg-subtle)]">
		<h2 class="text-xs font-medium text-[var(--text-secondary)] uppercase tracking-wider">
			{title}
		</h2>
	</div>
	<div class="divide-y divide-[var(--border)]">
		{@render children()}
	</div>
</div>

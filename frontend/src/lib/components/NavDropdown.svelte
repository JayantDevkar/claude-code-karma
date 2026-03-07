<script lang="ts">
	import { page } from '$app/stores';
	import { ChevronDown } from 'lucide-svelte';

	interface NavItem {
		readonly label: string;
		readonly href: string;
	}

	interface Props {
		label: string;
		items: readonly NavItem[];
		open: boolean;
		onToggle: () => void;
		onClose: () => void;
		align?: 'left' | 'right';
	}

	let { label, items, open, onToggle, onClose, align = 'left' }: Props = $props();

	let isActive = $derived(items.some((item) => $page.url.pathname.startsWith(item.href)));
</script>

<div class="relative">
	<button
		type="button"
		class="flex items-center gap-1 text-sm font-medium transition-colors {isActive
			? 'text-[var(--text-primary)]'
			: 'text-[var(--text-muted)] hover:text-[var(--text-primary)]'}"
		onclick={onToggle}
		aria-expanded={open}
		aria-haspopup="true"
	>
		{label}
		<ChevronDown
			size={13}
			strokeWidth={2.5}
			class="transition-transform {open ? 'rotate-180' : ''}"
			style="transition-duration: var(--duration-fast);"
		/>
	</button>

	{#if open}
		<div
			class="absolute top-full mt-2 w-44 bg-[var(--bg-base)] border border-[var(--border)] rounded-lg z-50 py-1 overflow-hidden {align ===
			'right'
				? 'right-0'
				: 'left-0'}"
			style="box-shadow: var(--shadow-elevated);"
			role="menu"
		>
			{#each items as item (item.href)}
				{@const active = $page.url.pathname.startsWith(item.href)}
				<a
					href={item.href}
					onclick={onClose}
					class="block px-3 py-2 text-sm transition-colors {active
						? 'text-[var(--text-primary)] font-medium bg-[var(--accent-subtle)]'
						: 'text-[var(--text-secondary)] hover:bg-[var(--bg-subtle)] hover:text-[var(--text-primary)]'}"
					role="menuitem"
					aria-current={active ? 'page' : undefined}
				>
					{item.label}
				</a>
			{/each}
		</div>
	{/if}
</div>

<script lang="ts">
	import { ChevronRight } from 'lucide-svelte';
	import { Collapsible } from 'bits-ui';
	import type { Snippet } from 'svelte';

	interface Props {
		open?: boolean;
		onOpenChange?: (open: boolean) => void;
		icon?: Snippet;
		title: string;
		metadata?: Snippet;
		children: Snippet;
		accentColor?: string;
		class?: string;
	}

	let {
		open = $bindable(false),
		onOpenChange,
		icon,
		title,
		metadata,
		children,
		accentColor,
		class: className = ''
	}: Props = $props();

	function handleOpenChange(isOpen: boolean) {
		open = isOpen;
		if (onOpenChange) {
			onOpenChange(isOpen);
		}
	}
</script>

<Collapsible.Root {open} onOpenChange={handleOpenChange} class="group {className}">
	<div
		class="
			border border-[var(--border)]
			rounded-[var(--radius-lg)]
			overflow-hidden
			bg-[var(--bg-base)]
			transition-shadow
		"
		style="transition-duration: var(--duration-normal);{accentColor
			? ` border-left: 3px solid ${accentColor};`
			: ''}"
	>
		<!-- Header -->
		<Collapsible.Trigger
			class="
				w-full
				flex items-center gap-3
				px-4 py-4
				text-left
				hover:bg-[var(--bg-subtle)]
				transition-colors
				focus-visible:outline-none
				focus-visible:ring-2
				focus-visible:ring-[var(--accent-primary)]
				focus-visible:ring-offset-2
			"
			style="transition-duration: var(--duration-fast);"
		>
			<!-- Chevron Icon -->
			<ChevronRight
				size={16}
				strokeWidth={2.5}
				class="
					text-[var(--text-muted)]
					transition-transform
					{open ? 'rotate-90' : 'rotate-0'}
				"
				style="transition-duration: var(--duration-normal);"
			/>

			<!-- Custom Icon Slot -->
			{#if icon}
				<div class="flex-shrink-0">
					{@render icon()}
				</div>
			{/if}

			<!-- Title -->
			<h3 class="flex-1 text-sm font-medium text-[var(--text-primary)]">
				{title}
			</h3>

			<!-- Metadata Slot -->
			{#if metadata}
				<div class="flex items-center gap-3">
					{@render metadata()}
				</div>
			{/if}
		</Collapsible.Trigger>

		<!-- Content -->
		<Collapsible.Content
			class="
				border-t border-[var(--border)]
				overflow-hidden
				transition-all
			"
			style="transition-duration: var(--duration-normal);"
		>
			<div class="p-4">
				{@render children()}
			</div>
		</Collapsible.Content>
	</div>
</Collapsible.Root>

<style>
	/* Ensure smooth transitions for bits-ui Collapsible */
	:global([data-collapsible-content]) {
		transition: height var(--duration-normal) ease-in-out;
	}
</style>

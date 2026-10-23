<script lang="ts">
	import { ChevronRight } from 'lucide-svelte';
	import { slide } from 'svelte/transition';
	import type { Snippet } from 'svelte';

	interface Props {
		open?: boolean;
		onOpenChange?: (open: boolean) => void;
		icon?: Snippet;
		title: string;
		metadata?: Snippet;
		children: Snippet;
		accentColor?: string;
		/** Use 3 when the group sits under a section h2. */
		headingLevel?: 2 | 3 | 4;
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
		headingLevel = 2,
		class: className = ''
	}: Props = $props();

	function toggle() {
		const next = !open;
		open = next;
		onOpenChange?.(next);
	}
</script>

<div class="group {className}">
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
		<button
			type="button"
			onclick={toggle}
			aria-expanded={open}
			class="
				w-full
				flex flex-wrap sm:flex-nowrap items-center gap-x-3 gap-y-2
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
					shrink-0
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
			<svelte:element
				this={`h${headingLevel}`}
				class="flex-1 text-sm font-medium text-[var(--text-primary)]"
			>
				{title}
			</svelte:element>

			<!-- Metadata Slot -->
			<!-- Phones: metadata gets its own line, indented past the chevron, so chips never clip. -->
			{#if metadata}
				<div
					class="flex flex-wrap sm:flex-nowrap items-center gap-2 sm:gap-3 max-sm:w-full max-sm:pl-7"
				>
					{@render metadata()}
				</div>
			{/if}
		</button>

		<!-- Content -->
		{#if open}
			<div
				transition:slide={{ duration: 200 }}
				class="border-t border-[var(--border)] overflow-hidden"
			>
				<div class="p-4">
					{@render children()}
				</div>
			</div>
		{/if}
	</div>
</div>

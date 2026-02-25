<script lang="ts">
	import { Dialog } from 'bits-ui';
	import { X } from 'lucide-svelte';
	import type { Snippet } from 'svelte';

	interface Props {
		open?: boolean;
		onOpenChange?: (open: boolean) => void;
		title: string;
		description?: string;
		children: Snippet;
		footer?: Snippet;
		maxWidth?: 'sm' | 'md' | 'lg' | 'xl';
	}

	let {
		open = $bindable(false),
		onOpenChange,
		title,
		description,
		children,
		footer,
		maxWidth = 'md'
	}: Props = $props();

	const maxWidthClasses: Record<string, string> = {
		sm: 'max-w-sm',
		md: 'max-w-md',
		lg: 'max-w-lg',
		xl: 'max-w-[80vw]'
	};

	function handleOpenChange(isOpen: boolean) {
		open = isOpen;
		if (onOpenChange) {
			onOpenChange(isOpen);
		}
	}
</script>

<Dialog.Root {open} onOpenChange={handleOpenChange}>
	<Dialog.Portal>
		<Dialog.Overlay
			class="
				fixed inset-0 z-50
				bg-black/50
				data-[state=open]:animate-in
				data-[state=closed]:animate-out
				data-[state=closed]:fade-out-0
				data-[state=open]:fade-in-0
			"
		/>
		<Dialog.Content
			class="
				fixed left-[50%] top-[50%] z-50
				translate-x-[-50%] translate-y-[-50%]
				bg-[var(--bg-base)]
				rounded-xl
				{maxWidthClasses[maxWidth]} w-full
				p-6
				border border-[var(--border)]
				focus:outline-none
				data-[state=open]:animate-in
				data-[state=closed]:animate-out
				data-[state=closed]:fade-out-0
				data-[state=open]:fade-in-0
				data-[state=closed]:zoom-out-95
				data-[state=open]:zoom-in-95
				data-[state=closed]:slide-out-to-left-1/2
				data-[state=closed]:slide-out-to-top-[48%]
				data-[state=open]:slide-in-from-left-1/2
				data-[state=open]:slide-in-from-top-[48%]
			"
			style="box-shadow: var(--shadow-elevated);"
		>
			<div class="flex items-center justify-between mb-4">
				<Dialog.Title class="text-lg font-semibold text-[var(--text-primary)]">
					{title}
				</Dialog.Title>
				<Dialog.Close
					class="
						text-[var(--text-muted)]
						hover:text-[var(--text-primary)]
						transition-colors
						focus:outline-none
						focus-visible:ring-2
						focus-visible:ring-[var(--accent)]
						rounded-md
						p-1
					"
					style="transition-duration: var(--duration-fast);"
					aria-label="Close dialog"
				>
					<X size={20} />
				</Dialog.Close>
			</div>

			{#if description}
				<Dialog.Description class="text-sm text-[var(--text-secondary)] mb-4">
					{description}
				</Dialog.Description>
			{/if}

			{@render children()}

			{#if footer}
				<div class="flex justify-end gap-3 pt-4 mt-4 border-t border-[var(--border)]">
					{@render footer()}
				</div>
			{/if}
		</Dialog.Content>
	</Dialog.Portal>
</Dialog.Root>

<style>
	/* Animation keyframes for modal transitions */
	:global(.animate-in) {
		animation-duration: 150ms;
		animation-timing-function: cubic-bezier(0.16, 1, 0.3, 1);
		animation-fill-mode: forwards;
	}

	:global(.animate-out) {
		animation-duration: 150ms;
		animation-timing-function: cubic-bezier(0.16, 1, 0.3, 1);
		animation-fill-mode: forwards;
	}

	:global(.fade-in-0) {
		animation-name: fadeIn;
	}

	:global(.fade-out-0) {
		animation-name: fadeOut;
	}

	:global(.zoom-in-95) {
		animation-name: zoomIn;
	}

	:global(.zoom-out-95) {
		animation-name: zoomOut;
	}

	@keyframes fadeIn {
		from {
			opacity: 0;
		}
		to {
			opacity: 1;
		}
	}

	@keyframes fadeOut {
		from {
			opacity: 1;
		}
		to {
			opacity: 0;
		}
	}

	@keyframes zoomIn {
		from {
			transform: translate(-50%, -50%) scale(0.95);
		}
		to {
			transform: translate(-50%, -50%) scale(1);
		}
	}

	@keyframes zoomOut {
		from {
			transform: translate(-50%, -50%) scale(1);
		}
		to {
			transform: translate(-50%, -50%) scale(0.95);
		}
	}
</style>

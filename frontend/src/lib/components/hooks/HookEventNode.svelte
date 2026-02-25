<script lang="ts">
	import { ChevronRight, AlertCircle } from 'lucide-svelte';
	import { Collapsible } from 'bits-ui';
	import type { HookEventSummary } from '$lib/api-types';
	import HookRegistrationCard from './HookRegistrationCard.svelte';

	interface Props {
		event: HookEventSummary;
		open?: boolean;
		onToggle?: () => void;
	}

	let { event, open = $bindable(false), onToggle }: Props = $props();

	function handleOpenChange(isOpen: boolean) {
		open = isOpen;
		onToggle?.();
	}
</script>

<Collapsible.Root {open} onOpenChange={handleOpenChange} class="group">
	<div class="relative">
		<!-- Timeline vertical line (connects nodes) -->
		<div
			class="absolute left-1 top-0 bottom-0 w-0.5 bg-[var(--nav-amber)] opacity-20"
			style="left: 3px;"
		></div>

		<!-- Timeline Node Content -->
		<div class="relative pl-8 pb-6">
			<!-- Circle dot at left -->
			<div
				class="absolute left-0 top-2 w-2 h-2 rounded-full border-2 border-[var(--bg-base)] z-10"
				style="background-color: {event.can_block
					? 'var(--status-error)'
					: 'var(--nav-amber)'};"
			></div>

			<!-- Collapsible Card -->
			<Collapsible.Trigger
				class="
					w-full
					flex items-center gap-3
					px-4 py-3
					text-left
					bg-[var(--bg-base)]
					border border-[var(--border)]
					rounded-lg
					hover:bg-[var(--bg-subtle)]
					transition-all
					focus-visible:outline-none
					focus-visible:ring-2
					focus-visible:ring-[var(--accent)]
					focus-visible:ring-offset-2
					shadow-sm
					hover:shadow-md
				"
			>
				<!-- Chevron Icon -->
				<ChevronRight
					size={14}
					strokeWidth={2.5}
					class="
						text-[var(--text-muted)]
						transition-transform
						{open ? 'rotate-90' : 'rotate-0'}
					"
					style="transition-duration: var(--duration-normal);"
				/>

				<!-- Event Content -->
				<div class="flex-1 min-w-0">
					<div class="flex items-center gap-2 mb-1">
						<a
							href="/hooks/{encodeURIComponent(event.event_type)}"
							class="
								text-sm font-semibold text-[var(--text-primary)]
								hover:text-[var(--accent)]
								transition-colors
							"
							onclick={(e) => e.stopPropagation()}
						>
							{event.event_type}
						</a>
						{#if event.can_block}
							<span
								class="
									inline-flex items-center gap-1
									px-1.5 py-0.5
									text-[10px] font-bold uppercase tracking-wider
									bg-red-500/10 text-red-600 dark:text-red-400
									rounded
								"
								title="This hook can block execution"
							>
								<AlertCircle size={10} />
								Can Block
							</span>
						{/if}
					</div>
					<div class="text-xs text-[var(--text-muted)]">
						Phase: {event.phase}
					</div>
				</div>

				<!-- Registration Count Badge -->
				<div
					class="
						flex items-center gap-1.5
						px-2.5 py-1
						text-xs font-medium
						text-[var(--text-muted)]
						bg-[var(--bg-muted)]
						rounded-full
						tabular-nums
					"
				>
					{event.total_registrations} hook{event.total_registrations !== 1 ? 's' : ''}
				</div>
			</Collapsible.Trigger>

			<!-- Expanded Content -->
			<Collapsible.Content
				class="
					overflow-hidden
					transition-all
				"
				style="transition-duration: var(--duration-normal);"
			>
				<div class="mt-3 space-y-2 pl-8">
					{#each event.registrations as registration, i (`${registration.source_id}-${i}`)}
						<HookRegistrationCard {registration} />
					{/each}
				</div>
			</Collapsible.Content>
		</div>
	</div>
</Collapsible.Root>

<style>
	/* Ensure smooth transitions for bits-ui Collapsible */
	:global([data-collapsible-content]) {
		transition: height var(--duration-normal) ease-in-out;
	}
</style>

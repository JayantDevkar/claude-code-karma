<script lang="ts">
	import type { Ticket } from '$lib/api-types';
	import {
		PROVIDER_META,
		normalizeStatus,
		statusColorVar
	} from '$lib/ticket-helpers';
	import { ExternalLink, X, MoreHorizontal, Hash, Copy } from 'lucide-svelte';
	import ProviderChip from './ProviderChip.svelte';

	type Variant = 'inline' | 'card' | 'pill';

	interface Props {
		ticket: Pick<Ticket, 'provider' | 'external_key' | 'url' | 'title' | 'status'>;
		variant?: Variant;
		/**
		 * If provided, the pill/card variant gets a kebab menu with Open / Copy /
		 * Unlink. Omit on read-only contexts (table cells, detail header).
		 */
		onRemove?: () => void;
		/** Hide the trailing status dot+label when the surrounding context already shows it. */
		showStatus?: boolean;
	}

	let { ticket, variant = 'pill', onRemove, showStatus = true }: Props = $props();

	let meta = $derived(PROVIDER_META[ticket.provider]);
	let norm = $derived(normalizeStatus(ticket.status));
	let menuOpen = $state(false);
	let menuEl: HTMLSpanElement | null = $state(null);

	function copyKey() {
		void navigator.clipboard.writeText(ticket.external_key);
		menuOpen = false;
	}

	function openProvider() {
		window.open(ticket.url, '_blank', 'noopener,noreferrer');
		menuOpen = false;
	}

	function unlink() {
		menuOpen = false;
		onRemove?.();
	}

	// Outside-click close
	function handleDocClick(e: MouseEvent) {
		if (!menuOpen) return;
		if (menuEl && !menuEl.contains(e.target as Node)) menuOpen = false;
	}

	function handleKey(e: KeyboardEvent) {
		if (e.key === 'Escape' && menuOpen) menuOpen = false;
	}
</script>

<svelte:document onclick={handleDocClick} onkeydown={handleKey} />

{#snippet statusDot(size = 6)}
	<span
		aria-hidden="true"
		class="inline-block rounded-full shrink-0"
		style="width: {size}px; height: {size}px; background: var({statusColorVar(norm.key)})"
	></span>
{/snippet}

{#if variant === 'card'}
	<div class="flex flex-col gap-2 p-4 rounded-lg border border-[var(--border)] bg-[var(--bg-subtle)]">
		<div class="flex items-center justify-between gap-3">
			<div class="flex items-center gap-2 min-w-0">
				<ProviderChip {ticket} />
				<a
					href={ticket.url}
					target="_blank"
					rel="noopener noreferrer"
					class="font-mono text-sm text-[var(--text-primary)] hover:text-[var(--accent)] inline-flex items-center gap-1 truncate"
				>
					<span class="truncate">{ticket.external_key}</span>
					<ExternalLink size={12} class="shrink-0" />
				</a>
			</div>
			{#if onRemove}
				<button
					type="button"
					onclick={unlink}
					class="text-[var(--text-muted)] hover:text-[var(--error)] p-1 rounded transition-colors focus-ring"
					aria-label="Unlink ticket"
					title="Unlink ticket"
				>
					<X size={14} />
				</button>
			{/if}
		</div>
		{#if ticket.title}
			<p class="text-sm text-[var(--text-primary)] leading-snug m-0">{ticket.title}</p>
		{/if}
		{#if showStatus && norm.verbatim}
			<span class="inline-flex items-center gap-1.5 text-xs text-[var(--text-muted)]">
				{@render statusDot(7)}
				{norm.verbatim}
			</span>
		{/if}
	</div>

{:else if variant === 'inline'}
	<span class="inline-flex items-center gap-1.5 text-sm min-w-0">
		<ProviderChip {ticket} />
		<span class="font-mono text-[var(--text-primary)] whitespace-nowrap">
			{ticket.external_key}
		</span>
		{#if ticket.title}
			<span class="text-[var(--text-secondary)] truncate max-w-[36ch]">— {ticket.title}</span>
		{/if}
	</span>

{:else}
	<!-- pill — provider chip + key + optional status + kebab. Title lives in
		 the `title` tooltip; the kebab provides "Open in {provider}" so the
		 external-link icon next to the key is redundant when onRemove is set. -->
	<span
		class="inline-flex items-center gap-1.5 pl-1.5 pr-2 py-[3px] rounded-full text-xs border border-[var(--border)] bg-[var(--bg-base)]"
		title={ticket.title ?? undefined}
	>
		<ProviderChip {ticket} />
		<a
			href={ticket.url}
			target="_blank"
			rel="noopener noreferrer"
			class="font-mono text-[11.5px] text-[var(--text-primary)] hover:text-[var(--accent)] inline-flex items-center gap-1 hover:underline whitespace-nowrap"
		>
			{ticket.external_key}
			{#if !onRemove}
				<ExternalLink size={9} />
			{/if}
		</a>
		{#if showStatus && norm.verbatim}
			<span class="inline-flex items-center gap-1 pl-1.5 ml-0.5 border-l border-[var(--border-subtle)] text-[11px] text-[var(--text-muted)] whitespace-nowrap">
				{@render statusDot(6)}
				{norm.verbatim}
			</span>
		{/if}
		{#if onRemove}
			<span class="relative inline-flex" bind:this={menuEl}>
				<button
					type="button"
					onclick={(e) => {
						e.stopPropagation();
						menuOpen = !menuOpen;
					}}
					class="-mr-1 ml-0.5 p-0.5 rounded text-[var(--text-muted)] hover:text-[var(--text-primary)] hover:bg-[var(--bg-muted)] transition-colors focus-ring"
					aria-label="Ticket options"
					aria-haspopup="menu"
					aria-expanded={menuOpen}
				>
					<MoreHorizontal size={12} />
				</button>
				{#if menuOpen}
					<div
						class="absolute right-0 top-full mt-1.5 z-20 min-w-[160px] p-1 rounded-md border border-[var(--border)] bg-[var(--bg-base)] shadow-[var(--shadow-md)]"
						role="menu"
					>
						<button
							type="button"
							onclick={openProvider}
							class="flex items-center gap-2 w-full px-2.5 py-1.5 text-xs text-[var(--text-primary)] rounded hover:bg-[var(--bg-subtle)] text-left"
							role="menuitem"
						>
							<ExternalLink size={12} /> Open in {meta.label}
						</button>
						<button
							type="button"
							onclick={copyKey}
							class="flex items-center gap-2 w-full px-2.5 py-1.5 text-xs text-[var(--text-primary)] rounded hover:bg-[var(--bg-subtle)] text-left"
							role="menuitem"
						>
							<Copy size={12} /> Copy key
						</button>
						<div class="my-1 h-px bg-[var(--border-subtle)]"></div>
						<button
							type="button"
							onclick={unlink}
							class="flex items-center gap-2 w-full px-2.5 py-1.5 text-xs text-[var(--error)] rounded hover:bg-[var(--error-subtle)] text-left"
							role="menuitem"
						>
							<X size={12} /> Unlink
						</button>
					</div>
				{/if}
			</span>
		{/if}
	</span>
{/if}

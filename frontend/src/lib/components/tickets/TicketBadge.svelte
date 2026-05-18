<script lang="ts">
	import type { Ticket, TicketProvider } from '$lib/api-types';
	import { ExternalLink, X } from 'lucide-svelte';

	type Variant = 'inline' | 'card' | 'pill';

	interface Props {
		ticket: Pick<Ticket, 'provider' | 'external_key' | 'url' | 'title' | 'status'>;
		variant?: Variant;
		onRemove?: () => void;
	}

	let { ticket, variant = 'pill', onRemove }: Props = $props();

	// Provider color tokens — kept loose; map only what we ship.
	const providerStyle: Record<TicketProvider, { bg: string; text: string; label: string }> = {
		linear: {
			bg: 'bg-[var(--accent-subtle,#eef2ff)]',
			text: 'text-[var(--accent,#6366f1)]',
			label: 'Linear'
		},
		jira: {
			bg: 'bg-[#deebff]',
			text: 'text-[#0052cc]',
			label: 'Jira'
		},
		github: {
			bg: 'bg-[var(--bg-muted,#e5e7eb)]',
			text: 'text-[var(--text-primary,#111827)]',
			label: 'GitHub'
		}
	};

	let style = $derived(providerStyle[ticket.provider]);
</script>

{#if variant === 'card'}
	<div
		class="flex flex-col gap-2 p-4 rounded-lg border border-[var(--border)] bg-[var(--bg-subtle)]"
	>
		<div class="flex items-center justify-between gap-3">
			<div class="flex items-center gap-2">
				<span
					class="text-xs font-medium px-1.5 py-0.5 rounded {style.bg} {style.text}"
					title={style.label}
				>
					{style.label}
				</span>
				<a
					href={ticket.url}
					target="_blank"
					rel="noopener noreferrer"
					class="font-mono text-sm text-[var(--text-primary)] hover:text-[var(--accent)] inline-flex items-center gap-1"
				>
					{ticket.external_key}
					<ExternalLink size={12} />
				</a>
			</div>
			{#if onRemove}
				<button
					type="button"
					onclick={onRemove}
					class="text-[var(--text-muted)] hover:text-[var(--error)] p-1 rounded transition-colors"
					title="Unlink ticket"
					aria-label="Unlink ticket"
				>
					<X size={14} />
				</button>
			{/if}
		</div>
		{#if ticket.title}
			<p class="text-sm text-[var(--text-secondary)] leading-snug">{ticket.title}</p>
		{/if}
		{#if ticket.status}
			<span class="text-xs text-[var(--text-muted)]">Status: {ticket.status}</span>
		{/if}
	</div>
{:else if variant === 'inline'}
	<a
		href={ticket.url}
		target="_blank"
		rel="noopener noreferrer"
		class="inline-flex items-center gap-1.5 text-sm hover:text-[var(--accent)]"
		title={ticket.title ?? ticket.external_key}
	>
		<span
			class="text-[10px] font-medium px-1 py-0.5 rounded {style.bg} {style.text} uppercase tracking-wide"
		>
			{style.label}
		</span>
		<span class="font-mono">{ticket.external_key}</span>
		{#if ticket.title}
			<span class="text-[var(--text-secondary)] truncate max-w-[24ch]">— {ticket.title}</span>
		{/if}
	</a>
{:else}
	<!-- pill -->
	<span
		class="inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full text-xs {style.bg} {style.text} border border-[var(--border)]"
	>
		<a
			href={ticket.url}
			target="_blank"
			rel="noopener noreferrer"
			class="font-mono inline-flex items-center gap-1 hover:underline"
			title={ticket.title ?? undefined}
		>
			{ticket.external_key}
			<ExternalLink size={10} />
		</a>
		{#if ticket.title}
			<span class="text-[var(--text-secondary)] truncate max-w-[18ch]" aria-hidden="true">
				{ticket.title}
			</span>
		{/if}
		{#if onRemove}
			<button
				type="button"
				onclick={onRemove}
				class="text-[var(--text-muted)] hover:text-[var(--error)] -mr-0.5"
				title="Unlink ticket"
				aria-label="Unlink ticket"
			>
				<X size={12} />
			</button>
		{/if}
	</span>
{/if}

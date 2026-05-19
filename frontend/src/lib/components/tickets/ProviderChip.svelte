<script lang="ts">
	/**
	 * Provider letter-mark chip (LIN / JIR / GH) with optional GitHub
	 * kind indicator (issue vs pull request).
	 *
	 * Extracted so every surface that renders a ticket — TicketBadge,
	 * tickets index, project Tickets tab, ticket detail header — agrees
	 * on the same visual treatment. Without this, the PR indicator would
	 * have to be re-implemented at each callsite or silently omitted at
	 * some of them (the original bug surface).
	 */
	import type { Ticket } from '$lib/api-types';
	import { PROVIDER_META, githubKindFromUrl } from '$lib/ticket-helpers';
	import { GitPullRequest } from 'lucide-svelte';

	interface Props {
		ticket: Pick<Ticket, 'provider' | 'url'>;
		/** Render the PR pip after the chip when applicable. Default true. */
		showKind?: boolean;
	}

	let { ticket, showKind = true }: Props = $props();

	let meta = $derived(PROVIDER_META[ticket.provider]);
	let isPullRequest = $derived(
		ticket.provider === 'github' && githubKindFromUrl(ticket.url) === 'pull_request'
	);
</script>

<span class="inline-flex items-center gap-1 shrink-0">
	<span
		class="inline-flex items-center font-mono font-bold px-1 py-[1px] rounded-sm text-[10px] tracking-wider leading-snug"
		style="background: var({meta.colorVar}); color: var({meta.fgVar})"
		title={meta.label}
		aria-label={meta.label}
	>
		{meta.short}
	</span>
	{#if showKind && isPullRequest}
		<!-- Pull-request indicator. The icon is GitHub's own glyph; the
			 monospace " PR " is for skim-readers who don't recognize it. -->
		<span
			class="inline-flex items-center gap-0.5 font-mono text-[9.5px] tracking-wider font-semibold uppercase text-[var(--text-muted)] leading-snug"
			title="Pull request"
			aria-label="Pull request"
		>
			<GitPullRequest size={10} aria-hidden="true" />
			PR
		</span>
	{/if}
</span>

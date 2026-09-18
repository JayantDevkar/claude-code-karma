<script lang="ts">
	import type { Snippet } from 'svelte';
	import { ExternalLink, Loader2, RotateCcw } from 'lucide-svelte';

	interface Props {
		title: string;
		description?: string;
		hint?: string;
		saving?: boolean;
		success?: string | null;
		control: Snippet;
		class?: string;
		/** Shows a small "New sessions" badge — settings.json is only read when a session starts. */
		restartRequired?: boolean;
		/** e.g. "Default: Off" — shown under the description when the setting has a known default. */
		defaultLabel?: string;
		/** Shows a "Reset" affordance next to defaultLabel when the current value differs from default. */
		showReset?: boolean;
		onReset?: () => void;
		/** Link to this setting's docs-reference section, shown next to defaultLabel/Reset. */
		docsUrl?: string;
	}

	let {
		title,
		description,
		hint,
		saving = false,
		success = null,
		control,
		class: className = '',
		restartRequired = false,
		defaultLabel,
		showReset = false,
		onReset,
		docsUrl
	}: Props = $props();
</script>

<div class="p-5 flex items-start justify-between gap-6 {className}">
	<div class="space-y-1.5 max-w-lg">
		<div class="flex items-center gap-2 flex-wrap">
			<h3 class="text-sm font-medium text-[var(--text-primary)]">{title}</h3>
			{#if restartRequired}
				<span
					class="inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-medium uppercase tracking-wide bg-[var(--bg-muted)] text-[var(--text-muted)] border border-[var(--border)]"
					title="Takes effect the next time you start a Claude Code session"
				>
					New sessions
				</span>
			{/if}
			{#if saving}
				<Loader2 size={12} class="animate-spin text-[var(--text-muted)]" />
			{/if}
			{#if success}
				<span class="text-xs text-[var(--success)] font-medium animate-fade-in">
					{success}
				</span>
			{/if}
		</div>
		{#if description}
			<p class="text-[13px] leading-relaxed text-[var(--text-secondary)]">
				{description}
			</p>
		{/if}
		{#if hint}
			<p class="text-xs text-[var(--text-muted)]">{hint}</p>
		{/if}
		{#if defaultLabel || docsUrl}
			<div class="flex items-center gap-2.5 pt-0.5 flex-wrap">
				{#if defaultLabel}
					<p class="text-xs text-[var(--text-muted)]">{defaultLabel}</p>
				{/if}
				{#if showReset}
					<button
						onclick={onReset}
						class="inline-flex items-center gap-1 text-xs text-[var(--accent)] hover:underline"
					>
						<RotateCcw size={11} />
						Reset
					</button>
				{/if}
				{#if docsUrl}
					<a
						href={docsUrl}
						target="_blank"
						rel="noreferrer"
						class="inline-flex items-center gap-1 text-xs text-[var(--text-muted)] hover:text-[var(--text-secondary)] transition-colors"
					>
						<ExternalLink size={11} />
						Docs
					</a>
				{/if}
			</div>
		{/if}
	</div>
	<div class="flex items-center gap-3 shrink-0 pt-0.5">
		{@render control()}
	</div>
</div>

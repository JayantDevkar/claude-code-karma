<script lang="ts">
	import { ChevronDown, Copy, Check } from 'lucide-svelte';
	import type { ArchivedPrompt } from '$lib/api-types';

	interface Props {
		prompt: ArchivedPrompt;
		showProject?: boolean;
		projectName?: string;
		compact?: boolean; // Compact mode for use inside expanded session cards
	}

	let { prompt, showProject = false, projectName = '', compact = false }: Props = $props();
	let expanded = $state(false);
	let copied = $state(false);

	function formatDateTime(timestamp: string) {
		const date = new Date(timestamp);
		return date.toLocaleDateString('en-US', {
			month: 'short',
			day: 'numeric',
			year: 'numeric'
		});
	}

	function formatTime(timestamp: string) {
		return new Date(timestamp).toLocaleTimeString('en-US', {
			hour: 'numeric',
			minute: '2-digit',
			hour12: true
		});
	}

	async function copyToClipboard() {
		try {
			await navigator.clipboard.writeText(prompt.display);
			copied = true;
			setTimeout(() => {
				copied = false;
			}, 2000);
		} catch (err) {
			console.error('Failed to copy:', err);
		}
	}

	// Truncate prompt for preview
	const previewLength = compact ? 200 : 150;
	const needsTruncation = $derived(prompt.display.length > previewLength);
	const displayText = $derived(
		expanded || !needsTruncation
			? prompt.display
			: prompt.display.slice(0, previewLength) + '...'
	);
</script>

{#if compact}
	<!-- Compact mode: simpler layout for inside expanded session cards -->
	<div
		class="
			group
			bg-[var(--bg-subtle)]
			border border-[var(--border-subtle)]
			rounded-[var(--radius-md)]
			p-3
			hover:border-[var(--border)]
			transition-colors
		"
	>
		<!-- Time + Prompt + Copy -->
		<div class="flex items-start gap-3">
			<span class="text-xs text-[var(--text-muted)] font-mono shrink-0 pt-0.5">
				{formatTime(prompt.timestamp)}
			</span>
			<div class="flex-1 min-w-0">
				<p
					class="text-sm text-[var(--text-secondary)] leading-relaxed whitespace-pre-wrap break-words"
				>
					{displayText}
				</p>
				{#if needsTruncation}
					<button
						onclick={() => (expanded = !expanded)}
						class="
							mt-1 flex items-center gap-1 text-xs text-[var(--text-muted)]
							hover:text-[var(--text-primary)] transition-colors
						"
					>
						<ChevronDown
							size={12}
							class="transition-transform {expanded ? 'rotate-180' : ''}"
						/>
						<span>{expanded ? 'Less' : 'More'}</span>
					</button>
				{/if}
			</div>
			<!-- Copy Button -->
			<button
				onclick={copyToClipboard}
				class="
					shrink-0 p-1.5 rounded-md
					text-[var(--text-muted)]
					opacity-0 group-hover:opacity-100
					hover:text-[var(--text-primary)] hover:bg-[var(--bg-muted)]
					transition-all
					{copied ? 'opacity-100 text-green-500' : ''}
				"
				title={copied ? 'Copied!' : 'Copy prompt'}
			>
				{#if copied}
					<Check size={14} />
				{:else}
					<Copy size={14} />
				{/if}
			</button>
		</div>
	</div>
{:else}
	<!-- Full mode: standalone card -->
	<div
		class="
			bg-[var(--bg-base)]
			border border-[var(--border)]
			rounded-[var(--radius-md)]
			transition-all
			hover:border-[var(--border-hover)]
			hover:shadow-sm
			overflow-hidden
			opacity-75
			hover:opacity-100
		"
		style="
			transition-duration: var(--duration-fast);
			transition-timing-function: var(--ease);
		"
	>
		<!-- HEADER ZONE: Timestamp -->
		<div class="p-4 pb-3">
			<!-- Top Row: Date + Time -->
			<div class="flex items-start justify-between gap-3 mb-1">
				<!-- Left: Date/Time -->
				<div class="flex items-center gap-2.5 min-w-0 flex-1">
					<!-- Date -->
					<span class="text-sm font-medium text-[var(--text-secondary)] leading-tight">
						{formatDateTime(prompt.timestamp)}
					</span>

					<!-- Time -->
					<span class="text-xs text-[var(--text-muted)]">
						{formatTime(prompt.timestamp)}
					</span>
				</div>
			</div>

			<!-- Project Name (when shown on history page) -->
			{#if showProject && projectName}
				<div class="mt-1">
					<span class="text-xs text-[var(--text-muted)] font-mono">
						{projectName}
					</span>
				</div>
			{/if}
		</div>

		<!-- BODY ZONE: Prompt (expandable) -->
		<div class="px-4 pb-3">
			<div
				class="text-sm text-[var(--text-secondary)] leading-relaxed bg-[var(--bg-muted)] px-3 py-2 rounded-md"
			>
				<p class="whitespace-pre-wrap break-words">{displayText}</p>
			</div>

			<!-- Expand/Collapse Button -->
			{#if needsTruncation}
				<button
					onclick={() => (expanded = !expanded)}
					class="
						mt-2 flex items-center gap-1 text-xs text-[var(--text-muted)]
						hover:text-[var(--text-primary)] transition-colors
					"
				>
					<ChevronDown
						size={14}
						class="transition-transform {expanded ? 'rotate-180' : ''}"
					/>
					<span>{expanded ? 'Show less' : 'Show more'}</span>
				</button>
			{/if}
		</div>

		<!-- FOOTER ZONE: Info message -->
		<div
			class="px-4 py-2.5 bg-[rgba(184,84,80,0.06)] border-t border-[rgba(184,84,80,0.15)] flex items-center"
		>
			<span class="text-[11px] text-[#B85450] italic">
				Session data no longer available
			</span>
		</div>
	</div>
{/if}

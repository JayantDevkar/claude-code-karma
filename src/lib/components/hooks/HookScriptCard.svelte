<script lang="ts">
	import { FileCode, ExternalLink } from 'lucide-svelte';
	import type { HookScript } from '$lib/api-types';
	import { getHookSourceColorVars } from '$lib/utils';

	interface Props {
		script: HookScript;
		sourceType: string;
		sourceName: string;
	}

	let { script, sourceType, sourceName }: Props = $props();

	let sourceColors = $derived(getHookSourceColorVars(sourceType, sourceName));

	// Language display names
	const languageLabels: Record<string, string> = {
		python: 'Python',
		node: 'Node.js',
		shell: 'Shell',
		bash: 'Shell'
	};

	let languageLabel = $derived(languageLabels[script.language] || script.language);
</script>

<a
	href="/hooks/scripts/{encodeURIComponent(script.filename)}"
	class="
		group block
		bg-[var(--bg-base)]
		border border-[var(--border)]
		rounded-xl
		p-5
		shadow-sm hover:shadow-xl hover:-translate-y-1
		transition-all duration-300
		relative overflow-hidden
		focus:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent)] focus-visible:ring-offset-2
	"
	style="border-left: 4px solid {sourceColors.color};"
>
	<!-- Filename and Language -->
	<div class="flex items-start justify-between gap-3 mb-4">
		<div class="flex items-center gap-2 min-w-0">
			<div
				class="shrink-0 p-2 rounded-lg transition-transform duration-300 group-hover:scale-110"
				style="background-color: {sourceColors.subtle}; color: {sourceColors.color};"
			>
				<FileCode size={18} strokeWidth={2} />
			</div>
			<div class="min-w-0">
				<h3
					class="text-sm font-bold text-[var(--text-primary)] truncate group-hover:text-[var(--accent)] transition-colors"
				>
					{script.filename}
				</h3>
				{#if script.is_symlink && script.symlink_target}
					<p
						class="text-[10px] text-[var(--text-muted)] truncate mt-0.5"
						title={script.symlink_target}
					>
						→ {script.symlink_target}
					</p>
				{/if}
			</div>
		</div>

		<!-- Language Badge -->
		<span
			class="
				shrink-0
				px-2 py-0.5
				text-[10px] font-semibold uppercase tracking-wider
				bg-[var(--bg-subtle)] text-[var(--text-muted)]
				rounded-full
			"
		>
			{languageLabel}
		</span>
	</div>

	<!-- Event Type Pills -->
	<div class="flex flex-wrap gap-1.5 mb-4">
		{#each script.event_types as eventType}
			<button
				type="button"
				onclick={(e) => {
					e.preventDefault();
					e.stopPropagation();
					window.location.href = `/hooks/${encodeURIComponent(eventType)}`;
				}}
				class="
					inline-flex items-center gap-1
					px-2 py-0.5
					text-[10px] font-medium
					rounded-full
					transition-colors
					bg-[var(--bg-muted)] text-[var(--text-secondary)]
					hover:bg-[var(--nav-amber-subtle)] hover:text-[var(--nav-amber)]
					border border-transparent
					hover:border-[var(--nav-amber)]
					cursor-pointer
				"
			>
				{eventType}
				<ExternalLink size={8} />
			</button>
		{/each}
	</div>

	<!-- Stats -->
	<div
		class="flex items-center justify-between text-xs text-[var(--text-muted)] pt-4 border-t border-[var(--border-subtle)]"
	>
		<span>
			{script.registrations} registration{script.registrations !== 1 ? 's' : ''}
		</span>
		<span>
			{script.event_types.length} event type{script.event_types.length !== 1 ? 's' : ''}
		</span>
	</div>
</a>

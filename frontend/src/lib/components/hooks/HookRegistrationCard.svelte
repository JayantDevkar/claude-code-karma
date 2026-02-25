<script lang="ts">
	import type { HookRegistration } from '$lib/api-types';
	import { getHookSourceColorVars } from '$lib/utils';
	import { truncate } from '$lib/utils';

	interface Props {
		registration: HookRegistration;
	}

	let { registration }: Props = $props();

	let sourceColors = $derived(
		getHookSourceColorVars(registration.source_type, registration.source_name)
	);

	// Language display names
	const languageLabels: Record<string, string> = {
		python: 'Python',
		node: 'Node.js',
		shell: 'Shell',
		bash: 'Shell'
	};

	let languageLabel = $derived(
		languageLabels[registration.script_language] || registration.script_language
	);
</script>

<div
	class="
		relative
		bg-[var(--bg-base)]
		border border-[var(--border)]
		rounded-lg
		p-3
		hover:border-[var(--border-hover)]
		transition-colors
		overflow-hidden
	"
	style="border-left: 4px solid {sourceColors.color};"
>
	<!-- Source and Script Info -->
	<div class="flex items-start justify-between gap-3 mb-2">
		<div class="flex-1 min-w-0">
			<div class="flex items-center gap-2 mb-1">
				<span class="text-xs font-semibold text-[var(--text-primary)]">
					{registration.source_name}
				</span>
				{#if registration.script_filename}
					<span class="text-xs text-[var(--text-muted)] truncate">
						{registration.script_filename}
					</span>
				{/if}
			</div>
		</div>

		<!-- Language Badge -->
		<span
			class="
				shrink-0
				px-2 py-0.5
				text-[10px] font-medium
				text-[var(--text-secondary)]
				bg-[var(--bg-muted)]
				rounded
			"
		>
			{languageLabel}
		</span>
	</div>

	<!-- Matcher (only if not "*") -->
	{#if registration.matcher && registration.matcher !== '*'}
		<div class="mb-2">
			<span class="text-[10px] text-[var(--text-muted)] uppercase tracking-wide"
				>Matcher:</span
			>
			<code class="ml-1.5 text-xs text-[var(--text-secondary)] font-mono">
				{registration.matcher}
			</code>
		</div>
	{/if}

	<!-- Command -->
	<div
		class="
			px-2 py-1.5
			text-xs font-mono
			text-[var(--text-secondary)]
			bg-[var(--bg-subtle)]
			border border-[var(--border-subtle)]
			rounded
			overflow-hidden
			whitespace-nowrap
			text-ellipsis
		"
		title={registration.command}
	>
		{truncate(registration.command, 80)}
	</div>
</div>

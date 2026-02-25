<script lang="ts">
	import { ChevronRight } from 'lucide-svelte';
	import McpContextBar from './McpContextBar.svelte';
	import type { McpToolSummary } from '$lib/api-types';

	interface Props {
		tool: McpToolSummary;
		serverTotalCalls: number;
		accentColor?: string;
	}

	let { tool, serverTotalCalls, accentColor = 'var(--nav-teal)' }: Props = $props();

	let proportion = $derived(serverTotalCalls > 0 ? (tool.calls / serverTotalCalls) * 100 : 0);
</script>

<div
	class="
		group
		bg-[var(--bg-base)]
		border border-[var(--border)]
		rounded-xl
		p-4
		hover:shadow-md
		transition-all duration-200
		relative overflow-hidden
	"
	style="border-left: 3px solid {accentColor};"
>
	<!-- Tool Name -->
	<div class="flex items-center justify-between mb-2">
		<h4
			class="text-sm font-semibold text-[var(--text-primary)] truncate pr-2"
			title={tool.full_name}
		>
			{tool.name}
		</h4>
		<ChevronRight
			size={14}
			class="text-[var(--text-faint)] group-hover:text-[var(--text-muted)] transition-colors flex-shrink-0"
		/>
	</div>

	<!-- Call Count -->
	<p class="text-xs text-[var(--text-muted)] mb-3 tabular-nums">
		{tool.calls.toLocaleString()} call{tool.calls !== 1 ? 's' : ''}
	</p>

	<!-- Proportion Bar -->
	<div class="h-1.5 bg-[var(--bg-subtle)] rounded-full overflow-hidden mb-3">
		<div
			class="h-full rounded-full transition-all duration-300"
			style="width: {proportion}%; background-color: {accentColor}; opacity: 0.7;"
		></div>
	</div>

	<!-- Main/Subagent Split -->
	<McpContextBar mainCalls={tool.main_calls} subagentCalls={tool.subagent_calls} compact />
</div>

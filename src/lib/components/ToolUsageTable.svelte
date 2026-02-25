<script lang="ts">
	import { Code, ChevronDown, ChevronUp, Cable } from 'lucide-svelte';
	import { parseMcpTool } from '$lib/utils/mcp';
	import type { ToolUsage } from '$lib/api-types';

	interface Props {
		tools: ToolUsage[];
		totalCalls?: number;
		class?: string;
		initialLimit?: number;
	}

	let { tools, totalCalls, class: className = '', initialLimit = 6 }: Props = $props();
	let showAll = $state(false);

	// Sort tools by count descending
	let sortedTools = $derived([...tools].sort((a, b) => b.count - a.count));
	let hasMore = $derived(sortedTools.length > initialLimit);
	let hiddenCount = $derived(sortedTools.length - initialLimit);
	let visibleTools = $derived(showAll ? sortedTools : sortedTools.slice(0, initialLimit));

	// Get max count for progress bar width
	let maxCount = $derived(Math.max(...tools.map((t) => t.count), 1));
</script>

<div
	class="
		rounded-lg border border-[var(--border)]
		bg-[var(--bg-subtle)]
		p-4
		{className}
	"
>
	<div class="flex items-center justify-between mb-4">
		<h3 class="text-sm font-medium text-[var(--text-primary)]">Tool Usage</h3>
		{#if totalCalls}
			<span class="text-xs font-mono text-[var(--text-muted)]">{totalCalls} total calls</span>
		{/if}
	</div>

	{#if sortedTools.length === 0}
		<div class="text-center py-8">
			<Code class="mx-auto h-8 w-8 text-[var(--text-muted)]" />
			<p class="mt-2 text-sm text-[var(--text-muted)]">No tools used</p>
		</div>
	{:else}
		<div class="space-y-3">
			{#each visibleTools as tool}
				{@const mcp = parseMcpTool(tool.tool_name)}
				<div class="space-y-1">
					<div class="flex items-center justify-between">
						{#if mcp}
							<span class="flex items-center gap-1.5 min-w-0 flex-1 truncate">
								<a
									href="/tools/{encodeURIComponent(mcp.server)}"
									class="inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] font-medium bg-[var(--nav-teal)]/10 text-[var(--nav-teal)] hover:bg-[var(--nav-teal)]/20 transition-colors flex-shrink-0"
									title="View {mcp.server} in MCP Tools"
								>
									<Cable size={10} />
									{mcp.server}
								</a>
								<span
									class="text-sm font-mono text-[var(--text-primary)] truncate"
									title={tool.tool_name}
								>
									{mcp.shortName}
								</span>
							</span>
						{:else}
							<span
								class="text-sm font-mono text-[var(--text-primary)] truncate"
								title={tool.tool_name}
							>
								{tool.tool_name}
							</span>
						{/if}
						<span class="text-sm font-mono text-[var(--accent)] flex-shrink-0 ml-2"
							>{tool.count}</span
						>
					</div>
					<div class="h-2 bg-[var(--bg-muted)] rounded-full overflow-hidden">
						<div
							class="h-full bg-[var(--accent)] rounded-full transition-all duration-300"
							style="width: {(tool.count / maxCount) * 100}%"
						></div>
					</div>
				</div>
			{/each}

			<!-- Show More / Show Less -->
			{#if hasMore}
				<button
					onclick={() => (showAll = !showAll)}
					class="
						flex items-center gap-1.5 w-full pt-3 mt-1
						text-xs text-[var(--text-muted)] hover:text-[var(--text-secondary)]
						border-t border-[var(--border)]
						transition-colors cursor-pointer
					"
				>
					{#if showAll}
						<ChevronUp size={14} />
						<span>Show less</span>
					{:else}
						<ChevronDown size={14} />
						<span>Show {hiddenCount} more tools</span>
					{/if}
				</button>
			{/if}
		</div>
	{/if}
</div>

<script lang="ts">
	import type { McpServer, McpToolSummary } from '$lib/api-types';
	import { formatDistanceToNow } from 'date-fns';
	import { getServerColorVars } from '$lib/utils/mcp';

	interface FlatTool extends McpToolSummary {
		serverName: string;
		serverDisplayName: string;
		lastUsed: string | null;
		pluginName: string | null;
	}

	interface Props {
		servers: McpServer[];
	}

	let { servers }: Props = $props();

	// Flatten all tools into a single list
	let allTools = $derived.by<FlatTool[]>(() => {
		const tools: FlatTool[] = [];
		for (const server of servers) {
			for (const tool of server.tools) {
				tools.push({
					...tool,
					serverName: server.name,
					serverDisplayName: server.display_name,
					lastUsed: server.last_used,
					pluginName: server.plugin_name ?? null
				});
			}
		}
		return tools;
	});

	// Sort state
	let sortKey = $state<'calls' | 'name' | 'server' | 'sessions' | 'main' | 'sub'>('calls');
	let sortDir = $state<'asc' | 'desc'>('desc');

	let sortedTools = $derived.by(() => {
		const sorted = [...allTools];
		sorted.sort((a, b) => {
			let cmp = 0;
			switch (sortKey) {
				case 'calls':
					cmp = a.calls - b.calls;
					break;
				case 'name':
					cmp = a.name.localeCompare(b.name);
					break;
				case 'server':
					cmp = a.serverDisplayName.localeCompare(b.serverDisplayName);
					break;
				case 'sessions':
					cmp = a.session_count - b.session_count;
					break;
				case 'main':
					cmp =
						(a.calls > 0 ? a.main_calls / a.calls : 0) -
						(b.calls > 0 ? b.main_calls / b.calls : 0);
					break;
				case 'sub':
					cmp =
						(a.calls > 0 ? a.subagent_calls / a.calls : 0) -
						(b.calls > 0 ? b.subagent_calls / b.calls : 0);
					break;
			}
			return sortDir === 'desc' ? -cmp : cmp;
		});
		return sorted;
	});

	function toggleSort(key: typeof sortKey) {
		if (sortKey === key) {
			sortDir = sortDir === 'desc' ? 'asc' : 'desc';
		} else {
			sortKey = key;
			sortDir = 'desc';
		}
	}

	function sortIndicator(key: typeof sortKey): string {
		if (sortKey !== key) return '';
		return sortDir === 'desc' ? ' ↓' : ' ↑';
	}
</script>

<div class="overflow-x-auto border border-[var(--border)] rounded-xl">
	<table class="w-full text-sm">
		<thead>
			<tr class="border-b border-[var(--border)] bg-[var(--bg-subtle)]">
				<th class="text-left px-4 py-3 font-medium text-[var(--text-secondary)]">
					<button
						onclick={() => toggleSort('name')}
						class="hover:text-[var(--text-primary)] transition-colors"
					>
						Tool{sortIndicator('name')}
					</button>
				</th>
				<th class="text-left px-4 py-3 font-medium text-[var(--text-secondary)]">
					<button
						onclick={() => toggleSort('server')}
						class="hover:text-[var(--text-primary)] transition-colors"
					>
						Server{sortIndicator('server')}
					</button>
				</th>
				<th class="text-right px-4 py-3 font-medium text-[var(--text-secondary)]">
					<button
						onclick={() => toggleSort('calls')}
						class="hover:text-[var(--text-primary)] transition-colors"
					>
						Calls{sortIndicator('calls')}
					</button>
				</th>
				<th
					class="text-right px-4 py-3 font-medium text-[var(--text-secondary)] hidden md:table-cell"
				>
					<button
						onclick={() => toggleSort('sessions')}
						class="hover:text-[var(--text-primary)] transition-colors"
					>
						Sessions{sortIndicator('sessions')}
					</button>
				</th>
				<th
					class="text-right px-4 py-3 font-medium text-[var(--text-secondary)] hidden lg:table-cell"
				>
					<button
						onclick={() => toggleSort('main')}
						class="hover:text-[var(--text-primary)] transition-colors"
					>
						Main %{sortIndicator('main')}
					</button>
				</th>
				<th
					class="text-right px-4 py-3 font-medium text-[var(--text-secondary)] hidden lg:table-cell"
				>
					<button
						onclick={() => toggleSort('sub')}
						class="hover:text-[var(--text-primary)] transition-colors"
					>
						Sub %{sortIndicator('sub')}
					</button>
				</th>
			</tr>
		</thead>
		<tbody>
			{#each sortedTools as tool (tool.full_name)}
				{@const toolColor = getServerColorVars(tool.serverName, tool.pluginName)}
				<tr
					class="border-b border-[var(--border)] hover:bg-[var(--bg-subtle)] transition-colors"
				>
					<td class="px-4 py-3">
						<div class="flex items-center gap-2.5">
							<span
								class="w-2 h-2 rounded-full flex-shrink-0"
								style="background-color: {toolColor.color};"
							></span>
							<a
								href="/tools/{tool.serverName}"
								class="font-medium text-[var(--text-primary)] hover:text-[var(--accent)] transition-colors"
							>
								{tool.name}
							</a>
						</div>
					</td>
					<td class="px-4 py-3">
						<a
							href="/tools/{tool.serverName}"
							class="text-[var(--text-secondary)] hover:text-[var(--accent)] transition-colors"
						>
							{tool.serverDisplayName}
						</a>
					</td>
					<td
						class="px-4 py-3 text-right tabular-nums text-[var(--text-primary)] font-medium"
					>
						{tool.calls.toLocaleString()}
					</td>
					<td
						class="px-4 py-3 text-right tabular-nums text-[var(--text-muted)] hidden md:table-cell"
					>
						{tool.session_count}
					</td>
					<td
						class="px-4 py-3 text-right tabular-nums text-[var(--text-muted)] hidden lg:table-cell"
					>
						{tool.calls > 0 ? Math.round((tool.main_calls / tool.calls) * 100) : 0}%
					</td>
					<td
						class="px-4 py-3 text-right tabular-nums text-[var(--text-muted)] hidden lg:table-cell"
					>
						{tool.calls > 0 ? Math.round((tool.subagent_calls / tool.calls) * 100) : 0}%
					</td>
				</tr>
			{/each}
		</tbody>
	</table>
</div>

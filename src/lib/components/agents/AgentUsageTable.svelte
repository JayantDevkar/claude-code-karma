<script lang="ts">
	import type { AgentUsageSummary } from '$lib/api-types';
	import { formatDistanceToNow } from 'date-fns';
	import { formatCost, getSubagentColorVars } from '$lib/utils';

	interface Props {
		agents: AgentUsageSummary[];
	}

	let { agents }: Props = $props();

	// Sort state
	let sortKey = $state<'runs' | 'name' | 'category' | 'cost' | 'duration' | 'projects' | 'last'>(
		'runs'
	);
	let sortDir = $state<'asc' | 'desc'>('desc');

	let sortedAgents = $derived.by(() => {
		const sorted = [...agents];
		sorted.sort((a, b) => {
			let cmp = 0;
			switch (sortKey) {
				case 'runs':
					cmp = a.total_runs - b.total_runs;
					break;
				case 'name':
					cmp = a.agent_name.localeCompare(b.agent_name);
					break;
				case 'category':
					cmp = a.category.localeCompare(b.category);
					break;
				case 'cost':
					cmp = a.total_cost_usd - b.total_cost_usd;
					break;
				case 'duration':
					cmp = a.avg_duration_seconds - b.avg_duration_seconds;
					break;
				case 'projects':
					cmp = a.projects_used_in.length - b.projects_used_in.length;
					break;
				case 'last':
					cmp =
						(a.last_used ? new Date(a.last_used).getTime() : 0) -
						(b.last_used ? new Date(b.last_used).getTime() : 0);
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

	function formatDuration(seconds: number): string {
		if (seconds < 60) return `${Math.round(seconds)}s`;
		return `${(seconds / 60).toFixed(1)}m`;
	}

	const categoryLabels: Record<string, string> = {
		builtin: 'Built-in',
		plugin: 'Plugin',
		custom: 'Custom',
		project: 'Project',
		claude_tax: 'Claude Tax',
		unknown: 'Unknown'
	};
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
						Agent{sortIndicator('name')}
					</button>
				</th>
				<th class="text-left px-4 py-3 font-medium text-[var(--text-secondary)]">
					<button
						onclick={() => toggleSort('category')}
						class="hover:text-[var(--text-primary)] transition-colors"
					>
						Category{sortIndicator('category')}
					</button>
				</th>
				<th class="text-right px-4 py-3 font-medium text-[var(--text-secondary)]">
					<button
						onclick={() => toggleSort('runs')}
						class="hover:text-[var(--text-primary)] transition-colors"
					>
						Runs{sortIndicator('runs')}
					</button>
				</th>
				<th
					class="text-right px-4 py-3 font-medium text-[var(--text-secondary)] hidden md:table-cell"
				>
					<button
						onclick={() => toggleSort('cost')}
						class="hover:text-[var(--text-primary)] transition-colors"
					>
						Cost{sortIndicator('cost')}
					</button>
				</th>
				<th
					class="text-right px-4 py-3 font-medium text-[var(--text-secondary)] hidden lg:table-cell"
				>
					<button
						onclick={() => toggleSort('duration')}
						class="hover:text-[var(--text-primary)] transition-colors"
					>
						Avg Duration{sortIndicator('duration')}
					</button>
				</th>
				<th
					class="text-right px-4 py-3 font-medium text-[var(--text-secondary)] hidden lg:table-cell"
				>
					<button
						onclick={() => toggleSort('projects')}
						class="hover:text-[var(--text-primary)] transition-colors"
					>
						Projects{sortIndicator('projects')}
					</button>
				</th>
				<th
					class="text-right px-4 py-3 font-medium text-[var(--text-secondary)] hidden md:table-cell"
				>
					<button
						onclick={() => toggleSort('last')}
						class="hover:text-[var(--text-primary)] transition-colors"
					>
						Last Used{sortIndicator('last')}
					</button>
				</th>
			</tr>
		</thead>
		<tbody>
			{#each sortedAgents as agent (agent.subagent_type)}
				{@const agentColor = getSubagentColorVars(agent.subagent_type)}
				<tr
					class="border-b border-[var(--border)] hover:bg-[var(--bg-subtle)] transition-colors"
				>
					<td class="px-4 py-3">
						<div class="flex items-center gap-2.5">
							<span
								class="w-2 h-2 rounded-full flex-shrink-0"
								style="background-color: {agentColor.color};"
							></span>
							<a
								href="/agents/{encodeURIComponent(agent.subagent_type)}"
								class="font-medium text-[var(--text-primary)] hover:text-[var(--accent)] transition-colors"
							>
								{agent.agent_name}
							</a>
						</div>
					</td>
					<td class="px-4 py-3">
						<span class="text-[var(--text-secondary)]">
							{categoryLabels[agent.category] || agent.category}
						</span>
					</td>
					<td
						class="px-4 py-3 text-right tabular-nums text-[var(--text-primary)] font-medium"
					>
						{agent.total_runs.toLocaleString()}
					</td>
					<td
						class="px-4 py-3 text-right tabular-nums text-[var(--text-muted)] hidden md:table-cell"
					>
						{formatCost(agent.total_cost_usd)}
					</td>
					<td
						class="px-4 py-3 text-right tabular-nums text-[var(--text-muted)] hidden lg:table-cell"
					>
						{formatDuration(agent.avg_duration_seconds)}
					</td>
					<td
						class="px-4 py-3 text-right tabular-nums text-[var(--text-muted)] hidden lg:table-cell"
					>
						{agent.projects_used_in.length}
					</td>
					<td
						class="px-4 py-3 text-right text-[var(--text-muted)] hidden md:table-cell"
					>
						{#if agent.last_used}
							{formatDistanceToNow(new Date(agent.last_used))} ago
						{:else}
							Never
						{/if}
					</td>
				</tr>
			{/each}
		</tbody>
	</table>
</div>

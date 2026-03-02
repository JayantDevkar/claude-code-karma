<script lang="ts">
	import type { SkillUsage } from '$lib/api-types';
	import { formatDistanceToNow } from 'date-fns';
	import { getSkillColorVars, cleanSkillName } from '$lib/utils';

	interface Props {
		skills: SkillUsage[];
	}

	let { skills }: Props = $props();

	// Sort state
	let sortKey = $state<'name' | 'type' | 'plugin' | 'uses' | 'sessions' | 'last'>('uses');
	let sortDir = $state<'asc' | 'desc'>('desc');

	let sortedSkills = $derived.by(() => {
		const sorted = [...skills];
		sorted.sort((a, b) => {
			let cmp = 0;
			switch (sortKey) {
				case 'name':
					cmp = a.name.localeCompare(b.name);
					break;
				case 'type':
					cmp = Number(a.is_plugin) - Number(b.is_plugin);
					break;
				case 'plugin':
					cmp = (a.plugin ?? '').localeCompare(b.plugin ?? '');
					break;
				case 'uses':
					cmp = a.count - b.count;
					break;
				case 'sessions':
					cmp = (a.session_count ?? 0) - (b.session_count ?? 0);
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
						Skill{sortIndicator('name')}
					</button>
				</th>
				<th class="text-left px-4 py-3 font-medium text-[var(--text-secondary)]">
					<button
						onclick={() => toggleSort('type')}
						class="hover:text-[var(--text-primary)] transition-colors"
					>
						Type{sortIndicator('type')}
					</button>
				</th>
				<th class="text-left px-4 py-3 font-medium text-[var(--text-secondary)]">
					<button
						onclick={() => toggleSort('plugin')}
						class="hover:text-[var(--text-primary)] transition-colors"
					>
						Plugin{sortIndicator('plugin')}
					</button>
				</th>
				<th class="text-right px-4 py-3 font-medium text-[var(--text-secondary)]">
					<button
						onclick={() => toggleSort('uses')}
						class="hover:text-[var(--text-primary)] transition-colors"
					>
						Uses{sortIndicator('uses')}
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
			{#each sortedSkills as skill (skill.name)}
				{@const skillColor = getSkillColorVars(skill.name, skill.is_plugin, skill.plugin)}
				<tr class="border-b border-[var(--border)] hover:bg-[var(--bg-subtle)] transition-colors">
					<td class="px-4 py-3">
						<div class="flex items-center gap-2.5">
							<span
								class="w-2 h-2 rounded-full flex-shrink-0"
								style="background-color: {skillColor.color};"
							></span>
							<a
								href="/skills/{encodeURIComponent(skill.name)}"
								class="font-medium text-[var(--text-primary)] hover:text-[var(--accent)] transition-colors"
							>
								{cleanSkillName(skill.name, skill.is_plugin)}
							</a>
						</div>
					</td>
					<td class="px-4 py-3">
						<span class="text-[var(--text-secondary)]">
							{skill.is_plugin ? 'Plugin' : 'Custom'}
						</span>
					</td>
					<td class="px-4 py-3">
						<span class="text-[var(--text-muted)]">
							{skill.plugin ?? '—'}
						</span>
					</td>
					<td class="px-4 py-3 text-right tabular-nums font-medium text-[var(--text-primary)]">
						{skill.count?.toLocaleString() ?? '0'}
					</td>
					<td
						class="px-4 py-3 text-right tabular-nums text-[var(--text-muted)] hidden md:table-cell"
					>
						{skill.session_count?.toLocaleString() ?? '—'}
					</td>
					<td class="px-4 py-3 text-right text-[var(--text-muted)] hidden md:table-cell">
						{#if skill.last_used}
							{formatDistanceToNow(new Date(skill.last_used))} ago
						{:else}
							Never
						{/if}
					</td>
				</tr>
			{/each}
		</tbody>
	</table>
</div>

<script lang="ts">
	import type { SkillUsage } from '$lib/api-types';
	import { getSkillColorVars, cleanSkillName } from '$lib/utils';
	import UsageTable from '$lib/components/shared/UsageTable.svelte';
	import type { UsageColumn } from '$lib/components/shared/UsageTable.svelte';

	interface Props {
		skills: SkillUsage[];
	}

	let { skills }: Props = $props();

	// Sort state
	let sortKey = $state<'name' | 'type' | 'plugin' | 'uses' | 'sessions' | 'last'>('uses');
	let sortDir = $state<'asc' | 'desc'>('desc');

	const columns: UsageColumn[] = [
		{ key: 'name', label: 'Skill' },
		{ key: 'type', label: 'Type' },
		{ key: 'plugin', label: 'Plugin' }
	];

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

	function toggleSort(key: string) {
		const k = key as typeof sortKey;
		if (sortKey === k) {
			sortDir = sortDir === 'desc' ? 'asc' : 'desc';
		} else {
			sortKey = k;
			sortDir = 'desc';
		}
	}
</script>

<UsageTable
	items={sortedSkills}
	getKey={(s) => s.name}
	{columns}
	{sortKey}
	{sortDir}
	onToggleSort={toggleSort}
>
	{#snippet customCells(skill)}
		{@const skillColor = getSkillColorVars(skill.name, skill.is_plugin, skill.plugin)}
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
	{/snippet}
</UsageTable>

<script lang="ts">
	import { Zap, ExternalLink } from 'lucide-svelte';
	import type { SkillUsage } from '$lib/api-types';
	import { cleanSkillName, getSkillColorVars } from '$lib/utils';

	interface Props {
		skills: SkillUsage[];
		projectEncodedName?: string;
	}

	let { skills, projectEncodedName }: Props = $props();

	let deduplicatedSkills = $derived.by(() => {
		const map = new Map<string, SkillUsage>();
		for (const skill of skills) {
			const existing = map.get(skill.name);
			if (existing) {
				map.set(skill.name, { ...existing, count: existing.count + skill.count });
			} else {
				map.set(skill.name, { ...skill });
			}
		}
		return [...map.values()];
	});

	let sortedSkills = $derived([...deduplicatedSkills].sort((a, b) => b.count - a.count));

	function getSkillHref(skill: SkillUsage): string {
		const encodedName = encodeURIComponent(skill.name);
		const projectParam = projectEncodedName ? `?project=${encodeURIComponent(projectEncodedName)}` : '';
		return `/skills/${encodedName}${projectParam}`;
	}
</script>

<div class="flex flex-col gap-2">
	<span class="text-[10px] uppercase tracking-wide font-medium text-[var(--text-muted)]">
		{sortedSkills.length} skill{sortedSkills.length !== 1 ? 's' : ''}
	</span>

	<div class="flex flex-col gap-1.5">
		{#each sortedSkills as skill (skill.name)}
			{@const href = getSkillHref(skill)}
			{@const cv = getSkillColorVars(skill.name, skill.is_plugin, skill.plugin)}
			{@const displayName = cleanSkillName(skill.name, skill.is_plugin)}
			<a
				{href}
				class="group flex items-center gap-2.5 px-3 py-2.5 no-underline rounded-lg border border-[var(--border)]/60 bg-[var(--bg-base)] hover:bg-[var(--bg-subtle)] hover:border-[var(--border-hover)] transition-colors"
			>
				<!-- Icon dot -->
				<span
					class="shrink-0 flex items-center justify-center w-6 h-6 rounded-md"
					style="background: {cv.subtle}; color: {cv.color};"
				>
					<Zap size={13} strokeWidth={2} />
				</span>

				<!-- Name + type -->
				<div class="flex-1 min-w-0">
					<span class="text-xs font-medium text-[var(--text-primary)] truncate block" title={skill.name}>{displayName}</span>
					<div class="flex items-center gap-1 mt-0.5">
						{#if skill.is_plugin}
							<span class="text-[10px] font-medium px-1 py-px rounded" style="background: {cv.subtle}; color: {cv.color};">Plugin</span>
							{#if skill.plugin}<span class="text-[10px] text-[var(--text-faint)] truncate">{skill.plugin}</span>{/if}
						{:else}
							<span class="text-[10px] font-medium px-1 py-px rounded bg-[var(--accent)]/10 text-[var(--accent)]">File</span>
						{/if}
					</div>
				</div>

				<!-- Count + link -->
				<div class="shrink-0 flex items-center gap-1.5">
					<span class="font-mono text-[11px] font-semibold" style="color: {cv.color};">{skill.count}×</span>
					<ExternalLink size={11} class="text-[var(--text-faint)] group-hover:text-[var(--accent)] transition-colors" />
				</div>
			</a>
		{/each}
	</div>

</div>

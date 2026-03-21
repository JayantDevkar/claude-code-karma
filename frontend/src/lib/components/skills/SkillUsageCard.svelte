<script lang="ts">
	import { goto } from '$app/navigation';
	import { Zap, Puzzle, Circle } from 'lucide-svelte';
	import UsageCard from '$lib/components/shared/UsageCard.svelte';
	import { getSkillColorVars, getSkillCategoryLabel, cleanSkillName } from '$lib/utils';
	import type { SkillCategory } from '$lib/api-types';

	interface Skill {
		name: string;
		count: number;
		is_plugin: boolean;
		plugin: string | null;
		last_used?: string | null;
		session_count?: number;
		category?: SkillCategory;
		description?: string | null;
		remote_count?: number;
		local_count?: number;
		remote_user_ids?: string[];
		is_remote_only?: boolean;
	}

	interface Props {
		skill: Skill;
		maxUsage?: number;
		class?: string;
	}

	let { skill, maxUsage = 100, class: className = '' }: Props = $props();

	let colorVars = $derived(getSkillColorVars(skill.name, skill.is_plugin, skill.plugin));
	let displayName = $derived(cleanSkillName(skill.name, skill.is_plugin));

	type BadgeVariant = 'purple' | 'emerald' | 'info' | 'accent';
	let categoryLabel = $derived(
		getSkillCategoryLabel(skill.category ?? (skill.is_plugin ? 'plugin_skill' : 'custom_skill'))
	);
	let badgeVariant = $derived<BadgeVariant>(
		skill.category === 'bundled_skill'
			? 'purple'
			: skill.category === 'plugin_skill'
				? 'emerald'
				: skill.category === 'custom_skill'
					? 'info'
					: skill.is_plugin
						? 'purple'
						: 'accent'
	);

	let detailHref = $derived(`/skills/${encodeURIComponent(skill.name)}`);
	let neverUsed = $derived(skill.count === 0);
</script>

<UsageCard
	name={skill.name}
	{displayName}
	href={detailHref}
	count={skill.count}
	{maxUsage}
	{colorVars}
	{categoryLabel}
	{badgeVariant}
	description={skill.description}
	lastUsed={skill.last_used}
	sessionCount={skill.session_count ?? null}
	{neverUsed}
	isRemoteOnly={skill.is_remote_only ?? false}
	remoteUserIds={skill.remote_user_ids ?? []}
	class={className}
>
	{#snippet icon()}
		<Zap size={22} strokeWidth={2.5} />
	{/snippet}

	{#snippet extraBadge()}
		{#if neverUsed}
			<span
				class="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-medium text-[var(--text-muted)] bg-[var(--bg-muted)]"
			>
				<Circle size={8} />
				Available
			</span>
		{/if}
	{/snippet}

	{#snippet footerOverride()}
		{#if neverUsed}
			<div class="pt-4 border-t border-[var(--border-subtle)]">
				<p class="text-xs text-[var(--text-faint)]">Invoke once to start tracking</p>
			</div>
		{/if}
	{/snippet}

	{#snippet subheader()}
		{#if skill.plugin}
			<div class="mb-4">
				<span
					role="link"
					tabindex={0}
					class="
						inline-flex items-center gap-1.5 px-2 py-1
						text-[10px] font-medium cursor-pointer
						text-[var(--text-muted)] hover:text-[var(--accent)]
						bg-[var(--bg-subtle)] hover:bg-[var(--accent-subtle)]
						rounded-full
						transition-colors
					"
					onclick={(e) => {
						e.preventDefault();
						e.stopPropagation();
						goto(`/plugins/${encodeURIComponent(skill.plugin!)}`);
					}}
					onkeydown={(e) => {
						if (e.key === 'Enter') {
							e.stopPropagation();
							goto(`/plugins/${encodeURIComponent(skill.plugin!)}`);
						}
					}}
					title="View plugin: {skill.plugin}"
				>
					<Puzzle size={10} />
					<span class="truncate max-w-[140px]">{skill.plugin}</span>
				</span>
			</div>
		{:else}
			<div class="mb-4"></div>
		{/if}
	{/snippet}
</UsageCard>

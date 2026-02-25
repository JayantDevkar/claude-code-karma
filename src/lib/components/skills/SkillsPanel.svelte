<script lang="ts">
	import { Zap, FileText, ExternalLink } from 'lucide-svelte';
	import type { SkillUsage } from '$lib/api-types';
	import EmptyState from '$lib/components/ui/EmptyState.svelte';
	import { cleanSkillName, getSkillColorVars } from '$lib/utils';

	interface Props {
		skills: SkillUsage[];
		projectEncodedName?: string;
	}

	let { skills, projectEncodedName }: Props = $props();

	// Sort skills by count (descending)
	let sortedSkills = $derived([...skills].sort((a, b) => b.count - a.count));

	// Get skill detail link
	function getSkillHref(skill: SkillUsage): string {
		const encodedName = encodeURIComponent(skill.name);
		const projectParam = projectEncodedName
			? `?project=${encodeURIComponent(projectEncodedName)}`
			: '';
		return `/skills/${encodedName}${projectParam}`;
	}
</script>

<div class="space-y-4">
	<div>
		<h2 class="text-lg font-semibold text-[var(--text-primary)]">
			Skills ({skills.length})
		</h2>
		<p class="text-sm text-[var(--text-muted)]">
			Skills invoked during this session via the /skill command
		</p>
	</div>

	{#if sortedSkills.length > 0}
		<div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
			{#each sortedSkills as skill (skill.name)}
				{@const href = getSkillHref(skill)}
				{@const skillColors = getSkillColorVars(skill.name, skill.is_plugin, skill.plugin)}
				<a
					{href}
					class="group flex items-start gap-4 p-4 bg-[var(--bg-base)] border border-[var(--border)] rounded-xl transition-all hover:border-[var(--accent)]/50 hover:shadow-sm focus:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent)] focus-visible:ring-offset-2 no-underline"
				>
					<!-- Icon -->
					<div
						class="p-2.5 rounded-lg shrink-0 transition-colors"
						style="background-color: {skillColors.subtle}; color: {skillColors.color};"
					>
						<Zap size={20} />
					</div>

					<!-- Content -->
					<div class="min-w-0 flex-1">
						<div class="flex items-center gap-2">
							<span
								class="font-medium text-[var(--text-primary)] truncate"
								title={skill.name}
							>
								{cleanSkillName(skill.name, skill.is_plugin)}
							</span>
							<ExternalLink
								size={14}
								class="text-[var(--text-muted)] group-hover:text-[var(--accent)] transition-colors shrink-0"
							/>
						</div>

						<div class="flex items-center gap-2 text-xs text-[var(--text-muted)] mt-1">
							{#if skill.is_plugin}
								{#if skill.plugin}
									<span class="inline-flex items-center gap-1.5">
										<span
											class="px-1.5 py-0.5 rounded text-[10px] uppercase font-medium"
											style="background-color: {skillColors.subtle}; color: {skillColors.color};"
										>
											Plugin
										</span>
										<span class="text-[var(--text-faint)]">{skill.plugin}</span>
									</span>
								{:else}
									<span
										class="px-1.5 py-0.5 rounded text-[10px] uppercase font-medium"
										style="background-color: {skillColors.subtle}; color: {skillColors.color};"
									>
										Plugin
									</span>
								{/if}
							{:else}
								<span
									class="px-1.5 py-0.5 bg-[var(--accent)]/10 text-[var(--accent)] rounded text-[10px] uppercase font-medium"
								>
									File
								</span>
							{/if}
						</div>
					</div>

					<!-- Count badge -->
					<div
						class="shrink-0 px-2.5 py-1 rounded-full text-xs font-medium"
						style="background-color: {skillColors.subtle}; color: {skillColors.color};"
					>
						{skill.count}x
					</div>
				</a>
			{/each}
		</div>
	{:else}
		<EmptyState
			icon={Zap}
			title="No skills used"
			description="Skills invoked via /skill commands will appear here"
		/>
	{/if}
</div>

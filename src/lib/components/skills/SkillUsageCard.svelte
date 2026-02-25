<script lang="ts">
	import { Zap, Flame, TrendingUp, Activity, Puzzle } from 'lucide-svelte';
	import Badge from '$lib/components/ui/Badge.svelte';
	import { getSkillColorVars, cleanSkillName } from '$lib/utils';

	interface Skill {
		name: string;
		count: number;
		is_plugin: boolean;
		plugin: string | null;
	}

	interface Props {
		skill: Skill;
		maxUsage?: number;
		class?: string;
	}

	let { skill, maxUsage = 100, class: className = '' }: Props = $props();

	// Determine color scheme based on skill type using consistent hash-based colors
	let colorVars = $derived(getSkillColorVars(skill.name, skill.is_plugin, skill.plugin));

	// Clean display name
	let displayName = $derived(cleanSkillName(skill.name, skill.is_plugin));

	// Badge variant based on type
	type BadgeVariant = 'purple' | 'accent';
	let badgeVariant = $derived<BadgeVariant>(skill.is_plugin ? 'purple' : 'accent');

	// Badge text
	let badgeText = $derived(skill.is_plugin ? 'Plugin' : 'Custom');

	// Calculate usage percentage for progress bar
	let usagePercentage = $derived(Math.min((skill.count / maxUsage) * 100, 100));

	// Derive usage tier
	type UsageTier = 'low' | 'medium' | 'high' | 'very-high';
	let usageTier = $derived.by<UsageTier>(() => {
		const pct = (skill.count / maxUsage) * 100;
		if (pct >= 75) return 'very-high';
		if (pct >= 50) return 'high';
		if (pct >= 25) return 'medium';
		return 'low';
	});

	// Tier configuration
	const tierConfig: Record<
		UsageTier,
		{
			bg: string;
			darkBg: string;
			icon: typeof Flame;
			iconColor: string;
			label: string;
		}
	> = {
		'very-high': {
			bg: 'rgba(251, 191, 36, 0.08)',
			darkBg: 'rgba(251, 191, 36, 0.12)',
			icon: Flame,
			iconColor: '#f59e0b',
			label: 'Hot'
		},
		high: {
			bg: 'rgba(34, 197, 94, 0.08)',
			darkBg: 'rgba(34, 197, 94, 0.12)',
			icon: TrendingUp,
			iconColor: '#22c55e',
			label: 'Trending'
		},
		medium: {
			bg: 'rgba(59, 130, 246, 0.08)',
			darkBg: 'rgba(59, 130, 246, 0.12)',
			icon: Activity,
			iconColor: '#3b82f6',
			label: 'Active'
		},
		low: {
			bg: 'rgba(156, 163, 175, 0.05)',
			darkBg: 'rgba(156, 163, 175, 0.08)',
			icon: Activity,
			iconColor: '#9ca3af',
			label: 'Low'
		}
	};

	let currentTier = $derived(tierConfig[usageTier]);

	// Build link for skill detail page
	// Route is /skills/[skill_name] which fetches both skill info and sessions
	let detailHref = $derived(`/skills/${encodeURIComponent(skill.name)}`);
</script>

<a
	href={detailHref}
	class="
			group block
			bg-[var(--bg-base)]
			border border-[var(--border)]
			rounded-xl
			p-6
			shadow-sm hover:shadow-xl hover:-translate-y-1
			transition-all duration-300
			relative overflow-hidden
			focus:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent)] focus-visible:ring-offset-2
			{className}
		"
	style="border-left: 4px solid {colorVars.color}; background: linear-gradient(135deg, {currentTier.bg} 0%, transparent 100%);"
	data-list-item
>
	<!-- Tier background overlay -->
	<div
		class="absolute inset-0 opacity-0 dark:opacity-100 transition-opacity duration-300 pointer-events-none"
		style="background: linear-gradient(135deg, {currentTier.darkBg} 0%, transparent 100%);"
	></div>

	<!-- Header row: Icon + Badge -->
	<div class="flex items-start justify-between mb-5 relative z-10">
		<div
			class="p-3 rounded-xl transition-all duration-300 group-hover:scale-110"
			style="background-color: {colorVars.subtle}; color: {colorVars.color};"
		>
			<Zap size={22} strokeWidth={2.5} />
		</div>
		<div class="flex items-center gap-2">
			{#if usageTier !== 'low'}
				<div
					class="flex items-center gap-1 px-2 py-1 rounded-full transition-all duration-300"
					style="background-color: {currentTier.bg};"
					title="{currentTier.label} usage tier"
				>
					<svelte:component
						this={currentTier.icon}
						size={12}
						strokeWidth={2.5}
						style="color: {currentTier.iconColor};"
					/>
					<span class="text-xs font-semibold" style="color: {currentTier.iconColor};">
						{currentTier.label}
					</span>
				</div>
			{/if}
			<Badge variant={badgeVariant} size="sm" rounded="full">
				{badgeText}
			</Badge>
		</div>
	</div>

	<!-- Skill name -->
	<h3
		class="text-lg font-bold text-[var(--text-primary)] mb-2 truncate pr-4 tracking-tight group-hover:text-[var(--accent)] transition-colors relative z-10"
		title={skill.name}
	>
		{displayName}
	</h3>

	<!-- Plugin source if applicable -->
	{#if skill.plugin}
		<div class="mb-4 relative z-10">
			<a
				href="/plugins/{encodeURIComponent(skill.plugin)}"
				class="
						inline-flex items-center gap-1.5 px-2 py-1
						text-[10px] font-medium
						text-[var(--text-muted)] hover:text-[var(--accent)]
						bg-[var(--bg-subtle)] hover:bg-[var(--accent-subtle)]
						rounded-full
						transition-colors
					"
				onclick={(e) => e.stopPropagation()}
				title="View plugin: {skill.plugin}"
			>
				<Puzzle size={10} />
				<span class="truncate max-w-[140px]">{skill.plugin}</span>
			</a>
		</div>
	{:else}
		<div class="mb-4"></div>
	{/if}

	<!-- Usage stat with progress bar -->
	<div class="space-y-3 relative z-10">
		<div>
			<div class="flex items-center justify-between mb-1.5">
				<span class="text-xs text-[var(--text-muted)] font-medium">Usage</span>
				<span class="text-sm font-semibold text-[var(--text-primary)] tabular-nums">
					{skill.count.toLocaleString()}
				</span>
			</div>
			<div class="h-1.5 bg-[var(--bg-subtle)] rounded-full overflow-hidden">
				<div
					class="h-full rounded-full transition-all duration-300"
					style="width: {usagePercentage}%; background-color: {colorVars.color};"
				></div>
			</div>
		</div>
	</div>
</a>

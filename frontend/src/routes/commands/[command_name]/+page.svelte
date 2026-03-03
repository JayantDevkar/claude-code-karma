<script lang="ts">
	import { navigating } from '$app/stores';
	import {
		Terminal,
		Play,
		FolderOpen,
		Zap,
		Package,
		FileText,
		TrendingUp,
		Layers,
		Sparkles
	} from 'lucide-svelte';
	import { formatDistanceToNow } from 'date-fns';
	import PageHeader from '$lib/components/layout/PageHeader.svelte';
	import StatsGrid from '$lib/components/StatsGrid.svelte';
	import SegmentedControl from '$lib/components/ui/SegmentedControl.svelte';
	import ContextSplitCard from '$lib/components/tools/ContextSplitCard.svelte';
	import McpTrendChart from '$lib/components/tools/McpTrendChart.svelte';
	import GlobalSessionCard from '$lib/components/GlobalSessionCard.svelte';
	import EmptyState from '$lib/components/ui/EmptyState.svelte';
	import Badge from '$lib/components/ui/Badge.svelte';
	import CollapsibleGroup from '$lib/components/ui/CollapsibleGroup.svelte';
	import { renderMarkdownEffect, getCommandCategoryColorVars, getCommandCategoryLabel, getCommandChartHex, getProjectNameFromEncoded } from '$lib/utils';
	import SkeletonBox from '$lib/components/skeleton/SkeletonBox.svelte';
	import SkeletonText from '$lib/components/skeleton/SkeletonText.svelte';
	import { SkeletonGlobalSessionCard } from '$lib/components/skeleton';
	import type { StatItem, SessionWithContext } from '$lib/api-types';

	let { data } = $props();

	let detail = $derived(data.detail);

	let isLoading = $derived(!!$navigating && $navigating.to?.route.id === '/commands/[command_name]');

	// Tab state
	let activeTab = $state<'overview' | 'history'>('overview');

	const tabOptions = [
		{ label: 'Overview', value: 'overview' },
		{ label: 'History', value: 'history' }
	];

	// Category colors
	let categoryColors = $derived(
		detail ? getCommandCategoryColorVars(detail.category) : { color: 'var(--accent)', subtle: 'var(--accent-subtle)' }
	);
	let categoryLabel = $derived(detail ? getCommandCategoryLabel(detail.category) : '');
	let chartAccentHex = $derived(detail ? getCommandChartHex(detail.name) : '#3b82f6');

	// Manual vs Auto breakdown
	let manualCalls = $derived(detail?.manual_calls ?? 0);
	let autoCalls = $derived(detail?.auto_calls ?? 0);
	let hasInvocationBreakdown = $derived(manualCalls > 0 || autoCalls > 0);
	let barTotal = $derived(manualCalls + autoCalls);
	let manualPercent = $derived(barTotal > 0 ? (manualCalls / barTotal) * 100 : 0);
	let autoPercent = $derived(barTotal > 0 ? (autoCalls / barTotal) * 100 : 0);

	// Stats
	let stats = $derived<StatItem[]>(
		detail
			? [
					{
						title: 'Total Calls',
						value: detail.calls.toLocaleString(),
						icon: Play,
						color: 'blue'
					},
					{
						title: 'Sessions',
						value: detail.session_count,
						icon: FolderOpen,
						color: 'green'
					},
					{
						title: 'Manual Rate',
						value:
							barTotal > 0
								? Math.round((manualCalls / barTotal) * 100) + '%'
								: '—',
						icon: Zap,
						color: 'purple'
					},
					{
						title: 'Category',
						value: categoryLabel,
						icon: Package,
						color: 'teal'
					}
				]
			: []
	);

	// Convert sessions to SessionWithContext
	function toSessionWithContext(s: any): SessionWithContext {
		return {
			uuid: s.uuid,
			slug: s.slug ?? '',
			message_count: s.message_count,
			start_time: s.start_time ?? '',
			end_time: s.end_time ?? undefined,
			duration_seconds: s.duration_seconds ?? undefined,
			models_used: s.models_used ?? [],
			subagent_count: s.subagent_count ?? 0,
			has_todos: false,
			initial_prompt: s.initial_prompt ?? undefined,
			git_branches: s.git_branches ?? [],
			session_titles: s.session_titles ?? [],
			project_encoded_name: s.project_encoded_name ?? undefined,
			project_path: s.project_encoded_name ?? '',
			project_name: s.project_display_name || getProjectNameFromEncoded(s.project_encoded_name ?? '')
		};
	}

	let sessions = $derived<SessionWithContext[]>(
		detail ? detail.sessions.map(toSessionWithContext) : []
	);

	let totalCount = $derived(detail?.sessions_total ?? 0);

	// Skill content (for user commands)
	let hasContent = $derived(detail?.content && detail.content.trim().length > 0);
	let renderedContent = $state('');
	$effect(() => {
		if (detail?.content) {
			renderMarkdownEffect(detail.content, {}, (html) => {
				renderedContent = html;
			});
		}
	});
</script>

<div class="space-y-8">
	{#if isLoading}
		<!-- Loading Skeleton -->
		<div class="space-y-6">
			<div>
				<div class="flex items-center gap-2 mb-2">
					<SkeletonText width="70px" size="xs" />
					<span class="text-[var(--text-muted)]">/</span>
					<SkeletonText width="50px" size="xs" />
					<span class="text-[var(--text-muted)]">/</span>
					<SkeletonText width="100px" size="xs" />
				</div>
				<div class="flex items-center gap-3">
					<SkeletonBox width="32px" height="32px" rounded="lg" />
					<SkeletonText width="150px" size="xl" />
				</div>
			</div>
			<div class="rounded-2xl p-8 border border-[var(--border)]">
				<div class="grid grid-cols-4 gap-6">
					{#each Array(4) as _}
						<div class="space-y-2">
							<SkeletonText width="80px" size="xs" />
							<SkeletonText width="60px" size="lg" />
						</div>
					{/each}
				</div>
			</div>
			<div class="flex items-center justify-between">
				<SkeletonBox width="200px" height="36px" rounded="lg" />
				<SkeletonText width="120px" size="sm" />
			</div>
			<div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
				{#each Array(6) as _}
					<SkeletonGlobalSessionCard />
				{/each}
			</div>
		</div>
	{:else if !detail}
		<EmptyState
			icon={Terminal}
			title="Command not found"
			description="The command you're looking for doesn't exist or couldn't be loaded."
		>
			<a
				href="/commands"
				class="text-sm text-[var(--accent)] hover:text-[var(--accent-hover)] transition-colors"
			>
				Back to Commands
			</a>
		</EmptyState>
	{:else}
		<!-- PageHeader -->
		<PageHeader
			title="/{detail.name}"
			icon={Terminal}
			iconColorRaw={categoryColors}
			breadcrumbs={[
				{ label: 'Dashboard', href: '/' },
				{ label: 'Commands', href: '/commands' },
				{ label: '/' + detail.name }
			]}
			metadata={[
				{ text: `${detail.calls.toLocaleString()} call${detail.calls !== 1 ? 's' : ''}` },
				{ text: `${detail.session_count} session${detail.session_count !== 1 ? 's' : ''}` }
			]}
		>
			{#snippet badges()}
				<span
					class="inline-flex items-center gap-1.5 px-2.5 py-1 text-xs font-medium rounded-full"
					style="color: {categoryColors.color}; background-color: {categoryColors.subtle};"
				>
					{categoryLabel}
				</span>
			{/snippet}
		</PageHeader>

		<!-- Hero Stats -->
		<div
			class="relative overflow-hidden rounded-2xl p-8 border border-[var(--border)]"
			style="background: linear-gradient(135deg, color-mix(in srgb, {categoryColors.color} 3%, transparent) 0%, color-mix(in srgb, {categoryColors.color} 8%, transparent) 100%);"
		>
			<div
				class="absolute -top-24 -right-24 w-96 h-96 opacity-10 rounded-full blur-3xl pointer-events-none"
				style="background-color: {categoryColors.color};"
			></div>
			<div class="relative space-y-4">
				<StatsGrid {stats} columns={4} />

				{#if hasInvocationBreakdown}
					<div class="flex items-center gap-4 px-1">
						<span class="text-[10px] uppercase tracking-wider font-semibold text-[var(--text-muted)] shrink-0">Invocations</span>
						<div class="flex-1 flex items-center gap-3">
							<div class="flex h-2.5 rounded-full overflow-hidden bg-[var(--bg-muted)] flex-1 max-w-xs">
								{#if manualPercent > 0}
									<div
										class="bg-blue-500 transition-all duration-300"
										style="width: {manualPercent}%"
										title="Manual: {manualCalls}"
									></div>
								{/if}
								{#if autoPercent > 0}
									<div
										class="bg-purple-500 transition-all duration-300"
										style="width: {autoPercent}%"
										title="Auto: {autoCalls}"
									></div>
								{/if}
							</div>
							<div class="flex items-center gap-3 text-[10px] text-[var(--text-secondary)]">
								<span class="flex items-center gap-1">
									<span class="w-2 h-2 rounded-full bg-blue-500"></span>
									Manual: {manualCalls}
								</span>
								<span class="flex items-center gap-1">
									<span class="w-2 h-2 rounded-full bg-purple-500"></span>
									Auto: {autoCalls}
								</span>
							</div>
						</div>
					</div>
				{/if}
			</div>
		</div>

		<!-- Description -->
		{#if detail.description}
			<div class="px-1 text-sm text-[var(--text-secondary)]">
				{detail.description}
			</div>
		{/if}

		<!-- Command Definition (for user commands with file content) -->
		{#if hasContent}
			<CollapsibleGroup title="Command Definition" open={false}>
				{#snippet icon()}
					<FileText size={16} style="color: {categoryColors.color};" />
				{/snippet}

				{#snippet children()}
					<div class="markdown-preview max-w-none prose prose-slate dark:prose-invert">
						{@html renderedContent}
					</div>
				{/snippet}
			</CollapsibleGroup>
		{/if}

		<!-- Tab Navigation -->
		<div class="flex items-center justify-between">
			<SegmentedControl options={tabOptions} bind:value={activeTab} />
			{#if detail.last_used}
				<span class="text-sm text-[var(--text-muted)]">
					Last used {formatDistanceToNow(new Date(detail.last_used))} ago
				</span>
			{/if}
		</div>

		<!-- Overview Tab -->
		{#if activeTab === 'overview'}
			<div class="grid grid-cols-1 lg:grid-cols-2 gap-6">
				<!-- Context Split Card -->
				<div
					class="bg-[var(--bg-base)] border border-[var(--border)] rounded-xl p-6 shadow-sm hover:shadow-md transition-shadow"
				>
					<ContextSplitCard
						mainCalls={detail.main_calls}
						subagentCalls={detail.subagent_calls}
						totalCalls={detail.calls}
						firstUsed={detail.first_used}
						lastUsed={detail.last_used}
						sessions={detail.sessions}
						accentColor={categoryColors.color}
					/>
				</div>

				<!-- Usage Trend -->
				{#if detail.trend && detail.trend.length > 0}
					<div
						class="bg-[var(--bg-base)] border border-[var(--border)] rounded-xl p-6 shadow-sm hover:shadow-md transition-shadow"
					>
						<div class="flex items-center gap-2 mb-6">
							<TrendingUp size={18} class="text-[var(--text-muted)]" />
							<h3 class="text-lg font-bold text-[var(--text-primary)]">Usage Trend</h3>
							<span class="text-xs text-[var(--text-muted)] ml-auto"
								>Last {detail.trend.length} days</span
							>
						</div>
						<McpTrendChart trend={detail.trend} accentColor={chartAccentHex} />
					</div>
				{/if}
			</div>

		<!-- History Tab -->
		{:else if activeTab === 'history'}
			<div class="space-y-4">
				<div class="flex items-center justify-between">
					<div class="flex items-center gap-2 text-sm text-[var(--text-muted)]">
						<Layers size={16} style="color: {categoryColors.color};" />
						<span class="font-medium text-[var(--text-primary)]">{totalCount}</span>
						<span>{totalCount === 1 ? 'session' : 'sessions'}</span>
					</div>
				</div>

				{#if sessions.length > 0}
					<div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
						{#each sessions as session (session.uuid)}
							<GlobalSessionCard {session} />
						{/each}
					</div>
				{:else}
					<EmptyState
						icon={Layers}
						title="No sessions yet"
						description="This command hasn't been used in any sessions."
					/>
				{/if}
			</div>
		{/if}
	{/if}
</div>

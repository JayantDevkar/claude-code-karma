<script lang="ts">
	import { ExternalLink, FileText, Clock, Eye, Edit3, Globe } from 'lucide-svelte';
	import { formatDistanceToNow } from 'date-fns';
	import PageHeader from '$lib/components/layout/PageHeader.svelte';
	import Card from '$lib/components/ui/Card.svelte';
	import { PlanViewer } from '$lib/components/plan';
	import { navigating } from '$app/stores';
	import { PlanDetailSkeleton } from '$lib/components/skeleton';
	import { getTeamMemberColor } from '$lib/utils';

	// Server data
	let { data } = $props();

	let isLoading = $derived(!!$navigating && $navigating.to?.route.id === '/plans/[slug]');

	// Remote plan handling
	const isRemote = $derived(!!data.remoteUser);
	const teamMemberColor = $derived(
		data.remoteUser ? getTeamMemberColor(data.remoteUser) : null
	);

	// Icon color for PageHeader — use team member color for remote plans
	const iconColorRaw = $derived(
		isRemote && teamMemberColor
			? { color: teamMemberColor.border, subtle: teamMemberColor.bg }
			: undefined
	);

	// Project encoded name for remote plan linked session links
	const remoteProjectEncoded = $derived(
		data.plan.project_encoded_name ?? null
	);

	// Format timestamp for display
	function formatTime(dateStr: string): string {
		try {
			return formatDistanceToNow(new Date(dateStr), { addSuffix: true });
		} catch {
			return dateStr;
		}
	}

	// Build breadcrumbs based on session context availability
	let breadcrumbs = $derived(() => {
		if (data.sessionContext) {
			const projectName = data.sessionContext.project_path.split('/').pop() || 'Project';
			return [
				{ label: 'Dashboard', href: '/' },
				{ label: 'Projects', href: '/projects' },
				{
					label: projectName,
					href: `/projects/${data.sessionContext.project_encoded_name}`
				},
				{
					label: data.sessionContext.session_slug,
					href: `/projects/${data.sessionContext.project_encoded_name}/${data.sessionContext.session_slug}`
				},
				{ label: 'Plan' }
			];
		}
		return [
			{ label: 'Dashboard', href: '/' },
			{ label: 'Plans', href: '/plans' },
			{ label: data.plan.title || data.slug }
		];
	});
</script>

<div class="space-y-6">
	{#if isLoading}
		<div role="status" aria-busy="true" aria-label="Loading...">
			<PlanDetailSkeleton />
		</div>
	{:else}
	<!-- Page Header with Breadcrumb -->
	<PageHeader
		title={data.plan.title || data.slug}
		icon={FileText}
		iconColorRaw={iconColorRaw}
		breadcrumbs={breadcrumbs()}
		subtitle="Updated {formatTime(
			data.plan.modified
		)} · {data.plan.word_count.toLocaleString()} words"
	>
		{#snippet headerRight()}
			<div class="flex items-center gap-3">
				{#if isRemote && data.remoteUser}
					<a
						href="/members/{encodeURIComponent(data.remoteUser)}"
						class="flex items-center gap-1 px-2 py-0.5 rounded-full border {teamMemberColor?.badge ?? ''} hover:opacity-80 transition-opacity"
						title="Remote plan from {data.remoteUser}"
					>
						<Globe size={10} strokeWidth={2} class={teamMemberColor?.text ?? ''} />
						<span class="font-medium text-[11px]">{data.remoteUser}</span>
					</a>
				{/if}
				{#if data.sessionContext}
					<a
						href="/projects/{data.sessionContext.project_encoded_name}/{data.sessionContext
							.session_slug}"
						class="inline-flex items-center gap-2 text-sm text-[var(--accent)] hover:underline"
					>
						<ExternalLink size={14} />
						View Session
					</a>
				{/if}
			</div>
		{/snippet}
	</PageHeader>

	<!-- Related Sessions Section -->
	{#if data.sessionContext}
		<Card variant="default" padding="md">
			<div class="flex items-center gap-2 mb-3">
				<Clock size={16} class="text-[var(--text-muted)]" />
				<h3 class="text-sm font-medium text-[var(--text-secondary)]">Related Sessions</h3>
			</div>
			<div class="flex flex-wrap gap-2">
				<a
					href="/projects/{data.sessionContext.project_encoded_name}/{data.sessionContext
						.session_slug}"
					class="inline-flex items-center gap-1.5 px-3 py-1.5 text-sm rounded-lg
						   bg-[var(--accent-subtle)] text-[var(--accent)] hover:bg-[var(--accent)]/20 transition-colors"
				>
					<Edit3 size={12} />
					<span class="font-medium">{data.sessionContext.session_slug}</span>
					<span class="text-[var(--text-muted)] text-xs">(created)</span>
				</a>
				{#await data.relatedSessions}
					<span
						class="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs text-[var(--text-muted)]"
					>
						Loading related sessions...
					</span>
				{:then relatedSessions}
					{#each relatedSessions as session}
						<a
							href="/projects/{session.project_encoded_name}/{session.session_slug}"
							class="inline-flex items-center gap-1.5 px-3 py-1.5 text-sm rounded-lg
								   bg-[var(--bg-subtle)] text-[var(--text-secondary)] hover:bg-[var(--bg-muted)] transition-colors"
						>
							{#if session.operation === 'read'}
								<Eye size={12} />
							{:else}
								<Edit3 size={12} />
							{/if}
							<span>{session.session_slug}</span>
							<span class="text-[var(--text-muted)] text-xs"
								>({session.operation})</span
							>
						</a>
					{/each}
				{/await}
			</div>
		</Card>
	{:else}
		{#await data.relatedSessions then relatedSessions}
			{#if relatedSessions.length > 0}
				<Card variant="default" padding="md">
					<div class="flex items-center gap-2 mb-3">
						<Clock size={16} class="text-[var(--text-muted)]" />
						<h3 class="text-sm font-medium text-[var(--text-secondary)]">
							Related Sessions
						</h3>
					</div>
					<div class="flex flex-wrap gap-2">
						{#each relatedSessions as session}
							<a
								href="/projects/{session.project_encoded_name}/{session.session_slug}"
								class="inline-flex items-center gap-1.5 px-3 py-1.5 text-sm rounded-lg
									   bg-[var(--bg-subtle)] text-[var(--text-secondary)] hover:bg-[var(--bg-muted)] transition-colors"
							>
								{#if session.operation === 'read'}
									<Eye size={12} />
								{:else}
									<Edit3 size={12} />
								{/if}
								<span>{session.session_slug}</span>
								<span class="text-[var(--text-muted)] text-xs"
									>({session.operation})</span
								>
							</a>
						{/each}
					</div>
				</Card>
			{/if}
		{/await}
	{/if}

	<!-- Linked Sessions for Remote Plans -->
	{#if isRemote && data.linkedSessions && data.linkedSessions.length > 0}
		<Card variant="default" padding="md">
			<div class="flex items-center gap-2 mb-3">
				<Globe size={16} class={teamMemberColor?.text ?? 'text-[var(--text-muted)]'} />
				<h3 class="text-sm font-medium text-[var(--text-secondary)]">Linked Sessions</h3>
			</div>
			<div class="flex flex-wrap gap-2">
				{#each data.linkedSessions as linked}
					{@const linkHref = remoteProjectEncoded
						? `/projects/${remoteProjectEncoded}/${linked.uuid.slice(0, 8)}?remote=1`
						: null}
					{#if linkHref}
						<a
							href={linkHref}
							class="inline-flex items-center gap-1.5 px-3 py-1.5 text-sm rounded-lg
								   bg-[var(--bg-subtle)] text-[var(--text-secondary)] hover:bg-[var(--bg-muted)] transition-colors"
						>
							{#if linked.operation === 'read'}
								<Eye size={12} />
							{:else}
								<Edit3 size={12} />
							{/if}
							<span class="font-mono text-xs">{linked.uuid.slice(0, 8)}</span>
							<span class="text-[var(--text-muted)] text-xs">({linked.operation})</span>
						</a>
					{:else}
						<div
							class="inline-flex items-center gap-1.5 px-3 py-1.5 text-sm rounded-lg
								   bg-[var(--bg-subtle)] text-[var(--text-secondary)]"
						>
							{#if linked.operation === 'read'}
								<Eye size={12} />
							{:else}
								<Edit3 size={12} />
							{/if}
							<span class="font-mono text-xs">{linked.uuid.slice(0, 8)}</span>
							<span class="text-[var(--text-muted)] text-xs">({linked.operation})</span>
						</div>
					{/if}
				{/each}
			</div>
		</Card>
	{/if}

	<!-- Plan Content -->
	<Card variant="default" padding="none" style={isRemote && teamMemberColor ? `background-color: ${teamMemberColor.bg}` : ''}>
		<div class="p-6 md:p-8">
			<PlanViewer plan={data.plan} embedded={true} stripFirstH1={true} />
		</div>
	</Card>
	{/if}
</div>

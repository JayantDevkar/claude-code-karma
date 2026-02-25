<script lang="ts">
	import { ExternalLink, FileText, Clock, Eye, Edit3 } from 'lucide-svelte';
	import { formatDistanceToNow } from 'date-fns';
	import PageHeader from '$lib/components/layout/PageHeader.svelte';
	import Card from '$lib/components/ui/Card.svelte';
	import { PlanViewer } from '$lib/components/plan';

	// Server data
	let { data } = $props();

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
	<!-- Page Header with Breadcrumb -->
	<PageHeader
		title={data.plan.title || data.slug}
		icon={FileText}
		breadcrumbs={breadcrumbs()}
		subtitle="Updated {formatTime(
			data.plan.modified
		)} · {data.plan.word_count.toLocaleString()} words"
	>
		{#snippet headerRight()}
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

	<!-- Plan Content -->
	<Card variant="default" padding="none">
		<div class="p-6 md:p-8">
			<PlanViewer plan={data.plan} embedded={true} stripFirstH1={true} />
		</div>
	</Card>
</div>

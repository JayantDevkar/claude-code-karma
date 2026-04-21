<script lang="ts">
	import { ConversationView } from '$lib/components/conversation';
	import type {
		SessionDetail,
		LiveSessionSummary,
		ToolUsage,
		Task,
		PlanDetail
	} from '$lib/api-types';
	import { AlertTriangle, ArrowLeft } from 'lucide-svelte';
	import { navigating } from '$app/stores';
	import { SessionDetailSkeleton } from '$lib/components/skeleton';

	let { data } = $props();

	// Use $derived to maintain reactivity when data changes
	let session = $derived(data.session as SessionDetail | null);
	let plan = $derived(data.plan as PlanDetail | null);
	let error = $derived(data.error as string | null);

	let isLoading = $derived(
		!!$navigating &&
			$navigating.to?.route.id === '/projects/[project_slug]/[session_slug]'
	);
</script>

{#if isLoading}
	<div role="status" aria-busy="true" aria-label="Loading...">
		<SessionDetailSkeleton />
	</div>
{:else if error}
	<div class="flex flex-col items-center justify-center min-h-[60vh] p-8">
		<div class="flex flex-col items-center gap-5 max-w-md text-center">
			<div
				class="flex h-14 w-14 items-center justify-center rounded-[var(--radius-md)] bg-[var(--error-subtle)] text-[var(--error)]"
			>
				<AlertTriangle size={26} strokeWidth={1.75} />
			</div>
			<h1
				class="text-3xl italic text-[var(--text-primary)]"
				style="font-family: var(--font-serif); font-weight: 400; letter-spacing: -0.02em; line-height: 1;"
			>
				Failed to load session
			</h1>
			<p class="text-sm text-[var(--text-secondary)] max-w-sm">{error}</p>
			<a
				href="/projects/{data.project_slug}"
				class="inline-flex items-center gap-2 mt-2 px-4 py-2 rounded-[var(--radius-sm)] bg-[var(--accent)] text-[var(--bg-base)] hover:bg-[var(--accent-hover)] transition-colors font-medium text-sm"
			>
				<ArrowLeft size={15} strokeWidth={1.75} />
				Back to project
			</a>
		</div>
	</div>
{:else}
	<ConversationView
		entity={session}
		encodedName={data.project_slug}
		sessionSlug={data.session_slug}
		projectPath={session?.project_path}
		liveSession={data.liveSession as LiveSessionSummary | null}
		isStarting={data.isStarting}
		timeline={session?.timeline}
		fileActivity={session?.file_activity}
		tools={session?.tools_used as unknown as ToolUsage[] | undefined}
		tasks={session?.tasks as Task[] | undefined}
		{plan}
	/>
{/if}

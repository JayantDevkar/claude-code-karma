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

	let { data } = $props();

	// Use $derived to maintain reactivity when data changes
	let session = $derived(data.session as SessionDetail | null);
	let plan = $derived(data.plan as PlanDetail | null);
	let error = $derived(data.error as string | null);
</script>

{#if error}
	<div class="flex flex-col items-center justify-center min-h-[60vh] p-8">
		<div class="flex flex-col items-center gap-4 max-w-md text-center">
			<div
				class="flex h-16 w-16 items-center justify-center rounded-full bg-[var(--error-subtle)]"
			>
				<AlertTriangle size={32} class="text-[var(--error)]" />
			</div>
			<h1 class="text-xl font-semibold text-[var(--text-primary)]">Failed to Load Session</h1>
			<p class="text-[var(--text-secondary)]">{error}</p>
			<a
				href="/projects/{data.project_slug}"
				class="inline-flex items-center gap-2 mt-4 px-4 py-2 rounded-lg bg-[var(--accent)] text-white hover:opacity-90 transition-opacity"
			>
				<ArrowLeft size={16} />
				Back to Project
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

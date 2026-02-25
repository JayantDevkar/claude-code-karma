<script lang="ts">
	import { ConversationView } from '$lib/components/conversation';
	import type {
		SubagentSessionDetail,
		TimelineEvent,
		FileActivity,
		ToolUsage,
		Task
	} from '$lib/api-types';
	import { AlertTriangle, ArrowLeft } from 'lucide-svelte';

	let { data } = $props();

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
			<h1 class="text-xl font-semibold text-[var(--text-primary)]">Failed to Load Agent</h1>
			<p class="text-[var(--text-secondary)]">{error}</p>
			<a
				href="/projects/{data.project_slug}/{data.session_slug}"
				class="inline-flex items-center gap-2 mt-4 px-4 py-2 rounded-lg bg-[var(--accent)] text-white hover:opacity-90 transition-opacity"
			>
				<ArrowLeft size={16} />
				Back to Session
			</a>
		</div>
	</div>
{:else}
	<ConversationView
		entity={data.agent as SubagentSessionDetail}
		encodedName={data.project_slug}
		sessionSlug={data.session_slug}
		parentSessionSlug={data.parent_session_slug ?? undefined}
		projectPath={data.project_path ?? undefined}
		sessionUuid={data.session_uuid ?? undefined}
		timeline={data.timeline as TimelineEvent[]}
		fileActivity={data.fileActivity as FileActivity[]}
		tools={data.tools as ToolUsage[]}
		tasks={data.tasks as Task[]}
	/>
{/if}

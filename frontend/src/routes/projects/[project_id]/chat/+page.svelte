<script lang="ts">
	import { goto } from '$app/navigation';
	import { FolderOpen, GitBranch, ArrowLeft } from 'lucide-svelte';
	import { ChatInput, LiveStreamPanel } from '$lib/components/chat';
	import type { LiveEvent } from '$lib/components/chat';
	import PageHeader from '$lib/components/layout/PageHeader.svelte';
	import { getProjectName } from '$lib/utils';
	import type { Project } from '$lib/api-types';

	let { data } = $props();
	let project = $derived(data.project as Project | null);
	let projectId = $derived(data.project_id as string);

	// ── Live stream state ─────────────────────────────────────────────────────
	let liveEvents = $state<LiveEvent[]>([]);
	let liveEventCounter = 0;
	let newSessionUuid = $state<string | null>(null);
	let hasStarted = $state(false);
	let chatInputRef = $state<{ setMessage: (text: string) => void } | null>(null);

	const SUGGESTIONS = [
		'Summarize the recent git history',
		'Run the test suite and report failures',
		'What is uncommitted in the working tree?'
	];

	function pushLiveEvent(ev: Omit<LiveEvent, 'id'>) {
		liveEvents = [...liveEvents, { ...ev, id: String(++liveEventCounter) }];
	}

	function clearLiveEvents() { liveEvents = []; }

	function handleTurnStart(userText: string) {
		clearLiveEvents();
		hasStarted = true;
		pushLiveEvent({ type: 'user_prompt', content: userText });
		pushLiveEvent({ type: 'thinking', content: '' });
	}

	function handleStreamEvent(event: Record<string, unknown>) {
		const type = event.type as string;

		if (type === 'system' && event.subtype === 'init') {
			liveEvents = liveEvents.filter((e) => e.type !== 'thinking');
			pushLiveEvent({ type: 'thinking', content: '' });
		}

		if (type === 'assistant') {
			const msg = event.message as Record<string, unknown> | undefined;
			const content = (msg?.content as unknown[]) ?? [];
			liveEvents = liveEvents.filter((e) => e.type !== 'thinking');

			for (const block of content) {
				const b = block as Record<string, unknown>;
				if (b.type === 'text' && b.text) {
					const text = b.text as string;
					const last = liveEvents[liveEvents.length - 1];
					if (last?.type === 'response_text') {
						liveEvents = [...liveEvents.slice(0, -1), { ...last, content: text }];
					} else {
						pushLiveEvent({ type: 'response_text', content: text });
					}
				} else if (b.type === 'tool_use') {
					const name = b.name as string;
					const input = b.input as Record<string, unknown> ?? {};
					let inputStr = (input.command ?? input.file_path ?? input.path ?? input.query) as string
						?? JSON.stringify(input, null, 2);
					pushLiveEvent({ type: 'tool_call', tool_name: name, content: inputStr });
					pushLiveEvent({ type: 'thinking', content: '' });
				}
			}
		}

		if (type === 'user') {
			const msg = event.message as Record<string, unknown> | undefined;
			const content = (msg?.content as unknown[]) ?? [];
			for (const block of content) {
				const b = block as Record<string, unknown>;
				if (b.type === 'tool_result') {
					liveEvents = liveEvents.filter((e) => e.type !== 'thinking');
					const raw = b.content;
					let resultStr = typeof raw === 'string' ? raw
						: Array.isArray(raw)
							? (raw as Record<string,unknown>[]).map((r) => r.text ?? r.content ?? '').join('\n')
							: JSON.stringify(raw);
					pushLiveEvent({ type: 'tool_result', content: resultStr.slice(0, 4000), is_error: !!(b.is_error) });
					pushLiveEvent({ type: 'thinking', content: '' });
				}
			}
		}

		if (type === 'result') {
			liveEvents = liveEvents.filter((e) => e.type !== 'thinking');
		}
	}

	function handleSessionCreated(uuid: string) {
		newSessionUuid = uuid;
	}

	function handleTurnComplete() {
		// Navigate to the real session page
		if (newSessionUuid) {
			goto(`/projects/${projectId}/${newSessionUuid}?tab=timeline`);
		}
	}
</script>

<div class="space-y-6">
	<PageHeader
		title="New Chat"
		icon={project?.is_git_repository ? GitBranch : FolderOpen}
		iconColor={project?.is_git_repository ? '--nav-green' : undefined}
		iconName={undefined}
		breadcrumbs={[
			{ label: 'Dashboard', href: '/' },
			{ label: 'Projects', href: '/projects' },
			{ label: project ? getProjectName(project.path) : projectId, href: `/projects/${projectId}` },
			{ label: 'New Chat' }
		]}
		subtitle={project?.path}
	>
		{#snippet headerRight()}
			<a
				href="/projects/{projectId}"
				class="inline-flex items-center gap-1.5 px-3 py-1.5 text-sm rounded-lg border border-[var(--border)] text-[var(--text-muted)] hover:text-[var(--text-primary)] hover:bg-[var(--bg-muted)] transition-colors"
			>
				<ArrowLeft size={14} strokeWidth={2} />
				Back to Project
			</a>
		{/snippet}
	</PageHeader>

	<!-- Chat area -->
	<div class="relative flex flex-col" style="min-height: 60vh;">
		<!-- Empty state / live stream -->
		<div class="flex-1 pb-2">
			{#if !hasStarted}
				<div class="max-w-xl mx-auto py-20">
					{#if project}
						<div class="font-mono text-sm mb-5">
							<span class="text-[var(--accent)] font-bold">❯</span>
							<span class="text-[var(--text-muted)] ml-1.5">{project.path}</span>
						</div>
					{/if}
					<h2 class="text-lg font-semibold text-[var(--text-primary)] mb-1.5">
						Start a new session
					</h2>
					<p class="text-sm text-[var(--text-muted)] mb-6">
						Claude works in this directory and the session lands in your project
						history like any other. Type below, or start from one of these:
					</p>
					<div class="flex flex-wrap gap-2">
						{#each SUGGESTIONS as suggestion}
							<button
								type="button"
								onclick={() => chatInputRef?.setMessage(suggestion)}
								class="px-3 py-1.5 text-sm rounded-lg border border-[var(--border)] text-[var(--text-secondary)] hover:border-[var(--accent)]/50 hover:text-[var(--text-primary)] hover:bg-[var(--bg-subtle)] transition-colors"
							>
								{suggestion}
							</button>
						{/each}
					</div>
				</div>
			{:else}
				<LiveStreamPanel events={liveEvents} visible={liveEvents.length > 0} />
			{/if}
		</div>

		<!-- Sticky chat input -->
		<ChatInput
			bind:this={chatInputRef}
			sessionUuid={null}
			projectPath={project?.path ?? null}
			autoFocus={true}
			onTurnStart={handleTurnStart}
			onStreamEvent={handleStreamEvent}
			onSessionCreated={handleSessionCreated}
			onTurnComplete={handleTurnComplete}
		/>
	</div>
</div>

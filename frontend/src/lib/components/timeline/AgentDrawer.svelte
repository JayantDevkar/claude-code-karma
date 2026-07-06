<script lang="ts">
	import { onMount, onDestroy } from 'svelte';
	import { API_BASE } from '$lib/config';
	import { Send, ExternalLink } from 'lucide-svelte';
	import type { TimelineEvent } from '$lib/api-types';

	interface Props {
		agentId: string;
		agentType: string | null;
		parentSessionUuid: string;
		encodedName: string;
	}

	let { agentId, agentType, parentSessionUuid, encodedName }: Props = $props();

	// Timeline events for this agent
	let events = $state<TimelineEvent[]>([]);
	let loading = $state(true);
	let fetchError = $state(false);

	// Live stream state
	let ws = $state<WebSocket | null>(null);
	let wsStatus = $state<'idle' | 'connecting' | 'open' | 'done' | 'error'>('idle');
	let liveLines = $state<{ id: string; type: string; text: string }[]>([]);
	let message = $state('');
	let isBusy = $state(false);
	let textareaEl: HTMLTextAreaElement | undefined = $state();
	let bottomEl: HTMLDivElement | undefined = $state();

	async function loadTimeline() {
		try {
			const r = await fetch(
				`${API_BASE}/agents/${encodedName}/${parentSessionUuid}/agents/${agentId}/timeline?fresh=1`
			);
			if (!r.ok) throw new Error();
			events = await r.json();
		} catch {
			fetchError = true;
		} finally {
			loading = false;
		}
	}

	// Try to connect WebSocket to the agent session (it may or may not be active)
	function connectWs() {
		wsStatus = 'connecting';
		const wsBase = API_BASE.replace(/^http/, 'ws');
		ws = new WebSocket(`${wsBase}/ws/chat/${agentId}`);

		ws.onopen = () => { wsStatus = 'open'; };
		ws.onclose = () => { wsStatus = ws?.readyState === WebSocket.CLOSED ? 'done' : 'error'; ws = null; };
		ws.onerror = () => { wsStatus = 'error'; };

		ws.onmessage = (e) => {
			try {
				const msg = JSON.parse(e.data);
				const type = msg.type as string;
				if (type === 'assistant') {
					const blocks = (msg.message?.content ?? []) as { type: string; text?: string }[];
					for (const b of blocks) {
						if (b.type === 'text' && b.text) {
							liveLines = [...liveLines, { id: crypto.randomUUID(), type: 'text', text: b.text }];
						}
					}
				} else if (type === 'result' || type === 'done') {
					isBusy = false;
					wsStatus = 'done';
				} else if (type === 'system') {
					// connected OK
				}
			} catch { /* ignore parse errors */ }
		};
	}

	async function send() {
		const text = message.trim();
		if (!text || isBusy) return;
		if (!ws || ws.readyState !== WebSocket.OPEN) return;
		isBusy = true;
		liveLines = [...liveLines, { id: crypto.randomUUID(), type: 'user', text }];
		message = '';
		ws.send(JSON.stringify({ type: 'human', content: text }));
	}

	function handleKey(e: KeyboardEvent) {
		if ((e.metaKey || e.ctrlKey) && e.key === 'Enter') { e.preventDefault(); send(); }
	}

	$effect(() => {
		if (liveLines.length && bottomEl) {
			bottomEl.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
		}
	});

	onMount(async () => {
		await loadTimeline();
		connectWs();
	});

	onDestroy(() => { ws?.close(); });

	// Type mapping for prefix symbols
	function prefix(et: string): string {
		switch (et) {
			case 'prompt': return '›';
			case 'thinking': return '✳';
			case 'tool_call': return '⎿';
			case 'todo_update': return '☑';
			case 'skill_invocation': return '⚡';
			default: return '•';
		}
	}
	function rowColor(et: string): string {
		switch (et) {
			case 'prompt': return 'text-[var(--text-primary)]';
			case 'thinking': return 'text-[var(--text-faint)] italic';
			case 'tool_call': return 'text-[var(--text-faint)]';
			default: return 'text-[var(--text-secondary)]';
		}
	}
</script>

<div class="flex flex-col h-full font-mono text-sm">

	<!-- Agent meta header -->
	<div class="px-5 py-3 border-b border-[var(--border)]/60 bg-[var(--bg-subtle)] flex items-center justify-between">
		<div>
			<span class="text-[var(--text-muted)] text-xs">agent</span>
			<span class="ml-2 text-[var(--text-faint)] text-xs opacity-60">{agentId.slice(0, 12)}</span>
		</div>
		<div class="flex items-center gap-3">
			{#if wsStatus === 'open'}
				<span class="flex items-center gap-1.5 text-[var(--success)] text-xs">
					<span class="w-1.5 h-1.5 rounded-full bg-[var(--success)] animate-pulse"></span>
					live
				</span>
			{:else if wsStatus === 'connecting'}
				<span class="text-[var(--text-faint)] text-xs">connecting…</span>
			{:else if wsStatus === 'done'}
				<span class="text-[var(--text-faint)] text-xs">completed</span>
			{/if}
			<a
				href="/projects/{encodedName}/agents/{agentId}"
				class="inline-flex items-center gap-1 text-xs text-[var(--text-faint)] hover:text-[var(--accent)] transition-colors"
			>
				<ExternalLink size={11} strokeWidth={2} />
				full view
			</a>
		</div>
	</div>

	<!-- Timeline scroll area -->
	<div class="flex-1 overflow-y-auto min-h-0 px-5 py-4">
		{#if loading}
			<div class="flex items-center gap-2 text-[var(--text-faint)] italic">
				<span class="animate-pulse">▊</span>
				<span>Loading…</span>
			</div>
		{:else if fetchError}
			<p class="text-[var(--text-faint)] italic">Could not load agent timeline.</p>
		{:else if events.length === 0}
			<p class="text-[var(--text-faint)] italic">No events recorded yet.</p>
		{:else}
			{#each events as ev (ev.id)}
				<div class="flex items-start gap-2 py-0.5 {rowColor(ev.event_type)}">
					<span class="shrink-0 opacity-50 mt-px">{prefix(ev.event_type)}</span>
					<span class="flex-1 whitespace-pre-wrap break-words">{ev.summary || ev.title || ''}</span>
				</div>
			{/each}
		{/if}

		<!-- Live lines streamed via WebSocket -->
		{#each liveLines as line (line.id)}
			{#if line.type === 'user'}
				<div class="flex items-baseline gap-2 py-0.5 mt-2 px-2 bg-[var(--bg-muted)] rounded-sm border-l-2 border-[var(--accent)]/50 text-[var(--text-primary)]">
					<span class="text-[var(--accent)]">›</span>
					<span class="flex-1 whitespace-pre-wrap break-words">{line.text}</span>
				</div>
			{:else}
				<div class="flex items-baseline gap-2 py-0.5 text-[var(--text-secondary)]">
					<span class="opacity-50">•</span>
					<span class="flex-1 whitespace-pre-wrap break-words">{line.text}</span>
				</div>
			{/if}
		{/each}
		<div bind:this={bottomEl}></div>
	</div>

	<!-- Chat input — only when live or open -->
	{#if wsStatus === 'open' || wsStatus === 'connecting'}
		<div class="border-t border-[var(--border)] px-4 py-3 bg-[var(--bg-subtle)]">
			<div class="flex items-end gap-2">
				<textarea
					bind:this={textareaEl}
					bind:value={message}
					onkeydown={handleKey}
					placeholder="Send a message to the agent…"
					rows={1}
					disabled={isBusy || wsStatus !== 'open'}
					class="flex-1 resize-none bg-transparent text-[var(--text-primary)] placeholder:text-[var(--text-faint)]
						text-sm font-mono leading-relaxed outline-none border-none focus:ring-0
						disabled:opacity-50 max-h-[120px] overflow-y-auto"
				></textarea>
				<button
					type="button"
					onclick={send}
					disabled={!message.trim() || isBusy || wsStatus !== 'open'}
					class="shrink-0 p-2 rounded text-[var(--text-muted)] hover:text-[var(--accent)]
						disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
					title="Send (⌘↵)"
				>
					<Send size={14} strokeWidth={2.5} />
				</button>
			</div>
		</div>
	{/if}
</div>

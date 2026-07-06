<script lang="ts">
	import { onMount, onDestroy, tick } from 'svelte';
	import { browser } from '$app/environment';
	import { Send, Square } from 'lucide-svelte';
	import { API_BASE } from '$lib/config';
	import type { LiveEvent } from './types';
	import { chatVisible } from '$lib/stores/chatVisible';

	interface Props {
		/** Existing session UUID. Omit for new-session mode. */
		sessionUuid?: string | null;
		projectPath?: string | null;
		/** Git branch for the status bar */
		branch?: string | null;
		/** Session start ISO timestamp for elapsed timer */
		sessionStart?: string | null;
		/** Known context tokens at load time (from session data) */
		contextTokens?: number | null;
		/** Called when user presses Send — gives parent the text immediately */
		onTurnStart?: (userText: string) => void;
		/** Called with each raw stream-json event */
		onStreamEvent?: (event: Record<string, unknown>) => void;
		/** Called when a turn fully completes */
		onTurnComplete?: () => void;
		/** Called when a new session is detected (new-session mode) */
		onSessionCreated?: (sessionUuid: string) => void;
		/** Auto-focus on mount */
		autoFocus?: boolean;
	}

	let {
		sessionUuid = null,
		projectPath = null,
		branch = null,
		sessionStart = null,
		contextTokens = null,
		onTurnStart,
		onStreamEvent,
		onTurnComplete,
		onSessionCreated,
		autoFocus = false,
	}: Props = $props();

	// ── Slash command definitions ─────────────────────────────────────────────
	type DirectCmd  = { cmd: string; desc: string; kind: 'direct'; category?: 'builtin' | 'skill' | 'plugin_skill' | 'agent' };
	type PickerCmd  = { cmd: string; desc: string; kind: 'picker'; label: string; options: { value: string; label: string; hint?: string }[]; category?: 'builtin' };
	type AgentCmd   = { cmd: string; desc: string; kind: 'agent'; agentName: string };
	type SlashCmd   = DirectCmd | PickerCmd | AgentCmd;

	const SLASH_COMMANDS: SlashCmd[] = [
		{ cmd: '/model',       desc: 'Switch the AI model for this session',    kind: 'picker', label: 'Choose model', category: 'builtin', options: [
			{ value: 'claude-sonnet-4-6',            label: 'Sonnet 4.6',  hint: 'Fast · balanced · default' },
			{ value: 'claude-opus-4-8',              label: 'Opus 4.8',    hint: 'Most capable · slower' },
			{ value: 'claude-haiku-4-5-20251001',    label: 'Haiku 4.5',   hint: 'Fastest · cheapest' },
		]},
		{ cmd: '/think',       desc: 'Enable brief extended thinking',          kind: 'picker', label: 'Thinking budget', category: 'builtin', options: [
			{ value: 'think',       label: 'think',       hint: 'Brief thinking (~1k tokens)' },
			{ value: 'think more',  label: 'think more',  hint: 'Medium thinking (~5k tokens)' },
			{ value: 'think hard',  label: 'think hard',  hint: 'Deep thinking (~10k tokens)' },
			{ value: 'ultrathink',  label: 'ultrathink',  hint: 'Maximum thinking (~32k tokens)' },
		]},
		{ cmd: '/compact',     desc: 'Compact conversation to free up context', kind: 'direct', category: 'builtin' },
		{ cmd: '/clear',       desc: 'Clear conversation history',              kind: 'direct', category: 'builtin' },
		{ cmd: '/cost',        desc: 'Show token usage and costs so far',       kind: 'direct', category: 'builtin' },
		{ cmd: '/memory',      desc: 'Edit CLAUDE.md memory files',             kind: 'direct', category: 'builtin' },
		{ cmd: '/review',      desc: 'Request a code review',                   kind: 'direct', category: 'builtin' },
		{ cmd: '/init',        desc: 'Init CLAUDE.md with project guidelines',  kind: 'direct', category: 'builtin' },
		{ cmd: '/status',      desc: 'Show account and subscription status',    kind: 'direct', category: 'builtin' },
		{ cmd: '/vim',         desc: 'Toggle vim keybindings',                  kind: 'direct', category: 'builtin' },
		{ cmd: '/help',        desc: 'Show help and available commands',        kind: 'direct', category: 'builtin' },
		{ cmd: '/bug',         desc: 'Report a bug to Anthropic',               kind: 'direct', category: 'builtin' },
		{ cmd: '/permissions', desc: 'View or update tool permissions',         kind: 'direct', category: 'builtin' },
		{ cmd: '/doctor',      desc: 'Check Claude Code installation health',   kind: 'direct', category: 'builtin' },
	];

	// Dynamic commands loaded from API
	let dynamicCommands = $state<SlashCmd[]>([]);

	async function loadDynamicCommands() {
		const cmds: SlashCmd[] = [];
		try {
			// 1. User skills from ~/.claude/skills/
			const rootRes = await fetch(`${API_BASE}/skills`);
			if (rootRes.ok) {
				const rootItems = await rootRes.json() as { name: string; path: string; type: string }[];
				const dirFetches: Promise<void>[] = [];
				for (const item of rootItems) {
					if (item.type === 'file') {
						const name = item.name.replace(/\.(md|txt|sh|py)$/i, '');
						cmds.push({ cmd: `/${name}`, desc: 'User skill', kind: 'direct', category: 'skill' });
					} else if (item.type === 'directory') {
						dirFetches.push(
							fetch(`${API_BASE}/skills?path=${encodeURIComponent(item.path)}`)
								.then(r => r.json())
								.then((children: { name: string; type: string }[]) => {
									if (children.some((c: { name: string; type: string }) => c.type === 'file')) {
										cmds.push({ cmd: `/${item.name}`, desc: 'User skill', kind: 'direct', category: 'skill' });
									}
								})
								.catch(() => {})
						);
					}
				}
				await Promise.all(dirFetches);
			}

			// 2. Plugin skills (superpowers:brainstorming etc.)
			const pluginRes = await fetch(`${API_BASE}/plugins/installed-skills`);
			if (pluginRes.ok) {
				const pluginSkills = await pluginRes.json() as { name: string; plugin: string }[];
				for (const s of pluginSkills) {
					cmds.push({ cmd: `/${s.name}`, desc: `Plugin · ${s.plugin.split('/').pop() ?? s.plugin}`, kind: 'direct', category: 'plugin_skill' });
				}
			}

			// 3. Custom agents from ~/.claude/agents/
			const agentsRes = await fetch(`${API_BASE}/agents`);
			if (agentsRes.ok) {
				const agents = await agentsRes.json() as { name: string }[];
				for (const a of agents) {
					// Agents aren't slash commands — selecting one inserts their name as context
					cmds.push({ cmd: `/@${a.name}`, desc: 'Custom agent — inserts as reference', kind: 'agent', agentName: a.name });
				}
			}
		} catch {
			// API not running — silently skip
		}
		dynamicCommands = cmds;
	}

	const allSlashCommands = $derived([...SLASH_COMMANDS, ...dynamicCommands]);

	// ── input state ──────────────────────────────────────────────────────────
	let message = $state('');
	let textareaEl: HTMLTextAreaElement | undefined = $state();
	let slashMenuIndex = $state(0);

	// Level-2: picker state (when a picker command is selected)
	let activePicker = $state<PickerCmd | null>(null);
	let pickerIndex  = $state(0);

	let slashMatches = $derived(
		message.startsWith('/') && !message.includes(' ') && !activePicker
			? allSlashCommands.filter(c => c.cmd.startsWith(message.toLowerCase()))
			: []
	);

	let showSlashMenu = $derived(slashMatches.length > 0 && !activePicker);

	// ── WebSocket ─────────────────────────────────────────────────────────────
	let ws: WebSocket | null = null;
	let wsStatus = $state<'disconnected' | 'connecting' | 'connected' | 'error'>('disconnected');

	// ── HUD state ─────────────────────────────────────────────────────────────
	type HudStatus = 'idle' | 'thinking' | 'tool' | 'done' | 'error';
	let hudStatus     = $state<HudStatus>('idle');
	let hudModel      = $state<string | null>(null);
	let hudTool       = $state<string | null>(null);
	let hudTokensIn   = $state<number | null>(null); // input tokens (↑)
	let hudTokensOut  = $state<number | null>(null); // output tokens (↓)
	let hudCost       = $state<number | null>(null);
	let hudError      = $state<string | null>(null);
	let isBusy        = $state(false);

	// ── Status bar & turn elapsed ─────────────────────────────────────────────
	let ctxInputTokens = $state<number | null>(contextTokens ?? null);
	let sessionElapsed = $state('');
	let elapsedTimer: ReturnType<typeof setInterval> | null = null;
	let todayCost          = $state<number | null>(null);
	let weekCost           = $state<number | null>(null);
	let fiveHourPct        = $state<number | null>(null);
	let weeklyPct          = $state<number | null>(null);
	let fiveHourResetsAt   = $state<string | null>(null); // ISO timestamp
	let fiveHourResetsIn   = $state<string | null>(null); // "Xh Ym"
	let resetsTimer: ReturnType<typeof setInterval> | null = null;

	function updateResetsIn() {
		if (!fiveHourResetsAt) { fiveHourResetsIn = null; return; }
		const ms = new Date(fiveHourResetsAt).getTime() - Date.now();
		if (ms <= 0) { fiveHourResetsIn = 'now'; return; }
		const totalMin = Math.floor(ms / 60_000);
		const h = Math.floor(totalMin / 60);
		const m = totalMin % 60;
		fiveHourResetsIn = h > 0 ? `${h}h ${m}m` : `${m}m`;
	}

	// Scroll-to-bottom state
	let atBottom = $state(true);

	function handleWindowScroll() {
		atBottom = window.scrollY + window.innerHeight >= document.body.scrollHeight - 40;
	}
	function scrollToBottom() {
		window.scrollTo({ top: document.body.scrollHeight, behavior: 'smooth' });
	}

	// Turn elapsed — ticks while busy
	let turnStartedAt = $state<number | null>(null);
	let turnElapsed   = $state('');
	let turnTimer: ReturnType<typeof setInterval> | null = null;

	function updateTurnElapsed() {
		if (turnStartedAt == null) return;
		const s = Math.floor((Date.now() - turnStartedAt) / 1000);
		const m = Math.floor(s / 60);
		turnElapsed = m > 0 ? `${m}m ${s % 60}s` : `${s}s`;
	}

	$effect(() => {
		if (isBusy) {
			turnStartedAt = Date.now();
			turnElapsed = '0s';
			turnTimer = setInterval(updateTurnElapsed, 1000);
		} else {
			if (turnTimer) { clearInterval(turnTimer); turnTimer = null; }
			turnStartedAt = null;
		}
	});

	const MODEL_CTX_LIMIT = 200_000;

	function updateElapsed() {
		if (!sessionStart) return;
		const ms = Date.now() - new Date(sessionStart).getTime();
		const totalSecs = Math.floor(ms / 1000);
		const mins = Math.floor(totalSecs / 60);
		const hrs = Math.floor(mins / 60);
		if (hrs > 0) sessionElapsed = `${hrs}h${String(mins % 60).padStart(2, '0')}m`;
		else if (mins > 0) sessionElapsed = `${mins}m${String(totalSecs % 60).padStart(2, '0')}s`;
		else sessionElapsed = `${totalSecs}s`;
	}

	function miniBar(pct: number, width = 8): { filled: string; empty: string } {
		const n = Math.min(width, Math.max(0, Math.round((pct / 100) * width)));
		return { filled: '█'.repeat(n), empty: '░'.repeat(width - n) };
	}

	let ctxPct = $derived(
		ctxInputTokens != null ? Math.min(100, Math.round((ctxInputTokens / MODEL_CTX_LIMIT) * 100)) : null
	);
	let ctxBar = $derived(ctxPct != null ? miniBar(ctxPct) : null);

	const wsBase = API_BASE.replace(/^http/, 'ws');

	function buildWsUrl(): string {
		if (sessionUuid) {
			return `${wsBase}/ws/chat/${sessionUuid}`;
		}
		const params = projectPath ? `?project_path=${encodeURIComponent(projectPath)}` : '';
		return `${wsBase}/ws/chat/new${params}`;
	}

	function connect() {
		if (ws && ws.readyState <= WebSocket.OPEN) return;
		wsStatus = 'connecting';
		ws = new WebSocket(buildWsUrl());

		ws.onopen = () => { wsStatus = 'connected'; };

		ws.onmessage = (ev) => {
			let msg: Record<string, unknown>;
			try { msg = JSON.parse(ev.data); } catch { return; }

			if (msg.type === 'session_created') {
				onSessionCreated?.(msg.session_uuid as string);
				return;
			}

			if (msg.type === 'stream' && msg.event) {
				const event = msg.event as Record<string, unknown>;
				handleStreamEvent(event);
				onStreamEvent?.(event);
			} else if (msg.type === 'done') {
				isBusy = false;
				if ((msg.exit_code as number) !== 0 && msg.stderr) {
					hudStatus = 'error';
					hudError = (msg.stderr as string).slice(0, 300);
				} else {
					hudStatus = 'done';
				}
				onTurnComplete?.();
			} else if (msg.type === 'error') {
				isBusy = false;
				hudStatus = 'error';
				hudError = (msg.message as string) ?? 'Unknown error';
			}
		};

		ws.onerror = () => {
			wsStatus = 'error';
			isBusy = false;
			hudStatus = 'error';
			hudError = 'WebSocket connection failed';
		};

		ws.onclose = () => {
			wsStatus = 'disconnected';
			ws = null;
		};
	}

	function handleStreamEvent(event: Record<string, unknown>) {
		const type = event.type as string;

		if (type === 'system' && event.subtype === 'init') {
			hudModel = (event.model as string) ?? null;
			hudStatus = 'thinking';
			hudTool = null;
		}

		if (type === 'assistant') {
			const msg = event.message as Record<string, unknown> | undefined;
			const content = (msg?.content as unknown[]) ?? [];
			const toolUse = content.find(
				(c) => (c as Record<string, unknown>).type === 'tool_use'
			);
			if (toolUse) {
				hudStatus = 'tool';
				hudTool = (toolUse as Record<string, unknown>).name as string;
			} else {
				hudStatus = 'thinking';
				hudTool = null;
			}
		}

		if (type === 'result') {
			const usage = event.usage as Record<string, number> | undefined;
			if (usage) {
				hudTokensIn  = usage.input_tokens  ?? null;
				hudTokensOut = usage.output_tokens ?? null;
				ctxInputTokens = usage.input_tokens ?? null;
			}
			hudCost = (event.total_cost_usd as number) ?? null;
			hudTool = null;
		}
	}

	async function send() {
		if (!message.trim() || isBusy) return;

		const text = message.trim();

		// Ensure connected — rebuild URL in case sessionUuid changed
		if (!ws || ws.readyState !== WebSocket.OPEN) {
			connect();
			await new Promise<void>((resolve) => {
				const deadline = Date.now() + 5000;
				const check = setInterval(() => {
					if (ws?.readyState === WebSocket.OPEN || Date.now() > deadline) {
						clearInterval(check);
						resolve();
					}
				}, 50);
			});
		}

		if (!ws || ws.readyState !== WebSocket.OPEN) {
			hudStatus = 'error';
			hudError = 'Could not connect to API';
			return;
		}

		// Tell parent immediately so it can add the user bubble to live panel
		onTurnStart?.(text);

		isBusy = true;
		hudStatus = 'thinking';
		hudError = null;
		hudTool = null;
		hudTokensIn  = null;
		hudTokensOut = null;
		hudCost = null;

		ws.send(JSON.stringify({
			type: 'message',
			text,
			project_path: projectPath ?? '',
		}));

		message = '';
		resetTextareaHeight();
	}

	function stop() {
		if (!ws || ws.readyState !== WebSocket.OPEN) return;
		ws.send(JSON.stringify({ type: 'stop' }));
		isBusy = false;
		hudStatus = 'idle';
	}

	function selectSlashCommand(cmd: SlashCmd) {
		if (cmd.kind === 'picker') {
			activePicker = cmd;
			pickerIndex = 0;
			message = cmd.cmd;
		} else if (cmd.kind === 'agent') {
			// Agents aren't real slash commands — insert as a reference the user can build on
			message = `[using agent: ${cmd.agentName}] `;
			activePicker = null;
		} else {
			message = cmd.cmd + ' ';
			activePicker = null;
		}
		slashMenuIndex = 0;
	}

	function commitPickerOption(opt: { value: string }) {
		if (!activePicker) return;
		message = activePicker.cmd + ' ' + opt.value;
		activePicker = null;
		pickerIndex = 0;
		// Auto-send picker commands immediately
		setTimeout(send, 0);
	}

	function handleKeydown(e: KeyboardEvent) {
		// Esc stops a running turn
		if (e.key === 'Escape' && isBusy) { e.preventDefault(); stop(); return; }
		// Level-2: picker navigation
		if (activePicker) {
			const opts = activePicker.options;
			if (e.key === 'ArrowDown') { e.preventDefault(); pickerIndex = (pickerIndex + 1) % opts.length; return; }
			if (e.key === 'ArrowUp')   { e.preventDefault(); pickerIndex = (pickerIndex - 1 + opts.length) % opts.length; return; }
			if (e.key === 'Tab' || e.key === 'Enter') { e.preventDefault(); commitPickerOption(opts[pickerIndex]); return; }
			if (e.key === 'Escape') { activePicker = null; message = ''; return; }
			return; // block other keys while picker is open
		}
		// Level-1: slash menu navigation
		if (showSlashMenu) {
			if (e.key === 'ArrowDown') { e.preventDefault(); slashMenuIndex = (slashMenuIndex + 1) % slashMatches.length; return; }
			if (e.key === 'ArrowUp')   { e.preventDefault(); slashMenuIndex = (slashMenuIndex - 1 + slashMatches.length) % slashMatches.length; return; }
			if (e.key === 'Tab' || e.key === 'Enter') { e.preventDefault(); selectSlashCommand(slashMatches[slashMenuIndex]); return; }
			if (e.key === 'Escape') { message = ''; return; }
		}
		if ((e.metaKey || e.ctrlKey) && e.key === 'Enter') {
			e.preventDefault();
			send();
		}
	}

	$effect(() => { if (message && !message.startsWith('/')) { slashMenuIndex = 0; activePicker = null; } });

	function autoGrow() {
		if (!textareaEl) return;
		textareaEl.style.height = 'auto';
		textareaEl.style.height = Math.min(textareaEl.scrollHeight, 220) + 'px';
	}

	function resetTextareaHeight() {
		if (!textareaEl) return;
		textareaEl.style.height = 'auto';
	}

	// ── formatted HUD values ──────────────────────────────────────────────────
	function fmtTokens(n: number | null) {
		if (n == null) return null;
		return n >= 1000 ? (n / 1000).toFixed(1) + 'k' : String(n);
	}
	let hudInFmt  = $derived(fmtTokens(hudTokensIn));
	let hudOutFmt = $derived(fmtTokens(hudTokensOut));
	let hudCostFormatted = $derived(hudCost != null ? '$' + hudCost.toFixed(4) : null);

	// Fix layout gap — keep body's padding-bottom in sync with our fixed height
	let inputWrapperEl: HTMLDivElement | undefined = $state();

	$effect(() => {
		const el = inputWrapperEl;
		if (!el) return;
		// Read from DOM directly (not a reactive var) so this runs after bind
		const syncPadding = () => {
			document.body.style.paddingBottom = el.offsetHeight + 'px';
		};
		syncPadding();
		const ro = new ResizeObserver(syncPadding);
		ro.observe(el);
		return () => {
			ro.disconnect();
			document.body.style.paddingBottom = '';
		};
	});

	onMount(() => {
		connect();
		loadDynamicCommands();
		chatVisible.set(true);
		if (autoFocus) textareaEl?.focus();
		if (sessionStart) {
			updateElapsed();
			elapsedTimer = setInterval(updateElapsed, 10_000);
		}

		fetch(`${API_BASE}/analytics/spend-summary`)
			.then(r => r.json())
			.then(d => { todayCost = d.today_cost; weekCost = d.week_cost; })
			.catch(() => {});

		fetch(`${API_BASE}/analytics/usage-limits`)
			.then(r => r.json())
			.then(d => {
				fiveHourPct = d.five_hour_pct;
				weeklyPct = d.weekly_pct;
				fiveHourResetsAt = d.five_hour_resets_at ?? null;
				updateResetsIn();
				resetsTimer = setInterval(updateResetsIn, 30_000);
			})
			.catch(() => {});

		window.addEventListener('scroll', handleWindowScroll, { passive: true });
		handleWindowScroll();
	});

	onDestroy(() => {
		ws?.close();
		chatVisible.set(false);
		if (elapsedTimer) clearInterval(elapsedTimer);
		if (turnTimer) clearInterval(turnTimer);
		if (resetsTimer) clearInterval(resetsTimer);
		// onDestroy also runs during SSR, where document/window don't exist
		if (browser) {
			document.body.style.paddingBottom = '';
			window.removeEventListener('scroll', handleWindowScroll);
		}
	});

	// Expose focus for external callers
	export function focus() { textareaEl?.focus(); }
	export function setMessage(text: string) {
		message = text;
		textareaEl?.focus();
		tick().then(autoGrow);
	}
	export function resetHud() {
		hudStatus = 'idle';
		hudError = null;
		hudTool = null;
		hudTokensIn  = null;
		hudTokensOut = null;
		hudCost = null;
	}
</script>

<!-- Fixed to viewport bottom, width-constrained to match layout -->
<div class="fixed bottom-0 left-0 right-0 z-20" bind:this={inputWrapperEl}>

	<!-- Scroll-to-bottom arrow — centered just above the input -->
	{#if !atBottom}
		<div class="flex justify-center mb-2">
			<button
				type="button"
				onclick={scrollToBottom}
				class="w-8 h-8 rounded-full flex items-center justify-center
					bg-[var(--bg-base)] border border-[var(--border)] text-[var(--text-primary)]
					shadow-lg hover:bg-[var(--bg-muted)] transition-colors"
				aria-label="Scroll to bottom"
			>
				<svg width="14" height="14" viewBox="0 0 14 14" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
					<path d="M7 2v10M3 8l4 4 4-4"/>
				</svg>
			</button>
		</div>
	{/if}

	<!-- Width-constrained input card -->
	<div class="max-w-[1200px] mx-auto px-5">
<div
	class="bg-[var(--bg-base)] rounded-t-xl overflow-hidden border border-[var(--border)]/60 border-b-0"
	style="box-shadow: 0 -4px 24px -4px rgba(0,0,0,0.1);"
>
	<!-- Slash command menu — level 1 -->
	{#if showSlashMenu}
		<div class="border-b border-[var(--border)]/60 bg-[var(--bg-subtle)] max-h-64 overflow-y-auto">
			{#each slashMatches as item, i}
				{@const cat = 'category' in item ? item.category : item.kind === 'agent' ? 'agent' : undefined}
				<button
					type="button"
					onclick={() => { selectSlashCommand(item); textareaEl?.focus(); }}
					class="w-full flex items-center gap-2 px-4 py-2 text-left transition-colors {i === slashMenuIndex ? 'bg-[var(--accent)]/10 border-l-2 border-[var(--accent)]' : 'hover:bg-[var(--bg-muted)] border-l-2 border-transparent'}"
				>
					<!-- Category badge -->
					{#if cat === 'skill'}
						<span class="shrink-0 text-[8px] font-bold uppercase tracking-wider text-[var(--accent)] w-10">skill</span>
					{:else if cat === 'plugin_skill'}
						<span class="shrink-0 text-[8px] font-bold uppercase tracking-wider text-[var(--nav-purple)] w-10">plugin</span>
					{:else if cat === 'agent'}
						<span class="shrink-0 text-[8px] font-bold uppercase tracking-wider text-[var(--nav-green)] w-10">agent</span>
					{:else}
						<span class="shrink-0 w-10"></span>
					{/if}
					<span class="font-mono text-sm font-semibold text-[var(--accent)] shrink-0 min-w-0 truncate max-w-[180px]">{item.cmd}</span>
					<span class="text-xs text-[var(--text-muted)] truncate flex-1">{item.desc}</span>
					{#if item.kind === 'picker'}
						<span class="ml-auto text-[10px] text-[var(--text-faint)] shrink-0">options →</span>
					{:else if item.kind === 'agent'}
						<span class="ml-auto text-[10px] text-[var(--text-faint)] shrink-0">inserts ref</span>
					{/if}
				</button>
			{/each}
			<div class="px-4 py-1.5 border-t border-[var(--border)]/40 flex gap-4 text-xs text-[var(--text-faint)]">
				<span><kbd class="font-mono font-bold">↑↓</kbd> navigate</span>
				<span><kbd class="font-mono font-bold">Tab</kbd> or <kbd class="font-mono font-bold">↵</kbd> select</span>
				<span><kbd class="font-mono font-bold">Esc</kbd> dismiss</span>
			</div>
		</div>
	{/if}

	<!-- Level-2 picker (model, think level, etc.) -->
	{#if activePicker}
		<div class="border-b border-[var(--border)]/60 bg-[var(--bg-subtle)]">
			<div class="flex items-center gap-2 px-4 py-2 border-b border-[var(--border)]/40">
				<span class="font-mono text-sm font-bold text-[var(--accent)]">{activePicker.cmd}</span>
				<span class="text-xs text-[var(--text-faint)]">·</span>
				<span class="text-sm text-[var(--text-muted)]">{activePicker.label}</span>
			</div>
			{#each activePicker.options as opt, i}
				<button
					type="button"
					onclick={() => { commitPickerOption(opt); textareaEl?.focus(); }}
					class="w-full flex items-center gap-3 px-4 py-2.5 text-left transition-colors {i === pickerIndex ? 'bg-[var(--accent)]/10 border-l-2 border-[var(--accent)]' : 'hover:bg-[var(--bg-muted)] border-l-2 border-transparent'}"
				>
					<span class="font-mono text-sm font-semibold text-[var(--text-primary)] w-40 shrink-0">{opt.label}</span>
					{#if opt.hint}
						<span class="text-xs text-[var(--text-muted)]">{opt.hint}</span>
					{/if}
				</button>
			{/each}
			<div class="px-4 py-1.5 border-t border-[var(--border)]/40 flex gap-4 text-xs text-[var(--text-faint)]">
				<span><kbd class="font-mono font-bold">↑↓</kbd> navigate</span>
				<span><kbd class="font-mono font-bold">↵</kbd> select & send</span>
				<span><kbd class="font-mono font-bold">Esc</kbd> back</span>
			</div>
		</div>
	{/if}

	<!-- Input row -->
	<div class="flex items-end gap-2 px-3 py-2.5">
		<textarea
			bind:this={textareaEl}
			bind:value={message}
			oninput={autoGrow}
			onkeydown={handleKeydown}
			placeholder={isBusy ? 'Claude is working...' : sessionUuid ? 'Continue this session… or type / for commands' : 'Start a new session… or type / for commands'}
			rows={1}
			disabled={wsStatus === 'error'}
			class="
				flex-1 resize-none overflow-hidden
				bg-[var(--bg-subtle)] border border-[var(--border)]
				rounded-xl px-3.5 py-2.5
				text-sm text-[var(--text-primary)]
				placeholder:text-[var(--text-faint)]
				focus:outline-none focus:border-[var(--accent)]/50 focus:ring-1 focus:ring-[var(--accent)]/20
				disabled:opacity-40
				transition-[border-color,box-shadow] duration-150
				leading-relaxed
			"
			style="min-height: 40px; max-height: 220px;"
		></textarea>

		{#if isBusy}
			<button
				type="button"
				onclick={stop}
				class="shrink-0 flex items-center justify-center w-9 h-9 rounded-xl bg-[var(--error)]/10 border border-[var(--error)]/25 text-[var(--error)] hover:bg-[var(--error)]/20 transition-colors"
				title="Stop generation"
			>
				<Square size={13} strokeWidth={2.5} fill="currentColor" />
			</button>
		{:else}
			<button
				type="button"
				onclick={send}
				disabled={!message.trim() || wsStatus === 'error'}
				class="
					shrink-0 flex items-center justify-center w-9 h-9 rounded-xl
					bg-[var(--accent)] text-white
					hover:opacity-90 active:scale-95
					disabled:opacity-30 disabled:cursor-not-allowed
					transition-all duration-100
				"
				title="Send (⌘↵)"
			>
				<Send size={14} strokeWidth={2.5} />
			</button>
		{/if}
	</div>

	<!-- Terminal-style statusline — the single meta bar for state + telemetry -->
	<div
		class="flex items-center px-4 py-1.5 font-mono text-xs overflow-x-auto whitespace-nowrap gap-0 transition-colors
			{isBusy ? 'border-t-2 border-[var(--accent)]' : 'border-t border-[var(--border)]/30'}"
	>
		<!-- Status segment (always first) -->
		{#if isBusy}
			<span class="text-[var(--accent)] animate-spin inline-block shrink-0 mr-1.5" style="animation-duration:0.8s">✳</span>
			<span class="text-[var(--text-primary)] font-semibold">{hudStatus === 'tool' && hudTool ? hudTool : 'Thinking…'}</span>
			<span class="ml-1.5 text-[var(--nav-amber)]">{turnElapsed}</span>
			{#if hudInFmt}<span class="ml-2 text-[var(--text-muted)]">↑ {hudInFmt}</span>{/if}
			{#if hudOutFmt}<span class="ml-2 text-[var(--text-muted)]">↓ {hudOutFmt}</span>{/if}
		{:else if hudStatus === 'done'}
			<span class="text-[var(--success)] mr-1.5">✓</span>
			<span class="text-[var(--text-muted)]">done</span>
			{#if hudInFmt}<span class="ml-2 text-[var(--text-muted)]">↑ {hudInFmt}</span>{/if}
			{#if hudOutFmt}<span class="ml-1.5 text-[var(--text-muted)]">↓ {hudOutFmt}</span>{/if}
			{#if hudCostFormatted}<span class="ml-1.5 text-[var(--text-muted)]">{hudCostFormatted}</span>{/if}
		{:else if hudStatus === 'error'}
			<span class="text-[var(--error)] mr-1.5">✗</span>
			<span class="text-[var(--error)] truncate max-w-[320px]" title={hudError}>{hudError}</span>
		{:else if wsStatus === 'error'}
			<button onclick={connect} class="text-[var(--error)] hover:underline">✗ disconnected — retry</button>
		{:else if wsStatus === 'connecting'}
			<span class="text-[var(--text-faint)]">connecting…</span>
		{:else}
			<span class="text-[var(--text-faint)]">{hudModel ?? 'ready'}</span>
		{/if}

		{#if branch}
			<span class="mx-3 text-[var(--border)]">│</span>
			<span class="text-[var(--accent)] font-bold">{branch}</span>
		{/if}
		{#if sessionElapsed}
			<span class="mx-3 text-[var(--border)]">│</span>
			<span class="text-[var(--text-faint)]">session </span>
			<span class="text-[var(--nav-orange)] ml-1">{sessionElapsed}</span>
		{/if}
		{#if ctxPct != null && ctxBar}
			<span class="mx-3 text-[var(--border)]">│</span>
			<span class="text-[var(--text-faint)]">ctx [</span><span style="color: {ctxPct > 80 ? 'var(--error)' : ctxPct > 50 ? 'var(--nav-orange)' : 'var(--success)'};">{ctxBar.filled}</span><span class="text-[var(--text-faint)] opacity-40">{ctxBar.empty}</span><span class="text-[var(--text-faint)]">]</span><span class="ml-1 text-[var(--text-secondary)]">{ctxPct}%</span>
		{/if}
		{#if hudCost != null && !isBusy}
			<span class="mx-3 text-[var(--border)]">│</span>
			<span class="text-[var(--text-faint)]">turn </span>
			<span class="text-[var(--text-secondary)] ml-1">${hudCost.toFixed(4)}</span>
		{/if}
		{#if fiveHourPct != null}
			{@const b5 = miniBar(fiveHourPct)}
			<span class="mx-3 text-[var(--border)]">│</span>
			<span class="text-[var(--text-faint)]">5h [</span><span style="color: {fiveHourPct > 80 ? 'var(--error)' : fiveHourPct > 50 ? 'var(--nav-orange)' : 'var(--success)'};">{b5.filled}</span><span class="text-[var(--text-faint)] opacity-40">{b5.empty}</span><span class="text-[var(--text-faint)]">]</span><span class="ml-1 text-[var(--text-secondary)]">{fiveHourPct}%</span>
		{/if}
		{#if weeklyPct != null}
			{@const bw = miniBar(weeklyPct)}
			<span class="mx-3 text-[var(--border)]">│</span>
			<span class="text-[var(--text-faint)]">wk [</span><span style="color: {weeklyPct > 80 ? 'var(--error)' : weeklyPct > 50 ? 'var(--nav-orange)' : 'var(--success)'};">{bw.filled}</span><span class="text-[var(--text-faint)] opacity-40">{bw.empty}</span><span class="text-[var(--text-faint)]">]</span><span class="ml-1 text-[var(--text-secondary)]">{weeklyPct}%</span>
		{/if}
		{#if fiveHourResetsIn}
			<span class="mx-3 text-[var(--border)]">│</span>
			<span class="text-[var(--text-faint)]">resets in </span>
			<span class="ml-1 text-[var(--text-secondary)]">{fiveHourResetsIn}</span>
		{/if}

		<!-- Right side: permission mode + send hint -->
		<span class="ml-auto pl-4 flex items-center gap-3 shrink-0">
			<span class="text-[var(--nav-amber)]" title="All tool permissions are auto-approved in this session">⏵⏵ auto-approve</span>
			{#if !isBusy}
				<span class="hidden sm:inline text-[var(--text-faint)]">⌘↵ send</span>
			{:else}
				<span class="hidden sm:inline text-[var(--text-faint)]">esc stop</span>
			{/if}
		</span>
	</div>
</div><!-- inner rounded container -->
	</div><!-- max-width wrapper -->
</div><!-- fixed viewport wrapper -->

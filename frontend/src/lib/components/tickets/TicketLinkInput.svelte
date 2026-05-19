<script lang="ts">
	import type { CreateLinkRequest, CreateLinkResponse, TicketProvider } from '$lib/api-types';
	import { API_BASE } from '$lib/config';
	import {
		PROVIDER_META,
		detectProviderFromRef,
		isAmbiguousKey
	} from '$lib/ticket-helpers';
	import {
		Plus,
		Loader2,
		Check,
		AlertCircle,
		Sparkles,
		ChevronDown
	} from 'lucide-svelte';

	interface Props {
		sessionUuid: string;
		sessionSlug?: string | null;
		onCreated?: (response: CreateLinkResponse) => void;
	}

	let { sessionUuid, sessionSlug, onCreated }: Props = $props();

	type State = 'idle' | 'typing' | 'validating' | 'error' | 'success';

	let ref = $state('');
	let providerHint = $state<TicketProvider | ''>('');
	let phase = $state<State>('idle');
	let error = $state<{ headline: string; hint: string | null } | null>(null);

	// Detection results — recomputed reactively
	let trimmed = $derived(ref.trim());
	let detected = $derived(detectProviderFromRef(trimmed));
	let needsHint = $derived(!detected && isAmbiguousKey(trimmed));
	let effectiveProvider = $derived(
		detected ?? (providerHint as TicketProvider | '') ?? ''
	);

	let canSubmit = $derived(
		trimmed.length > 0 &&
			phase !== 'validating' &&
			phase !== 'success' &&
			(!needsHint || providerHint.length > 0)
	);

	function onInput(e: Event) {
		const v = (e.target as HTMLInputElement).value;
		ref = v;
		// Any user input from a terminal phase returns us to typing/idle.
		error = null;
		phase = v.trim() ? 'typing' : 'idle';
	}

	async function submit(e: Event) {
		e.preventDefault();
		if (!canSubmit) return;

		phase = 'validating';
		error = null;

		const body: CreateLinkRequest = {
			ref: trimmed,
			source: 'dashboard',
			...(sessionSlug ? { session_slug: sessionSlug } : {}),
			...(needsHint && providerHint ? { provider: providerHint as TicketProvider } : {})
		};

		try {
			const res = await fetch(`${API_BASE}/sessions/${sessionUuid}/tickets`, {
				method: 'POST',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify(body)
			});
			if (!res.ok) {
				const detail = await res.json().catch(() => null);
				const hint = detail?.detail?.hint ?? detail?.detail?.error ?? null;
				const headline =
					typeof detail?.detail === 'string'
						? detail.detail
						: detail?.detail?.error ?? `Couldn't link (HTTP ${res.status})`;
				error = { headline: String(headline), hint: hint ? String(hint) : null };
				phase = 'error';
				return;
			}
			const data = (await res.json()) as CreateLinkResponse;
			phase = 'success';
			onCreated?.(data);
			// Hold the success phase briefly, then reset
			setTimeout(() => {
				ref = '';
				providerHint = '';
				phase = 'idle';
			}, 1200);
		} catch (err) {
			error = {
				headline: err instanceof Error ? err.message : String(err),
				hint: null
			};
			phase = 'error';
		}
	}
</script>

<form onsubmit={submit} class="flex flex-col gap-1.5 w-full">
	<div class="flex items-stretch gap-2 w-full">
		<!-- Input + in-input affordance -->
		<div class="relative flex-1 min-w-0">
			<input
				type="text"
				placeholder="Paste URL or ref (e.g. LINEAR-123, owner/repo#42)"
				value={ref}
				oninput={onInput}
				disabled={phase === 'validating' || phase === 'success'}
				class="w-full px-3 py-1.5 text-sm rounded-md bg-[var(--bg-base)] text-[var(--text-primary)] border transition-[border-color,box-shadow,background] duration-150 outline-none
					{phase === 'error'
					? 'border-[var(--error)] shadow-[0_0_0_3px_var(--error-subtle)]'
					: phase === 'success'
						? 'border-[var(--success)] shadow-[0_0_0_3px_var(--success-subtle)]'
						: phase === 'typing' || phase === 'validating'
							? 'border-[var(--accent)] shadow-[0_0_0_3px_var(--accent-subtle)]'
							: 'border-[var(--border)] hover:border-[var(--border-hover)]'}
					{ref ? 'font-mono' : ''}"
			/>
			{#if detected && (phase === 'typing' || phase === 'validating')}
				<div
					class="absolute right-2.5 top-1/2 -translate-y-1/2 inline-flex items-center gap-1.5 pointer-events-none"
				>
					{#if phase === 'validating'}
						<span
							class="inline-block w-1.5 h-1.5 rounded-full animate-pulse"
							style="background: var(--accent)"
						></span>
						<span class="text-[10px] uppercase tracking-wider text-[var(--text-muted)] font-semibold">
							checking…
						</span>
					{:else}
						<Check size={11} class="text-[var(--success)]" />
						<span class="text-[10px] uppercase tracking-wider text-[var(--text-secondary)] font-semibold">
							{PROVIDER_META[detected].label}
						</span>
					{/if}
				</div>
			{/if}
		</div>

		{#if needsHint}
			<label class="inline-flex items-center gap-1.5 px-2 text-xs text-[var(--text-secondary)] rounded-md border border-[var(--border)] bg-[var(--bg-base)]">
				<span class="text-[10px] uppercase tracking-wider text-[var(--text-faint)] font-semibold">as</span>
				<select
					bind:value={providerHint}
					disabled={phase === 'validating'}
					class="bg-transparent text-sm py-1 pr-1 outline-none"
					aria-label="Provider"
				>
					<option value="" disabled>provider…</option>
					<option value="linear">Linear</option>
					<option value="jira">Jira</option>
				</select>
				<ChevronDown size={11} class="text-[var(--text-muted)] -ml-1" />
			</label>
		{/if}

		<button
			type="submit"
			disabled={!canSubmit}
			class="inline-flex items-center gap-1.5 px-3 py-1.5 text-sm font-medium rounded-md text-white transition-all duration-150 disabled:opacity-40 disabled:cursor-not-allowed
				{phase === 'success' ? 'bg-[var(--success)]' : 'bg-[var(--accent)] hover:bg-[var(--accent-hover)]'}"
		>
			{#if phase === 'validating'}
				<Loader2 size={14} class="animate-spin" />
				Linking…
			{:else if phase === 'success'}
				<Check size={14} />
				Linked
			{:else}
				<Plus size={14} />
				Link
			{/if}
		</button>
	</div>

	<!-- Below-input feedback row -->
	{#if phase === 'idle'}
		<p class="text-[11px] text-[var(--text-faint)] inline-flex items-center gap-1.5 m-0">
			<Sparkles size={10} />
			<span>
				Or use
				<code class="font-mono px-1 py-px rounded bg-[var(--bg-muted)] text-[var(--text-secondary)]">/link</code>
				in this session, or push a branch named
				<code class="font-mono px-1 py-px rounded bg-[var(--bg-muted)] text-[var(--text-secondary)]">feat/OCC-1284-…</code>
			</span>
		</p>
	{:else if phase === 'typing' && detected}
		<p class="text-[11px] text-[var(--text-secondary)] inline-flex items-center gap-1.5 m-0">
			<Check size={10} class="text-[var(--success)]" />
			Recognized as <strong class="font-semibold text-[var(--text-primary)]">{PROVIDER_META[detected].label}</strong> ·
			press
			<code class="font-mono px-1 py-px rounded bg-[var(--bg-muted)] text-[var(--text-secondary)]">↵</code>
			to link
		</p>
	{:else if phase === 'typing' && needsHint}
		<p class="text-[11px] text-[var(--text-muted)] m-0">
			Ambiguous key — pick a provider on the right.
		</p>
	{:else if phase === 'validating'}
		<p class="text-[11px] text-[var(--text-muted)] inline-flex items-center gap-1.5 m-0">
			<span class="inline-block w-1.5 h-1.5 rounded-full animate-pulse" style="background: var(--accent)"></span>
			Fetching metadata via MCP — falls back to ref-only if unreachable.
		</p>
	{:else if phase === 'error' && error}
		<div
			class="text-[11px] text-[var(--error)] inline-flex items-start gap-1.5 px-2.5 py-1.5 rounded bg-[var(--error-subtle)] m-0"
			role="alert"
		>
			<AlertCircle size={11} class="mt-px shrink-0" />
			<div>
				<strong class="font-semibold">{error.headline}</strong>
				{#if error.hint}
					<div class="text-[var(--text-secondary)] mt-0.5">{error.hint}</div>
				{/if}
			</div>
		</div>
	{:else if phase === 'success'}
		<p class="text-[11px] text-[var(--success)] inline-flex items-center gap-1.5 m-0">
			<Check size={11} />
			Linked. <span class="text-[var(--text-secondary)]">You can paste another, or close.</span>
		</p>
	{/if}
</form>

<script lang="ts">
	import type { CreateLinkRequest, CreateLinkResponse, TicketProvider } from '$lib/api-types';
	import { API_BASE } from '$lib/config';
	import { Plus, Loader2 } from 'lucide-svelte';

	interface Props {
		sessionUuid: string;
		sessionSlug?: string | null;
		onCreated?: (response: CreateLinkResponse) => void;
	}

	let { sessionUuid, sessionSlug, onCreated }: Props = $props();

	let ref = $state('');
	let provider = $state<TicketProvider | ''>('');
	let busy = $state(false);
	let error = $state<string | null>(null);

	// Provider hint required only when the input is a bare key like ABC-123
	// (i.e., no URL scheme, no '/', no '#').
	let needsProviderHint = $derived(
		ref.trim().length > 0 &&
			!/^https?:/i.test(ref) &&
			!ref.includes('/') &&
			!ref.includes('#')
	);

	async function submit(e: Event) {
		e.preventDefault();
		const refValue = ref.trim();
		if (!refValue || busy) return;
		busy = true;
		error = null;

		const body: CreateLinkRequest = {
			ref: refValue,
			source: 'dashboard',
			...(sessionSlug ? { session_slug: sessionSlug } : {}),
			...(needsProviderHint && provider ? { provider: provider as TicketProvider } : {})
		};

		try {
			const res = await fetch(`${API_BASE}/sessions/${sessionUuid}/tickets`, {
				method: 'POST',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify(body)
			});
			if (!res.ok) {
				const detail = await res.json().catch(() => null);
				const hint = detail?.detail?.hint || detail?.detail?.error || `HTTP ${res.status}`;
				error = String(hint);
				return;
			}
			const data = (await res.json()) as CreateLinkResponse;
			ref = '';
			provider = '';
			onCreated?.(data);
		} catch (e) {
			error = e instanceof Error ? e.message : String(e);
		} finally {
			busy = false;
		}
	}
</script>

<form onsubmit={submit} class="flex flex-col gap-2 w-full">
	<div class="flex items-center gap-2 w-full">
		<input
			type="text"
			placeholder="Paste URL or ref (e.g. LINEAR-123, owner/repo#42)"
			bind:value={ref}
			disabled={busy}
			class="flex-1 px-3 py-1.5 text-sm rounded-md border border-[var(--border)] bg-[var(--bg-base)] text-[var(--text-primary)] focus:outline-none focus:ring-1 focus:ring-[var(--accent)]"
		/>
		{#if needsProviderHint}
			<select
				bind:value={provider}
				disabled={busy}
				class="px-2 py-1.5 text-sm rounded-md border border-[var(--border)] bg-[var(--bg-base)] text-[var(--text-primary)]"
				aria-label="Provider"
			>
				<option value="" disabled>provider…</option>
				<option value="linear">Linear</option>
				<option value="jira">Jira</option>
			</select>
		{/if}
		<button
			type="submit"
			disabled={busy || ref.trim().length === 0 || (needsProviderHint && !provider)}
			class="inline-flex items-center gap-1.5 px-3 py-1.5 text-sm rounded-md bg-[var(--accent)] text-white hover:opacity-90 disabled:opacity-40 disabled:cursor-not-allowed transition-opacity"
		>
			{#if busy}
				<Loader2 size={14} class="animate-spin" />
			{:else}
				<Plus size={14} />
			{/if}
			Link
		</button>
	</div>
	{#if error}
		<p class="text-xs text-[var(--error)]">{error}</p>
	{/if}
</form>

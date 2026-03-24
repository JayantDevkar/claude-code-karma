<script lang="ts">
	import { onMount } from 'svelte';
	import { Fingerprint, Loader2, Copy, CheckCircle, Check } from 'lucide-svelte';
	import { copyToClipboard } from '$lib/utils';
	import { API_BASE } from '$lib/config';

	interface Props {
		/** 'card' renders a full bordered card with header; 'inline' renders just the code + copy button */
		variant?: 'card' | 'inline';
	}

	let { variant = 'card' }: Props = $props();

	let pairingCode = $state<string | null>(null);
	let pairingMemberTag = $state<string | null>(null);
	let pairingLoading = $state(true);
	let copied = $state(false);

	async function loadPairingCode() {
		try {
			const res = await fetch(`${API_BASE}/sync/pairing/code`);
			if (res.ok) {
				const data = await res.json();
				pairingCode = data.code;
				pairingMemberTag = data.member_tag ?? null;
			}
		} catch {
			/* non-critical */
		} finally {
			pairingLoading = false;
		}
	}

	async function copyPairingCode() {
		if (!pairingCode) return;
		const ok = await copyToClipboard(pairingCode);
		if (ok) {
			copied = true;
			setTimeout(() => (copied = false), 2000);
		}
	}

	onMount(() => {
		loadPairingCode();
	});
</script>

{#if variant === 'card'}
	<!-- Full card variant (used in OverviewTab) -->
	<div class="rounded-[var(--radius-lg)] border border-[var(--accent)]/30 bg-[var(--bg-subtle)]">
		<div class="px-5 py-4">
			<div class="flex items-center gap-2 mb-1">
				<Fingerprint size={16} class="text-[var(--accent)]" />
				<h3 class="text-sm font-semibold text-[var(--text-primary)]">Your Pairing Code</h3>
			</div>
			<p class="text-xs text-[var(--text-muted)] mb-3">Share this with a team leader so they can add you to their team</p>

			{#if pairingLoading}
				<div class="flex items-center gap-2 px-4 py-3 rounded-[var(--radius-md)] bg-[var(--bg-muted)] border border-[var(--border)]">
					<Loader2 size={14} class="animate-spin text-[var(--text-muted)]" />
					<span class="text-xs text-[var(--text-muted)]">Loading pairing code...</span>
				</div>
			{:else if pairingCode}
				<div class="flex items-center gap-2">
					<code
						class="flex-1 px-4 py-3 text-base font-mono font-semibold tracking-wider rounded-[var(--radius-md)] border border-[var(--border)] bg-[var(--bg-muted)] text-[var(--text-primary)] select-all leading-relaxed"
					>
						{pairingCode}
					</code>
					<button
						onclick={copyPairingCode}
						aria-label="Copy pairing code"
						class="shrink-0 p-3 rounded-[var(--radius-md)] border border-[var(--border)] bg-[var(--bg-base)] text-[var(--text-muted)] hover:text-[var(--accent)] hover:border-[var(--accent)]/40 hover:bg-[var(--accent)]/5 transition-colors"
					>
						{#if copied}
							<CheckCircle size={16} class="text-[var(--success)]" />
						{:else}
							<Copy size={16} />
						{/if}
					</button>
				</div>
				{#if pairingMemberTag}
					<p class="text-[11px] text-[var(--text-muted)] mt-2.5">
						Your identity: <span class="font-mono text-[var(--text-secondary)]">{pairingMemberTag}</span>
					</p>
				{/if}
			{:else}
				<div class="px-4 py-3 rounded-[var(--radius-md)] bg-[var(--bg-muted)] border border-[var(--border)]">
					<p class="text-xs text-[var(--text-muted)]">Pairing code unavailable. Make sure sync is configured.</p>
				</div>
			{/if}
		</div>
	</div>
{:else}
	<!-- Inline variant (used in team page "Join a Team" card) -->
	{#if pairingLoading}
		<div class="flex items-center gap-2">
			<div class="flex-1 h-10 rounded-lg bg-[var(--bg-muted)] animate-pulse"></div>
			<div class="w-10 h-10 rounded-lg bg-[var(--bg-muted)] animate-pulse"></div>
		</div>
	{:else if pairingCode}
		<div class="flex items-center gap-2">
			<div
				class="flex-1 px-3 py-2.5 rounded-lg bg-[var(--bg-muted)] border border-[var(--border)]
					font-mono text-sm text-[var(--text-primary)] tracking-wide select-all truncate"
			>
				{pairingCode}
			</div>
			<button
				onclick={copyPairingCode}
				aria-label={copied ? 'Copied' : 'Copy pairing code'}
				class="flex items-center justify-center w-10 h-10 rounded-lg border border-[var(--border)]
					bg-[var(--bg-subtle)] hover:bg-[var(--bg-muted)] transition-colors cursor-pointer
					{copied ? 'text-[var(--success)]' : 'text-[var(--text-muted)]'}"
			>
				{#if copied}
					<Check size={16} />
				{:else}
					<Copy size={16} />
				{/if}
			</button>
		</div>
		{#if pairingMemberTag}
			<p class="mt-2 text-xs text-[var(--text-faint)]">
				Your identity: <span class="font-mono text-[var(--text-muted)]">{pairingMemberTag}</span>
			</p>
		{/if}
	{:else}
		<div
			class="px-3 py-2.5 rounded-lg bg-[var(--bg-muted)] border border-[var(--border)]
				text-xs text-[var(--text-muted)] text-center"
		>
			Pairing code unavailable. Check <a href="/sync" class="text-[var(--accent)] hover:underline">/sync</a> setup.
		</div>
	{/if}
{/if}

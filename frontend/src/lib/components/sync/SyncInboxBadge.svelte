<script lang="ts">
	import { boundedFetch } from '$lib/utils/api-fetch';
	import { onMount } from 'svelte';
	import { Inbox } from 'lucide-svelte';
	import { API_BASE } from '$lib/config';

	let count = $state(0);
	let configured = $state(true);

	async function poll() {
		try {
			const resp = await boundedFetch(`${API_BASE}/sync/inbox`);
			if (resp.status === 400 || resp.status === 404) {
				// Sync not initialized on this machine — stay hidden
				configured = false;
				return;
			}
			if (!resp.ok) return;
			configured = true;
			const data = await resp.json();
			count = data.count ?? 0;
		} catch {
			// API unreachable — keep last known state
		}
	}

	onMount(() => {
		poll();
		const interval = setInterval(poll, 30_000);
		const onFocus = () => poll();
		window.addEventListener('focus', onFocus);
		return () => {
			clearInterval(interval);
			window.removeEventListener('focus', onFocus);
		};
	});
</script>

{#if configured && count > 0}
	<a
		href="/sync"
		class="relative p-2 rounded-lg text-[var(--text-muted)] hover:text-[var(--text-primary)] hover:bg-[var(--bg-muted)] transition-colors"
		title="{count} pending sync decision{count === 1 ? '' : 's'}"
		aria-label="Sync inbox: {count} pending"
	>
		<Inbox size={18} strokeWidth={1.75} />
		<span
			class="absolute -top-0.5 -right-0.5 min-w-[16px] h-4 px-1 rounded-full bg-[var(--accent)] text-white text-[10px] font-semibold flex items-center justify-center leading-none"
		>
			{count > 9 ? '9+' : count}
		</span>
	</a>
{/if}

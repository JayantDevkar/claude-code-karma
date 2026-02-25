<script lang="ts">
	import { Bot } from 'lucide-svelte';
	import { formatDistanceToNow } from 'date-fns';

	interface Props {
		mainCalls: number;
		subagentCalls: number;
		totalCalls: number;
		firstUsed: string | null;
		lastUsed: string | null;
		sessions?: Array<{ start_time?: string | null }>;
		subagentColor?: string;
	}

	let {
		mainCalls,
		subagentCalls,
		totalCalls,
		firstUsed,
		lastUsed,
		sessions,
		subagentColor = 'var(--nav-teal)'
	}: Props = $props();

	let mainPct = $derived(totalCalls > 0 ? Math.round((mainCalls / totalCalls) * 100) : 0);
	let subPct = $derived(totalCalls > 0 ? 100 - mainPct : 0);

	let effectiveFirstUsed = $derived(
		firstUsed ??
			(sessions && sessions.length > 0
				? (sessions
						.map((s) => s.start_time)
						.filter((t): t is string => !!t)
						.sort()[0] ?? null)
				: null)
	);
	let effectiveLastUsed = $derived(
		lastUsed ??
			(sessions && sessions.length > 0
				? (sessions
						.map((s) => s.start_time)
						.filter((t): t is string => !!t)
						.sort()
						.reverse()[0] ?? null)
				: null)
	);
</script>

<div class="flex items-center gap-2 mb-6">
	<Bot size={18} class="text-[var(--text-muted)]" />
	<h3 class="text-lg font-bold text-[var(--text-primary)]">Context Split</h3>
</div>

<!-- Main vs Subagent bar -->
<div class="mb-6">
	<div class="flex h-5 rounded-full overflow-hidden bg-[var(--bg-muted)] shadow-inner">
		<div
			class="transition-all duration-300 ease-out flex items-center justify-center text-[10px] font-bold text-white"
			style="width: {mainPct}%; background: linear-gradient(90deg, var(--accent) 0%, #a78bfa 100%);"
			title="Main: {mainCalls.toLocaleString()}"
		>
			{#if mainPct > 15}{mainPct}%{/if}
		</div>
		<div
			class="transition-all duration-300 ease-out flex items-center justify-center text-[10px] font-bold text-white"
			style="width: {subPct}%; background: linear-gradient(90deg, {subagentColor} 0%, color-mix(in srgb, {subagentColor} 60%, white) 100%);"
			title="Subagent: {subagentCalls.toLocaleString()}"
		>
			{#if subPct > 15}{subPct}%{/if}
		</div>
	</div>
</div>

<!-- Legend -->
<div class="grid grid-cols-2 gap-3 text-xs">
	<div
		class="flex items-center gap-2 text-[var(--text-secondary)] bg-[var(--bg-subtle)] rounded-lg p-2.5"
	>
		<span
			class="w-3 h-3 rounded-full"
			style="background: linear-gradient(135deg, var(--accent) 0%, #a78bfa 100%);"
		></span>
		<div class="flex-1 min-w-0">
			<div class="font-medium">Main Session</div>
			<div class="text-[var(--text-primary)] font-semibold tabular-nums">
				{mainCalls.toLocaleString()} calls
			</div>
		</div>
	</div>
	<div
		class="flex items-center gap-2 text-[var(--text-secondary)] bg-[var(--bg-subtle)] rounded-lg p-2.5"
	>
		<span
			class="w-3 h-3 rounded-full"
			style="background: linear-gradient(135deg, {subagentColor} 0%, color-mix(in srgb, {subagentColor} 60%, white) 100%);"
		></span>
		<div class="flex-1 min-w-0">
			<div class="font-medium">Subagent</div>
			<div class="text-[var(--text-primary)] font-semibold tabular-nums">
				{subagentCalls.toLocaleString()} calls
			</div>
		</div>
	</div>
</div>

<!-- Activity & Timeline -->
<div class="grid grid-cols-2 gap-3 mt-6">
	<div class="bg-[var(--bg-subtle)] rounded-lg p-4">
		<p class="text-xs text-[var(--text-muted)] uppercase tracking-wider font-semibold mb-2">
			First Used
		</p>
		<p class="text-base font-semibold text-[var(--text-primary)]">
			{#if effectiveFirstUsed}
				{formatDistanceToNow(new Date(effectiveFirstUsed))} ago
			{:else}
				Unknown
			{/if}
		</p>
	</div>
	<div class="bg-[var(--bg-subtle)] rounded-lg p-4">
		<p class="text-xs text-[var(--text-muted)] uppercase tracking-wider font-semibold mb-2">
			Last Used
		</p>
		<p class="text-base font-semibold text-[var(--text-primary)]">
			{#if effectiveLastUsed}
				{formatDistanceToNow(new Date(effectiveLastUsed))} ago
			{:else}
				Unknown
			{/if}
		</p>
	</div>
</div>

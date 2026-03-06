<script lang="ts">
	import {
		Monitor,
		ChevronDown,
		ChevronRight,
		ArrowUp,
		ArrowDown,
		Lock,
		Copy,
		CheckCircle
	} from 'lucide-svelte';
	import type { SyncDevice } from '$lib/api-types';
	import { formatBytes } from '$lib/utils';

	let { device }: { device: SyncDevice } = $props();

	let expanded = $state(false);
	let copiedId = $state(false);

	let statusDotClass = $derived(
		device.connected || device.is_self ? 'bg-[var(--success)]' : 'bg-[var(--warning)]'
	);

	let statusText = $derived(
		device.is_self ? 'Online' : device.connected ? 'Connected' : 'Disconnected'
	);

	let truncatedId = $derived(
		device.device_id.length > 32 ? device.device_id.slice(0, 32) + '\u2026' : device.device_id
	);

	function copyDeviceId() {
		navigator.clipboard
			.writeText(device.device_id)
			.then(() => {
				copiedId = true;
				setTimeout(() => (copiedId = false), 2000);
			})
			.catch(() => {});
	}
</script>

<div
	class="rounded-[var(--radius-lg)] border border-[var(--border)] bg-[var(--bg-subtle)] overflow-hidden"
>
	<!-- Header (always visible) -->
	<button
		onclick={() => (expanded = !expanded)}
		class="w-full flex items-center gap-3 px-4 py-3 text-left hover:bg-[var(--bg-muted)] transition-colors"
		aria-expanded={expanded}
	>
		<!-- Chevron -->
		<span class="shrink-0 text-[var(--text-muted)]">
			{#if expanded}
				<ChevronDown size={15} />
			{:else}
				<ChevronRight size={15} />
			{/if}
		</span>

		<!-- Monitor icon -->
		<span class="shrink-0 text-[var(--text-muted)]">
			<Monitor size={16} />
		</span>

		<!-- Name + badge -->
		<div class="flex items-center gap-2 flex-1 min-w-0">
			<span class="text-sm font-medium text-[var(--text-primary)] truncate">
				{device.name}
			</span>
			{#if device.is_self}
				<span
					class="shrink-0 px-1.5 py-0.5 text-[10px] font-medium rounded bg-[var(--accent-subtle)] text-[var(--accent)] border border-[var(--accent)]/30"
				>
					This Machine
				</span>
			{/if}
		</div>

		<!-- Status -->
		<div class="flex items-center gap-1.5 shrink-0">
			<span class="w-2 h-2 rounded-full {statusDotClass}" aria-hidden="true"></span>
			<span class="text-xs text-[var(--text-secondary)]">{statusText}</span>
		</div>

		<!-- Transfer stats -->
		<div class="flex items-center gap-3 shrink-0 ml-2">
			<span class="flex items-center gap-1 text-xs text-[var(--text-muted)]">
				<ArrowUp size={11} />
				{formatBytes(device.out_bytes_total ?? 0)}
			</span>
			<span class="flex items-center gap-1 text-xs text-[var(--text-muted)]">
				<ArrowDown size={11} />
				{formatBytes(device.in_bytes_total ?? 0)}
			</span>
		</div>
	</button>

	<!-- Expanded details -->
	{#if expanded}
		<div class="px-4 pb-4 pt-2 border-t border-[var(--border)] space-y-4">
			<!-- Connection section -->
			<div>
				<h4
					class="text-[11px] font-semibold text-[var(--text-muted)] uppercase tracking-wide mb-2"
				>
					Connection
				</h4>
				<div class="space-y-1.5">
					{#if device.address}
						<div class="flex items-center justify-between gap-4">
							<span class="text-xs text-[var(--text-secondary)]">Address</span>
							<span
								class="text-xs font-mono text-[var(--text-primary)] truncate max-w-[60%] text-right"
							>
								{device.address}
							</span>
						</div>
					{/if}
					{#if device.type}
						<div class="flex items-center justify-between gap-4">
							<span class="text-xs text-[var(--text-secondary)]">Type</span>
							<span class="text-xs text-[var(--text-primary)]">{device.type}</span>
						</div>
					{/if}
					{#if device.crypto}
						<div class="flex items-center justify-between gap-4">
							<span class="flex items-center gap-1 text-xs text-[var(--text-secondary)]">
								<Lock size={11} />
								Encryption
							</span>
							<span class="text-xs text-[var(--text-primary)]">{device.crypto}</span>
						</div>
					{/if}
					<div class="flex items-center justify-between gap-4">
						<span class="text-xs text-[var(--text-secondary)]">Device ID</span>
						<div class="flex items-center gap-1.5">
							<code
								class="text-[11px] font-mono text-[var(--text-muted)] truncate max-w-[55%] text-right"
							>
								{truncatedId}
							</code>
							<button
								onclick={(e) => {
									e.stopPropagation();
									copyDeviceId();
								}}
								aria-label="Copy device ID"
								class="shrink-0 p-1 rounded text-[var(--text-muted)] hover:text-[var(--text-primary)] transition-colors"
							>
								{#if copiedId}
									<CheckCircle size={12} class="text-[var(--success)]" />
								{:else}
									<Copy size={12} />
								{/if}
							</button>
						</div>
					</div>
				</div>
			</div>

			<!-- Transfer section -->
			<div>
				<h4
					class="text-[11px] font-semibold text-[var(--text-muted)] uppercase tracking-wide mb-2"
				>
					Transfer
				</h4>
				<div class="space-y-1.5">
					<div class="flex items-center justify-between gap-4">
						<span class="flex items-center gap-1 text-xs text-[var(--text-secondary)]">
							<ArrowUp size={11} />
							Total Sent
						</span>
						<span class="text-xs font-medium text-[var(--text-primary)]">
							{formatBytes(device.out_bytes_total ?? 0)}
						</span>
					</div>
					<div class="flex items-center justify-between gap-4">
						<span class="flex items-center gap-1 text-xs text-[var(--text-secondary)]">
							<ArrowDown size={11} />
							Total Received
						</span>
						<span class="text-xs font-medium text-[var(--text-primary)]">
							{formatBytes(device.in_bytes_total ?? 0)}
						</span>
					</div>
				</div>
			</div>
		</div>
	{/if}
</div>

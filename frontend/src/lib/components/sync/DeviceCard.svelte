<script lang="ts">
	import { Monitor, ChevronDown, ChevronRight, ArrowUp, ArrowDown, Lock } from 'lucide-svelte';

	interface Device {
		device_id: string;
		name: string;
		connected: boolean;
		address?: string;
		type?: string;
		crypto?: string;
		in_bytes_total?: number;
		out_bytes_total?: number;
		is_self?: boolean;
	}

	let { device }: { device: Device } = $props();

	let expanded = $state(false);

	function formatBytes(bytes: number): string {
		if (bytes < 1024) return `${bytes} B`;
		if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
		if (bytes < 1024 * 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
		return `${(bytes / (1024 * 1024 * 1024)).toFixed(1)} GB`;
	}

	let statusDotClass = $derived(
		device.connected || device.is_self ? 'bg-[var(--success)]' : 'bg-[var(--text-muted)]'
	);

	let statusText = $derived(
		device.is_self ? 'Online' : device.connected ? 'Connected' : 'Disconnected'
	);

	let truncatedId = $derived(
		device.device_id.length > 32 ? device.device_id.slice(0, 32) + '…' : device.device_id
	);
</script>

<div class="rounded-[var(--radius-lg)] border border-[var(--border)] bg-[var(--bg-subtle)] overflow-hidden">
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
				<h4 class="text-[11px] font-semibold text-[var(--text-muted)] uppercase tracking-wide mb-2">
					Connection
				</h4>
				<div class="space-y-1.5">
					{#if device.address}
						<div class="flex items-center justify-between gap-4">
							<span class="text-xs text-[var(--text-secondary)]">Address</span>
							<span class="text-xs font-mono text-[var(--text-primary)] truncate max-w-[60%] text-right">
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
						<code class="text-[11px] font-mono text-[var(--text-muted)] truncate max-w-[60%] text-right">
							{truncatedId}
						</code>
					</div>
				</div>
			</div>

			<!-- Transfer section -->
			<div>
				<h4 class="text-[11px] font-semibold text-[var(--text-muted)] uppercase tracking-wide mb-2">
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

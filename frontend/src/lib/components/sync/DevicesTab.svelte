<script lang="ts">
	import { onMount } from 'svelte';
	import { Monitor, XCircle } from 'lucide-svelte';
	import { API_BASE } from '$lib/config';
	import DeviceCard from './DeviceCard.svelte';

	interface SyncDetect {
		installed: boolean;
		running: boolean;
		version: string | null;
		device_id: string | null;
		uptime: number | null;
	}

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

	let { detect }: { detect: SyncDetect | null } = $props();

	let devices = $state<Device[]>([]);
	let loading = $state(true);
	let error = $state<string | null>(null);

	async function loadDevices() {
		loading = true;
		error = null;
		try {
			const res = await fetch(`${API_BASE}/sync/devices`);
			if (res.ok) {
				const raw: Device[] = (await res.json()).devices;
				// Mark "this machine" and sort: self first, then paired by name
				const selfId = detect?.device_id ?? null;
				devices = raw
					.map((d) => ({
						...d,
						is_self: selfId ? d.device_id === selfId : false
					}))
					.sort((a, b) => {
						if (a.is_self) return -1;
						if (b.is_self) return 1;
						return a.name.localeCompare(b.name);
					});
			} else {
				error = 'Could not load devices.';
			}
		} catch {
			error = 'Cannot reach backend. Is the API running?';
		} finally {
			loading = false;
		}
	}

	onMount(() => {
		loadDevices();
	});
</script>

<div class="p-6 space-y-4">
	{#if loading}
		<!-- Skeleton -->
		<div class="space-y-3">
			{#each [1, 2, 3] as _}
				<div
					class="h-12 rounded-[var(--radius-lg)] bg-[var(--bg-muted)] animate-pulse"
					aria-hidden="true"
				></div>
			{/each}
		</div>
	{:else if error}
		<!-- Error state -->
		<div
			class="flex items-center gap-3 p-4 rounded-[var(--radius-lg)] border border-[var(--error)]/20 bg-[var(--error-subtle)] text-xs text-[var(--error)]"
		>
			<XCircle size={14} class="shrink-0" />
			<span class="flex-1">{error}</span>
			<button
				onclick={loadDevices}
				class="ml-auto underline hover:no-underline text-[var(--error)] font-medium"
			>
				Retry
			</button>
		</div>
	{:else if devices.length === 0}
		<!-- Empty state -->
		<div
			class="py-12 flex flex-col items-center gap-3 text-center border border-dashed border-[var(--border)] rounded-[var(--radius-lg)]"
		>
			<Monitor size={28} class="text-[var(--text-muted)]" />
			<p class="text-sm text-[var(--text-muted)]">No devices paired yet</p>
		</div>
	{:else}
		<!-- Device list -->
		<div class="space-y-2">
			{#each devices as device (device.device_id)}
				<DeviceCard {device} />
			{/each}
		</div>
	{/if}
</div>

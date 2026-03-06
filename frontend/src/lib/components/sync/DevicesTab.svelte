<script lang="ts">
	import { onMount } from 'svelte';
	import { Monitor, XCircle, Plus, Loader2, Trash2 } from 'lucide-svelte';
	import type { SyncDetect, SyncDevice } from '$lib/api-types';
	import { API_BASE } from '$lib/config';
	import DeviceCard from './DeviceCard.svelte';

	let { detect }: { detect: SyncDetect | null } = $props();

	let devices = $state<SyncDevice[]>([]);
	let loading = $state(true);
	let error = $state<string | null>(null);

	// Pair device state
	let newDeviceId = $state('');
	let newDeviceName = $state('');
	let pairingDevice = $state(false);
	let pairError = $state<string | null>(null);
	let removingDeviceId = $state<string | null>(null);
	let removeConfirmId = $state<string | null>(null);

	async function loadDevices() {
		loading = true;
		error = null;
		try {
			const res = await fetch(`${API_BASE}/sync/devices`);
			if (res.ok) {
				const raw: SyncDevice[] = (await res.json()).devices;
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

	async function pairDevice() {
		if (!newDeviceId.trim()) return;
		pairingDevice = true;
		pairError = null;
		try {
			const res = await fetch(`${API_BASE}/sync/devices`, {
				method: 'POST',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify({
					device_id: newDeviceId.trim(),
					name: newDeviceName.trim() || newDeviceId.trim()
				})
			});
			if (res.ok) {
				newDeviceId = '';
				newDeviceName = '';
				await loadDevices();
			} else {
				const body = await res.json().catch(() => ({}));
				pairError = body?.detail ?? 'Failed to pair device.';
			}
		} catch {
			pairError = 'Cannot reach backend.';
		} finally {
			pairingDevice = false;
		}
	}

	async function removeDevice(deviceId: string) {
		removingDeviceId = deviceId;
		try {
			const res = await fetch(`${API_BASE}/sync/devices/${encodeURIComponent(deviceId)}`, {
				method: 'DELETE'
			});
			if (res.ok) {
				await loadDevices();
			}
		} catch {
			// ignore
		} finally {
			removingDeviceId = null;
			removeConfirmId = null;
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
				<div class="relative group">
					<DeviceCard {device} />
					{#if !device.is_self}
						<!-- Remove button overlay -->
						{#if removeConfirmId === device.device_id}
							<div class="absolute top-2 right-2 flex items-center gap-1.5 bg-[var(--bg-subtle)] rounded-md p-1 border border-[var(--border)]">
								<span class="text-xs text-[var(--text-muted)] px-1">Remove?</span>
								<button
									onclick={() => removeDevice(device.device_id)}
									disabled={removingDeviceId === device.device_id}
									class="px-2 py-0.5 text-xs font-medium rounded bg-[var(--error-subtle)] text-[var(--error)] border border-[var(--error)]/20 hover:bg-[var(--error)]/20 transition-colors disabled:opacity-50"
								>
									{removingDeviceId === device.device_id ? '...' : 'Yes'}
								</button>
								<button
									onclick={() => (removeConfirmId = null)}
									class="px-2 py-0.5 text-xs font-medium rounded border border-[var(--border)] text-[var(--text-muted)] hover:text-[var(--text-primary)] transition-colors"
								>
									No
								</button>
							</div>
						{:else}
							<button
								onclick={() => (removeConfirmId = device.device_id)}
								aria-label="Remove device {device.name}"
								class="absolute top-2 right-2 opacity-0 group-hover:opacity-100 p-1.5 rounded-[var(--radius)] text-[var(--text-muted)] hover:text-[var(--error)] hover:bg-[var(--error-subtle)] transition-all"
							>
								<Trash2 size={14} />
							</button>
						{/if}
					{/if}
				</div>
			{/each}
		</div>
	{/if}

	<!-- Add Device form -->
	<div class="mt-6">
		<h3 class="text-sm font-semibold text-[var(--text-primary)] mb-3">Add Device</h3>
		<div
			class="rounded-[var(--radius-lg)] border border-[var(--border)] bg-[var(--bg-subtle)] p-5 space-y-4"
		>
			<div class="grid grid-cols-1 gap-3 sm:grid-cols-2">
				<div class="space-y-1.5">
					<label for="new-device-id" class="block text-xs font-medium text-[var(--text-secondary)]">
						Device ID
					</label>
					<input
						id="new-device-id"
						type="text"
						bind:value={newDeviceId}
						placeholder="XXXXXXX-XXXXXXX-..."
						class="w-full px-3 py-2 text-xs font-mono rounded-[var(--radius)] border border-[var(--border)] bg-[var(--bg-base)] text-[var(--text-primary)] placeholder:text-[var(--text-muted)] focus:outline-none focus:ring-2 focus:ring-[var(--accent)]/40 focus:border-[var(--accent)] transition-colors"
					/>
				</div>
				<div class="space-y-1.5">
					<label for="new-device-name" class="block text-xs font-medium text-[var(--text-secondary)]">
						Device Name
					</label>
					<input
						id="new-device-name"
						type="text"
						bind:value={newDeviceName}
						placeholder="e.g. home-desktop"
						class="w-full px-3 py-2 text-sm rounded-[var(--radius)] border border-[var(--border)] bg-[var(--bg-base)] text-[var(--text-primary)] placeholder:text-[var(--text-muted)] focus:outline-none focus:ring-2 focus:ring-[var(--accent)]/40 focus:border-[var(--accent)] transition-colors"
					/>
				</div>
			</div>

			{#if pairError}
				<p class="text-xs text-[var(--error)]">{pairError}</p>
			{/if}

			<button
				onclick={pairDevice}
				disabled={pairingDevice || !newDeviceId.trim()}
				class="flex items-center gap-2 px-4 py-2 text-sm font-medium rounded-[var(--radius)] bg-[var(--accent)] text-white hover:bg-[var(--accent-hover)] transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
			>
				{#if pairingDevice}
					<Loader2 size={14} class="animate-spin" />
					Pairing...
				{:else}
					<Plus size={14} />
					Pair Device
				{/if}
			</button>
		</div>
	</div>
</div>

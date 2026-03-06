<script lang="ts">
	import { CheckCircle, XCircle, Copy, Plus, Trash2, Loader2 } from 'lucide-svelte';
	import { API_BASE } from '$lib/config';

	interface SyncDetect {
		installed: boolean;
		running: boolean;
		version: string | null;
		device_id: string | null;
		uptime?: number | null;
	}

	interface SyncStatus {
		configured: boolean;
		user_id?: string;
		machine_id?: string;
		teams?: Record<string, unknown>;
	}

	interface PairedDevice {
		device_id: string;
		name: string;
		address?: string;
		connected: boolean;
	}

	let {
		detect = $bindable(),
		status = $bindable()
	}: {
		detect: SyncDetect | null;
		status: SyncStatus | null;
	} = $props();

	// --- State 1: Not Detected ---
	let checkingAgain = $state(false);
	let checkError = $state<string | null>(null);

	// Detect OS for install instructions highlight
	const userAgent = typeof navigator !== 'undefined' ? navigator.userAgent : '';
	let detectedOS = $derived<'macos' | 'linux' | 'windows'>(
		userAgent.includes('Mac')
			? 'macos'
			: userAgent.includes('Win')
				? 'windows'
				: 'linux'
	);

	async function checkAgain() {
		checkingAgain = true;
		checkError = null;
		try {
			const res = await fetch(`${API_BASE}/sync/detect`);
			if (res.ok) {
				detect = await res.json();
			} else {
				checkError = 'Detection failed. Is Syncthing installed?';
			}
		} catch {
			checkError = 'Cannot reach backend. Is the API running?';
		} finally {
			checkingAgain = false;
		}
	}

	// --- State 2: Detected, Not Initialized ---
	let machineName = $state('');
	let initializing = $state(false);
	let initError = $state<string | null>(null);
	let copiedDeviceId = $state(false);

	async function initialize() {
		if (!machineName.trim()) return;
		initializing = true;
		initError = null;
		try {
			const res = await fetch(`${API_BASE}/sync/init`, {
				method: 'POST',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify({ user_id: machineName.trim() })
			});
			if (res.ok) {
				// Re-fetch both detect and status
				const [dRes, sRes] = await Promise.all([
					fetch(`${API_BASE}/sync/detect`),
					fetch(`${API_BASE}/sync/status`)
				]);
				if (dRes.ok) detect = await dRes.json();
				if (sRes.ok) status = await sRes.json();
			} else {
				const body = await res.json().catch(() => ({}));
				initError = body?.detail ?? 'Initialization failed. Please try again.';
			}
		} catch {
			initError = 'Cannot reach backend. Is the API running?';
		} finally {
			initializing = false;
		}
	}

	async function copyToClipboard(text: string, onSuccess: () => void) {
		try {
			await navigator.clipboard.writeText(text);
			onSuccess();
		} catch {
			// fallback — ignore
		}
	}

	function copyDeviceId() {
		const id = detect?.device_id ?? '';
		copyToClipboard(id, () => {
			copiedDeviceId = true;
			setTimeout(() => (copiedDeviceId = false), 2000);
		});
	}

	// --- State 3: Initialized — Pair Devices ---
	let devices = $state<PairedDevice[]>([]);
	let devicesLoading = $state(false);
	let devicesError = $state<string | null>(null);

	let newDeviceId = $state('');
	let newDeviceName = $state('');
	let pairingDevice = $state(false);
	let pairError = $state<string | null>(null);

	let removingDeviceId = $state<string | null>(null);
	let removeConfirmId = $state<string | null>(null);

	let copiedThisDeviceId = $state(false);

	async function loadDevices() {
		devicesLoading = true;
		devicesError = null;
		try {
			const res = await fetch(`${API_BASE}/sync/devices`);
			if (res.ok) {
				const data = await res.json();
				const selfId = detect?.device_id ?? null;
				devices = (data.devices ?? []).filter(
					(d: PairedDevice & { device_id: string }) => !selfId || d.device_id !== selfId
				);
			} else {
				devicesError = 'Could not load paired devices.';
			}
		} catch {
			devicesError = 'Cannot reach backend.';
		} finally {
			devicesLoading = false;
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

	function copyThisDeviceId() {
		const id = detect?.device_id ?? '';
		copyToClipboard(id, () => {
			copiedThisDeviceId = true;
			setTimeout(() => (copiedThisDeviceId = false), 2000);
		});
	}

	// Load devices when entering state 3
	$effect(() => {
		if (status?.configured) {
			loadDevices();
		}
	});

	const installInstructions = [
		{
			os: 'macos' as const,
			label: 'macOS',
			command: 'brew install syncthing && brew services start syncthing'
		},
		{
			os: 'linux' as const,
			label: 'Linux (apt)',
			command: 'sudo apt install syncthing && systemctl --user enable --now syncthing'
		},
		{
			os: 'windows' as const,
			label: 'Windows (winget)',
			command: 'winget install Syncthing.Syncthing'
		}
	];
</script>

{#if !detect?.running}
	<!-- STATE 1: Syncthing not detected -->
	<div class="p-6 space-y-6">
		<!-- Backend selection cards -->
		<div>
			<h2 class="text-sm font-semibold text-[var(--text-primary)] mb-3">Choose sync backend</h2>
			<div class="grid grid-cols-2 gap-3">
				<!-- Syncthing (selected) -->
				<div
					class="relative p-4 rounded-[var(--radius-lg)] border-2 border-[var(--accent)] bg-[var(--accent-muted)] cursor-default"
				>
					<div class="flex items-center gap-2 mb-1">
						<span class="text-sm font-semibold text-[var(--text-primary)]">Syncthing</span>
						<span
							class="px-1.5 py-0.5 text-[10px] font-medium rounded bg-[var(--accent-subtle)] text-[var(--accent)] border border-[var(--accent)]/30"
						>
							Selected
						</span>
					</div>
					<p class="text-xs text-[var(--text-secondary)]">
						Open-source P2P sync. No cloud, fully private.
					</p>
				</div>

				<!-- IPFS (coming soon) -->
				<div
					class="relative p-4 rounded-[var(--radius-lg)] border border-[var(--border)] bg-[var(--bg-subtle)] opacity-50 cursor-not-allowed"
				>
					<div class="flex items-center gap-2 mb-1">
						<span class="text-sm font-semibold text-[var(--text-muted)]">IPFS</span>
						<span
							class="px-1.5 py-0.5 text-[10px] font-medium rounded bg-[var(--bg-muted)] text-[var(--text-muted)] border border-[var(--border)]"
						>
							Coming soon
						</span>
					</div>
					<p class="text-xs text-[var(--text-muted)]">Distributed content-addressed sync.</p>
				</div>
			</div>
		</div>

		<!-- Install instructions -->
		<div
			class="rounded-[var(--radius-lg)] border border-[var(--warning)]/30 bg-[var(--status-idle-bg)] p-5 space-y-4"
		>
			<div class="flex items-start gap-3">
				<XCircle size={18} class="text-[var(--warning)] mt-0.5 shrink-0" />
				<div>
					<h3 class="text-sm font-semibold text-[var(--text-primary)]">
						Syncthing not detected
					</h3>
					<p class="text-xs text-[var(--text-secondary)] mt-0.5">
						Install and start Syncthing, then click "Check Again".
					</p>
				</div>
			</div>

			<div class="space-y-2">
				{#each installInstructions as instr}
					<div
						class="rounded-[var(--radius)] px-3 py-2.5 {instr.os === detectedOS
							? 'bg-[var(--bg-muted)]'
							: ''}"
					>
						<div class="flex items-center gap-2 mb-1">
							<span class="text-[11px] font-medium text-[var(--text-muted)] uppercase tracking-wide">
								{instr.label}
							</span>
							{#if instr.os === detectedOS}
								<span class="text-[10px] text-[var(--text-muted)]">(detected)</span>
							{/if}
						</div>
						<code
							class="block text-xs font-mono text-[var(--text-secondary)] bg-[var(--bg-base)] border border-[var(--border)] rounded px-2.5 py-1.5 break-all"
						>
							{instr.command}
						</code>
					</div>
				{/each}
			</div>

			{#if checkError}
				<p class="text-xs text-[var(--error)]">{checkError}</p>
			{/if}

			<button
				onclick={checkAgain}
				disabled={checkingAgain}
				aria-label="Check if Syncthing is now running"
				class="flex items-center gap-2 px-4 py-2 text-sm font-medium rounded-[var(--radius)] bg-[var(--accent)] text-white hover:bg-[var(--accent-hover)] transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
			>
				{#if checkingAgain}
					<Loader2 size={14} class="animate-spin" />
					Checking...
				{:else}
					Check Again
				{/if}
			</button>
		</div>
	</div>
{:else if !status?.configured}
	<!-- STATE 2: Detected, not initialized -->
	<div class="p-6 space-y-5">
		<!-- Success banner -->
		<div
			class="flex items-center gap-3 p-4 rounded-[var(--radius-lg)] border border-[var(--success)]/30 bg-[var(--status-active-bg)]"
		>
			<span
				class="w-2.5 h-2.5 rounded-full bg-[var(--success)] shrink-0"
				aria-hidden="true"
			></span>
			<div>
				<span class="text-sm font-semibold text-[var(--text-primary)]">
					Syncthing {detect.version ?? ''} running
				</span>
				<p class="text-xs text-[var(--text-secondary)] mt-0.5">
					One more step — name this machine to start syncing.
				</p>
			</div>
		</div>

		<!-- Init form -->
		<div
			class="rounded-[var(--radius-lg)] border border-[var(--border)] bg-[var(--bg-subtle)] p-5 space-y-4"
		>
			<h3 class="text-sm font-semibold text-[var(--text-primary)]">Initialize this machine</h3>

			<!-- Machine Name input -->
			<div class="space-y-1.5">
				<label for="machine-name" class="block text-xs font-medium text-[var(--text-secondary)]">
					Machine Name
				</label>
				<input
					id="machine-name"
					type="text"
					bind:value={machineName}
					placeholder="e.g. my-laptop, work-mac"
					class="w-full px-3 py-2 text-sm rounded-[var(--radius)] border border-[var(--border)] bg-[var(--bg-base)] text-[var(--text-primary)] placeholder:text-[var(--text-muted)] focus:outline-none focus:ring-2 focus:ring-[var(--accent)]/40 focus:border-[var(--accent)] transition-colors"
				/>
				<p class="text-[11px] text-[var(--text-muted)]">
					Used to identify this machine in the sync network.
				</p>
			</div>

			<!-- Device ID (read-only) -->
			{#if detect.device_id}
				<div class="space-y-1.5">
					<p class="block text-xs font-medium text-[var(--text-secondary)]">Device ID</p>
					<div class="flex items-center gap-2">
						<code
							class="flex-1 px-3 py-2 text-xs font-mono rounded-[var(--radius)] border border-[var(--border)] bg-[var(--bg-muted)] text-[var(--text-secondary)] truncate"
						>
							{detect.device_id}
						</code>
						<button
							onclick={copyDeviceId}
							aria-label="Copy device ID to clipboard"
							class="shrink-0 p-2 rounded-[var(--radius)] border border-[var(--border)] bg-[var(--bg-base)] text-[var(--text-muted)] hover:text-[var(--text-primary)] hover:bg-[var(--bg-muted)] transition-colors"
						>
							{#if copiedDeviceId}
								<CheckCircle size={14} class="text-[var(--success)]" />
								<span class="sr-only">Copied</span>
							{:else}
								<Copy size={14} />
							{/if}
						</button>
					</div>
				</div>
			{/if}

			{#if initError}
				<div
					class="flex items-start gap-2.5 p-3 rounded-[var(--radius)] bg-[var(--error-subtle)] border border-[var(--error)]/20"
				>
					<XCircle size={14} class="text-[var(--error)] mt-0.5 shrink-0" />
					<div>
						<p class="text-xs text-[var(--error)]">{initError}</p>
						<button
							onclick={() => (initError = null)}
							class="text-[11px] text-[var(--error)] underline hover:no-underline mt-0.5"
						>
							Dismiss
						</button>
					</div>
				</div>
			{/if}

			<button
				onclick={initialize}
				disabled={initializing || !machineName.trim()}
				class="flex items-center gap-2 px-4 py-2 text-sm font-medium rounded-[var(--radius)] bg-[var(--accent)] text-white hover:bg-[var(--accent-hover)] transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
			>
				{#if initializing}
					<Loader2 size={14} class="animate-spin" />
					Initializing...
				{:else}
					Initialize
				{/if}
			</button>
		</div>
	</div>
{:else}
	<!-- STATE 3: Initialized — Pair Devices -->
	<div class="p-6 space-y-6">
		<!-- This Machine card -->
		<div>
			<h2 class="text-sm font-semibold text-[var(--text-primary)] mb-3">This Machine</h2>
			<div
				class="rounded-[var(--radius-lg)] border border-[var(--border)] bg-[var(--bg-subtle)] p-4 space-y-3"
			>
				<div class="flex items-center gap-2">
					<span
						class="w-2 h-2 rounded-full bg-[var(--success)] shrink-0"
						aria-hidden="true"
					></span>
					<span class="text-sm font-semibold text-[var(--text-primary)]">
						{status.machine_id ?? status.user_id ?? 'This Machine'}
					</span>
					{#if detect.version}
						<span class="text-xs text-[var(--text-muted)]">v{detect.version}</span>
					{/if}
				</div>

				{#if detect.device_id}
					<div class="flex items-center gap-2">
						<code
							class="flex-1 min-w-0 px-2.5 py-1.5 text-xs font-mono rounded-[var(--radius)] border border-[var(--border)] bg-[var(--bg-muted)] text-[var(--text-secondary)] truncate"
						>
							{detect.device_id}
						</code>
						<button
							onclick={copyThisDeviceId}
							aria-label="Copy this device ID to clipboard"
							class="shrink-0 p-1.5 rounded-[var(--radius)] border border-[var(--border)] bg-[var(--bg-base)] text-[var(--text-muted)] hover:text-[var(--text-primary)] hover:bg-[var(--bg-muted)] transition-colors"
						>
							{#if copiedThisDeviceId}
								<CheckCircle size={13} class="text-[var(--success)]" />
								<span class="sr-only">Copied</span>
							{:else}
								<Copy size={13} />
							{/if}
						</button>
					</div>
				{/if}
			</div>
		</div>

		<!-- Paired Devices -->
		<div>
			<h2 class="text-sm font-semibold text-[var(--text-primary)] mb-3">Paired Devices</h2>

			{#if devicesLoading}
				<div class="flex items-center gap-2 py-6 text-sm text-[var(--text-muted)]">
					<Loader2 size={14} class="animate-spin" />
					Loading devices...
				</div>
			{:else if devicesError}
				<div
					class="flex items-center gap-2 p-4 rounded-[var(--radius-lg)] border border-[var(--error)]/20 bg-[var(--error-subtle)] text-xs text-[var(--error)]"
				>
					<XCircle size={14} class="shrink-0" />
					{devicesError}
					<button
						onclick={loadDevices}
						class="ml-auto underline hover:no-underline text-[var(--error)]"
					>
						Retry
					</button>
				</div>
			{:else if devices.length === 0}
				<div
					class="py-8 text-center text-sm text-[var(--text-muted)] border border-dashed border-[var(--border)] rounded-[var(--radius-lg)]"
				>
					No devices paired yet. Add a device below.
				</div>
			{:else}
				<div class="space-y-2">
					{#each devices as device (device.device_id)}
						<div
							class="flex items-center gap-3 p-3 rounded-[var(--radius-lg)] border border-[var(--border)] bg-[var(--bg-subtle)] group"
						>
							<span
								class="w-2 h-2 rounded-full shrink-0 {device.connected
									? 'bg-[var(--success)]'
									: 'bg-[var(--text-muted)]'}"
								aria-hidden="true"
							></span>

							<div class="flex-1 min-w-0">
								<p class="text-sm font-medium text-[var(--text-primary)] truncate">
									{device.name}
								</p>
								<p class="text-xs text-[var(--text-muted)] truncate">
									{device.connected ? (device.address ?? 'Connected') : 'Disconnected'}
								</p>
							</div>

							<!-- Remove button with confirm -->
							{#if removeConfirmId === device.device_id}
								<div class="flex items-center gap-1.5">
									<span class="text-xs text-[var(--text-muted)]">Remove?</span>
									<button
										onclick={() => removeDevice(device.device_id)}
										disabled={removingDeviceId === device.device_id}
										aria-label="Confirm remove device {device.name}"
										class="px-2 py-1 text-xs font-medium rounded bg-[var(--error-subtle)] text-[var(--error)] border border-[var(--error)]/20 hover:bg-[var(--error)]/20 transition-colors disabled:opacity-50"
									>
										{removingDeviceId === device.device_id ? 'Removing...' : 'Yes'}
									</button>
									<button
										onclick={() => (removeConfirmId = null)}
										class="px-2 py-1 text-xs font-medium rounded border border-[var(--border)] text-[var(--text-muted)] hover:text-[var(--text-primary)] hover:bg-[var(--bg-muted)] transition-colors"
									>
										Cancel
									</button>
								</div>
							{:else}
								<button
									onclick={() => (removeConfirmId = device.device_id)}
									aria-label="Remove device {device.name}"
									class="opacity-0 group-hover:opacity-100 p-1.5 rounded-[var(--radius)] text-[var(--text-muted)] hover:text-[var(--error)] hover:bg-[var(--error-subtle)] transition-all"
								>
									<Trash2 size={14} />
								</button>
							{/if}
						</div>
					{/each}
				</div>
			{/if}
		</div>

		<!-- Add Device form -->
		<div>
			<h2 class="text-sm font-semibold text-[var(--text-primary)] mb-3">Add Device</h2>
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
						<label
							for="new-device-name"
							class="block text-xs font-medium text-[var(--text-secondary)]"
						>
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
{/if}

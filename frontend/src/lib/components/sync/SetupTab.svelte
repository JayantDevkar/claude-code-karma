<script lang="ts">
	import { onMount } from 'svelte';
	import { CheckCircle, XCircle, Copy, Loader2, Monitor, FolderGit2, ArrowUp, ArrowDown } from 'lucide-svelte';
	import type { SyncDetect, SyncStatusResponse } from '$lib/api-types';
	import { formatBytes } from '$lib/utils';
	import { API_BASE } from '$lib/config';

	let {
		detect = $bindable(),
		status = $bindable()
	}: {
		detect: SyncDetect | null;
		status: SyncStatusResponse | null;
	} = $props();

	// --- State 1: Not Detected ---
	let checkingAgain = $state(false);
	let checkError = $state<string | null>(null);

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

	function copyDeviceId() {
		const id = detect?.device_id ?? '';
		navigator.clipboard.writeText(id).then(() => {
			copiedDeviceId = true;
			setTimeout(() => (copiedDeviceId = false), 2000);
		}).catch(() => {});
	}

	// --- State 3: Overview stats ---
	let totalDevices = $state(0);
	let syncedProjects = $state(0);
	let syncedInBytes = $state(0);
	let syncedOutBytes = $state(0);

	// Derive synced project count from status.teams (already available as prop)
	let teamProjectCount = $derived(() => {
		if (!status?.teams) return 0;
		let count = 0;
		for (const team of Object.values(status.teams) as Array<{ project_count?: number }>) {
			count += team.project_count ?? 0;
		}
		return count;
	});

	async function loadOverview() {
		syncedProjects = teamProjectCount();
		try {
			const [devicesRes, foldersRes] = await Promise.all([
				fetch(`${API_BASE}/sync/devices`).catch(() => null),
				fetch(`${API_BASE}/sync/projects`).catch(() => null)
			]);
			if (devicesRes?.ok) {
				const data = await devicesRes.json();
				const selfId = detect?.device_id ?? null;
				totalDevices = (data.devices ?? []).filter(
					(d: { device_id: string }) => !selfId || d.device_id !== selfId
				).length;
			}
			if (foldersRes?.ok) {
				const data = await foldersRes.json();
				const folders = data.folders ?? [];
				let inBytes = 0;
				let outBytes = 0;
				for (const f of folders) {
					const syncBytes = (f.inSyncBytes as number) ?? 0;
					const fType = (f.type as string) ?? 'sendreceive';
					if (fType === 'sendonly' || fType === 'sendreceive') outBytes += syncBytes;
					if (fType === 'receiveonly' || fType === 'sendreceive') inBytes += syncBytes;
				}
				syncedInBytes = inBytes;
				syncedOutBytes = outBytes;
			}
		} catch {
			// Non-critical
		}
	}

	$effect(() => {
		if (status?.configured) {
			loadOverview();
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

		<div
			class="rounded-[var(--radius-lg)] border border-[var(--border)] bg-[var(--bg-subtle)] p-5 space-y-4"
		>
			<h3 class="text-sm font-semibold text-[var(--text-primary)]">Initialize this machine</h3>

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
	<!-- STATE 3: Initialized — Summary -->
	<div class="p-6 space-y-5">
		<div
			class="flex items-center gap-3 p-4 rounded-[var(--radius-lg)] border border-[var(--success)]/30 bg-[var(--status-active-bg)]"
		>
			<CheckCircle size={18} class="text-[var(--success)] shrink-0" />
			<div>
				<span class="text-sm font-semibold text-[var(--text-primary)]">
					Sync configured
				</span>
				<p class="text-xs text-[var(--text-secondary)] mt-0.5">
					Syncthing {detect?.version ?? ''} is running. Manage devices in the Devices tab.
				</p>
			</div>
		</div>

		<!-- Overview stats -->
		<div class="grid grid-cols-4 gap-3">
			<div class="rounded-[var(--radius-lg)] border border-[var(--border)] bg-[var(--bg-subtle)] p-4 text-center">
				<Monitor size={16} class="mx-auto text-[var(--text-muted)] mb-1.5" />
				<p class="text-lg font-semibold text-[var(--text-primary)]">{totalDevices}</p>
				<p class="text-[11px] text-[var(--text-muted)]">Devices</p>
			</div>
			<div class="rounded-[var(--radius-lg)] border border-[var(--border)] bg-[var(--bg-subtle)] p-4 text-center">
				<FolderGit2 size={16} class="mx-auto text-[var(--text-muted)] mb-1.5" />
				<p class="text-lg font-semibold text-[var(--text-primary)]">{syncedProjects}</p>
				<p class="text-[11px] text-[var(--text-muted)]">Synced Projects</p>
			</div>
			<div class="rounded-[var(--radius-lg)] border border-[var(--border)] bg-[var(--bg-subtle)] p-4 text-center">
				<ArrowDown size={16} class="mx-auto text-[var(--info)] mb-1.5" />
				<p class="text-lg font-semibold text-[var(--text-primary)]">{formatBytes(syncedInBytes)}</p>
				<p class="text-[11px] text-[var(--text-muted)]">Synced In</p>
			</div>
			<div class="rounded-[var(--radius-lg)] border border-[var(--border)] bg-[var(--bg-subtle)] p-4 text-center">
				<ArrowUp size={16} class="mx-auto text-[var(--accent)] mb-1.5" />
				<p class="text-lg font-semibold text-[var(--text-primary)]">{formatBytes(syncedOutBytes)}</p>
				<p class="text-[11px] text-[var(--text-muted)]">Synced Out</p>
			</div>
		</div>

		<!-- Machine details -->
		<div class="rounded-[var(--radius-lg)] border border-[var(--border)] bg-[var(--bg-subtle)] p-5 space-y-3">
			<div class="flex items-center justify-between">
				<span class="text-xs font-medium text-[var(--text-secondary)]">Machine</span>
				<span class="text-sm font-medium text-[var(--text-primary)]">
					{status.machine_id ?? status.user_id ?? '—'}
				</span>
			</div>
			{#if detect?.device_id}
				<div class="flex items-center justify-between gap-2">
					<span class="text-xs font-medium text-[var(--text-secondary)]">Device ID</span>
					<div class="flex items-center gap-1.5">
						<code class="text-xs font-mono text-[var(--text-muted)] truncate max-w-[280px]">
							{detect.device_id}
						</code>
						<button
							onclick={copyDeviceId}
							aria-label="Copy device ID"
							class="shrink-0 p-1 rounded text-[var(--text-muted)] hover:text-[var(--text-primary)] transition-colors"
						>
							{#if copiedDeviceId}
								<CheckCircle size={12} class="text-[var(--success)]" />
							{:else}
								<Copy size={12} />
							{/if}
						</button>
					</div>
				</div>
			{/if}
			{#if detect?.version}
				<div class="flex items-center justify-between">
					<span class="text-xs font-medium text-[var(--text-secondary)]">Version</span>
					<span class="text-xs text-[var(--text-muted)]">v{detect.version}</span>
				</div>
			{/if}
		</div>
	</div>
{/if}

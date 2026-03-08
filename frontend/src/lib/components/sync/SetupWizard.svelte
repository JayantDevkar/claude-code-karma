<script lang="ts">
	import {
		CheckCircle,
		XCircle,
		Copy,
		Loader2,
		ArrowRight,
		Check,
		Shield,
		Wifi,
		HardDrive,
		RefreshCw
	} from 'lucide-svelte';
	import type { SyncDetect, SyncStatusResponse } from '$lib/api-types';
	import { API_BASE } from '$lib/config';
	import { copyToClipboard } from '$lib/utils';
	import { goto } from '$app/navigation';

	let {
		detect = $bindable(),
		status = $bindable(),
		ondone
	}: {
		detect: SyncDetect | null;
		status: SyncStatusResponse | null;
		ondone: () => void;
	} = $props();

	// -----------------------------------------------
	// Step tracking
	// -----------------------------------------------
	// step 0 = how it works, 1 = install, 2 = name machine
	let step = $state<0 | 1 | 2>(0);
	let hasNavigated = $state(false);

	// Auto-advance: when detect.running becomes true on step 1, move to step 2
	$effect(() => {
		if (detect?.running && step === 1) {
			step = 2;
		}
	});

	// After init succeeds, redirect to /team
	$effect(() => {
		if (status?.configured && step === 2 && !hasNavigated) {
			hasNavigated = true;
			goto('/team');
		}
	});

	// -----------------------------------------------
	// OS detection
	// -----------------------------------------------
	const userAgent = typeof navigator !== 'undefined' ? navigator.userAgent : '';
	let detectedOS = $derived<'macos' | 'linux' | 'windows'>(
		userAgent.includes('Mac') ? 'macos' : userAgent.includes('Win') ? 'windows' : 'linux'
	);

	const installInstructions: Array<{ os: 'macos' | 'linux' | 'windows'; label: string; command: string }> = [
		{
			os: 'macos',
			label: 'macOS',
			command: 'brew install syncthing && brew services start syncthing'
		},
		{
			os: 'linux',
			label: 'Linux (apt)',
			command: 'sudo apt install syncthing && systemctl --user enable --now syncthing'
		},
		{
			os: 'windows',
			label: 'Windows (winget)',
			command: 'winget install Syncthing.Syncthing'
		}
	];

	// -----------------------------------------------
	// Step 1 — Install & detect
	// -----------------------------------------------
	let copiedCommand = $state<string | null>(null);

	async function copyCommand(command: string) {
		const ok = await copyToClipboard(command);
		if (ok) {
			copiedCommand = command;
			setTimeout(() => (copiedCommand = null), 2000);
		}
	}

	let checkingAgain = $state(false);
	let checkError = $state<string | null>(null);

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

	// -----------------------------------------------
	// Step 2 — Name machine / init
	// -----------------------------------------------
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
				// redirect handled by the $effect above
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

	async function copyDeviceId() {
		const ok = await copyToClipboard(detect?.device_id ?? '');
		if (ok) {
			copiedDeviceId = true;
			setTimeout(() => (copiedDeviceId = false), 2000);
		}
	}

	// -----------------------------------------------
	// Progress step labels
	// -----------------------------------------------
	const STEPS = ['How It Works', 'Install', 'Name Machine'] as const;
</script>

<!-- Wizard shell -->
<div class="p-6 space-y-6">
	<!-- Progress bar -->
	<div>
		<div class="flex items-start">
			{#each STEPS as label, i}
				{@const idx = i}
				{@const done = step > idx}
				{@const active = step === idx}
				<div class="flex {i < STEPS.length - 1 ? 'flex-1' : ''} items-start">
					<!-- Step column (circle + label) -->
					<div class="flex flex-col items-center shrink-0">
						<!-- Circle -->
						<div
							class="w-6 h-6 rounded-full flex items-center justify-center text-[11px] font-semibold transition-colors {done
								? 'bg-[var(--success)] text-white'
								: active
									? 'bg-[var(--accent)] text-white'
									: 'bg-[var(--bg-muted)] text-[var(--text-muted)] border border-[var(--border)]'}"
						>
							{#if done}
								<Check size={12} />
							{:else}
								{idx + 1}
							{/if}
						</div>
						<!-- Label -->
						<span
							class="text-[10px] font-medium uppercase tracking-wide mt-1.5 whitespace-nowrap transition-colors {done
								? 'text-[var(--success)]'
								: active
									? 'text-[var(--accent)]'
									: 'text-[var(--text-muted)]'}"
						>
							{label}
						</span>
					</div>
					<!-- Connector line -->
					{#if i < STEPS.length - 1}
						<div
							class="flex-1 h-px mx-1.5 mt-3 transition-colors {done
								? 'bg-[var(--success)]'
								: 'bg-[var(--border)]'}"
						></div>
					{/if}
				</div>
			{/each}
		</div>
	</div>

	<!-- ============================================ -->
	<!-- STEP 0: How It Works                        -->
	<!-- ============================================ -->
	{#if step === 0}
		<div class="space-y-4">
			<div>
				<h2 class="text-sm font-semibold text-[var(--text-primary)]">Peer-to-Peer Session Sync</h2>
				<p class="text-xs text-[var(--text-secondary)] mt-0.5">
					Share Claude Code sessions across your machines or with teammates — without any cloud service.
				</p>
			</div>

			<div class="rounded-[var(--radius-lg)] border border-[var(--border)] bg-[var(--bg-subtle)] p-5 space-y-5">
				<p class="text-sm text-[var(--text-secondary)] leading-relaxed">
					Claude Karma uses <strong class="text-[var(--text-primary)]">Syncthing</strong> to sync sessions
					directly between your devices. There's no cloud server in the middle — your data travels
					encrypted from one machine to another, and stays entirely under your control.
				</p>

				<div class="grid grid-cols-1 sm:grid-cols-2 gap-3">
					<div class="flex items-start gap-2.5">
						<div class="w-7 h-7 rounded-[var(--radius-md)] bg-[var(--accent)]/10 flex items-center justify-center shrink-0 mt-0.5">
							<Shield size={14} class="text-[var(--accent)]" />
						</div>
						<div>
							<p class="text-xs font-semibold text-[var(--text-primary)]">Your data, your machines</p>
							<p class="text-[11px] text-[var(--text-muted)] mt-0.5">Sessions never leave your devices. No accounts, no third-party storage.</p>
						</div>
					</div>

					<div class="flex items-start gap-2.5">
						<div class="w-7 h-7 rounded-[var(--radius-md)] bg-[var(--success)]/10 flex items-center justify-center shrink-0 mt-0.5">
							<Wifi size={14} class="text-[var(--success)]" />
						</div>
						<div>
							<p class="text-xs font-semibold text-[var(--text-primary)]">Encrypted in transit</p>
							<p class="text-[11px] text-[var(--text-muted)] mt-0.5">All transfers use TLS encryption. Only paired devices can connect.</p>
						</div>
					</div>

					<div class="flex items-start gap-2.5">
						<div class="w-7 h-7 rounded-[var(--radius-md)] bg-[var(--info)]/10 flex items-center justify-center shrink-0 mt-0.5">
							<HardDrive size={14} class="text-[var(--info)]" />
						</div>
						<div>
							<p class="text-xs font-semibold text-[var(--text-primary)]">No central server</p>
							<p class="text-[11px] text-[var(--text-muted)] mt-0.5">Direct device-to-device sync over your local network or internet.</p>
						</div>
					</div>

					<div class="flex items-start gap-2.5">
						<div class="w-7 h-7 rounded-[var(--radius-md)] bg-[var(--warning)]/10 flex items-center justify-center shrink-0 mt-0.5">
							<RefreshCw size={14} class="text-[var(--warning)]" />
						</div>
						<div>
							<p class="text-xs font-semibold text-[var(--text-primary)]">Open source & auditable</p>
							<p class="text-[11px] text-[var(--text-muted)] mt-0.5">Syncthing is fully open source. You can inspect every line of code.</p>
						</div>
					</div>
				</div>

				<button
					onclick={() => (step = 1)}
					class="flex items-center gap-2 px-4 py-2 text-sm font-medium rounded-[var(--radius-md)] bg-[var(--accent)] text-white hover:bg-[var(--accent-hover)] transition-colors"
				>
					Get Started
					<ArrowRight size={14} />
				</button>
			</div>
		</div>

	<!-- ============================================ -->
	<!-- STEP 1: Install Syncthing                   -->
	<!-- ============================================ -->
	{:else if step === 1}
		<div class="space-y-4">
			<div>
				<h2 class="text-sm font-semibold text-[var(--text-primary)]">Install Syncthing</h2>
				<p class="text-xs text-[var(--text-secondary)] mt-0.5">
					Claude Karma uses Syncthing to sync sessions between your machines.
				</p>
			</div>

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
							class="rounded-[var(--radius-md)] px-3 py-2.5 {instr.os === detectedOS
								? 'bg-[var(--bg-muted)]'
								: ''}"
						>
							<div class="flex items-center gap-2 mb-1">
								<span
									class="text-[11px] font-medium text-[var(--text-muted)] uppercase tracking-wide"
								>
									{instr.label}
								</span>
								{#if instr.os === detectedOS}
									<span class="text-[10px] text-[var(--text-muted)]">(detected)</span>
								{/if}
							</div>
							<div class="flex items-center gap-1.5">
								<code
									class="flex-1 text-xs font-mono text-[var(--text-secondary)] bg-[var(--bg-base)] border border-[var(--border)] rounded px-2.5 py-1.5 break-all"
								>
									{instr.command}
								</code>
								<button
									onclick={() => copyCommand(instr.command)}
									aria-label="Copy command to clipboard"
									class="shrink-0 p-1.5 rounded-[var(--radius-md)] border border-[var(--border)] bg-[var(--bg-base)] text-[var(--text-muted)] hover:text-[var(--text-primary)] hover:bg-[var(--bg-muted)] transition-colors"
								>
									{#if copiedCommand === instr.command}
										<CheckCircle size={13} class="text-[var(--success)]" />
									{:else}
										<Copy size={13} />
									{/if}
								</button>
							</div>
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
					class="flex items-center gap-2 px-4 py-2 text-sm font-medium rounded-[var(--radius-md)] bg-[var(--accent)] text-white hover:bg-[var(--accent-hover)] transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
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

	<!-- ============================================ -->
	<!-- STEP 2: Name this machine                   -->
	<!-- ============================================ -->
	{:else if step === 2}
		<div class="space-y-4">
			<div>
				<h2 class="text-sm font-semibold text-[var(--text-primary)]">Name This Machine</h2>
				<p class="text-xs text-[var(--text-secondary)] mt-0.5">
					Give this device an identifier so others can recognize it in the sync network.
				</p>
			</div>

			<!-- Running banner -->
			<div
				class="flex items-center gap-3 p-4 rounded-[var(--radius-lg)] border border-[var(--success)]/30 bg-[var(--status-active-bg)]"
			>
				<span class="w-2.5 h-2.5 rounded-full bg-[var(--success)] shrink-0" aria-hidden="true"
				></span>
				<div>
					<span class="text-sm font-semibold text-[var(--text-primary)]">
						Syncthing{#if detect?.version}&nbsp;v{detect.version}{/if} running
					</span>
					<p class="text-xs text-[var(--text-secondary)] mt-0.5">
						One more step — name this machine to start syncing.
					</p>
				</div>
			</div>

			<div
				class="rounded-[var(--radius-lg)] border border-[var(--border)] bg-[var(--bg-subtle)] p-5 space-y-4"
			>
				<!-- Machine name input -->
				<div class="space-y-1.5">
					<label for="wizard-machine-name" class="block text-xs font-medium text-[var(--text-secondary)]">
						Machine Name
					</label>
					<input
						id="wizard-machine-name"
						type="text"
						bind:value={machineName}
						placeholder="e.g. my-laptop, work-mac"
						class="w-full px-3 py-2 text-sm rounded-[var(--radius-md)] border border-[var(--border)] bg-[var(--bg-base)] text-[var(--text-primary)] placeholder:text-[var(--text-muted)] focus:outline-none focus:ring-2 focus:ring-[var(--accent)]/40 focus:border-[var(--accent)] transition-colors"
					/>
					<p class="text-[11px] text-[var(--text-muted)]">
						Used to identify this machine in the sync network.
					</p>
				</div>

				<!-- Device ID (copyable) -->
				{#if detect?.device_id}
					<div class="space-y-1.5">
						<p class="block text-xs font-medium text-[var(--text-secondary)]">Device ID</p>
						<div class="flex items-center gap-2">
							<code
								class="flex-1 px-3 py-2 text-xs font-mono rounded-[var(--radius-md)] border border-[var(--border)] bg-[var(--bg-muted)] text-[var(--text-secondary)] truncate"
							>
								{detect.device_id}
							</code>
							<button
								onclick={copyDeviceId}
								aria-label="Copy device ID to clipboard"
								class="shrink-0 p-2 rounded-[var(--radius-md)] border border-[var(--border)] bg-[var(--bg-base)] text-[var(--text-muted)] hover:text-[var(--text-primary)] hover:bg-[var(--bg-muted)] transition-colors"
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

				<!-- Error -->
				{#if initError}
					<div
						class="flex items-start gap-2.5 p-3 rounded-[var(--radius-md)] bg-[var(--error-subtle)] border border-[var(--error)]/20"
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
					class="flex items-center gap-2 px-4 py-2 text-sm font-medium rounded-[var(--radius-md)] bg-[var(--accent)] text-white hover:bg-[var(--accent-hover)] transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
				>
					{#if initializing}
						<Loader2 size={14} class="animate-spin" />
						Saving...
					{:else}
						Continue
						<ArrowRight size={14} />
					{/if}
				</button>
			</div>
		</div>
	{/if}
</div>

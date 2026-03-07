<script lang="ts">
	import {
		CheckCircle,
		XCircle,
		Copy,
		Loader2,
		Users,
		FolderGit2,
		MonitorSmartphone,
		ArrowRight,
		Check
	} from 'lucide-svelte';
	import type { SyncDetect, SyncStatusResponse } from '$lib/api-types';
	import { API_BASE } from '$lib/config';

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
	// step 1 = install, 2 = name machine, 3 = group
	let step = $state<1 | 2 | 3>(1);

	// Auto-advance: when detect.running becomes true, move to step 2
	$effect(() => {
		if (detect?.running && step === 1) {
			step = 2;
		}
	});

	// Auto-advance: when status.configured becomes true after init, move to step 3
	$effect(() => {
		if (status?.configured && step === 2) {
			step = 3;
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
				// step 3 advanced by the $effect above
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
		navigator.clipboard
			.writeText(id)
			.then(() => {
				copiedDeviceId = true;
				setTimeout(() => (copiedDeviceId = false), 2000);
			})
			.catch(() => {});
	}

	// -----------------------------------------------
	// Step 3 — Group mode
	// -----------------------------------------------
	type GroupMode = 'create' | 'join' | 'solo' | null;
	let groupMode = $state<GroupMode>(null);

	// Project list for create/solo
	interface ApiProject {
		display_name: string | null;
		encoded_name: string;
	}
	let availableProjects = $state<ApiProject[]>([]);
	let loadingProjects = $state(false);
	let selectedProjects = $state<Set<string>>(new Set());

	async function loadAvailableProjects() {
		if (availableProjects.length > 0) return;
		loadingProjects = true;
		try {
			const res = await fetch(`${API_BASE}/projects`);
			if (res.ok) {
				availableProjects = await res.json();
				// Select all by default
				selectedProjects = new Set(availableProjects.map((p) => p.encoded_name));
			}
		} catch {
			// non-critical
		} finally {
			loadingProjects = false;
		}
	}

	$effect(() => {
		if (groupMode === 'create' || groupMode === 'solo') {
			loadAvailableProjects();
		}
	});

	function toggleProject(encodedName: string) {
		const next = new Set(selectedProjects);
		if (next.has(encodedName)) {
			next.delete(encodedName);
		} else {
			next.add(encodedName);
		}
		selectedProjects = next;
	}

	// Create group form
	let teamName = $state('');
	let creating = $state(false);
	let createError = $state<string | null>(null);

	async function createGroup() {
		const name = groupMode === 'solo' ? (machineName.trim() || 'solo') : teamName.trim();
		if (!name) return;
		creating = true;
		createError = null;
		try {
			// Create team
			const teamRes = await fetch(`${API_BASE}/sync/teams`, {
				method: 'POST',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify({ name, backend: 'syncthing' })
			});
			if (!teamRes.ok) {
				const body = await teamRes.json().catch(() => ({}));
				createError = body?.detail ?? 'Failed to create team.';
				return;
			}

			// Add selected projects
			if (selectedProjects.size > 0) {
				await Promise.all(
					Array.from(selectedProjects).map((encodedName) =>
						fetch(`${API_BASE}/sync/teams/${encodeURIComponent(name)}/projects`, {
							method: 'POST',
							headers: { 'Content-Type': 'application/json' },
							body: JSON.stringify({ name: encodedName, path: '' })
						})
					)
				);
			}

			// Start watch
			await fetch(`${API_BASE}/sync/watch/start`, { method: 'POST' });

			ondone();
		} catch {
			createError = 'Cannot reach backend. Is the API running?';
		} finally {
			creating = false;
		}
	}

	// "Join existing" — no API calls, just show device ID
	let copiedJoinId = $state(false);

	function copyJoinId() {
		const id = detect?.device_id ?? '';
		navigator.clipboard
			.writeText(id)
			.then(() => {
				copiedJoinId = true;
				setTimeout(() => (copiedJoinId = false), 2000);
			})
			.catch(() => {});
	}

	// -----------------------------------------------
	// Progress step labels
	// -----------------------------------------------
	const STEPS = ['Install', 'Name Machine', 'Get Started'] as const;
</script>

<!-- Wizard shell -->
<div class="p-6 space-y-6">
	<!-- Progress bar -->
	<div>
		<div class="flex items-center gap-0 mb-3">
			{#each STEPS as label, i}
				{@const idx = i + 1}
				{@const done = step > idx}
				{@const active = step === idx}
				<div class="flex items-center {i < STEPS.length - 1 ? 'flex-1' : ''}">
					<!-- Circle -->
					<div
						class="w-6 h-6 rounded-full flex items-center justify-center shrink-0 text-[11px] font-semibold transition-colors {done
							? 'bg-[var(--success)] text-white'
							: active
								? 'bg-[var(--accent)] text-white'
								: 'bg-[var(--bg-muted)] text-[var(--text-muted)] border border-[var(--border)]'}"
					>
						{#if done}
							<Check size={12} />
						{:else}
							{idx}
						{/if}
					</div>
					<!-- Connector line -->
					{#if i < STEPS.length - 1}
						<div
							class="flex-1 h-px mx-1.5 transition-colors {done
								? 'bg-[var(--success)]'
								: 'bg-[var(--border)]'}"
						></div>
					{/if}
				</div>
			{/each}
		</div>
		<!-- Step labels -->
		<div class="flex">
			{#each STEPS as label, i}
				{@const idx = i + 1}
				{@const done = step > idx}
				{@const active = step === idx}
				<div class="flex-1 {i === STEPS.length - 1 ? 'text-right' : i === 0 ? 'text-left' : 'text-center'}">
					<span
						class="text-[10px] font-medium uppercase tracking-wide transition-colors {done
							? 'text-[var(--success)]'
							: active
								? 'text-[var(--accent)]'
								: 'text-[var(--text-muted)]'}"
					>
						{label}
					</span>
				</div>
			{/each}
		</div>
	</div>

	<!-- ============================================ -->
	<!-- STEP 1: Install Syncthing                   -->
	<!-- ============================================ -->
	{#if step === 1}
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
							class="rounded-[var(--radius)] px-3 py-2.5 {instr.os === detectedOS
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
						class="w-full px-3 py-2 text-sm rounded-[var(--radius)] border border-[var(--border)] bg-[var(--bg-base)] text-[var(--text-primary)] placeholder:text-[var(--text-muted)] focus:outline-none focus:ring-2 focus:ring-[var(--accent)]/40 focus:border-[var(--accent)] transition-colors"
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

				<!-- Error -->
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
						Saving...
					{:else}
						Continue
						<ArrowRight size={14} />
					{/if}
				</button>
			</div>
		</div>

	<!-- ============================================ -->
	<!-- STEP 3: Create or Join Group                -->
	<!-- ============================================ -->
	{:else if step === 3}
		<div class="space-y-4">
			<div>
				<h2 class="text-sm font-semibold text-[var(--text-primary)]">Get Started</h2>
				<p class="text-xs text-[var(--text-secondary)] mt-0.5">
					How would you like to use sync?
				</p>
			</div>

			<!-- Mode selection cards -->
			{#if groupMode === null}
				<div class="grid grid-cols-1 gap-3">
					<!-- Create Group -->
					<button
						onclick={() => (groupMode = 'create')}
						class="group text-left p-4 rounded-[var(--radius-lg)] border border-[var(--border)] bg-[var(--bg-subtle)] hover:border-[var(--accent)] hover:bg-[var(--accent-muted)] transition-all"
					>
						<div class="flex items-start gap-3">
							<div
								class="w-9 h-9 rounded-[var(--radius)] bg-[var(--bg-muted)] group-hover:bg-[var(--accent-subtle)] flex items-center justify-center shrink-0 transition-colors"
							>
								<Users size={16} class="text-[var(--text-muted)] group-hover:text-[var(--accent)]" />
							</div>
							<div class="flex-1 min-w-0">
								<div class="flex items-center justify-between gap-2">
									<span class="text-sm font-semibold text-[var(--text-primary)]">
										Create Group
									</span>
									<ArrowRight
										size={14}
										class="text-[var(--text-muted)] group-hover:text-[var(--accent)] shrink-0 transition-colors"
									/>
								</div>
								<p class="text-xs text-[var(--text-secondary)] mt-0.5">
									Start a new sync group and invite teammates to join.
								</p>
							</div>
						</div>
					</button>

					<!-- Join Existing -->
					<button
						onclick={() => (groupMode = 'join')}
						class="group text-left p-4 rounded-[var(--radius-lg)] border border-[var(--border)] bg-[var(--bg-subtle)] hover:border-[var(--accent)] hover:bg-[var(--accent-muted)] transition-all"
					>
						<div class="flex items-start gap-3">
							<div
								class="w-9 h-9 rounded-[var(--radius)] bg-[var(--bg-muted)] group-hover:bg-[var(--accent-subtle)] flex items-center justify-center shrink-0 transition-colors"
							>
								<MonitorSmartphone
									size={16}
									class="text-[var(--text-muted)] group-hover:text-[var(--accent)]"
								/>
							</div>
							<div class="flex-1 min-w-0">
								<div class="flex items-center justify-between gap-2">
									<span class="text-sm font-semibold text-[var(--text-primary)]">
										Join Existing
									</span>
									<ArrowRight
										size={14}
										class="text-[var(--text-muted)] group-hover:text-[var(--accent)] shrink-0 transition-colors"
									/>
								</div>
								<p class="text-xs text-[var(--text-secondary)] mt-0.5">
									Share your Device ID with a teammate who already has a group set up.
								</p>
							</div>
						</div>
					</button>

					<!-- Solo sync -->
					<button
						onclick={() => (groupMode = 'solo')}
						class="group text-left p-4 rounded-[var(--radius-lg)] border border-[var(--border)] bg-[var(--bg-subtle)] hover:border-[var(--accent)] hover:bg-[var(--accent-muted)] transition-all"
					>
						<div class="flex items-start gap-3">
							<div
								class="w-9 h-9 rounded-[var(--radius)] bg-[var(--bg-muted)] group-hover:bg-[var(--accent-subtle)] flex items-center justify-center shrink-0 transition-colors"
							>
								<FolderGit2
									size={16}
									class="text-[var(--text-muted)] group-hover:text-[var(--accent)]"
								/>
							</div>
							<div class="flex-1 min-w-0">
								<div class="flex items-center justify-between gap-2">
									<span class="text-sm font-semibold text-[var(--text-primary)]">
										Solo Sync
									</span>
									<ArrowRight
										size={14}
										class="text-[var(--text-muted)] group-hover:text-[var(--accent)] shrink-0 transition-colors"
									/>
								</div>
								<p class="text-xs text-[var(--text-secondary)] mt-0.5">
									Sync just your own sessions across personal machines — no team needed.
								</p>
							</div>
						</div>
					</button>
				</div>

			<!-- ---- Create Group form ---- -->
			{:else if groupMode === 'create'}
				<div class="space-y-4">
					<button
						onclick={() => (groupMode = null)}
						class="text-xs text-[var(--text-muted)] hover:text-[var(--text-secondary)] transition-colors"
					>
						&larr; Back
					</button>

					<div
						class="rounded-[var(--radius-lg)] border border-[var(--border)] bg-[var(--bg-subtle)] p-5 space-y-4"
					>
						<h3 class="text-sm font-semibold text-[var(--text-primary)]">Create a new group</h3>

						<!-- Team name -->
						<div class="space-y-1.5">
							<label
								for="wizard-team-name"
								class="block text-xs font-medium text-[var(--text-secondary)]"
							>
								Team Name
							</label>
							<input
								id="wizard-team-name"
								type="text"
								bind:value={teamName}
								placeholder="e.g. my-team, dev-crew"
								class="w-full px-3 py-2 text-sm rounded-[var(--radius)] border border-[var(--border)] bg-[var(--bg-base)] text-[var(--text-primary)] placeholder:text-[var(--text-muted)] focus:outline-none focus:ring-2 focus:ring-[var(--accent)]/40 focus:border-[var(--accent)] transition-colors"
							/>
						</div>

						<!-- Project selector -->
						<div class="space-y-1.5">
							<p class="block text-xs font-medium text-[var(--text-secondary)]">
								Projects to sync
							</p>

							{#if loadingProjects}
								<div class="space-y-2">
									{#each [1, 2, 3] as i (i)}
										<div
											class="h-9 rounded-[var(--radius)] bg-[var(--bg-muted)] animate-pulse"
										></div>
									{/each}
								</div>
							{:else if availableProjects.length === 0}
								<p class="text-xs text-[var(--text-muted)]">No projects found.</p>
							{:else}
								<div
									class="max-h-40 overflow-y-auto rounded-[var(--radius)] border border-[var(--border)] divide-y divide-[var(--border)]"
								>
									{#each availableProjects as project (project.encoded_name)}
										{@const checked = selectedProjects.has(project.encoded_name)}
										<label
											class="flex items-center gap-2.5 px-3 py-2 cursor-pointer hover:bg-[var(--bg-muted)] transition-colors"
										>
											<input
												type="checkbox"
												{checked}
												onchange={() => toggleProject(project.encoded_name)}
												class="rounded border-[var(--border)] text-[var(--accent)] focus:ring-[var(--accent)]/30"
											/>
											<span class="text-xs text-[var(--text-primary)] truncate">
												{project.display_name ?? project.encoded_name}
											</span>
										</label>
									{/each}
								</div>
								<p class="text-[11px] text-[var(--text-muted)]">
									{selectedProjects.size} of {availableProjects.length} selected
								</p>
							{/if}
						</div>

						<!-- Error -->
						{#if createError}
							<div
								class="flex items-start gap-2.5 p-3 rounded-[var(--radius)] bg-[var(--error-subtle)] border border-[var(--error)]/20"
							>
								<XCircle size={14} class="text-[var(--error)] mt-0.5 shrink-0" />
								<div>
									<p class="text-xs text-[var(--error)]">{createError}</p>
									<button
										onclick={() => (createError = null)}
										class="text-[11px] text-[var(--error)] underline hover:no-underline mt-0.5"
									>
										Dismiss
									</button>
								</div>
							</div>
						{/if}

						<button
							onclick={createGroup}
							disabled={creating || !teamName.trim()}
							class="flex items-center gap-2 px-4 py-2 text-sm font-medium rounded-[var(--radius)] bg-[var(--accent)] text-white hover:bg-[var(--accent-hover)] transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
						>
							{#if creating}
								<Loader2 size={14} class="animate-spin" />
								Creating...
							{:else}
								Create Group
							{/if}
						</button>
					</div>
				</div>

			<!-- ---- Join Existing ---- -->
			{:else if groupMode === 'join'}
				<div class="space-y-4">
					<button
						onclick={() => (groupMode = null)}
						class="text-xs text-[var(--text-muted)] hover:text-[var(--text-secondary)] transition-colors"
					>
						&larr; Back
					</button>

					<div
						class="rounded-[var(--radius-lg)] border border-[var(--border)] bg-[var(--bg-subtle)] p-5 space-y-4"
					>
						<h3 class="text-sm font-semibold text-[var(--text-primary)]">Join an existing group</h3>
						<p class="text-xs text-[var(--text-secondary)]">
							Share your Device ID with the person who manages your sync group. Once they add you,
							sessions will start syncing automatically.
						</p>

						{#if detect?.device_id}
							<div class="space-y-1.5">
								<p class="block text-xs font-medium text-[var(--text-secondary)]">Your Device ID</p>
								<div class="flex items-center gap-2">
									<code
										class="flex-1 px-3 py-2 text-xs font-mono rounded-[var(--radius)] border border-[var(--border)] bg-[var(--bg-muted)] text-[var(--text-secondary)] break-all"
									>
										{detect.device_id}
									</code>
									<button
										onclick={copyJoinId}
										aria-label="Copy device ID to clipboard"
										class="shrink-0 p-2 rounded-[var(--radius)] border border-[var(--border)] bg-[var(--bg-base)] text-[var(--text-muted)] hover:text-[var(--text-primary)] hover:bg-[var(--bg-muted)] transition-colors"
									>
										{#if copiedJoinId}
											<CheckCircle size={14} class="text-[var(--success)]" />
											<span class="sr-only">Copied</span>
										{:else}
											<Copy size={14} />
										{/if}
									</button>
								</div>
								<p class="text-[11px] text-[var(--text-muted)]">
									Send this to your teammate so they can add you to their group.
								</p>
							</div>
						{:else}
							<p class="text-xs text-[var(--text-muted)] italic">
								Device ID not yet available.
							</p>
						{/if}

						<button
							onclick={ondone}
							class="flex items-center gap-2 px-4 py-2 text-sm font-medium rounded-[var(--radius)] bg-[var(--accent)] text-white hover:bg-[var(--accent-hover)] transition-colors"
						>
							Done — I've shared my ID
						</button>
					</div>
				</div>

			<!-- ---- Solo Sync form ---- -->
			{:else if groupMode === 'solo'}
				<div class="space-y-4">
					<button
						onclick={() => (groupMode = null)}
						class="text-xs text-[var(--text-muted)] hover:text-[var(--text-secondary)] transition-colors"
					>
						&larr; Back
					</button>

					<div
						class="rounded-[var(--radius-lg)] border border-[var(--border)] bg-[var(--bg-subtle)] p-5 space-y-4"
					>
						<h3 class="text-sm font-semibold text-[var(--text-primary)]">Solo sync</h3>
						<p class="text-xs text-[var(--text-secondary)]">
							Sync your sessions between your own machines without a shared team. A personal group
							will be created under your machine name.
						</p>

						<!-- Project selector -->
						<div class="space-y-1.5">
							<p class="block text-xs font-medium text-[var(--text-secondary)]">
								Projects to sync
							</p>

							{#if loadingProjects}
								<div class="space-y-2">
									{#each [1, 2, 3] as i (i)}
										<div
											class="h-9 rounded-[var(--radius)] bg-[var(--bg-muted)] animate-pulse"
										></div>
									{/each}
								</div>
							{:else if availableProjects.length === 0}
								<p class="text-xs text-[var(--text-muted)]">No projects found.</p>
							{:else}
								<div
									class="max-h-40 overflow-y-auto rounded-[var(--radius)] border border-[var(--border)] divide-y divide-[var(--border)]"
								>
									{#each availableProjects as project (project.encoded_name)}
										{@const checked = selectedProjects.has(project.encoded_name)}
										<label
											class="flex items-center gap-2.5 px-3 py-2 cursor-pointer hover:bg-[var(--bg-muted)] transition-colors"
										>
											<input
												type="checkbox"
												{checked}
												onchange={() => toggleProject(project.encoded_name)}
												class="rounded border-[var(--border)] text-[var(--accent)] focus:ring-[var(--accent)]/30"
											/>
											<span class="text-xs text-[var(--text-primary)] truncate">
												{project.display_name ?? project.encoded_name}
											</span>
										</label>
									{/each}
								</div>
								<p class="text-[11px] text-[var(--text-muted)]">
									{selectedProjects.size} of {availableProjects.length} selected
								</p>
							{/if}
						</div>

						<!-- Error -->
						{#if createError}
							<div
								class="flex items-start gap-2.5 p-3 rounded-[var(--radius)] bg-[var(--error-subtle)] border border-[var(--error)]/20"
							>
								<XCircle size={14} class="text-[var(--error)] mt-0.5 shrink-0" />
								<div>
									<p class="text-xs text-[var(--error)]">{createError}</p>
									<button
										onclick={() => (createError = null)}
										class="text-[11px] text-[var(--error)] underline hover:no-underline mt-0.5"
									>
										Dismiss
									</button>
								</div>
							</div>
						{/if}

						<button
							onclick={createGroup}
							disabled={creating || !machineName.trim()}
							class="flex items-center gap-2 px-4 py-2 text-sm font-medium rounded-[var(--radius)] bg-[var(--accent)] text-white hover:bg-[var(--accent-hover)] transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
						>
							{#if creating}
								<Loader2 size={14} class="animate-spin" />
								Setting up...
							{:else}
								Start Solo Sync
							{/if}
						</button>
					</div>
				</div>
			{/if}
		</div>
	{/if}
</div>

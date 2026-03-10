<script lang="ts">
	import { onMount } from 'svelte';
	import { API_BASE } from '$lib/config';
	import {
		Loader2,
		ShieldCheck,
		ShieldAlert,
		ArrowUpDown,
		ArrowUp,
		ArrowDown,
		Ban,
		Info
	} from 'lucide-svelte';

	interface Props {
		teamName: string;
	}

	let { teamName }: Props = $props();

	interface SettingValue {
		value: string;
		source: string;
	}

	interface TeamSettingsResponse {
		team_name: string;
		settings: {
			auto_accept_members: SettingValue;
			sync_direction: SettingValue;
			sync_session_limit: SettingValue;
		};
	}

	let loading = $state(true);
	let error = $state<string | null>(null);
	let saving = $state<string | null>(null);

	let autoAccept = $state<SettingValue>({ value: 'false', source: 'default' });
	let syncDirection = $state<SettingValue>({ value: 'both', source: 'default' });
	let sessionLimit = $state<SettingValue>({ value: 'all', source: 'default' });

	const DIRECTION_OPTIONS: { value: string; label: string; icon: typeof ArrowUpDown; desc: string }[] = [
		{ value: 'both', label: 'Both', icon: ArrowUpDown, desc: 'Full two-way sync — sending and receiving sessions with this team' },
		{ value: 'send_only', label: 'Send', icon: ArrowUp, desc: 'Outbound only — sharing your sessions but not receiving from others' },
		{ value: 'receive_only', label: 'Receive', icon: ArrowDown, desc: 'Inbound only — receiving team sessions but not sharing yours' },
		{ value: 'none', label: 'Paused', icon: Ban, desc: 'Sync paused — no session data flows in either direction' }
	];

	const LIMIT_OPTIONS: { value: string; label: string; desc: string }[] = [
		{ value: 'all', label: 'All sessions', desc: 'Sync every session for shared projects' },
		{ value: 'recent_100', label: 'Recent 100', desc: 'Only the most recent 100 sessions per project' },
		{ value: 'recent_10', label: 'Recent 10', desc: 'Only the most recent 10 sessions per project' }
	];

	let activeDirOption = $derived(DIRECTION_OPTIONS.find((o) => o.value === syncDirection.value));
	let activeLimitOption = $derived(LIMIT_OPTIONS.find((o) => o.value === sessionLimit.value));

	function sourceLabel(source: string): string {
		switch (source) {
			case 'default':
				return 'Default';
			case 'team':
				return 'Team override';
			case 'device':
				return 'Device override';
			case 'member':
				return 'Member override';
			default:
				return source;
		}
	}

	async function fetchSettings() {
		loading = true;
		error = null;
		try {
			const res = await fetch(
				`${API_BASE}/sync/teams/${encodeURIComponent(teamName)}/settings`
			);
			if (!res.ok) {
				const body = await res.json().catch(() => ({}));
				error = body.detail || `Failed to load settings (${res.status})`;
				return;
			}
			const data: TeamSettingsResponse = await res.json();
			autoAccept = data.settings.auto_accept_members;
			syncDirection = data.settings.sync_direction;
			sessionLimit = data.settings.sync_session_limit;
		} catch {
			error = 'Network error loading settings.';
		} finally {
			loading = false;
		}
	}

	async function patchSetting(field: string, value: string) {
		saving = field;
		try {
			const res = await fetch(
				`${API_BASE}/sync/teams/${encodeURIComponent(teamName)}/settings`,
				{
					method: 'PATCH',
					headers: { 'Content-Type': 'application/json' },
					body: JSON.stringify({ [field]: value })
				}
			);
			if (res.ok) {
				if (field === 'auto_accept_members') {
					autoAccept = { value, source: 'team' };
				} else if (field === 'sync_direction') {
					syncDirection = { value, source: 'team' };
				} else if (field === 'sync_session_limit') {
					sessionLimit = { value, source: 'team' };
				}
			} else {
				const body = await res.json().catch(() => ({}));
				error = body.detail || `Failed to save ${field} (${res.status})`;
			}
		} finally {
			saving = null;
		}
	}

	function handleToggleAutoAccept() {
		const newValue = autoAccept.value === 'true' ? 'false' : 'true';
		patchSetting('auto_accept_members', newValue);
	}

	function handleDirectionChange(value: string) {
		if (value === syncDirection.value) return;
		patchSetting('sync_direction', value);
	}

	function handleLimitChange(value: string) {
		if (value === sessionLimit.value) return;
		patchSetting('sync_session_limit', value);
	}

	onMount(() => {
		fetchSettings();
	});
</script>

{#if loading}
	<div class="flex items-center justify-center py-16">
		<Loader2 size={24} class="animate-spin text-[var(--text-muted)]" />
	</div>
{:else if error}
	<div class="rounded-lg border border-[var(--error)]/20 bg-[var(--error)]/5 p-4">
		<p class="text-sm text-[var(--error)]">{error}</p>
		<button
			onclick={fetchSettings}
			class="mt-2 text-xs text-[var(--accent)] hover:underline"
		>
			Retry
		</button>
	</div>
{:else}
	<div class="space-y-5">

		<!-- ═══ ACCESS CONTROL ═══ -->
		<div
			class="rounded-lg border overflow-hidden transition-colors
				{autoAccept.value === 'true'
					? 'border-[var(--warning)]/30'
					: 'border-[var(--success)]/30'}"
		>
			<!-- Colored top accent bar -->
			<div class="h-[3px] {autoAccept.value === 'true' ? 'bg-[var(--warning)]' : 'bg-[var(--success)]'}"></div>

			<div class="p-5">
				<div class="flex items-start justify-between gap-4">
					<div class="flex items-start gap-3.5">
						<!-- Status icon -->
						<div
							class="mt-0.5 p-2 rounded-lg transition-colors
								{autoAccept.value === 'true'
									? 'bg-[var(--warning)]/10 text-[var(--warning)]'
									: 'bg-[var(--success)]/10 text-[var(--success)]'}"
						>
							{#if autoAccept.value === 'true'}
								<ShieldAlert size={18} />
							{:else}
								<ShieldCheck size={18} />
							{/if}
						</div>

						<div>
							<div class="flex items-center gap-2.5">
								<h3 class="text-sm font-semibold text-[var(--text-primary)]">
									Auto-accept new members
								</h3>
								{#if autoAccept.source !== 'default'}
									<span class="px-1.5 py-0.5 text-[10px] font-medium rounded bg-[var(--bg-muted)] text-[var(--text-muted)] border border-[var(--border-subtle)]">
										{sourceLabel(autoAccept.source)}
									</span>
								{/if}
							</div>

							<!-- Consequence description — changes with state -->
							<div class="mt-2 flex items-start gap-2">
								<span
									class="mt-[3px] w-1.5 h-1.5 rounded-full shrink-0
										{autoAccept.value === 'true'
											? 'bg-[var(--warning)]'
											: 'bg-[var(--success)]'}"
								></span>
								<p class="text-xs leading-relaxed
									{autoAccept.value === 'true'
										? 'text-[var(--warning)]'
										: 'text-[var(--text-muted)]'}">
									{#if autoAccept.value === 'true'}
										Open access — any device with your join code is automatically added to this team
									{:else}
										Manual approval — new devices appear as join requests for you to review before syncing
									{/if}
								</p>
							</div>
						</div>
					</div>

					<!-- Toggle switch -->
					<button
						onclick={handleToggleAutoAccept}
						disabled={saving === 'auto_accept_members'}
						class="relative inline-flex h-6 w-11 shrink-0 cursor-pointer rounded-full border-2 border-transparent
							transition-colors duration-200 ease-in-out
							disabled:opacity-50 disabled:cursor-not-allowed
							{autoAccept.value === 'true'
								? 'bg-[var(--warning)]'
								: 'bg-[var(--bg-muted)] border-[var(--border)]'}"
						role="switch"
						aria-checked={autoAccept.value === 'true'}
						aria-label="Auto-accept members"
					>
						{#if saving === 'auto_accept_members'}
							<span class="absolute inset-0 flex items-center justify-center">
								<Loader2 size={12} class="animate-spin text-white" />
							</span>
						{:else}
							<span
								class="pointer-events-none inline-block h-5 w-5 transform rounded-full bg-white shadow-sm ring-0
									transition duration-200 ease-in-out
									{autoAccept.value === 'true' ? 'translate-x-5' : 'translate-x-0'}"
							></span>
						{/if}
					</button>
				</div>
			</div>
		</div>

		<!-- ═══ DATA FLOW ═══ -->
		<div class="rounded-lg border border-[var(--border)] bg-[var(--bg-subtle)] p-5">
			<div class="flex items-center justify-between mb-1">
				<h3 class="text-sm font-semibold text-[var(--text-primary)]">Sync direction</h3>
				{#if syncDirection.source !== 'default'}
					<span class="px-1.5 py-0.5 text-[10px] font-medium rounded bg-[var(--bg-muted)] text-[var(--text-muted)] border border-[var(--border-subtle)]">
						{sourceLabel(syncDirection.source)}
					</span>
				{/if}
			</div>
			<p class="text-xs text-[var(--text-muted)] mb-4">
				Controls what session data flows between you and this team
			</p>

			<!-- Direction grid with icons -->
			<div class="grid grid-cols-4 gap-1.5 mb-3">
				{#each DIRECTION_OPTIONS as opt (opt.value)}
					{@const active = syncDirection.value === opt.value}
					{@const DirIcon = opt.icon}
					<button
						class="flex flex-col items-center gap-1.5 py-2.5 px-2 rounded-lg text-xs font-medium transition-all
							{active
								? 'bg-[var(--accent)] text-white shadow-sm'
								: 'bg-[var(--bg-muted)] text-[var(--text-secondary)] hover:text-[var(--text-primary)] border border-[var(--border)]/50'}"
						onclick={() => handleDirectionChange(opt.value)}
						disabled={saving === 'sync_direction'}
					>
						<DirIcon size={15} />
						{opt.label}
					</button>
				{/each}
			</div>

			<!-- Active description -->
			{#if activeDirOption}
				<p class="text-[11px] text-[var(--text-muted)] flex items-start gap-1.5">
					<Info size={11} class="shrink-0 mt-0.5" />
					{activeDirOption.desc}
				</p>
			{/if}
		</div>

		<!-- ═══ SESSION SCOPE ═══ -->
		<div class="rounded-lg border border-[var(--border)] bg-[var(--bg-subtle)] p-5">
			<div class="flex items-center justify-between mb-1">
				<h3 class="text-sm font-semibold text-[var(--text-primary)]">Sessions per project</h3>
				{#if sessionLimit.source !== 'default'}
					<span class="px-1.5 py-0.5 text-[10px] font-medium rounded bg-[var(--bg-muted)] text-[var(--text-muted)] border border-[var(--border-subtle)]">
						{sourceLabel(sessionLimit.source)}
					</span>
				{/if}
			</div>
			<p class="text-xs text-[var(--text-muted)] mb-4">
				Limits how many sessions are synced for each shared project
			</p>

			<div class="inline-flex rounded-lg border border-[var(--border)] bg-[var(--bg-muted)] p-0.5 gap-0.5">
				{#each LIMIT_OPTIONS as opt (opt.value)}
					<button
						class="rounded-md px-3.5 py-1.5 text-xs font-medium transition-all
							{sessionLimit.value === opt.value
								? 'bg-[var(--accent)] text-white shadow-sm'
								: 'text-[var(--text-secondary)] hover:text-[var(--text-primary)]'}"
						onclick={() => handleLimitChange(opt.value)}
						disabled={saving === 'sync_session_limit'}
					>
						{opt.label}
					</button>
				{/each}
			</div>

			<!-- Active limit description -->
			{#if activeLimitOption}
				<p class="mt-2.5 text-[11px] text-[var(--text-muted)] flex items-start gap-1.5">
					<Info size={11} class="shrink-0 mt-0.5" />
					{activeLimitOption.desc}
				</p>
			{/if}
		</div>
	</div>
{/if}

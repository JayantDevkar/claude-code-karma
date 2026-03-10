<script lang="ts">
	import { onMount } from 'svelte';
	import { API_BASE } from '$lib/config';
	import { Loader2, Info } from 'lucide-svelte';

	interface Props {
		teamName: string;
	}

	let { teamName }: Props = $props();

	// Setting shape from API
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
	let saving = $state<string | null>(null); // which field is currently saving

	// Setting values
	let autoAccept = $state<SettingValue>({ value: 'true', source: 'default' });
	let syncDirection = $state<SettingValue>({ value: 'both', source: 'default' });
	let sessionLimit = $state<SettingValue>({ value: 'all', source: 'default' });

	const DIRECTION_OPTIONS: { value: string; label: string }[] = [
		{ value: 'both', label: 'Both' },
		{ value: 'send_only', label: 'Send Only' },
		{ value: 'receive_only', label: 'Receive Only' },
		{ value: 'none', label: 'None' }
	];

	const LIMIT_OPTIONS: { value: string; label: string }[] = [
		{ value: 'all', label: 'All' },
		{ value: 'recent_100', label: 'Recent 100' },
		{ value: 'recent_10', label: 'Recent 10' }
	];

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
				// Update local state on success
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
	<div class="space-y-6">
		<!-- Auto-accept members -->
		<div class="rounded-lg border border-[var(--border)] bg-[var(--bg-subtle)] p-4">
			<div class="flex items-center justify-between">
				<div class="flex-1 min-w-0">
					<div class="flex items-center gap-2">
						<h3 class="text-sm font-medium text-[var(--text-primary)]">Auto-accept members</h3>
						<span class="inline-flex items-center gap-1 px-1.5 py-0.5 text-[10px] font-medium rounded bg-[var(--bg-muted)] text-[var(--text-muted)] border border-[var(--border-subtle)]">
							<Info size={9} />
							{sourceLabel(autoAccept.source)}
						</span>
					</div>
					<p class="text-xs text-[var(--text-muted)] mt-1">
						Automatically accept new devices that request to join this team
					</p>
				</div>
				<button
					onclick={handleToggleAutoAccept}
					disabled={saving === 'auto_accept_members'}
					class="relative inline-flex h-6 w-11 shrink-0 cursor-pointer rounded-full border-2 border-transparent
						transition-colors duration-200 ease-in-out
						disabled:opacity-50 disabled:cursor-not-allowed
						{autoAccept.value === 'true' ? 'bg-[var(--accent)]' : 'bg-[var(--bg-muted)] border-[var(--border)]'}"
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

		<!-- Sync direction -->
		<div class="rounded-lg border border-[var(--border)] bg-[var(--bg-subtle)] p-4">
			<div class="flex items-center gap-2 mb-3">
				<h3 class="text-sm font-medium text-[var(--text-primary)]">Sync direction</h3>
				<span class="inline-flex items-center gap-1 px-1.5 py-0.5 text-[10px] font-medium rounded bg-[var(--bg-muted)] text-[var(--text-muted)] border border-[var(--border-subtle)]">
					<Info size={9} />
					{sourceLabel(syncDirection.source)}
				</span>
			</div>
			<p class="text-xs text-[var(--text-muted)] mb-3">
				Control whether this machine sends, receives, or both for session data
			</p>
			<div class="inline-flex rounded-md border border-[var(--border)] bg-[var(--bg-muted)] p-0.5">
				{#each DIRECTION_OPTIONS as opt}
					<button
						class="rounded px-3 py-1.5 text-xs font-medium transition-colors
							{syncDirection.value === opt.value
								? 'bg-[var(--accent)] text-white shadow-sm'
								: 'text-[var(--text-secondary)] hover:text-[var(--text-primary)]'}"
						onclick={() => handleDirectionChange(opt.value)}
						disabled={saving === 'sync_direction'}
					>
						{opt.label}
					</button>
				{/each}
			</div>
		</div>

		<!-- Session limit -->
		<div class="rounded-lg border border-[var(--border)] bg-[var(--bg-subtle)] p-4">
			<div class="flex items-center gap-2 mb-3">
				<h3 class="text-sm font-medium text-[var(--text-primary)]">Session limit</h3>
				<span class="inline-flex items-center gap-1 px-1.5 py-0.5 text-[10px] font-medium rounded bg-[var(--bg-muted)] text-[var(--text-muted)] border border-[var(--border-subtle)]">
					<Info size={9} />
					{sourceLabel(sessionLimit.source)}
				</span>
			</div>
			<p class="text-xs text-[var(--text-muted)] mb-3">
				How many sessions to sync per project
			</p>
			<div class="inline-flex rounded-md border border-[var(--border)] bg-[var(--bg-muted)] p-0.5">
				{#each LIMIT_OPTIONS as opt}
					<button
						class="rounded px-3 py-1.5 text-xs font-medium transition-colors
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
		</div>
	</div>
{/if}

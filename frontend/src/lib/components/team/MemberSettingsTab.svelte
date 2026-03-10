<script lang="ts">
	import { onMount } from 'svelte';
	import { API_BASE } from '$lib/config';
	import { Loader2, Info, RotateCcw } from 'lucide-svelte';
	import type { MemberProfile } from '$lib/api-types';

	interface Props {
		profile: MemberProfile;
	}

	let { profile }: Props = $props();

	interface SettingValue {
		value: string;
		source: string;
	}

	interface MemberSettingsResponse {
		team_name: string;
		device_id: string;
		member_name: string;
		settings: {
			auto_accept_members: SettingValue;
			sync_direction: SettingValue;
		};
	}

	interface TeamSettingsState {
		teamName: string;
		loading: boolean;
		error: string | null;
		syncDirection: SettingValue;
		saving: boolean;
	}

	const DIRECTION_OPTIONS: { value: string; label: string }[] = [
		{ value: 'both', label: 'Both' },
		{ value: 'send_only', label: 'Send Only' },
		{ value: 'receive_only', label: 'Recv Only' },
		{ value: 'none', label: 'None' }
	];

	function sourceLabel(source: string): string {
		switch (source) {
			case 'default':
				return 'Default';
			case 'team':
				return 'Inherits from team';
			case 'device':
				return 'Device override';
			case 'member':
				return 'Member override';
			default:
				return source;
		}
	}

	function sourceBadgeClass(source: string): string {
		if (source === 'member') {
			return 'bg-[var(--accent)]/10 text-[var(--accent)] border-[var(--accent)]/20';
		}
		return 'bg-[var(--bg-muted)] text-[var(--text-muted)] border-[var(--border-subtle)]';
	}

	let teamStates = $state<TeamSettingsState[]>([]);

	async function fetchTeamSettings(teamName: string, idx: number) {
		teamStates[idx].loading = true;
		teamStates[idx].error = null;
		try {
			const res = await fetch(
				`${API_BASE}/sync/teams/${encodeURIComponent(teamName)}/members/${encodeURIComponent(profile.device_id)}/settings`
			);
			if (!res.ok) {
				const body = await res.json().catch(() => ({}));
				teamStates[idx].error = body.detail || `Failed to load (${res.status})`;
				return;
			}
			const data: MemberSettingsResponse = await res.json();
			teamStates[idx].syncDirection = data.settings.sync_direction;
		} catch {
			teamStates[idx].error = 'Network error';
		} finally {
			teamStates[idx].loading = false;
		}
	}

	async function handleDirectionChange(idx: number, value: string) {
		const state = teamStates[idx];
		if (state.saving || value === state.syncDirection.value) return;

		// Optimistic update
		const prev = { ...state.syncDirection };
		teamStates[idx].syncDirection = { value, source: 'member' };
		teamStates[idx].saving = true;

		try {
			const res = await fetch(
				`${API_BASE}/sync/teams/${encodeURIComponent(state.teamName)}/members/${encodeURIComponent(profile.device_id)}/settings`,
				{
					method: 'PATCH',
					headers: { 'Content-Type': 'application/json' },
					body: JSON.stringify({ sync_direction: value })
				}
			);
			if (!res.ok) {
				// Revert on failure
				teamStates[idx].syncDirection = prev;
				const body = await res.json().catch(() => ({}));
				teamStates[idx].error = body.detail || `Save failed (${res.status})`;
			}
		} catch {
			teamStates[idx].syncDirection = prev;
			teamStates[idx].error = 'Network error saving';
		} finally {
			teamStates[idx].saving = false;
		}
	}

	async function handleReset(idx: number) {
		const state = teamStates[idx];
		if (state.saving) return;

		teamStates[idx].saving = true;

		try {
			const res = await fetch(
				`${API_BASE}/sync/teams/${encodeURIComponent(state.teamName)}/members/${encodeURIComponent(profile.device_id)}/settings`,
				{
					method: 'PATCH',
					headers: { 'Content-Type': 'application/json' },
					body: JSON.stringify({ sync_direction: null })
				}
			);
			if (res.ok) {
				// Re-fetch to get the resolved team/default value
				await fetchTeamSettings(state.teamName, idx);
			} else {
				const body = await res.json().catch(() => ({}));
				teamStates[idx].error = body.detail || `Reset failed (${res.status})`;
			}
		} catch {
			teamStates[idx].error = 'Network error resetting';
		} finally {
			teamStates[idx].saving = false;
		}
	}

	onMount(() => {
		teamStates = profile.teams.map((t) => ({
			teamName: t.name,
			loading: true,
			error: null,
			syncDirection: { value: 'both', source: 'default' },
			saving: false
		}));

		profile.teams.forEach((t, i) => {
			fetchTeamSettings(t.name, i);
		});
	});
</script>

{#if profile.teams.length === 0}
	<div class="text-center py-12">
		<p class="text-sm text-[var(--text-muted)]">Not a member of any teams.</p>
	</div>
{:else}
	<div class="space-y-4">
		<p class="text-xs text-[var(--text-muted)]">
			Override sync direction per team. When no override is set, the team's default applies.
		</p>

		{#each teamStates as state, idx (state.teamName)}
			<div class="rounded-lg border border-[var(--border)] bg-[var(--bg-subtle)]">
				<!-- Team header -->
				<div class="flex items-center justify-between px-4 py-3 border-b border-[var(--border)]/50">
					<div class="flex items-center gap-2">
						<a
							href="/team/{encodeURIComponent(state.teamName)}"
							class="text-sm font-medium text-[var(--text-primary)] hover:text-[var(--accent)] transition-colors"
						>
							{state.teamName}
						</a>
						{#if profile.teams[idx]}
							<span class="text-[11px] text-[var(--text-muted)]">
								{profile.teams[idx].member_count} member{profile.teams[idx].member_count !== 1 ? 's' : ''}
							</span>
						{/if}
					</div>

					{#if state.syncDirection.source === 'member' && !state.loading}
						<button
							onclick={() => handleReset(idx)}
							disabled={state.saving}
							class="inline-flex items-center gap-1 px-2 py-1 text-[11px] font-medium rounded
								text-[var(--text-muted)] hover:text-[var(--text-primary)] hover:bg-[var(--bg-muted)]
								transition-colors disabled:opacity-50"
							title="Reset to team default"
						>
							{#if state.saving}
								<Loader2 size={11} class="animate-spin" />
							{:else}
								<RotateCcw size={11} />
							{/if}
							Reset
						</button>
					{/if}
				</div>

				<!-- Settings body -->
				<div class="p-4">
					{#if state.loading}
						<div class="flex items-center justify-center py-6">
							<Loader2 size={18} class="animate-spin text-[var(--text-muted)]" />
						</div>
					{:else if state.error}
						<div class="rounded-md border border-[var(--error)]/20 bg-[var(--error)]/5 p-3">
							<p class="text-xs text-[var(--error)]">{state.error}</p>
							<button
								onclick={() => fetchTeamSettings(state.teamName, idx)}
								class="mt-1 text-[11px] text-[var(--accent)] hover:underline"
							>
								Retry
							</button>
						</div>
					{:else}
						<div>
							<div class="flex items-center gap-2 mb-3">
								<span class="text-xs font-medium text-[var(--text-secondary)]">Sync direction</span>
								<span class="inline-flex items-center gap-1 px-1.5 py-0.5 text-[10px] font-medium rounded border {sourceBadgeClass(state.syncDirection.source)}">
									<Info size={9} />
									{sourceLabel(state.syncDirection.source)}
								</span>
							</div>

							<div class="inline-flex rounded-md border border-[var(--border)] bg-[var(--bg-muted)] p-0.5">
								{#each DIRECTION_OPTIONS as opt}
									<button
										class="rounded px-3 py-1.5 text-xs font-medium transition-colors
											{state.syncDirection.value === opt.value
												? 'bg-[var(--accent)] text-white shadow-sm'
												: 'text-[var(--text-secondary)] hover:text-[var(--text-primary)]'}"
										onclick={() => handleDirectionChange(idx, opt.value)}
										disabled={state.saving}
									>
										{opt.label}
									</button>
								{/each}
							</div>

							{#if state.syncDirection.source !== 'member'}
								<p class="mt-2 text-[11px] text-[var(--text-muted)]">
									Click a direction to create a member-level override for this team.
								</p>
							{/if}
						</div>
					{/if}
				</div>
			</div>
		{/each}
	</div>
{/if}

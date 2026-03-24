<script lang="ts">
	import { onMount } from 'svelte';
	import { API_BASE } from '$lib/config';
	import {
		Loader2,
		Info,
		RotateCcw,
		ArrowUpDown,
		ArrowUp,
		ArrowDown,
		Ban,
		ChevronRight
	} from 'lucide-svelte';
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

	const DIRECTION_OPTIONS: {
		value: string;
		label: string;
		icon: typeof ArrowUpDown;
		desc: string;
	}[] = [
		{
			value: 'both',
			label: 'Both',
			icon: ArrowUpDown,
			desc: 'Sending and receiving sessions'
		},
		{
			value: 'send_only',
			label: 'Send',
			icon: ArrowUp,
			desc: 'Sharing sessions, not receiving'
		},
		{
			value: 'receive_only',
			label: 'Receive',
			icon: ArrowDown,
			desc: 'Receiving sessions, not sharing'
		},
		{ value: 'none', label: 'Paused', icon: Ban, desc: 'No data flows in either direction' }
	];

	function sourceLabel(source: string): string {
		switch (source) {
			case 'default':
				return 'Default';
			case 'team':
				return 'Team setting';
			case 'device':
				return 'Device override';
			case 'member':
				return 'Member override';
			default:
				return source;
		}
	}

	const CASCADE_STEPS: string[] = ['default', 'team', 'member'];

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
	<div class="space-y-5">
		<!-- Explainer banner -->
		<div class="flex items-start gap-3 p-4 rounded-lg bg-[var(--bg-subtle)] border border-[var(--border)]/50">
			<Info size={14} class="shrink-0 mt-0.5 text-[var(--text-muted)]" />
			<p class="text-xs text-[var(--text-muted)] leading-relaxed">
				Override sync direction for this member per team. When no override is set,
				the team default applies. Overrides only affect this member's data flow.
			</p>
		</div>

		{#each teamStates as state, idx (state.teamName)}
			<div class="rounded-lg border border-[var(--border)] overflow-hidden">
				<!-- Team header -->
				<div class="flex items-center justify-between px-5 py-3 bg-[var(--bg-subtle)] border-b border-[var(--border)]/50">
					<div class="flex items-center gap-2.5">
						<a
							href="/team/{encodeURIComponent(state.teamName)}"
							class="text-sm font-semibold text-[var(--text-primary)] hover:text-[var(--accent)] transition-colors"
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
							class="inline-flex items-center gap-1.5 px-2.5 py-1 text-[11px] font-medium rounded-md
								text-[var(--text-muted)] hover:text-[var(--error)] hover:bg-[var(--error)]/5
								border border-transparent hover:border-[var(--error)]/20
								transition-all disabled:opacity-50"
							title="Remove override, use team default"
						>
							{#if state.saving}
								<Loader2 size={11} class="animate-spin" />
							{:else}
								<RotateCcw size={11} />
							{/if}
							Remove override
						</button>
					{/if}
				</div>

				<!-- Settings body -->
				<div class="p-5">
					{#if state.loading}
						<div class="flex items-center justify-center py-8">
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
						<!-- Cascade indicator: default → team → member -->
						<div class="flex items-center gap-1.5 mb-4">
							{#each CASCADE_STEPS as step, i}
								{@const isActive = state.syncDirection.source === step}
								{@const isPast = CASCADE_STEPS.indexOf(state.syncDirection.source) > i}
								{#if i > 0}
									<ChevronRight
										size={10}
										class="{isPast || isActive ? 'text-[var(--accent)]' : 'text-[var(--text-faint)]'}"
									/>
								{/if}
								<span
									class="text-[11px] transition-colors
										{isActive
											? 'font-semibold text-[var(--accent)]'
											: isPast
												? 'text-[var(--text-muted)]'
												: 'text-[var(--text-faint)]'}"
								>
									{step}
									{#if isActive}
										<span class="ml-0.5 inline-block w-1.5 h-1.5 rounded-full bg-[var(--accent)] align-middle"></span>
									{/if}
								</span>
							{/each}
						</div>

						<!-- Direction grid -->
						<div class="grid grid-cols-4 gap-1.5 mb-3">
							{#each DIRECTION_OPTIONS as opt (opt.value)}
								{@const active = state.syncDirection.value === opt.value}
								{@const DirIcon = opt.icon}
								<button
									class="flex flex-col items-center gap-1.5 py-2.5 px-2 rounded-lg text-xs font-medium transition-all
										{active
											? 'bg-[var(--accent)] text-white shadow-sm'
											: 'bg-[var(--bg-muted)] text-[var(--text-secondary)] hover:text-[var(--text-primary)] border border-[var(--border)]/50'}"
									onclick={() => handleDirectionChange(idx, opt.value)}
									disabled={state.saving}
								>
									<DirIcon size={15} />
									{opt.label}
								</button>
							{/each}
						</div>

						<!-- Active description -->
						{#each DIRECTION_OPTIONS.filter((o) => o.value === state.syncDirection.value) as activeDir}
							<p class="text-[11px] text-[var(--text-muted)] flex items-start gap-1.5">
								<Info size={11} class="shrink-0 mt-0.5" />
								{activeDir.desc}
								{#if state.syncDirection.source !== 'member'}
									<span class="italic text-[var(--text-faint)]">
										(inherited from {sourceLabel(state.syncDirection.source).toLowerCase()})
									</span>
								{/if}
							</p>
						{/each}

						{#if state.syncDirection.source !== 'member'}
							<p class="mt-3 text-[11px] text-[var(--text-faint)] italic">
								Select a direction to create a member-level override
							</p>
						{/if}
					{/if}
				</div>
			</div>
		{/each}
	</div>
{/if}

<script lang="ts">
	import { API_BASE } from '$lib/config';
	import { Wifi, WifiOff, Trash2, Loader2, ArrowUpDown, Settings } from 'lucide-svelte';
	import type { SyncTeamMember, SyncDevice, TeamSessionStat } from '$lib/api-types';
	import { getTeamMemberColor, getTeamMemberHexColor, formatBytes } from '$lib/utils';
	import MemberSparkline from './MemberSparkline.svelte';

	interface Props {
		members: SyncTeamMember[];
		teamName: string;
		devices: SyncDevice[];
		userId: string | undefined;
		sessionStats: TeamSessionStat[];
		detectData: { running: boolean } | null;
		onrefresh: () => void;
	}

	let { members, teamName, devices, userId, sessionStats, detectData, onrefresh }: Props =
		$props();

	let confirmRemove = $state<string | null>(null);
	let removing = $state(false);

	function getDeviceInfo(member: SyncTeamMember): SyncDevice | undefined {
		return devices.find((d) => d.device_id === member.device_id);
	}

	function isConnected(member: SyncTeamMember): boolean {
		return getDeviceInfo(member)?.connected ?? member.connected ?? false;
	}

	function isSelf(member: SyncTeamMember): boolean {
		return member.name === userId;
	}

	// Build 14-day sparkline data for a member
	function buildSparklineData(memberName: string): number[] {
		const today = new Date();
		const days: number[] = new Array(14).fill(0);

		for (const stat of sessionStats) {
			if (stat.member_name !== memberName) continue;
			const statDate = new Date(stat.date);
			const diffMs = today.getTime() - statDate.getTime();
			const diffDays = Math.floor(diffMs / (1000 * 60 * 60 * 24));
			if (diffDays >= 0 && diffDays < 14) {
				days[13 - diffDays] += stat.packaged + stat.received;
			}
		}

		return days;
	}

	function getMemberSessionTotals(memberName: string): { sent: number; received: number } {
		let sent = 0;
		let received = 0;
		for (const stat of sessionStats) {
			if (stat.member_name !== memberName) continue;
			sent += stat.packaged;
			received += stat.received;
		}
		return { sent, received };
	}

	async function handleRemove(memberName: string) {
		if (removing) return;
		removing = true;

		try {
			const res = await fetch(
				`${API_BASE}/sync/teams/${encodeURIComponent(teamName)}/members/${encodeURIComponent(memberName)}`,
				{ method: 'DELETE' }
			);

			if (res.ok) {
				onrefresh();
			}
		} catch {
			// best-effort
		} finally {
			removing = false;
			confirmRemove = null;
		}
	}
</script>

<div class="space-y-4">
	{#if members.length === 0}
		<p class="text-sm text-[var(--text-muted)] py-8 text-center">
			No members yet. Share your join code to invite teammates.
		</p>
	{:else}
		<div class="grid grid-cols-1 md:grid-cols-2 gap-3">
			{#each members as member (member.name)}
				{@const colors = getTeamMemberColor(member.name)}
				{@const hexColor = getTeamMemberHexColor(member.name)}
				{@const device = getDeviceInfo(member)}
				{@const connected = device?.connected ?? member.connected ?? false}
				{@const self = isSelf(member)}
				{@const inBytes = device?.in_bytes_total ?? member.in_bytes_total ?? 0}
				{@const outBytes = device?.out_bytes_total ?? member.out_bytes_total ?? 0}
				{@const sparkline = buildSparklineData(member.name)}
				{@const totals = getMemberSessionTotals(member.name)}
				<a
					href="/members/{encodeURIComponent(member.device_id)}"
					class="relative flex flex-col gap-3 p-4 rounded-lg border border-[var(--border)] bg-[var(--bg-base)] hover:border-[var(--accent)]/30 hover:shadow-sm transition-all"
				>
					<!-- Top row: avatar + name + connection status -->
					<div class="flex items-center gap-3">
						<!-- Avatar -->
						<div
							class="w-10 h-10 rounded-full flex items-center justify-center text-sm font-bold shrink-0"
							style="background: {hexColor}; color: white; box-shadow: 0 0 0 2px {hexColor}33;"
						>
							{member.name.charAt(0).toUpperCase()}
						</div>

						<div class="flex-1 min-w-0">
							<div class="flex items-center gap-2">
								<span class="text-sm font-medium text-[var(--text-primary)] truncate">
									{member.name}
								</span>
								{#if self}
									<span
										class="shrink-0 px-1.5 py-0.5 text-[10px] font-medium rounded {colors.badge}"
									>
										You
									</span>
								{/if}
							</div>
							<span
								class="flex items-center gap-1 text-[11px] mt-0.5 {connected || self
									? 'text-[var(--success)]'
									: 'text-[var(--text-muted)]'}"
							>
								{#if connected || self}
									<Wifi size={11} />
									Online
								{:else}
									<WifiOff size={11} />
									Offline
								{/if}
							</span>
						</div>

						<!-- Settings + Remove buttons (top-right) -->
						{#if !self}
							<button
								onclick={(e) => { e.preventDefault(); e.stopPropagation(); window.location.href = `/members/${encodeURIComponent(member.device_id)}?tab=settings`; }}
								class="p-1 rounded text-[var(--text-muted)] hover:text-[var(--accent)] hover:bg-[var(--accent)]/10 transition-colors shrink-0"
								title="Member settings"
								aria-label="Settings for {member.name}"
							>
								<Settings size={13} />
							</button>
						{/if}

						{#if !self}
							{#if confirmRemove === member.name}
								<div class="flex items-center gap-1 shrink-0">
									<button
										onclick={(e) => { e.preventDefault(); e.stopPropagation(); handleRemove(member.name); }}
										disabled={removing}
										class="px-2 py-1 text-xs font-medium rounded bg-[var(--error)] text-white hover:bg-[var(--error)]/80 transition-colors disabled:opacity-50"
									>
										{#if removing}
											<Loader2 size={12} class="animate-spin" />
										{:else}
											Remove
										{/if}
									</button>
									<button
										onclick={(e) => { e.preventDefault(); e.stopPropagation(); confirmRemove = null; }}
										class="px-2 py-1 text-xs rounded text-[var(--text-muted)] hover:bg-[var(--bg-muted)] transition-colors"
									>
										Cancel
									</button>
								</div>
							{:else}
								<button
									onclick={(e) => { e.preventDefault(); e.stopPropagation(); confirmRemove = member.name; }}
									class="p-1 rounded text-[var(--text-muted)] hover:text-[var(--error)] hover:bg-[var(--error)]/10 transition-colors shrink-0"
									title="Remove member"
									aria-label="Remove member {member.name}"
								>
									<Trash2 size={13} />
								</button>
							{/if}
						{/if}
					</div>

					<!-- Stats row: sessions + transfer + sparkline -->
					<div class="flex items-center justify-between gap-3 pt-2 border-t border-[var(--border)]/50">
						<div class="flex items-center gap-4 text-[11px] text-[var(--text-muted)]">
							{#if totals.sent > 0 || totals.received > 0}
								<span class="flex items-center gap-1" title="Sessions shared">
									<ArrowUpDown size={11} />
									{totals.sent + totals.received} sessions
								</span>
							{/if}
							{#if inBytes > 0 || outBytes > 0}
								<span title="Data received">&darr; {formatBytes(inBytes)}</span>
								<span title="Data sent">&uarr; {formatBytes(outBytes)}</span>
							{:else if totals.sent === 0 && totals.received === 0}
								<span>No activity yet</span>
							{/if}
						</div>

						{#if sparkline.some((v) => v > 0)}
							<MemberSparkline data={sparkline} color={hexColor} />
						{/if}
					</div>
				</a>
			{/each}
		</div>
	{/if}

	<!-- Diagnostic hints when waiting for members -->
	{#if members.length <= 1}
		<div class="p-4 rounded-lg border border-[var(--border)]/50 bg-[var(--bg-subtle)]">
			<p class="text-xs font-semibold text-[var(--text-secondary)] uppercase tracking-wider mb-2">
				Waiting for members?
			</p>
			<ul class="space-y-1.5 text-xs text-[var(--text-muted)]">
				<li class="flex items-start gap-2">
					<span class="shrink-0 mt-0.5 w-1 h-1 rounded-full bg-[var(--text-muted)]"></span>
					Share the join code with your teammate
				</li>
				<li class="flex items-start gap-2">
					<span class="shrink-0 mt-0.5 w-1 h-1 rounded-full bg-[var(--text-muted)]"></span>
					Both machines need
					<span class="font-medium text-[var(--text-secondary)]">Syncthing running</span>
					&mdash; check with
					<code
						class="px-1 py-0.5 rounded bg-[var(--bg-muted)] text-[10px] font-mono"
						>brew services info syncthing</code
					>
				</li>
				<li class="flex items-start gap-2">
					<span class="shrink-0 mt-0.5 w-1 h-1 rounded-full bg-[var(--text-muted)]"></span>
					Discovery via relay can take 15-60 seconds after joining
				</li>
			</ul>
			<div class="mt-3 flex items-center gap-2 text-xs">
				{#if detectData?.running}
					<span class="flex items-center gap-1 text-[var(--success)]">
						<span class="w-1.5 h-1.5 rounded-full bg-[var(--success)]"></span>
						Your Syncthing is running
					</span>
				{:else}
					<span class="flex items-center gap-1 text-[var(--error)]">
						<span class="w-1.5 h-1.5 rounded-full bg-[var(--error)]"></span>
						Your Syncthing is not running
					</span>
					<span class="text-[var(--text-muted)]">&mdash; start with</span>
					<code class="px-1 py-0.5 rounded bg-[var(--bg-muted)] text-[10px] font-mono"
						>brew services start syncthing</code
					>
				{/if}
			</div>
		</div>
	{/if}
</div>

<script lang="ts">
	import { API_BASE } from '$lib/config';
	import { Trash2, Loader2, UserPlus } from 'lucide-svelte';
	import type { SyncTeamMember } from '$lib/api-types';
	import { getTeamMemberColor, getTeamMemberHexColor } from '$lib/utils';

	interface Props {
		members: SyncTeamMember[];
		teamName: string;
		memberTag: string | undefined;
		isLeader?: boolean;
		onrefresh: () => void;
	}

	let { members, teamName, memberTag, isLeader = false, onrefresh }: Props = $props();

	let confirmRemove = $state<string | null>(null);
	let removing = $state(false);

	// Add member state
	let showAddForm = $state(false);
	let pairingCode = $state('');
	let adding = $state(false);
	let addError = $state<string | null>(null);

	async function handleAddMember() {
		if (!pairingCode.trim() || adding) return;
		adding = true;
		addError = null;

		try {
			const res = await fetch(
				`${API_BASE}/sync/teams/${encodeURIComponent(teamName)}/members`,
				{
					method: 'POST',
					headers: { 'Content-Type': 'application/json' },
					body: JSON.stringify({ pairing_code: pairingCode.trim() })
				}
			);

			if (res.ok) {
				pairingCode = '';
				showAddForm = false;
				onrefresh();
			} else {
				const data = await res.json().catch(() => ({}));
				addError = data.detail || `Failed to add member (${res.status})`;
			}
		} catch {
			addError = 'Network error';
		} finally {
			adding = false;
		}
	}

	function memberDisplayName(member: SyncTeamMember): string {
		return member.user_id || member.member_tag;
	}

	function isSelf(member: SyncTeamMember): boolean {
		return member.member_tag === memberTag;
	}

	function statusColor(status: string): string {
		switch (status) {
			case 'active':
				return 'bg-[var(--success)]/10 text-[var(--success)] border-[var(--success)]/20';
			case 'added':
				return 'bg-[var(--warning)]/10 text-[var(--warning)] border-[var(--warning)]/20';
			case 'removed':
				return 'bg-[var(--error)]/10 text-[var(--error)] border-[var(--error)]/20';
			default:
				return 'bg-[var(--bg-muted)] text-[var(--text-muted)] border-[var(--border)]';
		}
	}

	async function handleRemove(tag: string) {
		if (removing) return;
		removing = true;

		try {
			const res = await fetch(
				`${API_BASE}/sync/teams/${encodeURIComponent(teamName)}/members/${encodeURIComponent(tag)}`,
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
	<!-- Add Member Section (leader only) -->
	{#if isLeader && showAddForm}
		<div class="p-4 rounded-lg border border-[var(--accent)]/30 bg-[var(--accent)]/5 space-y-3">
			<div class="space-y-1.5">
				<label for="pairing-code" class="block text-xs font-medium text-[var(--text-secondary)]">
					Paste your teammate's pairing code
				</label>
				<textarea
					id="pairing-code"
					bind:value={pairingCode}
					placeholder="MFZWI3D-BONSGYC-YLTMRWG-..."
					rows={2}
					class="w-full px-3 py-2 text-sm font-mono rounded-[var(--radius-md)] border border-[var(--border)]
						bg-[var(--bg-base)] text-[var(--text-primary)] placeholder:text-[var(--text-muted)]
						focus:outline-none focus:ring-2 focus:ring-[var(--accent)]/40 focus:border-[var(--accent)]
						transition-colors resize-none"
				></textarea>
				<p class="text-[11px] text-[var(--text-muted)]">
					Your teammate can find their pairing code on the <a href="/sync" class="text-[var(--accent)] hover:underline">/sync</a> page.
				</p>
			</div>
			{#if addError}
				<p class="text-xs text-[var(--error)]">{addError}</p>
			{/if}
			<div class="flex items-center gap-2">
				<button
					onclick={handleAddMember}
					disabled={!pairingCode.trim() || adding}
					class="px-3 py-1.5 text-sm font-medium rounded-[var(--radius-md)] bg-[var(--accent)] text-white
						hover:bg-[var(--accent-hover)] transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
				>
					{#if adding}
						<span class="flex items-center gap-2">
							<Loader2 size={14} class="animate-spin" />
							Adding...
						</span>
					{:else}
						Add Member
					{/if}
				</button>
				<button
					onclick={() => { showAddForm = false; pairingCode = ''; addError = null; }}
					class="px-3 py-1.5 text-sm rounded-[var(--radius-md)] text-[var(--text-secondary)]
						hover:bg-[var(--bg-muted)] transition-colors"
				>
					Cancel
				</button>
			</div>
		</div>
	{:else if isLeader}
		<button
			onclick={() => (showAddForm = true)}
			class="flex items-center gap-1.5 px-3 py-1.5 text-sm font-medium rounded-[var(--radius-md)]
				border border-dashed border-[var(--border)] text-[var(--text-secondary)]
				hover:border-[var(--accent)] hover:text-[var(--accent)] hover:bg-[var(--accent)]/5 transition-colors"
		>
			<UserPlus size={14} />
			Add Member
		</button>
	{/if}

	{#if members.length === 0 && !showAddForm}
		<p class="text-sm text-[var(--text-muted)] py-8 text-center">
			No members yet. Click "Add Member" and paste a teammate's pairing code.
		</p>
	{:else if members.length > 0}
		<div class="grid grid-cols-1 md:grid-cols-2 gap-3">
			{#each members as member (member.member_tag)}
				{@const displayName = memberDisplayName(member)}
				{@const colors = getTeamMemberColor(displayName)}
				{@const hexColor = getTeamMemberHexColor(displayName)}
				{@const self = isSelf(member)}
				<div
					class="relative flex flex-col gap-3 p-4 rounded-lg border border-[var(--border)] bg-[var(--bg-base)]"
				>
					<!-- Top row: avatar + name + status -->
					<div class="flex items-center gap-3">
						<!-- Avatar -->
						<a href="/members/{member.member_tag}" class="shrink-0 group">
							<div
								class="w-10 h-10 rounded-full flex items-center justify-center text-sm font-bold group-hover:ring-2 group-hover:ring-[var(--accent)]/40 transition-all"
								style="background: {hexColor}; color: white; box-shadow: 0 0 0 2px {hexColor}33;"
							>
								{displayName.charAt(0).toUpperCase()}
							</div>
						</a>

						<div class="flex-1 min-w-0">
							<div class="flex items-center gap-2">
								<a
									href="/members/{member.member_tag}"
									class="text-sm font-semibold text-[var(--text-primary)] hover:underline hover:text-[var(--accent)] transition-colors truncate"
								>
									{member.user_id}
								</a>
								{#if self}
									<span
										class="shrink-0 px-1.5 py-0.5 text-[10px] font-medium rounded {colors.badge}"
									>
										You
									</span>
								{/if}
								<span
									class="shrink-0 px-1.5 py-0.5 text-[10px] font-medium rounded-full border {statusColor(member.status)}"
								>
									{member.status}
								</span>
							</div>
							<div class="flex items-center gap-2 mt-0.5">
								<span class="text-[11px] text-[var(--text-muted)] font-mono truncate">
									{member.machine_tag}
								</span>
							</div>
						</div>

						<!-- Remove button (leader only) -->
						{#if isLeader && !self}
							{#if confirmRemove === member.member_tag}
								<div class="flex items-center gap-1 shrink-0">
									<button
										onclick={() => handleRemove(member.member_tag)}
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
										onclick={() => (confirmRemove = null)}
										class="px-2 py-1 text-xs rounded text-[var(--text-muted)] hover:bg-[var(--bg-muted)] transition-colors"
									>
										Cancel
									</button>
								</div>
							{:else}
								<button
									onclick={() => (confirmRemove = member.member_tag)}
									class="p-1 rounded text-[var(--text-muted)] hover:text-[var(--error)] hover:bg-[var(--error)]/10 transition-colors shrink-0"
									title="Remove member"
									aria-label="Remove member {displayName}"
								>
									<Trash2 size={13} />
								</button>
							{/if}
						{/if}
					</div>

					<!-- Detail row -->
					<div class="flex items-center gap-3 pt-2 border-t border-[var(--border)]/50 text-[11px] text-[var(--text-muted)]">
						<span class="font-mono truncate" title="Member tag">{member.member_tag}</span>
						<span class="text-[var(--border)]">&middot;</span>
						<span class="font-mono truncate" title="Device ID">{member.device_id.slice(0, 7)}&hellip;</span>
					</div>
				</div>
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
					Ask your teammate to copy their pairing code from /sync
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
		</div>
	{/if}
</div>

<script lang="ts">
	/**
	 * Empty state for ticket surfaces — shown on `/tickets` (global) and on
	 * each project's Tickets tab when zero tickets are linked.
	 *
	 * Three "ways to start" cards, ordered by friction (least → most):
	 *   1. Dashboard paste — works out of the box, no install
	 *   2. Slash command   — needs the link-ticket-to-session skill installed
	 *   3. Branch hook     — opt-in, requires hook + config (Tier 4)
	 *
	 * Card #2 carries an inline "install once" block with the symlink and
	 * cp variants from SETUP.md → Tier 4. Lying about the install state
	 * ("installed by default") was a real bug that made first-time users
	 * type `/link-ticket-to-session` and get nothing — see the v0.2.0
	 * release notes for context.
	 */
	import { ExternalLink, GitBranch, Link as LinkIcon, Slash, Sparkles } from 'lucide-svelte';

	interface Props {
		/** Adjusts copy slightly. 'global' = /tickets index. 'project' = ProjectTicketsTab. */
		scope?: 'global' | 'project';
	}

	let { scope = 'global' }: Props = $props();

	const pasteSub =
		scope === 'project'
			? 'Open any session in this project and use the Tickets section.'
			: 'Open the session, scroll to the Tickets section, paste the URL.';

	const LINK_PATHS = [
		{
			n: '01',
			title: 'Paste a URL from any session page',
			cmd: 'https://linear.app/team/issue/ABC-123',
			sub: pasteSub,
			badge: 'works out of the box',
			Icon: LinkIcon,
			install: null as null | { heading: string; commands: readonly string[] }
		},
		{
			n: '02',
			title: 'In a session — type a slash command',
			cmd: '/link-ticket-to-session ABC-123',
			sub: 'Agent fetches title via your Linear / Atlassian / GitHub MCP if installed.',
			badge: 'one-time setup',
			Icon: Slash,
			install: {
				heading: 'Install once from the karma repo:',
				commands: [
					'ln -sf "$PWD/skills/link-ticket-to-session" ~/.claude/skills/',
					'# or: cp -R skills/link-ticket-to-session ~/.claude/skills/'
				]
			}
		},
		{
			n: '03',
			title: 'Push a branch that names the ticket',
			cmd: 'git checkout -b feat/ABC-123-…',
			sub: 'Configure patterns in ~/.claude_karma/config.json. See SETUP.md → Tier 4.',
			badge: 'opt-in hook',
			Icon: GitBranch,
			install: null as null | { heading: string; commands: readonly string[] }
		}
	] as const;

	const headline =
		scope === 'project'
			? 'Nothing linked here yet. Three ways to start.'
			: 'No tickets yet. Three ways to start linking.';

	const subhead =
		scope === 'project'
			? 'When a session in this project gets linked to a ticket, it shows up here.'
			: 'Karma links sessions to tickets in Linear, Jira, or GitHub Issues.';

	const headerSuffix = scope === 'project' ? '[0 linked in this project]' : '[0 linked]';
</script>

<div
	class="w-full p-6 rounded-lg border border-dashed border-[var(--border)] bg-[var(--bg-subtle)] flex flex-col gap-5"
>
	<div class="flex items-center gap-2.5">
		<span class="font-mono text-sm text-[var(--accent)]">$ tickets</span>
		<span class="font-mono text-sm text-[var(--text-faint)]">{headerSuffix}</span>
	</div>

	<div>
		<h3 class="text-lg font-semibold text-[var(--text-primary)] m-0 leading-tight">
			{headline}
		</h3>
		<p class="text-sm text-[var(--text-muted)] mt-1 mb-0 max-w-[60ch]">{subhead}</p>
	</div>

	<div
		class="flex flex-col rounded-md border border-[var(--border)] bg-[var(--bg-base)] overflow-hidden"
	>
		{#each LINK_PATHS as row, i (row.n)}
			<div
				class="flex flex-col"
				class:border-t={i > 0}
				class:border-[var(--border-subtle)]={i > 0}
			>
				<!-- Main row: number · title+sub · primary command -->
				<div
					class="grid items-center gap-4 px-4 py-3"
					style="grid-template-columns: 28px 1fr auto"
				>
					<span class="font-mono text-xs text-[var(--text-faint)]">{row.n}</span>
					<div>
						<div
							class="text-sm font-medium text-[var(--text-primary)] flex items-center gap-2 flex-wrap"
						>
							<row.Icon size={12} class="text-[var(--text-muted)]" />
							{row.title}
							<span
								class="font-mono text-[9.5px] uppercase tracking-wider px-1.5 py-[1px] rounded-sm bg-[var(--bg-muted)] text-[var(--text-muted)]"
							>
								{row.badge}
							</span>
						</div>
						<p class="text-xs text-[var(--text-muted)] mt-0.5 mb-0">{row.sub}</p>
					</div>
					<code
						class="font-mono text-[11.5px] px-2.5 py-1.5 rounded bg-[var(--bg-muted)] text-[var(--text-primary)] border border-[var(--border-subtle)] whitespace-nowrap"
					>
						{row.cmd}
					</code>
				</div>

				<!-- Optional install block: full-width under the main row -->
				{#if row.install}
					<div
						class="px-4 pb-3 pt-0 grid gap-2"
						style="grid-template-columns: 28px 1fr; padding-left: calc(1rem + 28px + 1rem);"
					>
						<div class="col-span-2 flex flex-col gap-1.5">
							<p class="text-[11px] text-[var(--text-muted)] m-0">{row.install.heading}</p>
							<div class="flex flex-col gap-1">
								{#each row.install.commands as command}
									<code
										class="font-mono text-[11px] px-2.5 py-1.5 rounded bg-[var(--bg-muted)] text-[var(--text-primary)] border border-[var(--border-subtle)] whitespace-pre-wrap break-all"
									>
										{command}
									</code>
								{/each}
							</div>
						</div>
					</div>
				{/if}
			</div>
		{/each}
	</div>

	<div class="flex items-center justify-between gap-2 text-[11px] text-[var(--text-faint)]">
		<span class="flex items-center gap-2">
			<Sparkles size={11} />
			Karma is read-only — the ticket lives in its source of truth.
		</span>
		<a
			href="https://github.com/JayantDevkar/claude-code-karma/blob/main/SETUP.md#tier-4-auto-link-tickets-optional"
			target="_blank"
			rel="noopener noreferrer"
			class="inline-flex items-center gap-1 text-[var(--text-muted)] hover:text-[var(--accent)]"
		>
			SETUP.md → Tier 4
			<ExternalLink size={10} />
		</a>
	</div>
</div>

<script lang="ts">
	import NavigationCard from '$lib/components/NavigationCard.svelte';
	import TerminalDisplay from '$lib/components/TerminalDisplay.svelte';
	import LiveSessionsTerminal from '$lib/components/LiveSessionsTerminal.svelte';
	import {
		FolderOpen,
		LineChart,
		Bot,
		Wrench,
		History,
		Settings,
		FileText,
		MessageSquare,
		Puzzle,
		Cable,
		Webhook,
		Terminal
	} from 'lucide-svelte';

	// Index entries — ordered like a table of contents
	const entries = [
		{ title: 'Projects', href: '/projects', icon: FolderOpen, color: 'blue' as const },
		{ title: 'Sessions', href: '/sessions', icon: MessageSquare, color: 'teal' as const },
		{ title: 'Analytics', href: '/analytics', icon: LineChart, color: 'green' as const },
		{ title: 'Plans', href: '/plans', icon: FileText, color: 'yellow' as const },
		{ title: 'Skills', href: '/skills', icon: Wrench, color: 'orange' as const },
		{ title: 'Agents', href: '/agents', icon: Bot, color: 'purple' as const },
		{ title: 'Tools', href: '/tools', icon: Cable, color: 'teal' as const },
		{ title: 'Hooks', href: '/hooks', icon: Webhook, color: 'amber' as const },
		{ title: 'Commands', href: '/commands', icon: Terminal, color: 'red' as const },
		{ title: 'Plugins', href: '/plugins', icon: Puzzle, color: 'violet' as const },
		{ title: 'Archived', href: '/archived', icon: History, color: 'gray' as const },
		{ title: 'Settings', href: '/settings', icon: Settings, color: 'indigo' as const }
	];
</script>

<div class="home">
	<!-- Live Wire -->
	<section class="home__section home__live">
		<div class="section-head">
			<span class="section-head__tag">§ 01</span>
			<h2 class="section-head__title">Live Wire</h2>
			<span class="section-head__rule rule"></span>
			<span class="section-head__meta eyebrow">real-time</span>
		</div>
		<LiveSessionsTerminal />
	</section>

	<!-- Index (navigation) -->
	<section class="home__section home__index">
		<div class="section-head">
			<span class="section-head__tag">§ 02</span>
			<h2 class="section-head__title">Index</h2>
			<span class="section-head__rule rule"></span>
			<span class="section-head__meta eyebrow">{entries.length} entries</span>
		</div>

		<div class="entries stagger-children">
			{#each entries as entry, i (entry.href)}
				<NavigationCard
					title={entry.title}
					href={entry.href}
					icon={entry.icon}
					color={entry.color}
					index={i}
				/>
			{/each}
		</div>
	</section>

	<!-- Dispatch (typewriter terminal) -->
	<section class="home__section home__dispatch">
		<div class="section-head">
			<span class="section-head__tag">§ 03</span>
			<h2 class="section-head__title">Dispatch</h2>
			<span class="section-head__rule rule"></span>
			<span class="section-head__meta eyebrow">today</span>
		</div>
		<div class="dispatch-body">
			<TerminalDisplay />
		</div>
	</section>

	<!-- Colophon -->
	<footer class="home__colophon">
		<div class="rule"></div>
		<div class="colophon-row">
			<span class="eyebrow">Colophon</span>
			<span class="colophon-text">
				Set in <em>Instrument Serif</em> and <em>Geist</em>. Data in <em>Geist Mono</em>.
				All sessions local to <code>~/.claude/</code>.
			</span>
		</div>
	</footer>
</div>

<style>
	.home {
		display: flex;
		flex-direction: column;
		gap: 64px;
		padding-top: 8px;
		padding-bottom: 24px;
	}

	/* ====== Section header — ruled masthead style ====== */
	.section-head {
		display: grid;
		grid-template-columns: auto auto 1fr auto;
		align-items: center;
		gap: 14px;
		margin-bottom: 24px;
	}

	.section-head__tag {
		font-family: var(--font-mono);
		font-size: 10px;
		letter-spacing: 0.18em;
		text-transform: uppercase;
		color: var(--accent);
		font-weight: 500;
	}

	.section-head__title {
		font-family: var(--font-serif);
		font-style: italic;
		font-size: 32px;
		font-weight: 400;
		line-height: 1;
		letter-spacing: -0.02em;
		color: var(--text-primary);
		margin: 0;
	}

	.section-head__rule {
		align-self: center;
		height: 1px;
	}

	/* ====== Index grid ====== */
	.entries {
		display: grid;
		grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
		gap: 8px;
	}

	@media (min-width: 640px) {
		.entries {
			grid-template-columns: repeat(2, 1fr);
		}
	}

	@media (min-width: 860px) {
		.entries {
			grid-template-columns: repeat(3, 1fr);
		}
	}

	@media (min-width: 1100px) {
		.entries {
			grid-template-columns: repeat(4, 1fr);
		}
	}

	/* ====== Dispatch ====== */
	.dispatch-body {
		padding: 28px 16px;
		border: 1px solid var(--border);
		border-radius: var(--radius-md);
		background: var(--bg-subtle);
	}

	/* ====== Colophon ====== */
	.home__colophon {
		margin-top: 24px;
	}

	.colophon-row {
		display: flex;
		align-items: baseline;
		gap: 16px;
		padding-top: 16px;
	}

	.colophon-text {
		font-size: 13px;
		color: var(--text-muted);
		line-height: 1.6;
	}

	.colophon-text em {
		font-family: var(--font-serif);
		font-style: italic;
		font-size: 1.08em;
		color: var(--text-secondary);
	}

	.colophon-text code {
		font-family: var(--font-mono);
		font-size: 0.92em;
		padding: 1px 6px;
		background: var(--bg-subtle);
		border: 1px solid var(--border-subtle);
		border-radius: 3px;
		color: var(--text-secondary);
	}
</style>

<script lang="ts">
	import HomeSessionsStrip from '$lib/components/home/HomeSessionsStrip.svelte';
	import MonitorCard from '$lib/components/home/MonitorCard.svelte';
	import CompactNavItem from '$lib/components/home/CompactNavItem.svelte';
	import HomeIcon from '$lib/components/home/HomeIcon.svelte';
	import { Settings, Info } from 'lucide-svelte';

	let { data } = $props();

	function fmtDuration(secs: number): string {
		const h = Math.floor(secs / 3600);
		const m = Math.floor((secs % 3600) / 60);
		if (h > 0) return `${h}h ${m}m`;
		return `${m}m`;
	}

	const PERIOD_LABEL: Record<string, string> = {
		today: 'today',
		yesterday: 'yesterday',
		this_week: 'this week',
		none: ''
	};

	const automate = [
		{
			title: 'Agents',
			href: '/agents',
			icon: 'agents',
			color: 'var(--nav-purple)',
			tint: 'var(--nav-purple-subtle)'
		},
		{
			title: 'Skills',
			href: '/skills',
			icon: 'skills',
			color: 'var(--nav-orange)',
			tint: 'var(--nav-orange-subtle)'
		},
		{
			title: 'MCP',
			href: '/mcp',
			icon: 'tools',
			color: 'var(--nav-indigo)',
			tint: 'var(--nav-indigo-subtle)'
		},
		{
			title: 'Commands',
			href: '/commands',
			icon: 'commands',
			color: 'var(--nav-red)',
			tint: 'var(--nav-red-subtle)'
		},
		{
			title: 'Hooks',
			href: '/hooks',
			icon: 'hooks',
			color: 'var(--nav-cyan)',
			tint: 'var(--nav-cyan-subtle)'
		},
		{
			title: 'Cron',
			href: '/cron',
			icon: 'cron',
			color: 'var(--nav-yellow)',
			tint: 'var(--nav-yellow-subtle)'
		}
	];

	const manage = [
		{
			title: 'Plans',
			href: '/plans',
			icon: 'plans',
			color: 'var(--nav-amber)',
			tint: 'var(--nav-amber-subtle)'
		},
		{
			title: 'Tickets',
			href: '/tickets',
			icon: 'tickets',
			color: 'var(--nav-amber)',
			tint: 'var(--nav-amber-subtle)'
		},
		{
			title: 'Plugins',
			href: '/plugins',
			icon: 'plugins',
			color: 'var(--nav-violet)',
			tint: 'var(--nav-violet-subtle)'
		},
		{
			title: 'Shells',
			href: '/shells',
			icon: 'shells',
			color: 'var(--nav-green)',
			tint: 'var(--nav-green-subtle)'
		},
		{
			title: 'Memory',
			href: '/memory',
			icon: 'memory',
			color: 'var(--nav-blue)',
			tint: 'var(--nav-blue-subtle)'
		}
	];
</script>

<div class="page">
	<div class="card">
		<!-- Header -->
		<div class="header">
			<div class="logo-mark">
				<img src="/logo.png" alt="Claude Code Karma" />
			</div>
			<div class="app-name">Claude Code Karma</div>
			<div class="tagline">Track work, not terminals</div>
		</div>

		<!-- Monitor (elevated) -->
		<section class="group">
			<div class="group-header">
				<span class="group-label">Monitor</span>
				<span class="group-rule"></span>
			</div>
			<div class="monitor-grid">
				<MonitorCard
					title="Projects"
					description="Browse active codebases"
					href="/projects"
					icon="projects"
					color="var(--nav-blue)"
					tint="var(--nav-blue-subtle)"
				/>
				<MonitorCard
					title="Sessions"
					description="All Claude Code runs"
					href="/sessions"
					icon="sessions"
					color="var(--nav-teal)"
					tint="var(--nav-teal-subtle)"
				/>
				<MonitorCard
					title="Analytics"
					description="Usage trends & stats"
					href="/analytics"
					icon="analytics"
					color="var(--nav-green)"
					tint="var(--nav-green-subtle)"
				/>
			</div>
		</section>

		<!-- Automate -->
		<section class="group">
			<div class="group-header">
				<span class="group-label">Automate</span>
				<span class="group-rule"></span>
			</div>
			<div class="compact-grid">
				{#each automate as item (item.href)}
					<CompactNavItem {...item} />
				{/each}
			</div>
		</section>

		<!-- Manage -->
		<section class="group">
			<div class="group-header">
				<span class="group-label">Manage</span>
				<span class="group-rule"></span>
			</div>
			<div class="compact-grid">
				{#each manage as item (item.href)}
					<CompactNavItem {...item} />
				{/each}
			</div>
		</section>

		<!-- Live Sessions Strip -->
		<div class="strip-wrap">
			<HomeSessionsStrip />
		</div>

		<!-- System (demoted to text links) -->
		<section class="group last">
			<div class="group-header">
				<span class="group-label">System</span>
				<span class="group-rule"></span>
			</div>
			<div class="system-row">
				<div class="system-links">
					<a class="system-link" href="/settings">
						<span style="color: var(--nav-indigo)"><Settings size={16} strokeWidth={1.75} /></span>
						Settings
					</a>
					<a class="system-link" href="/about">
						<span style="color: var(--nav-gray)"><Info size={16} strokeWidth={1.75} /></span>
						About
					</a>
				</div>
				{#if data.stats && data.stats.period !== 'none' && data.stats.duration_seconds > 0}
					<a href="/analytics" class="stats-line">
						<span class="stats-prompt">&gt;</span>
						<span>You spent <strong>{fmtDuration(data.stats.duration_seconds)}</strong> with agents {PERIOD_LABEL[data.stats.period]}</span>
					</a>
				{/if}
			</div>
		</section>
	</div>
</div>

<style>
	.page {
		width: 100%;
		max-width: 700px;
		margin: 0 auto;
		padding: 0 16px;
	}

	.card {
		padding: 8px 0 0;
	}

	/* Header */
	.header {
		text-align: center;
		margin-bottom: 32px;
	}

	.logo-mark {
		width: 64px;
		height: 64px;
		border-radius: 50%;
		background: radial-gradient(circle, #2d2240 55%, transparent 100%);
		display: flex;
		align-items: center;
		justify-content: center;
		margin: 0 auto 12px;
	}

	.logo-mark img {
		width: 48px;
		height: 48px;
		object-fit: contain;
	}

	.app-name {
		font-size: 19px;
		font-weight: 700;
		color: var(--text-primary);
		margin-bottom: 4px;
	}

	.tagline {
		font-size: 12.5px;
		font-weight: 500;
		background: linear-gradient(135deg, #a855f7, #7c3aed);
		-webkit-background-clip: text;
		background-clip: text;
		-webkit-text-fill-color: transparent;
	}

	.strip-wrap {
		margin-bottom: 24px;
	}

	/* Groups */
	.group {
		margin-bottom: 20px;
	}

	.group.last {
		margin-bottom: 0;
	}

	.group-header {
		display: flex;
		align-items: center;
		gap: 8px;
		margin-bottom: 10px;
	}

	.group-label {
		font-size: 10px;
		font-weight: 700;
		letter-spacing: 0.12em;
		text-transform: uppercase;
		color: var(--text-faint);
		white-space: nowrap;
	}

	.group-rule {
		flex: 1;
		height: 1px;
		background: var(--border);
	}

	.monitor-grid {
		display: grid;
		grid-template-columns: 1fr 1fr 1fr;
		gap: 10px;
	}

	.compact-grid {
		display: grid;
		grid-template-columns: repeat(3, 1fr);
		gap: 8px;
	}

	/* System row */
	.system-row {
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: 16px;
	}

	/* System links */
	.system-links {
		display: flex;
		gap: 20px;
		align-items: center;
	}

	.system-link {
		display: flex;
		align-items: center;
		gap: 6px;
		color: var(--text-muted);
		font-size: 12.5px;
		font-weight: 500;
		text-decoration: none;
		transition: color 100ms;
	}

	.system-link:hover {
		color: var(--text-primary);
	}

	/* Stats line */
	.stats-line {
		display: flex;
		align-items: center;
		gap: 6px;
		text-decoration: none;
		font-family: var(--font-mono, 'JetBrains Mono', monospace);
		font-size: 11.5px;
		color: var(--text-muted);
		white-space: nowrap;
		transition: color 100ms;
	}

	.stats-line:hover {
		color: var(--text-primary);
	}

	.stats-line strong {
		font-weight: 600;
		color: var(--text-secondary);
	}

	.stats-prompt {
		color: var(--accent);
		font-weight: 700;
	}

	.terminal-wrap {
		margin-top: 16px;
	}

	/* Mobile */
	@media (max-width: 640px) {
		.monitor-grid {
			grid-template-columns: 1fr;
		}

		.compact-grid {
			grid-template-columns: 1fr 1fr;
		}

		.system-row {
			flex-direction: column;
			align-items: flex-start;
			gap: 12px;
		}

		.system-links {
			flex-direction: column;
			align-items: flex-start;
			gap: 10px;
		}

		.stats-line {
			font-size: 11px;
		}
	}
</style>

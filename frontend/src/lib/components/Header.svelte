<script lang="ts">
	import { page } from '$app/stores';
	import { Menu, X, Settings } from 'lucide-svelte';

	let mobileMenuOpen = $state(false);

	let isHome = $derived($page.url.pathname === '/');

	// Dispatch number — deterministic per-day issue number, editorial flourish
	const issueNo = $derived.by(() => {
		const start = new Date('2024-01-01').getTime();
		const today = new Date();
		today.setHours(0, 0, 0, 0);
		const days = Math.floor((today.getTime() - start) / (1000 * 60 * 60 * 24));
		return String(days % 999).padStart(3, '0');
	});

	const todayLabel = $derived.by(() => {
		return new Date()
			.toLocaleDateString('en-US', { year: 'numeric', month: 'short', day: '2-digit' })
			.toUpperCase();
	});

	function toggleMobileMenu() {
		mobileMenuOpen = !mobileMenuOpen;
	}
	function closeMobileMenu() {
		mobileMenuOpen = false;
	}
	function handleKeydown(e: KeyboardEvent) {
		if (e.key === 'Escape' && mobileMenuOpen) closeMobileMenu();
	}

	const navItems = [
		{ href: '/projects', label: 'Projects' },
		{ href: '/sessions', label: 'Sessions' },
		{ href: '/plans', label: 'Plans' },
		{ href: '/agents', label: 'Agents' },
		{ href: '/skills', label: 'Skills' },
		{ href: '/commands', label: 'Commands' },
		{ href: '/tools', label: 'Tools' },
		{ href: '/hooks', label: 'Hooks' },
		{ href: '/plugins', label: 'Plugins' },
		{ href: '/analytics', label: 'Analytics' },
		{ href: '/archived', label: 'Archived' }
	];
</script>

<svelte:window onkeydown={handleKeydown} />

{#if isHome}
	<!-- Editorial masthead (home) -->
	<header class="masthead">
		<div class="masthead__rule rule"></div>
		<div class="masthead__meta">
			<span class="eyebrow">№ {issueNo}</span>
			<span class="eyebrow">Claude Code · Dispatch</span>
			<span class="eyebrow">{todayLabel}</span>
		</div>
		<div class="masthead__rule-strong rule-strong"></div>

		<div class="masthead__title">
			<span class="masthead__kicker">track work · not terminals</span>
			<h1 class="masthead__display">
				<span class="masthead__word">karma</span><span class="masthead__amp">.</span>
			</h1>
			<p class="masthead__sub">
				A quiet, meticulous log of your <em>Claude Code</em> sessions — projects, plans,
				tools, agents, and skills, all indexed.
			</p>
		</div>

		<div class="masthead__rule rule"></div>
	</header>
{:else}
	<!-- Compact route header -->
	<header class="route-header">
		<div class="route-header__bar">
			<a href="/" class="route-header__brand" aria-label="Home">
				<span class="route-header__dot"></span>
				<span class="route-header__name">
					<span class="route-header__name-display">karma</span>
					<span class="route-header__name-sub">Claude Code</span>
				</span>
			</a>

			<nav class="route-header__nav" aria-label="Main navigation">
				{#each navItems as item (item.href)}
					<a
						href={item.href}
						class="route-header__link"
						class:is-active={$page.url.pathname.startsWith(item.href)}
						aria-current={$page.url.pathname.startsWith(item.href) ? 'page' : undefined}
					>
						{item.label}
					</a>
				{/each}
			</nav>

			<div class="route-header__right">
				<a href="/settings" class="route-header__icon" title="Settings">
					<Settings size={16} strokeWidth={1.75} />
				</a>
				<button
					onclick={toggleMobileMenu}
					class="route-header__icon route-header__mobile"
					aria-label="Toggle menu"
				>
					{#if mobileMenuOpen}
						<X size={18} strokeWidth={1.75} />
					{:else}
						<Menu size={18} strokeWidth={1.75} />
					{/if}
				</button>
			</div>
		</div>
	</header>

	{#if mobileMenuOpen}
		<div
			class="mobile-menu"
			onclick={closeMobileMenu}
			role="presentation"
		>
			<nav aria-label="Mobile navigation">
				{#each navItems as item (item.href)}
					<a
						href={item.href}
						onclick={closeMobileMenu}
						class="mobile-menu__link"
						class:is-active={$page.url.pathname.startsWith(item.href)}
						aria-current={$page.url.pathname.startsWith(item.href) ? 'page' : undefined}
					>
						{item.label}
					</a>
				{/each}
			</nav>
		</div>
	{/if}
{/if}

<style>
	/* ====== Editorial masthead (home) ====== */
	.masthead {
		width: 100%;
		max-width: 1100px;
		margin: 0 auto;
		padding: 32px 24px 8px;
	}

	.masthead__meta {
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: 16px;
		padding: 10px 0 12px;
	}

	.masthead__rule {
		width: 100%;
	}

	.masthead__rule-strong {
		width: 100%;
		margin-bottom: 18px;
	}

	.masthead__title {
		padding: 20px 0 36px;
		display: grid;
		grid-template-columns: auto 1fr;
		grid-template-rows: auto auto;
		column-gap: 28px;
		row-gap: 14px;
		align-items: end;
	}

	.masthead__kicker {
		grid-column: 1 / -1;
		font-family: var(--font-mono);
		font-size: 11px;
		letter-spacing: 0.22em;
		text-transform: uppercase;
		color: var(--accent);
		font-weight: 500;
	}

	.masthead__display {
		font-family: var(--font-serif);
		font-style: italic;
		font-weight: 400;
		font-size: clamp(84px, 15vw, 180px);
		line-height: 0.9;
		letter-spacing: -0.04em;
		color: var(--text-primary);
		margin: 0;
		grid-column: 1;
	}

	.masthead__word {
		display: inline-block;
	}

	.masthead__amp {
		color: var(--accent);
	}

	.masthead__sub {
		grid-column: 2;
		font-size: 15px;
		line-height: 1.55;
		color: var(--text-secondary);
		max-width: 360px;
		padding-bottom: 16px;
		border-left: 1px solid var(--border);
		padding-left: 20px;
	}

	.masthead__sub em {
		font-family: var(--font-serif);
		font-style: italic;
		font-size: 1.08em;
		color: var(--text-primary);
	}

	@media (max-width: 720px) {
		.masthead {
			padding: 20px 16px 4px;
		}
		.masthead__title {
			grid-template-columns: 1fr;
			padding: 12px 0 24px;
			row-gap: 10px;
		}
		.masthead__sub {
			grid-column: 1;
			border-left: none;
			border-top: 1px solid var(--border);
			padding-left: 0;
			padding-top: 14px;
		}
		.masthead__meta .eyebrow:nth-child(2) {
			display: none;
		}
	}

	/* ====== Compact route header ====== */
	.route-header {
		position: sticky;
		top: 0;
		z-index: 50;
		background: color-mix(in srgb, var(--bg-base) 88%, transparent);
		backdrop-filter: blur(14px) saturate(1.2);
		-webkit-backdrop-filter: blur(14px) saturate(1.2);
		border-bottom: 1px solid var(--border);
	}

	.route-header__bar {
		width: 100%;
		max-width: 1200px;
		margin: 0 auto;
		padding: 0 20px;
		height: 56px;
		display: grid;
		grid-template-columns: auto 1fr auto;
		align-items: center;
		gap: 16px;
	}

	.route-header__brand {
		display: inline-flex;
		align-items: center;
		gap: 10px;
		text-decoration: none;
		color: var(--text-primary);
		transition: opacity var(--duration-fast);
	}

	.route-header__brand:hover {
		opacity: 0.75;
	}

	.route-header__dot {
		width: 8px;
		height: 8px;
		border-radius: 50%;
		background: var(--accent);
		box-shadow: 0 0 0 3px var(--accent-muted);
		flex-shrink: 0;
	}

	.route-header__name {
		display: inline-flex;
		align-items: baseline;
		gap: 8px;
	}

	.route-header__name-display {
		font-family: var(--font-serif);
		font-style: italic;
		font-size: 22px;
		line-height: 1;
		letter-spacing: -0.02em;
		color: var(--text-primary);
	}

	.route-header__name-sub {
		display: none;
		font-family: var(--font-mono);
		font-size: 10px;
		letter-spacing: 0.2em;
		text-transform: uppercase;
		color: var(--text-muted);
	}

	@media (min-width: 640px) {
		.route-header__name-sub {
			display: inline;
		}
	}

	.route-header__nav {
		display: none;
		justify-self: center;
		align-items: center;
		gap: 4px;
	}

	@media (min-width: 900px) {
		.route-header__nav {
			display: flex;
		}
	}

	.route-header__link {
		position: relative;
		padding: 6px 10px;
		font-family: var(--font-mono);
		font-size: 11px;
		letter-spacing: 0.12em;
		text-transform: uppercase;
		color: var(--text-muted);
		text-decoration: none;
		transition: color var(--duration-fast);
		white-space: nowrap;
	}

	.route-header__link::after {
		content: '';
		position: absolute;
		left: 10px;
		right: 10px;
		bottom: -1px;
		height: 1px;
		background: var(--accent);
		transform: scaleX(0);
		transform-origin: left center;
		transition: transform var(--duration-base) var(--ease);
	}

	.route-header__link:hover {
		color: var(--text-primary);
	}

	.route-header__link.is-active {
		color: var(--text-primary);
	}

	.route-header__link.is-active::after {
		transform: scaleX(1);
	}

	.route-header__right {
		display: flex;
		align-items: center;
		justify-self: end;
		gap: 6px;
	}

	.route-header__icon {
		display: inline-flex;
		align-items: center;
		justify-content: center;
		width: 32px;
		height: 32px;
		border-radius: var(--radius-sm);
		color: var(--text-muted);
		background: transparent;
		border: 1px solid transparent;
		cursor: pointer;
		transition: all var(--duration-fast);
		text-decoration: none;
	}

	.route-header__icon:hover {
		color: var(--text-primary);
		background: var(--bg-subtle);
		border-color: var(--border);
	}

	.route-header__mobile {
		display: inline-flex;
	}

	@media (min-width: 900px) {
		.route-header__mobile {
			display: none;
		}
	}

	/* ====== Mobile menu ====== */
	.mobile-menu {
		position: fixed;
		inset: 56px 0 0 0;
		z-index: 40;
		background: color-mix(in srgb, var(--bg-base) 96%, transparent);
		backdrop-filter: blur(18px);
		-webkit-backdrop-filter: blur(18px);
	}

	@media (min-width: 900px) {
		.mobile-menu {
			display: none;
		}
	}

	.mobile-menu nav {
		display: flex;
		flex-direction: column;
		padding: 20px;
		gap: 2px;
		max-width: 1200px;
		margin: 0 auto;
	}

	.mobile-menu__link {
		display: flex;
		align-items: center;
		justify-content: space-between;
		padding: 14px 16px;
		font-family: var(--font-mono);
		font-size: 12px;
		letter-spacing: 0.14em;
		text-transform: uppercase;
		color: var(--text-secondary);
		text-decoration: none;
		border-bottom: 1px solid var(--border-subtle);
		transition: all var(--duration-fast);
	}

	.mobile-menu__link:hover,
	.mobile-menu__link.is-active {
		color: var(--text-primary);
	}

	.mobile-menu__link.is-active {
		background: var(--accent-muted);
		border-color: var(--accent);
	}
</style>

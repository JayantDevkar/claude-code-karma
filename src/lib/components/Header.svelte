<script lang="ts">
	import { page } from '$app/stores';
	import { Orbit, Menu, X, Settings } from 'lucide-svelte';

	let mobileMenuOpen = $state(false);

	let isHome = $derived($page.url.pathname === '/');

	function toggleMobileMenu() {
		mobileMenuOpen = !mobileMenuOpen;
	}

	function closeMobileMenu() {
		mobileMenuOpen = false;
	}

	function handleKeydown(e: KeyboardEvent) {
		if (e.key === 'Escape' && mobileMenuOpen) {
			closeMobileMenu();
		}
	}
</script>

<svelte:window onkeydown={handleKeydown} />

{#if isHome}
	<!-- Big Centered Header (Home) -->
	<header
		class="w-full max-w-[1000px] mx-auto pt-8 sm:pt-12 md:pt-16 pb-6 md:pb-8 px-4 flex items-center justify-center relative"
	>
		<div class="flex flex-col items-center gap-4 md:gap-5">
			<div
				class="p-2.5 md:p-3 rounded-2xl bg-[var(--bg-base)] border border-[var(--border)] shadow-[var(--shadow-sm)]"
			>
				<Orbit size={28} class="text-[var(--accent)] md:w-8 md:h-8" strokeWidth={1.5} />
			</div>
			<div class="text-center flex flex-col items-center gap-1">
				<h1
					class="text-2xl sm:text-3xl font-semibold tracking-tight text-[var(--text-primary)]"
				>
					Claude Karma
				</h1>
				<p class="text-sm text-[var(--text-muted)]">Track work not terminals</p>
			</div>
		</div>
	</header>
{:else}
	<!-- Compact Inline Header (Routes) -->
	<header
		class="sticky top-0 z-50 bg-[var(--bg-base)]/90 backdrop-blur-md border-b border-[var(--border)] h-14 flex items-center"
	>
		<div
			class="w-full max-w-[1200px] mx-auto px-4 md:px-6 grid grid-cols-[auto_1fr_auto] items-center"
		>
			<!-- Left: Brand -->
			<div class="flex items-center gap-3">
				<a
					href="/"
					class="flex items-center gap-2 md:gap-3 hover:opacity-80 transition-opacity group"
				>
					<div
						class="p-1 rounded bg-[var(--bg-muted)] border border-[var(--border)] text-[var(--accent)] group-hover:text-[var(--accent-hover)] transition-colors"
					>
						<Orbit size={16} strokeWidth={2} />
					</div>
					<h1
						class="hidden sm:block text-sm font-semibold tracking-tight text-[var(--text-primary)]"
					>
						Claude Karma
					</h1>
				</a>
			</div>

			<!-- Center: Desktop Navigation -->
			<nav
				class="hidden md:flex items-center justify-center gap-4 overflow-visible"
				aria-label="Main navigation"
			>
				<a
					href="/projects"
					class="text-sm font-medium text-[var(--text-muted)] hover:text-[var(--text-primary)] transition-colors"
					class:text-[var(--text-primary)]={$page.url.pathname.startsWith('/projects')}
					aria-current={$page.url.pathname.startsWith('/projects') ? 'page' : undefined}
				>
					Projects
				</a>
				<a
					href="/sessions"
					class="text-sm font-medium text-[var(--text-muted)] hover:text-[var(--text-primary)] transition-colors"
					class:text-[var(--text-primary)]={$page.url.pathname.startsWith('/sessions')}
					aria-current={$page.url.pathname.startsWith('/sessions') ? 'page' : undefined}
				>
					Sessions
				</a>
				<a
					href="/plans"
					class="text-sm font-medium text-[var(--text-muted)] hover:text-[var(--text-primary)] transition-colors"
					class:text-[var(--text-primary)]={$page.url.pathname.startsWith('/plans')}
					aria-current={$page.url.pathname.startsWith('/plans') ? 'page' : undefined}
				>
					Plans
				</a>
				<a
					href="/agents"
					class="text-sm font-medium text-[var(--text-muted)] hover:text-[var(--text-primary)] transition-colors"
					class:text-[var(--text-primary)]={$page.url.pathname.startsWith('/agents')}
					aria-current={$page.url.pathname.startsWith('/agents') ? 'page' : undefined}
				>
					Agents
				</a>
				<a
					href="/skills"
					class="text-sm font-medium text-[var(--text-muted)] hover:text-[var(--text-primary)] transition-colors"
					class:text-[var(--text-primary)]={$page.url.pathname.startsWith('/skills')}
					aria-current={$page.url.pathname.startsWith('/skills') ? 'page' : undefined}
				>
					Skills
				</a>
				<a
					href="/tools"
					class="text-sm font-medium text-[var(--text-muted)] hover:text-[var(--text-primary)] transition-colors"
					class:text-[var(--text-primary)]={$page.url.pathname.startsWith('/tools')}
					aria-current={$page.url.pathname.startsWith('/tools') ? 'page' : undefined}
				>
					Tools
				</a>
				<a
					href="/hooks"
					class="text-sm font-medium text-[var(--text-muted)] hover:text-[var(--text-primary)] transition-colors"
					class:text-[var(--text-primary)]={$page.url.pathname.startsWith('/hooks')}
					aria-current={$page.url.pathname.startsWith('/hooks') ? 'page' : undefined}
				>
					Hooks
				</a>
				<a
					href="/plugins"
					class="text-sm font-medium text-[var(--text-muted)] hover:text-[var(--text-primary)] transition-colors"
					class:text-[var(--text-primary)]={$page.url.pathname.startsWith('/plugins')}
					aria-current={$page.url.pathname.startsWith('/plugins') ? 'page' : undefined}
				>
					Plugins
				</a>
				<a
					href="/analytics"
					class="text-sm font-medium text-[var(--text-muted)] hover:text-[var(--text-primary)] transition-colors"
					class:text-[var(--text-primary)]={$page.url.pathname.startsWith('/analytics')}
					aria-current={$page.url.pathname.startsWith('/analytics') ? 'page' : undefined}
				>
					Analytics
				</a>
				<a
					href="/archived"
					class="text-sm font-medium text-[var(--text-muted)] hover:text-[var(--text-primary)] transition-colors"
					class:text-[var(--text-primary)]={$page.url.pathname.startsWith('/archived')}
					aria-current={$page.url.pathname.startsWith('/archived') ? 'page' : undefined}
				>
					Archived
				</a>
			</nav>

			<div class="flex items-center justify-end gap-3">
				<a
					href="/settings"
					class="p-2 rounded-lg hover:bg-[var(--bg-muted)] transition-colors text-[var(--text-muted)] hover:text-[var(--text-primary)]"
					title="Settings"
				>
					<Settings size={18} strokeWidth={2} />
				</a>

				<!-- Mobile Menu Button - visible only on mobile -->
				<button
					onclick={toggleMobileMenu}
					class="md:hidden p-2 rounded-lg hover:bg-[var(--bg-muted)] transition-colors text-[var(--text-muted)]"
					aria-label="Toggle menu"
				>
					{#if mobileMenuOpen}
						<X size={20} strokeWidth={2} />
					{:else}
						<Menu size={20} strokeWidth={2} />
					{/if}
				</button>
			</div>
		</div>
	</header>

	<!-- Mobile Menu Overlay -->
	{#if mobileMenuOpen}
		<div
			class="fixed inset-0 top-14 z-40 bg-[var(--bg-base)]/95 backdrop-blur-md md:hidden"
			onclick={closeMobileMenu}
			role="presentation"
		>
			<nav class="flex flex-col p-6 gap-1" aria-label="Mobile navigation">
				<a
					href="/projects"
					onclick={closeMobileMenu}
					class="text-base font-medium text-[var(--text-muted)] hover:text-[var(--text-primary)] hover:bg-[var(--bg-subtle)] py-3 px-4 rounded-lg transition-colors"
					class:text-[var(--text-primary)]={$page.url.pathname.startsWith('/projects')}
					class:bg-[var(--bg-subtle)]={$page.url.pathname.startsWith('/projects')}
					aria-current={$page.url.pathname.startsWith('/projects') ? 'page' : undefined}
				>
					Projects
				</a>
				<a
					href="/sessions"
					onclick={closeMobileMenu}
					class="text-base font-medium text-[var(--text-muted)] hover:text-[var(--text-primary)] hover:bg-[var(--bg-subtle)] py-3 px-4 rounded-lg transition-colors"
					class:text-[var(--text-primary)]={$page.url.pathname.startsWith('/sessions')}
					class:bg-[var(--bg-subtle)]={$page.url.pathname.startsWith('/sessions')}
					aria-current={$page.url.pathname.startsWith('/sessions') ? 'page' : undefined}
				>
					Sessions
				</a>
				<a
					href="/plans"
					onclick={closeMobileMenu}
					class="text-base font-medium text-[var(--text-muted)] hover:text-[var(--text-primary)] hover:bg-[var(--bg-subtle)] py-3 px-4 rounded-lg transition-colors"
					class:text-[var(--text-primary)]={$page.url.pathname.startsWith('/plans')}
					class:bg-[var(--bg-subtle)]={$page.url.pathname.startsWith('/plans')}
					aria-current={$page.url.pathname.startsWith('/plans') ? 'page' : undefined}
				>
					Plans
				</a>
				<a
					href="/agents"
					onclick={closeMobileMenu}
					class="text-base font-medium text-[var(--text-muted)] hover:text-[var(--text-primary)] hover:bg-[var(--bg-subtle)] py-3 px-4 rounded-lg transition-colors"
					class:text-[var(--text-primary)]={$page.url.pathname.startsWith('/agents')}
					class:bg-[var(--bg-subtle)]={$page.url.pathname.startsWith('/agents')}
					aria-current={$page.url.pathname.startsWith('/agents') ? 'page' : undefined}
				>
					Agents
				</a>
				<a
					href="/skills"
					onclick={closeMobileMenu}
					class="text-base font-medium text-[var(--text-muted)] hover:text-[var(--text-primary)] hover:bg-[var(--bg-subtle)] py-3 px-4 rounded-lg transition-colors"
					class:text-[var(--text-primary)]={$page.url.pathname.startsWith('/skills')}
					class:bg-[var(--bg-subtle)]={$page.url.pathname.startsWith('/skills')}
					aria-current={$page.url.pathname.startsWith('/skills') ? 'page' : undefined}
				>
					Skills
				</a>
				<a
					href="/tools"
					onclick={closeMobileMenu}
					class="text-base font-medium text-[var(--text-muted)] hover:text-[var(--text-primary)] hover:bg-[var(--bg-subtle)] py-3 px-4 rounded-lg transition-colors"
					class:text-[var(--text-primary)]={$page.url.pathname.startsWith('/tools')}
					class:bg-[var(--bg-subtle)]={$page.url.pathname.startsWith('/tools')}
					aria-current={$page.url.pathname.startsWith('/tools') ? 'page' : undefined}
				>
					Tools
				</a>
				<a
					href="/hooks"
					onclick={closeMobileMenu}
					class="text-base font-medium text-[var(--text-muted)] hover:text-[var(--text-primary)] hover:bg-[var(--bg-subtle)] py-3 px-4 rounded-lg transition-colors"
					class:text-[var(--text-primary)]={$page.url.pathname.startsWith('/hooks')}
					class:bg-[var(--bg-subtle)]={$page.url.pathname.startsWith('/hooks')}
					aria-current={$page.url.pathname.startsWith('/hooks') ? 'page' : undefined}
				>
					Hooks
				</a>
				<a
					href="/plugins"
					onclick={closeMobileMenu}
					class="text-base font-medium text-[var(--text-muted)] hover:text-[var(--text-primary)] hover:bg-[var(--bg-subtle)] py-3 px-4 rounded-lg transition-colors"
					class:text-[var(--text-primary)]={$page.url.pathname.startsWith('/plugins')}
					class:bg-[var(--bg-subtle)]={$page.url.pathname.startsWith('/plugins')}
					aria-current={$page.url.pathname.startsWith('/plugins') ? 'page' : undefined}
				>
					Plugins
				</a>
				<a
					href="/analytics"
					onclick={closeMobileMenu}
					class="text-base font-medium text-[var(--text-muted)] hover:text-[var(--text-primary)] hover:bg-[var(--bg-subtle)] py-3 px-4 rounded-lg transition-colors"
					class:text-[var(--text-primary)]={$page.url.pathname.startsWith('/analytics')}
					class:bg-[var(--bg-subtle)]={$page.url.pathname.startsWith('/analytics')}
					aria-current={$page.url.pathname.startsWith('/analytics') ? 'page' : undefined}
				>
					Analytics
				</a>
				<a
					href="/archived"
					onclick={closeMobileMenu}
					class="text-base font-medium text-[var(--text-muted)] hover:text-[var(--text-primary)] hover:bg-[var(--bg-subtle)] py-3 px-4 rounded-lg transition-colors"
					class:text-[var(--text-primary)]={$page.url.pathname.startsWith('/archived')}
					class:bg-[var(--bg-subtle)]={$page.url.pathname.startsWith('/archived')}
					aria-current={$page.url.pathname.startsWith('/archived') ? 'page' : undefined}
				>
					Archived
				</a>
			</nav>
		</div>
	{/if}
{/if}
